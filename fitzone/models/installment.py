from odoo import fields, models


class Installment(models.Model):
    _name = 'fitzone.installment'
    _description = 'Installment'

    plan_id = fields.Many2one('fitzone.installment.plan', required=True)
    due_date = fields.Date()
    amount = fields.Float()
    status = fields.Char()