from odoo import api, fields, models

class PoolBooking(models.Model):
    _name = 'fitzone.pool.booking'
    _description = 'Pool Booking'

    member_id = fields.Many2one('res.partner', required=True, domain="[('membership_ids', '!=', False)]")
    membership_id = fields.Many2one('fitzone.membership', required=True)
    pool_slot_id = fields.Many2one('fitzone.pool.slot', required=True)
    trainer_id = fields.Many2one('fitzone.trainer')
    booking_date = fields.Datetime()
    status = fields.Char()
    @api.constrains('trainer_id', 'pool_slot_id', 'booking_date', 'status')
    def _fz_check_trainer_schedule(self):
        """Pool sessions with a trainer: booking_date = session start,
        its length = the length of the pool slot."""
        for rec in self:
            if not rec.trainer_id or not rec.booking_date:
                continue
            if rec.status == 'cancelled':
                continue
            slot = rec.pool_slot_id
            hours = (slot.end_time - slot.start_time) if slot else 1.0
            rec.trainer_id._check_available(
                rec.booking_date, rec.booking_date + timedelta(hours=hours),
                exclude=(rec._name, rec.id))