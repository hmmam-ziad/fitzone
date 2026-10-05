from odoo import fields, models


class ClassBooking(models.Model):
    _name = 'fitzone.class.booking'
    _description = 'Class Booking'
    _rec_name = 'member_id'

    member_id = fields.Many2one('res.partner', required=True)
    membership_id = fields.Many2one('fitzone.membership', required=True)
    class_id = fields.Many2one('fitzone.gym.class', required=True)
    booking_date = fields.Datetime()
    status = fields.Char()