from odoo import fields, models


class InstallmentPlan(models.Model):
    _name = 'fitzone.installment.plan'
    _description = 'Installment Plan'
    _rec_name = 'membership_id'

    membership_id = fields.Many2one('fitzone.membership', required=True)
    total_amount = fields.Float()
    down_payment = fields.Float()
    status = fields.Char()