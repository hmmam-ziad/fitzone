from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


class Attendance(models.Model):
    _name = 'fitzone.attendance'
    _description = 'Attendance'
    _rec_name = 'id'

    booking_id = fields.Many2one('fitzone.class.booking', required=True,
        groups='fitzone.group_fitzone_manager,fitzone.group_fitzone_reception')
    class_id = fields.Many2one('fitzone.gym.class', compute='_compute_identity', compute_sudo=False)
    member_name = fields.Char(compute='_compute_identity', compute_sudo=False)
    membership_number = fields.Char(compute='_compute_identity', compute_sudo=False)
    attended = fields.Boolean(default=False)
    safe_restrictions = fields.Text(
        string='Forbidden movements / restrictions', compute='_compute_safe_restrictions',
        compute_sudo=False, readonly=True)

    def _own_class_safe_restrictions(self):
        """Return only authored safe text for a noncancelled attendee of this trainer."""
        self.ensure_one()
        if (not self.env.user.has_group('fitzone.group_fitzone_trainer')
                or not self.has_access('read')):
            return False
        # Bypass protected routing fields only after attendance access; never read partner/clinic data.
        booking = self.sudo().booking_id
        if (booking.status == 'cancelled'
                or booking.class_id.trainer_id.employee_id.user_id.id != self.env.uid):
            return False
        restrictions = self.env['fitzone.injury.type'].sudo().search([
            ('member_id', '=', booking.member_id.id)], order='id')
        return '\n'.join(text for restriction in restrictions
                         for text in (restriction.prohibited_exercises, restriction.restriction)
                         if text and text.strip()) or False

    @api.depends_context('uid')
    @api.depends('booking_id.status', 'booking_id.class_id.trainer_id.employee_id.user_id',
                 'booking_id.member_id.trainer_restriction_ids',
                 'booking_id.member_id.trainer_restriction_ids.restriction',
                 'booking_id.member_id.trainer_restriction_ids.prohibited_exercises')
    def _compute_safe_restrictions(self):
        for record in self:
            record.safe_restrictions = record._own_class_safe_restrictions()


    _unique_booking = models.Constraint('UNIQUE(booking_id)', 'A booking can have only one attendance record.')

    def _identity(self):
        self.ensure_one()
        self.check_access('read')
        # Attendance reveals only the two D3 identity strings from its protected booking.
        booking = self.sudo().booking_id
        member = booking.member_id
        return member.name, member.membership_no, booking.class_id.id

    def _compute_identity(self):
        for record in self:
            record.member_name, record.membership_number, record.class_id = record._identity()

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for vals in vals_list:
            vals = dict(vals)
            booking = self.env['fitzone.class.booking'].browse(vals.get('booking_id'))
            booking.check_access('read')
            vals.pop('class_id', None)
            prepared.append(vals)
        return super().create(prepared)

    def write(self, vals):
        self.check_access('write')
        if {'booking_id', 'class_id'} & vals.keys():
            raise AccessError('Attendance assignment cannot be changed.')
        if not self.env.su and self.env.user.has_group('fitzone.group_fitzone_trainer'):
            if set(vals) - {'attended'}:
                raise AccessError('Only attendance may be edited.')
            if 'attended' in vals:
                for record in self:
                    record._mark_booking_attended(vals['attended'])
        return super().write(vals)

    def _mark_booking_attended(self, attended):
        self.ensure_one()
        self.check_access('write')
        # Validate existing booking entitlement without granting membership/freeze writes or reads.
        booking = self.sudo().booking_id
        self.env.cr.execute('SELECT id FROM fitzone_class_booking WHERE id = %s FOR UPDATE', (booking.id,))
        booking.invalidate_recordset(['status', 'membership_id'])
        if not attended:
            if booking.status == 'attended':
                raise ValidationError(_('An attended booking cannot be reopened.'))
            return True
        if booking.status == 'attended':
            return True
        if booking.status != 'booked':
            raise ValidationError(_('Only a booked attendee can check in.'))
        membership = booking.membership_id
        if membership.state != 'active':
            raise ValidationError(_('Check-in denied.'))
        today = fields.Date.context_today(self)
        if self.env['fitzone.freeze'].sudo().search_count([
                ('membership_id', '=', membership.id), ('start_date', '<=', today),
                ('end_date', '>=', today)]):
            raise ValidationError(_('Check-in denied.'))
        booking.write({'status': 'attended'})
        return True

    @api.model
    def _ensure_booking_attendance(self, booking):
        """Create a minimal attendance row for a readable booking; return its ID only."""
        booking.check_access('read')
        self.env.cr.execute('SELECT id FROM fitzone_class_booking WHERE id = %s FOR UPDATE', (booking.id,))
        # Reception can book classes without attendance create permission.
        attendance = self.sudo().search([('booking_id', '=', booking.id)], limit=1)
        if not attendance:
            attendance = self.sudo().create({'booking_id': booking.id,
                'attended': booking.status == 'attended'})
        elif booking.status == 'attended' and not attendance.attended and booking.has_access('write'):
            attendance.write({'attended': True})
        return attendance.id

    @api.model
    def _trainer_check_in(self, class_id, barcode):
        """Match only a barcode booked into the caller's own class; return a minimal row."""
        gym_class = self.env['fitzone.gym.class'].browse(class_id)
        gym_class.check_access('read')
        if not self.env.user.has_group('fitzone.group_fitzone_trainer') or gym_class.trainer_id.employee_id.user_id != self.env.user:
            raise AccessError('Check-in is limited to your own classes.')
        # Barcode matching stays inside the validated class and returns no entitlement/member data.
        booking = self.env['fitzone.class.booking'].sudo().search([
            ('class_id', '=', class_id), ('membership_id.barcode', '=', barcode),
            ('status', '=', 'booked')], limit=1)
        if not booking:
            raise ValidationError(_('Not pre-registered for this class.'))
        booking = booking.with_env(self.env)
        attendance = self.browse(self._ensure_booking_attendance(booking))
        attendance.write({'attended': True})
        return attendance


    def _incident_member_id(self):
        self.ensure_one()
        self.check_access('read')
        # Only routing metadata is needed to create an incident from minimal attendance.
        return self.sudo().booking_id.member_id.id

    def action_report_incident(self):
        self.ensure_one()
        trainer = self.env['fitzone.trainer'].search([('employee_id.user_id', '=', self.env.uid)], limit=1)
        report = self.env['fitzone.injury'].create({'member_id': self._incident_member_id(),
                                                  'reported_by': trainer.employee_id.id})
        return {'type': 'ir.actions.act_window', 'res_model': 'fitzone.injury',
                'view_mode': 'form', 'res_id': report.id}
