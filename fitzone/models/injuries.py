from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class FitzoneInjuryCause(models.Model):
    _name = 'fitzone.injury.cause'
    _description = 'Injury Cause Master'

    name = fields.Char(string='Cause Name', required=True)


class Injury(models.Model):
    _name = 'fitzone.injury'
    _inherit = 'fitzone.medical.audit.mixin'
    _rec_name = 'id'
    _description = 'Injury'

    member_id = fields.Many2one(
        'res.partner',
        required=True,
    )

    reported_by = fields.Many2one(
        'hr.employee',
        required=True,
    )

    physiotherapist_id = fields.Many2one(
        'hr.employee', groups='fitzone.group_fitzone_physiotherapist,fitzone.group_fitzone_manager',
    )

    member_name = fields.Char(compute='_compute_report_identity', compute_sudo=False)
    membership_number = fields.Char(compute='_compute_report_identity', compute_sudo=False)

    injury_date = fields.Date()

    cause = fields.Char()

    description = fields.Text()

    type_ids = fields.One2many(
        'fitzone.injury.type',
        'injury_id',
        string='Types', groups='fitzone.group_fitzone_physiotherapist,fitzone.group_fitzone_manager',
    )

    injury_cause_id = fields.Many2one(
        'fitzone.injury.cause', string='Cause of Injury', groups='fitzone.group_fitzone_physiotherapist,fitzone.group_fitzone_manager',
    )
    state = fields.Selection(
        [('draft', 'Draft'), ('submitted', 'Submitted to Clinic'),
         ('processed', 'In Rehab')],
        default='draft', required=True, copy=False,
    )

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and not self.env.user.has_group('fitzone.group_fitzone_manager') and any(vals.get('state', 'draft') not in ('draft', 'submitted') for vals in vals_list):
            raise AccessError(_('New incident reports cannot be processed at creation.'))
        if not self.env.su and not self.env.user.has_group('fitzone.group_fitzone_manager'):
            for vals in vals_list:
                member_id = vals.get('member_id')
                own_pt = self.env['fitzone.pt.session'].search_count([('member_id', '=', member_id), ('trainer_id.employee_id.user_id', '=', self.env.uid)])
                own_class = self._own_class_attendee(member_id)
                if not self.env.user.has_group('fitzone.group_fitzone_trainer') or not (own_pt or own_class):
                    raise AccessError(_('Incidents require an own trainee or an attendee of your class.'))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su and not self.env.user.has_group('fitzone.group_fitzone_manager'):
            physio = self.env.user.has_group('fitzone.group_fitzone_physiotherapist')
            trainer = self.env.user.has_group('fitzone.group_fitzone_trainer')
            if 'member_id' in vals:
                raise AccessError(_('The incident member cannot be reassigned.'))
            incident_fields = {'member_id', 'reported_by', 'injury_date', 'cause', 'description'}
            if incident_fields.intersection(vals):
                if not trainer or any(rec.create_uid != self.env.user for rec in self):
                    raise AccessError(_('Incident-submitted fields are read-only in the clinic inbox.'))
            if 'state' in vals:
                if vals['state'] == 'processed':
                    if not physio:
                        raise AccessError(_('Only a physiotherapist can process an incident.'))
                elif not trainer or any(rec.create_uid != self.env.user for rec in self):
                    raise AccessError(_('Only the reporting trainer can submit an incident.'))
        return super().write(vals)

    def action_submit(self):
        self.write({'state': 'submitted'})
        return True

    def action_create_rehab_file(self):
        self.ensure_one()
        if not self.physiotherapist_id:
            raise UserError(_('Assign a physiotherapist before creating a rehab file.'))
        rehabilitation = self.env['fitzone.rehabilitation'].create({
            'member_id': self.member_id.id,
            'injury_id': self.id,
            'physiotherapist_id': self.physiotherapist_id.id,
            'sport_type': self.env.context.get('default_sport_type') or _('To be specified'),
        })
        self.write({'state': 'processed'})
        return {
            'type': 'ir.actions.act_window',
            'name': _('Rehabilitation'),
            'res_model': 'fitzone.rehabilitation',
            'view_mode': 'form',
            'res_id': rehabilitation.id,
            'target': 'current',
        }

    @api.model
    def get_pending_injury_count(self):
        # Only clinic users get a count; everyone else gets 0
        if not self.env.user.has_group('fitzone.group_fitzone_physiotherapist'):
            return 0
        return self.search_count([('state', '=', 'submitted')])


    @api.model
    def _own_class_attendee(self, member_id):
        """Return only whether this member attends a class assigned to the caller."""
        if not self.env.user.has_group('fitzone.group_fitzone_trainer'):
            return False
        # Incident validation needs no member or entitlement values from class bookings.
        return bool(self.env['fitzone.class.booking'].sudo().search_count([
            ('member_id', '=', member_id), ('class_id.trainer_id.employee_id.user_id', '=', self.env.uid),
            ('status', 'in', ['booked', 'attended'])]))


    def _report_identity(self):
        self.ensure_one()
        self.check_access('read')
        # Own incident readers get D3 identity only, including an own-class non-trainee.
        member = self.sudo().member_id
        return member.name, member.membership_no

    def _compute_report_identity(self):
        for report in self:
            report.member_name, report.membership_number = report._report_identity()


    @api.model
    def _has_field_access(self, field, operation):
        # Incident creation accepts a validated target; Trainer reads use only minimal identity.
        if (field.name == 'member_id' and operation == 'read' and not self.env.su
                and self.env.user.has_group('fitzone.group_fitzone_trainer')
                and not any(self.env.user.has_group('fitzone.group_fitzone_' + role)
                            for role in ('manager', 'reception', 'physiotherapist', 'nutritionist'))):
            return False
        return super()._has_field_access(field, operation)
