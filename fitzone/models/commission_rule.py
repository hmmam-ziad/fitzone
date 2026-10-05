from odoo import fields, models


class CommissionRule(models.Model):
    _name = 'fitzone.commission.rule'
    _description = 'Commission Rule'

    name = fields.Char()
    rate = fields.Float()
    active = fields.Boolean(default=True)
    effective_from = fields.Date()
    effective_to = fields.Date()