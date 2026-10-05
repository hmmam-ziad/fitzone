from odoo import fields, models


class Room(models.Model):
    _name = 'fitzone.room'
    _description = 'Room'

    name = fields.Char()
    capacity = fields.Integer()