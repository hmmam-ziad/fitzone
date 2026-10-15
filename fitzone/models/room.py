from odoo import api, fields, models
from odoo.exceptions import ValidationError


class Room(models.Model):
    _name = 'fitzone.room'
    _description = 'Room'

    name = fields.Char(required=True)
    capacity = fields.Integer(string='Max Capacity', required=True)

    @api.constrains('capacity')
    def _check_capacity(self):
        for rec in self:
            if rec.capacity <= 0:
                raise ValidationError(_("Room capacity must be greater than zero."))