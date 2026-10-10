from odoo import fields, models


class PoolBooking(models.Model):
    _name = 'fitzone.pool.booking'
    _description = 'Pool Booking'

    member_id = fields.Many2one('res.partner', required=True, domain="[('membership_ids', '!=', False)]")
    membership_id = fields.Many2one('fitzone.membership', required=True)
    pool_slot_id = fields.Many2one('fitzone.pool.slot', required=True)
    trainer_id = fields.Many2one('fitzone.trainer')
    booking_date = fields.Datetime()
    status = fields.Char()