from odoo import fields, models


class PoolSlot(models.Model):
    _name = 'fitzone.pool.slot'
    _description = 'Pool Slot'
    _rec_name = 'day_of_week'

    day_of_week = fields.Char()
    start_time = fields.Float()
    end_time = fields.Float()
    capacity = fields.Integer()
    slot_type = fields.Char()