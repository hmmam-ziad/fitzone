from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


class PTSession(models.Model):
    _name = 'fitzone.pt.session'
    _description = 'Personal Training Session'
    _rec_name = 'member_id'

    member_id = fields.Many2one('res.partner', required=True, domain="[('membership_ids', '!=', False)]")
    trainee_id = fields.Many2one(
        'res.partner', related='member_id', readonly=False, string='Trainee',
    )
    trainer_id = fields.Many2one('fitzone.trainer', required=True)
    membership_id = fields.Many2one('fitzone.membership', required=True, domain="[('member_id', '=', member_id)]")
    package_id = fields.Many2one('product.template', required=True)
    session_date = fields.Datetime()
    end_datetime = fields.Datetime()
    # Keep the legacy status field for existing views and availability searches.
    status = fields.Char(default='draft')
    state = fields.Selection(
        [('draft', 'Draft'), ('completed', 'Completed'), ('cancelled', 'Cancelled')],
        default='draft', required=True, copy=False,
    )
    session_type = fields.Char(default='personal_training', required=True)
    session_price = fields.Float(groups='fitzone.group_fitzone_manager,fitzone.group_fitzone_reception', required=True, default=0.0)
    applied_commission_rate = fields.Float(groups='fitzone.group_fitzone_manager,fitzone.group_fitzone_reception', readonly=True, copy=False)
    calculated_commission = fields.Float(groups='fitzone.group_fitzone_manager,fitzone.group_fitzone_reception', readonly=True, copy=False)

    can_report_incident = fields.Boolean(compute='_compute_can_report_incident', compute_sudo=False)

    @api.depends_context('uid')
    @api.depends('trainer_id')
    def _compute_can_report_incident(self):
        for session in self:
            session.can_report_incident = (
                self.env.user.has_group('fitzone.group_fitzone_trainer')
                and session.trainer_id.employee_id.user_id.id == self.env.uid)

    def action_report_incident(self):
        self.ensure_one()
        self.check_access('read')
        if not self.can_report_incident:
            raise AccessError('Incidents can only be reported from your own PT sessions.')
        # Use the member ID only; the injury create method enforces D4 independently.
        report = self.env['fitzone.injury'].create({
            'member_id': self.member_id.id,
            'reported_by': self.trainer_id.employee_id.id,
        })
        return {'type': 'ir.actions.act_window', 'res_model': 'fitzone.injury',
                'view_mode': 'form', 'res_id': report.id}

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for values in vals_list:
            values = dict(values)
            if {'applied_commission_rate', 'calculated_commission'} & values.keys():
                raise ValidationError("Commission snapshots are set by session completion.")
            state = values.get('state', values.get('status', 'draft'))
            if state == 'completed':
                raise ValidationError("Create the session as a draft before completing it.")
            if state in ('draft', 'cancelled'):
                values.update(state=state, status=state)
            prepared.append(values)
        return super().create(prepared)

    def write(self, vals):
        self.check_access('write')
        vals = dict(vals)
        if (not self.env.su and self.env.user.has_group('fitzone.group_fitzone_trainer')
                and not any(self.env.user.has_group('fitzone.group_fitzone_' + role) for role in ('manager', 'reception'))
                and {'trainer_id', 'member_id', 'trainee_id', 'membership_id', 'package_id'} & vals.keys()):
            raise AccessError('Session assignments cannot be changed by a trainer.')
        if {'applied_commission_rate', 'calculated_commission'} & vals.keys():
            raise ValidationError("Commission snapshots are set by session completion.")
        locked = {
            'member_id', 'trainee_id', 'trainer_id', 'session_date',
            'session_type', 'session_price', 'state', 'status',
        }
        if locked & vals.keys() and any(s.state == 'completed' for s in self):
            raise ValidationError("Completed sessions and their commission inputs are locked.")
        state = vals.get('state', vals.get('status'))
        if state == 'completed':
            vals.pop('state', None)
            vals.pop('status', None)
            if vals:
                super().write(vals)
            return self.action_complete_session()
        if state in ('draft', 'cancelled'):
            vals.update(state=state, status=state)
        return super().write(vals)

    @api.constrains('session_price')
    def _check_session_price(self):
        for session in self:
            if session.session_price < 0:
                raise ValidationError("Session price cannot be negative.")

    def action_complete_session(self):
        self.check_access('write')
        for session in self:
            if session.state == 'completed':
                continue
            if session.state == 'cancelled' or session.status == 'cancelled':
                raise ValidationError("Cancelled sessions cannot be completed.")
            membership = session.membership_id

            if membership.member_id != session.member_id:
                raise ValidationError(
                    "The selected membership does not belong to this member."
                )

            if membership.package_id.id != session.package_id.id:
                raise ValidationError(
                    "The session package must match the selected membership."
                )

            if (
                session.package_id.package_type == 'private'
                and session.package_id.total_sessions > 0
                and membership.remaining_sessions <= 0
            ):
                raise ValidationError(
                    "This membership has no remaining PT sessions."
                )
            if not session.session_date:
                raise ValidationError("Set the session date before completing the session.")
            session_day = fields.Date.to_date(session.session_date)
            rate = session._completion_rate_snapshot(session_day)
            session._persist_validated_completion(rate)
        return True

    def _completion_rate_snapshot(self, session_day):
        """Private lookup returns only a rate for an accessible session."""
        self.ensure_one()
        self.check_access('write')
        # Session completers cannot read commission configuration.
        rules = self.env['fitzone.commission.rule']
        if self.env.user.has_group('fitzone.group_fitzone_trainer'):
            rules = rules.sudo()
        rule = rules.search([
            ('active', '=', True), ('trainer_id', '=', self.trainer_id.id),
            ('session_type', '=', self.session_type), ('effective_from', '<=', session_day),
            '|', ('effective_to', '=', False), ('effective_to', '>=', session_day),
        ], order='effective_from desc, id desc', limit=1)
        return rule.rate if rule else 50.0

    def _persist_validated_completion(self, rate):
        """Persist the financial snapshot and consume the validated entitlement only."""
        self.ensure_one()
        self.check_access('write')
        # Trainers complete sessions without financial reads or membership write ACLs.
        session = self.sudo()
        self.env.cr.execute('SELECT id FROM fitzone_pt_session WHERE id = %s FOR UPDATE', (self.id,))
        session.invalidate_recordset(['state'])
        if session.state == 'completed':
            return True
        membership = session.membership_id
        self.env.cr.execute('SELECT id FROM fitzone_membership WHERE id = %s FOR UPDATE', (membership.id,))
        membership.invalidate_recordset(['consumed_sessions', 'remaining_sessions'])
        private = session.package_id.package_type == 'private' and session.package_id.total_sessions > 0
        if private and membership.remaining_sessions <= 0:
            raise ValidationError('This membership has no remaining PT sessions.')
        super(PTSession, session).write({
            'applied_commission_rate': rate,
            'calculated_commission': session.session_price * rate / 100,
            'state': 'completed', 'status': 'completed',
        })
        if private:
            membership.consumed_sessions += 1
        return True

    @api.constrains('trainer_id', 'session_date', 'end_datetime', 'status')
    def _check_trainer_availability(self):
        for record in self:
            if (
                not record.trainer_id
                or not record.session_date
                or not record.end_datetime
            ):
                continue

            if record.status == 'cancelled':
                continue

            if not record.trainer_id.employee_id.is_available_during(
                record.session_date,
                record.end_datetime,
                exclude_pt_id=record.id,
            ):
                raise ValidationError(
                    "The trainer is not available during the selected time."
                )
