from odoo import api, fields, models
from odoo.exceptions import ValidationError


class PoolSlot(models.Model):
    _name = 'fitzone.pool.slot'
    _description = 'Pool Slot'
    _order = 'day_of_week, start_time'

    day_of_week = fields.Selection([
        ('0', 'Monday'), ('1', 'Tuesday'), ('2', 'Wednesday'),
        ('3', 'Thursday'), ('4', 'Friday'), ('5', 'Saturday'), ('6', 'Sunday'),
    ], required=True)
    start_time = fields.Float(required=True, help='Hour of day, e.g. 9.5 = 09:30')
    end_time = fields.Float(required=True)
    capacity = fields.Integer(required=True)
    slot_type = fields.Selection([
        ('free_swim', 'Free Swim'),
        ('lesson', 'Lesson'),
        ('private_pt', 'Private PT'),
    ], required=True)

    @api.constrains('start_time', 'end_time', 'capacity')
    def _check_slot(self):
        for rec in self:
            if rec.end_time <= rec.start_time:
                raise ValidationError('End time must be after start time.')
            if rec.capacity <= 0:
                raise ValidationError('Capacity must be greater than zero.')


class PoolBooking(models.Model):
    _name = 'fitzone.pool.booking'
    _description = 'Pool Booking'

    member_id = fields.Many2one(
        'res.partner', string='Member', required=True, ondelete='restrict')
    membership_id = fields.Many2one(
        'fitzone.membership', string='Membership', required=True)
    pool_slot_id = fields.Many2one(
        'fitzone.pool.slot', string='Pool Slot', required=True)
    trainer_id = fields.Many2one(
        'fitzone.trainer', help='Only for Private PT slots')
    booking_date = fields.Datetime(default=fields.Datetime.now)
    status = fields.Selection([
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
    ], default='confirmed', required=True)

    @api.constrains('trainer_id', 'pool_slot_id')
    def _check_trainer(self):
        for rec in self:
            if rec.trainer_id and rec.pool_slot_id.slot_type != 'private_pt':
                raise ValidationError(
                    'A trainer can only be set on Private PT slots.')