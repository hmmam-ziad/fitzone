from odoo import fields, models


class PoolBooking(models.Model):
    _name = 'fitzone.pool.booking'
    _description = 'Pool Booking'

    member_id = fields.Many2one('res.partner', required=True, groups='fitzone.group_fitzone_manager,fitzone.group_fitzone_reception', domain="[('membership_ids', '!=', False)]")
    membership_id = fields.Many2one('fitzone.membership', required=True, groups='fitzone.group_fitzone_manager,fitzone.group_fitzone_reception')
    pool_slot_id = fields.Many2one('fitzone.pool.slot', required=True)
    trainer_id = fields.Many2one('fitzone.trainer')
    booking_date = fields.Datetime()
    status = fields.Char()
    member_name = fields.Char(compute='_compute_booking_identity', compute_sudo=False)
    membership_number = fields.Char(compute='_compute_booking_identity', compute_sudo=False)

    def _booking_identity(self):
        self.ensure_one()
        self.check_access('read')
        # Assigned pool-booking readers need only minimal identity, never unrestricted partner data.
        member = self.sudo().member_id
        return member.name, member.membership_no

    def _compute_booking_identity(self):
        for booking in self:
            booking.member_name, booking.membership_number = booking._booking_identity()
