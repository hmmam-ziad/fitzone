# ------------------------------------------------------------
# Modified By   : HmMam Alsukhni
# Modified       : 07-10-2026 | 03:45 PM (GMT+3)
# ------------------------------------------------------------
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class PurchaseOrder(models.Model):
    _name = 'purchase.order'
    _inherit = ['purchase.order', 'fitzone.department.company.mixin']

    requested_by = fields.Many2one('hr.employee')
    fz_request_id = fields.Many2one('fitzone.purchase.request', string='Purchase Request', readonly=True, copy=False)

    def action_rfq_send(self):
        """Nothing goes to the supplier before management approval.

        The company is configured with two-step PO validation (threshold 0),
        so every PO reaches state 'purchase' only after a Purchase Manager
        approves it. Until then sending is blocked.
        """
        unapproved = self.filtered(lambda po: po.state not in ('purchase', 'done'))
        if unapproved:
            raise UserError(_(
                "Purchase orders cannot be sent to the supplier before "
                "management approval. Confirm the order and wait for a "
                "Purchase Manager to approve it first.\n\nOrders: %s",
                ', '.join(unapproved.mapped('name'))))
        return super().action_rfq_send()

    department_id = fields.Many2one('hr.department', check_company=True, index=True, domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]")

    def button_confirm(self):
        if self.filtered(lambda order: not order.department_id):
            raise ValidationError(_('Select a department before confirming a purchase order.'))
        return super().button_confirm()

    @api.constrains('state', 'department_id')
    def _check_department_on_confirmation(self):
        if self.filtered(lambda order: order.state in ('to approve', 'purchase', 'done') and not order.department_id):
            raise ValidationError(_('Confirmed purchase orders require a department.'))


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    department_id = fields.Many2one(related='order_id.department_id', store=True, index=True)


class DepartmentBill(models.Model):
    _name = 'account.move'
    _inherit = ['account.move', 'fitzone.department.company.mixin']

    fitzone_department_id = fields.Many2one(
        'hr.department', string='Department (without PO)', check_company=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help='Used for vendor bill lines without a linked purchase order.')
