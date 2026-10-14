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

    _unique_fz_request = models.UniqueIndex(
        "(fz_request_id) WHERE state != 'cancel'",
        'A purchase request can have only one active RFQ.')

    def _auto_init(self):
        # Replace the previous unconditional uniqueness constraint on upgrades.
        self.env.cr.execute('ALTER TABLE purchase_order DROP CONSTRAINT IF EXISTS purchase_order_unique_fz_request')
        return super()._auto_init()

    def _sync_fitzone_requests(self):
        requests = self.sudo().mapped('fz_request_id')
        requests.filtered(lambda req: req.purchase_order_id in self)._sync_purchase_progress()

    def write(self, vals):
        result = super().write(vals)
        if any(key in vals for key in ('state', 'order_line', 'date_planned')):
            self._sync_fitzone_requests()
        return result

    def _approval_allowed(self):
        self.ensure_one()
        # The Manager already approved this request. Its requester can complete
        # purchasing without being granted Purchase Manager approval rights.
        req = self.fz_request_id
        if (self.env.user.has_group('fitzone.group_fitzone_sales')
                and req and req.create_uid == self.env.user
                and req.purchase_order_id == self and req.approver_id
                and req.state == 'approved'):
            return True
        return super()._approval_allowed()

    def action_rfq_send(self):
        unapproved = self.filtered(lambda po: po.state not in ('purchase', 'done')
            and not (po.fz_request_id and po.fz_request_id.approver_id
                     and po.fz_request_id.purchase_order_id == po
                     and po.fz_request_id.state == 'approved'))
        if unapproved:
            raise UserError(_('Purchase orders require management approval before sending to the supplier.'))
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

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        moves.sudo().line_ids.purchase_line_id.order_id._sync_fitzone_requests()
        return moves

    def write(self, vals):
        synchronize = any(key in vals for key in ('state', 'line_ids', 'invoice_line_ids'))
        orders = self.sudo().line_ids.purchase_line_id.order_id if synchronize else self.env['purchase.order']
        result = super().write(vals)
        if synchronize:
            (orders | self.sudo().line_ids.purchase_line_id.order_id)._sync_fitzone_requests()
        return result

    fitzone_department_id = fields.Many2one(
        'hr.department', string='Department (without PO)', check_company=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help='Used for vendor bill lines without a linked purchase order.')


class PurchaseRequestReceipt(models.Model):
    _inherit = 'stock.picking'

    def _action_done(self):
        result = super()._action_done()
        self.sudo().move_ids.purchase_line_id.order_id._sync_fitzone_requests()
        return result

    def action_cancel(self):
        orders = self.sudo().move_ids.purchase_line_id.order_id
        result = super().action_cancel()
        orders._sync_fitzone_requests()
        return result
