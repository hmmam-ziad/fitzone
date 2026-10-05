from odoo import fields, models


class Freeze(models.Model):
    _name = 'fitzone.freeze'
    _description = 'Freeze'

    membership_id = fields.Many2one('fitzone.membership', required=True)
    start_date = fields.Date()
    end_date = fields.Date()
    days = fields.Integer()