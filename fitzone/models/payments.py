from odoo import api, fields, models
from odoo.exceptions import ValidationError


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    membership_id = fields.Many2one('fitzone.membership', string='Membership')


class InstallmentPlan(models.Model):
    _name = 'fitzone.installment.plan'
    _description = 'Installment Plan'

    membership_id = fields.Many2one(
        'fitzone.membership', string='Membership', required=True, ondelete='cascade')
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id)
    total_amount = fields.Monetary(currency_field='currency_id')
    down_payment = fields.Monetary(currency_field='currency_id')
    status = fields.Selection([
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('defaulted', 'Defaulted'),
    ], default='active')
    installment_ids = fields.One2many('fitzone.installment', 'plan_id')

    _membership_uniq = models.Constraint(
        'unique(membership_id)', 'A membership can only have one installment plan.')

    @api.constrains('total_amount', 'down_payment')
    def _check_amounts(self):
        for rec in self:
            if rec.down_payment < 0 or rec.down_payment > rec.total_amount:
                raise ValidationError(
                    'Down payment must be between 0 and the total amount.')


class Installment(models.Model):
    _name = 'fitzone.installment'
    _description = 'Installment'
    _order = 'due_date'

    plan_id = fields.Many2one(
        'fitzone.installment.plan', string='Plan', required=True, ondelete='cascade')
    currency_id = fields.Many2one(related='plan_id.currency_id')
    due_date = fields.Date(required=True)
    amount = fields.Monetary(currency_field='currency_id')
    status = fields.Selection([
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
    ], default='pending')