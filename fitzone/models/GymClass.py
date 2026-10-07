from odoo import api, fields, models


class GymClass(models.Model):
    _name = 'fitzone.gym.class'
    _description = 'Group Class'

    trainer_id = fields.Many2one(
        'fitzone.trainer',
        required=True,
    )

    room_id = fields.Many2one(
        'fitzone.room',
        required=True,
    )

    name = fields.Char(
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
        compute='_compute_seats',
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