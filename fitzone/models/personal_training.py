from odoo import api, fields, models
from odoo.exceptions import ValidationError


class PTSession(models.Model):
    _name = 'fitzone.pt.session'
    _description = 'Personal Training Session'
    _rec_name = 'member_id'

    member_id = fields.Many2one('res.partner', required=True)
    trainee_id = fields.Many2one(
        'res.partner', related='member_id', readonly=False, string='Trainee',
    )
    trainer_id = fields.Many2one('fitzone.trainer', required=True)
    membership_id = fields.Many2one('fitzone.membership', required=True)
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
    session_price = fields.Float(required=True, default=0.0)
    applied_commission_rate = fields.Float(readonly=True, copy=False)
    calculated_commission = fields.Float(readonly=True, copy=False)

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
        vals = dict(vals)
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
            rule = self.env['fitzone.commission.rule'].search([
                ('active', '=', True),
                ('trainer_id', '=', session.trainer_id.id),
                ('session_type', '=', session.session_type),
                ('effective_from', '<=', session_day),
                '|', ('effective_to', '=', False),
                ('effective_to', '>=', session_day),
            ], order='effective_from desc, id desc', limit=1)
            rate = rule.rate if rule else 50.0
            # Bypass only our public write guard; persist an ordinary snapshot.
            super(PTSession, session).write({
                'applied_commission_rate': rate,
                'calculated_commission': session.session_price * (rate / 100.0),
                'state': 'completed',
                'status': 'completed',
            })

            if (
                session.package_id.package_type == 'private'
                and session.package_id.total_sessions > 0
            ):
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
