from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError

from .smart_button_helpers import (
    OPERATIONS, FINANCE_READERS, check_navigation, check_trainer_owner,
    grouped_counts, has_roles, related_action,
)


class GymClass(models.Model):
    _name = 'fitzone.gym.class'
    _description = 'Group Class'

    booking_count = fields.Integer(
        compute='_compute_booking_count', compute_sudo=False,
        groups='fitzone.group_fitzone_manager,fitzone.group_fitzone_reception,fitzone.group_fitzone_trainer',
    )
    can_view_bookings = fields.Boolean(compute='_compute_can_view_bookings', compute_sudo=False)

    @api.depends('booking_ids', 'trainer_id')
    @api.depends_context('uid', 'allowed_company_ids')
    def _compute_booking_count(self):
        counts = grouped_counts(self, 'fitzone.class.booking', 'class_id', OPERATIONS)
        for gym_class in self:
            gym_class.booking_count = counts.get(gym_class.id, 0)

    @api.depends('trainer_id', 'trainer_id.employee_id.user_id')
    @api.depends_context('uid')
    def _compute_can_view_bookings(self):
        for gym_class in self:
            gym_class.can_view_bookings = has_roles(self.env, FINANCE_READERS) or (
                has_roles(self.env, ('trainer',))
                and gym_class.trainer_id.employee_id.user_id == self.env.user
            )

    def action_view_bookings(self):
        check_navigation(self, OPERATIONS, 'fitzone.class.booking')
        check_trainer_owner(self, self.trainer_id)
        return related_action(self, 'fitzone.action_fitzone_class_booking',
                              [('class_id', '=', self.id)], {'default_class_id': self.id})

    name = fields.Char(
        required=True,
    )

    trainer_id = fields.Many2one(
        'fitzone.trainer',
        required=True,
    )

    room_id = fields.Many2one(
        'fitzone.room',
        required=True,
    )

    start_datetime = fields.Datetime(
        required=True,
    )

    end_datetime = fields.Datetime(
        required=True,
    )

    # All bookings belonging to this class
    booking_ids = fields.One2many(
        'fitzone.class.booking',
        'class_id',
        string='Bookings',
    )

    # Capacity comes from the room
    capacity = fields.Integer(
        related='room_id.capacity',
        readonly=True,
    )

    booked_count = fields.Integer(
        compute='_compute_seats',
    )

    available_seats = fields.Integer(
        compute='_compute_seats',
    )

    alert_level = fields.Selection(
        [
            ('ok', 'Available'),
            ('near_full', 'Almost Full'),
            ('full', 'Full'),
        ],
        compute='_compute_alert_level', store=True
    )

    _name_uniq = models.Constraint(
        'UNIQUE(name)',
        'A class with this name already exists.',
    )

    @api.constrains('start_datetime', 'end_datetime')
    def _check_class_datetimes(self):
        for rec in self:
            if (
                rec.start_datetime
                and rec.end_datetime
                and rec.end_datetime <= rec.start_datetime
            ):
                raise ValidationError(_("End Datetime cannot be earlier than Start Datetime."))

    def _get_booked_count(self):
        """Return only the occupied-seat count for an accessible timetable class."""
        self.ensure_one()
        self.check_access('read')
        # Timetable readers need counts without access to booking/member records.
        return self.env['fitzone.class.booking'].sudo().search_count([
            ('class_id', '=', self.id),
            ('status', 'in', ('booked', 'attended')),
        ])

    @api.depends(
        'room_id.capacity',
        'booking_ids.status',
    )
    def _compute_seats(self):
        for rec in self:
            booked = rec._get_booked_count()

            capacity = rec.capacity or 0

            rec.booked_count = booked
            rec.available_seats = max(capacity - booked, 0)

    @api.depends('room_id.capacity', 'booking_ids.status')
    def _compute_alert_level(self):
        for rec in self:
            booked = rec._get_booked_count()
            capacity = rec.capacity or 0
            if capacity and booked >= capacity:
                rec.alert_level = 'full'
            elif capacity and booked >= 0.8 * capacity:
                rec.alert_level = 'near_full'
            else:
                rec.alert_level = 'ok'

    @api.constrains('trainer_id', 'start_datetime', 'end_datetime')
    def _check_trainer_working_hours(self):
        for record in self:
            if not record.trainer_id or not record.start_datetime or not record.end_datetime:
                continue

            if not record.trainer_id.is_available_during(
                record.start_datetime,
                record.end_datetime,
            ):
                raise ValidationError(_("The trainer is not available during the selected working hours."))

    @api.constrains('trainer_id', 'start_datetime', 'end_datetime')
    def _fz_check_trainer_schedule(self):
        for rec in self:
            if rec.trainer_id and rec.start_datetime and rec.end_datetime:
                rec.trainer_id._check_available(
                    rec.start_datetime, rec.end_datetime,
                    exclude=(rec._name, rec.id))

    def action_attendance(self):
        """Open the minimal roster, initializing missing attendance rows on demand."""
        self.ensure_one()
        self.check_access('read')
        if (not self.env.su and self.env.user.has_group('fitzone.group_fitzone_trainer')
                and not any(self.env.user.has_group('fitzone.group_fitzone_' + role) for role in ('manager', 'reception'))
                and self.trainer_id.employee_id.user_id != self.env.user):
            raise AccessError('Attendance is limited to your own classes.')
        ids = []
        for booking in self.env['fitzone.class.booking'].search([('class_id', '=', self.id)]):
            ids.append(self.env['fitzone.attendance']._ensure_booking_attendance(booking))
        return {'type': 'ir.actions.act_window', 'name': 'Class attendance',
                'res_model': 'fitzone.attendance', 'view_mode': 'list,form',
                'domain': [('id', 'in', ids)]}
