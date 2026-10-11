from odoo import api, fields, models
from odoo.exceptions import ValidationError


class GymClass(models.Model):
    _name = 'fitzone.gym.class'
    _description = 'Group Class'

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
        compute='_compute_seats', store=True
    )

    @api.constrains('start_datetime', 'end_datetime')
    def _check_class_datetimes(self):
        for rec in self:
            if (
                rec.start_datetime
                and rec.end_datetime
                and rec.end_datetime <= rec.start_datetime
            ):
                raise ValidationError(
                    "End Datetime cannot be earlier than Start Datetime."
                )

    @api.depends(
        'room_id.capacity',
        'booking_ids.status',
    )
    def _compute_seats(self):
        for rec in self:
            booked = len(
                rec.booking_ids.filtered(
                    lambda booking: booking.status in ('booked', 'attended')
                )
            )

            capacity = rec.capacity or 0

            rec.booked_count = booked
            rec.available_seats = max(capacity - booked, 0)

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
                raise ValidationError(
                    "The trainer is not available during the selected working hours."
                )

    @api.constrains('trainer_id', 'start_datetime', 'end_datetime')
    def _fz_check_trainer_schedule(self):
        for rec in self:
            if rec.trainer_id and rec.start_datetime and rec.end_datetime:
                rec.trainer_id._check_available(
                    rec.start_datetime, rec.end_datetime,
                    exclude=(rec._name, rec.id))    
