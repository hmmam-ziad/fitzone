# ------------------------------------------------------------
# Auther   : HmMam Alsukhni
# Created  : 07-10-2026 | 04:00 PM (GMT+3)
# ------------------------------------------------------------

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PurchaseRequest(models.Model):
    _name = 'fitzone.purchase.request'
    _description = 'Purchase Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(default='New', readonly=True, copy=False)
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('to_approve', 'Waiting Approval'),
            ('approved', 'Approved'),
            ('ordered', 'RFQ Created'),
            ('rejected', 'Rejected'),
        ],
        default='draft', required=True, tracking=True, copy=False)
    
    source = fields.Selection([('manual', 'Manual'), ('auto', 'Automatic (low stock)')], default='manual', required=True, readonly=True)
    requested_by = fields.Many2one('hr.employee', default=lambda self: self.env.user.employee_id)
    request_date = fields.Date(default=fields.Date.context_today)
    vendor_id = fields.Many2one('res.partner', string='Supplier', tracking=True, help="Required to create the RFQ. Auto requests use the product's first supplier when one is defined.")
    approver_id = fields.Many2one('res.users', readonly=True, copy=False)
    approval_date = fields.Datetime(readonly=True, copy=False)
    reject_reason = fields.Text(copy=False)
    notes = fields.Text()
    purchase_order_id = fields.Many2one('purchase.order', string='RFQ / Purchase Order', readonly=True, copy=False)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)
    line_ids = fields.One2many('fitzone.purchase.request.line', 'request_id', string='Products')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'fitzone.purchase.request') or 'New'
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------
    def _get_managers(self):
        users = self.env['res.users'].sudo().search([('share', '=', False)])
        return users.filtered(
            lambda u: u.has_group('purchase.group_purchase_manager'))

    def action_submit(self):
        for req in self:
            if req.state != 'draft':
                continue
            if not req.line_ids:
                raise UserError(_("Add at least one product before submitting."))
            req.state = 'to_approve'
            for manager in req._get_managers():
                req.activity_schedule(
                    'mail.mail_activity_data_todo',
                    user_id=manager.id,
                    summary=_("Approve purchase request %s", req.name),
                )

    def action_approve(self):
        if not (self.env.user.has_group('purchase.group_purchase_manager')
                or self.env.user.has_group('fitzone.group_fitzone_manager')):
            raise UserError(_("Only Owners or Purchase Managers can approve purchase requests."))
        for req in self.filtered(lambda r: r.state == 'to_approve'):
            req.write({
                'state': 'approved',
                'approver_id': self.env.user.id,
                'approval_date': fields.Datetime.now(),
            })
            req.activity_feedback(['mail.mail_activity_data_todo'])

    def action_reject(self):
        if not (self.env.user.has_group('purchase.group_purchase_manager')
                or self.env.user.has_group('fitzone.group_fitzone_manager')):
            raise UserError(_("Only Owners or Purchase Managers can reject purchase requests."))
        for req in self.filtered(lambda r: r.state == 'to_approve'):
            req.write({
                'state': 'rejected',
                'approver_id': self.env.user.id,
                'approval_date': fields.Datetime.now(),
            })
            req.activity_feedback(['mail.mail_activity_data_todo'])

    def action_reset_draft(self):
        self.filtered(lambda r: r.state == 'rejected').write({
            'state': 'draft', 'approver_id': False, 'approval_date': False})

    def action_create_rfq(self):
        self.ensure_one()
        if self.state != 'approved':
            raise UserError(_("Only approved requests can be converted to an RFQ."))
        if not self.vendor_id:
            raise UserError(_("Select a supplier before creating the RFQ."))
        Line = self.env['purchase.order.line']
        uom_field = 'product_uom_id' if 'product_uom_id' in Line._fields else 'product_uom'
        order_lines = []
        for line in self.line_ids:
            order_lines.append((0, 0, {
                'product_id': line.product_id.id,
                'name': line.product_id.display_name,
                'product_qty': line.qty,
                uom_field: line.product_id.uom_id.id,
            }))
        po = self.env['purchase.order'].create({
            'partner_id': self.vendor_id.id,
            'origin': self.name,
            'requested_by': self.requested_by.id,
            'fz_request_id': self.id,
            'order_line': order_lines,
        })
        self.write({'purchase_order_id': po.id, 'state': 'ordered'})
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'res_id': po.id,
            'view_mode': 'form',
        }


class PurchaseRequestLine(models.Model):
    _name = 'fitzone.purchase.request.line'
    _description = 'Purchase Request Line'

    request_id = fields.Many2one(
        'fitzone.purchase.request', required=True, ondelete='cascade')
    product_id = fields.Many2one(
        'product.product', required=True,
        domain="[('fz_product_type', 'in', ('supplement', 'health'))]")
    product_tmpl_id = fields.Many2one(
        related='product_id.product_tmpl_id', store=True)
    qty = fields.Float(string='Quantity', required=True, default=1.0,
                       digits='Product Unit')
    uom_id = fields.Many2one(related='product_id.uom_id', string='Unit')
    usable_qty = fields.Float(
        related='product_tmpl_id.fz_usable_qty', string='Usable Stock')
    min_qty = fields.Float(
        related='product_tmpl_id.fz_min_stock_level', string='Minimum Level')

    @api.constrains('qty')
    def _check_qty(self):
        for line in self:
            if line.qty <= 0:
                raise UserError(_("Quantity must be greater than zero."))

    def _check_request_editable(self):
        for line in self:
            if line.request_id.state not in ('draft', 'to_approve'):
                raise UserError(_(
                    "Lines cannot be changed once the request is approved, "
                    "ordered or rejected."))

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._check_request_editable()
        return lines

    def write(self, vals):
        self._check_request_editable()
        return super().write(vals)

    def unlink(self):
        self._check_request_editable()
        return super().unlink()
