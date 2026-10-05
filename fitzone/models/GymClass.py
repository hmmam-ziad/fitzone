from odoo import fields, models


class GymClass(models.Model):
    _name = 'fitzone.gym.class'
    _description = 'Group Class'

    trainer_id = fields.Many2one('fitzone.trainer', required=True)
    room_id = fields.Many2one('fitzone.room', required=True)
    name = fields.Char()
    capacity = fields.Integer()
    start_datetime = fields.Datetime()
    end_datetime = fields.Datetime()