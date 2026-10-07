from odoo import fields, models, _
from odoo.exceptions import ValidationError


class Attendance(models.Model):
    _name = 'fitzone.attendance'
    _description = 'Attendance'

    booking_id = fields.Many2one(
        'fitzone.class.booking',
        required=True,
    )

    attended = fields.Boolean(
        default=False,
    )

    _unique_booking = models.Constraint(
        'UNIQUE(booking_id)',
        _('A booking can have only one attendance record.'),
    )