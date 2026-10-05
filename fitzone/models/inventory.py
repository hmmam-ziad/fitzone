from odoo import fields, models

# Product, Stock (stock.quant), Product_Lot (stock.lot) and Reorder_Rule
# (stock.warehouse.orderpoint) are standard Odoo and need no custom code.


class PurchaseOrder(models.Model):
    """Purchase Request = purchase.order extended."""
    _inherit = 'purchase.order'

    requested_by = fields.Many2one('hr.employee', string='Requested By')