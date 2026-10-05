from odoo import fields, models


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    membership_id = fields.Many2one('fitzone.membership')