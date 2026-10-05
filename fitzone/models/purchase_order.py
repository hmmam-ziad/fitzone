from odoo import fields, models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    requested_by = fields.Many2one('hr.employee')