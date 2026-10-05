from odoo import fields, models


class Attendance(models.Model):
    _name = 'fitzone.attendance'
    _description = 'Attendance'

    booking_id = fields.Many2one('fitzone.class.booking', required=True)
    attended = fields.Boolean()