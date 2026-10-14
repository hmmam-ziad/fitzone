# ------------------------------------------------------------
# Auther   : HmMam Alsukhni
# Created  : 07-10-2026 | 04:00 PM (GMT+3)
# ------------------------------------------------------------

import logging

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)


class PurchaseRequest(models.Model):
    _name = 'fitzone.purchase.request'
    _description = 'Purchase Request'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'fitzone.department.company.mixin']
    _order = 'id desc'

    name = fields.Char(default='New', readonly=True, copy=False)
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('to_approve', 'Waiting Approval'),
            ('approved', 'Approved'),
            ('ordered', 'Ordered'),
            ('received', 'Received'),
            ('billed', 'Billed'),
            ('cancelled', 'Cancelled'),
            ('rejected', 'Refused'),
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
    purchase_order_id = fields.Many2one('purchase.order', string='RFQ / Purchase Order', readonly=True, copy=False,
                                        groups='purchase.group_purchase_user,fitzone.group_fitzone_manager')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)
    department_id = fields.Many2one(
        'hr.department', check_company=True, tracking=True,
        default=lambda self: self.env.user.employee_id.department_id,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]")
    line_ids = fields.One2many('fitzone.purchase.request.line', 'request_id', string='Products')

    purchase_progress = fields.Selection(
        [('approved', 'Approved'), ('ordered', 'Ordered'),
         ('received', 'Received'), ('billed', 'Billed')],
        compute='_compute_purchase_progress', store=True, compute_sudo=True)
    expected_arrival = fields.Datetime(compute='_compute_purchase_progress', store=True)
    partially_received = fields.Boolean(compute='_compute_purchase_progress', store=True)
    bill_payment_status = fields.Char(string='Bill payment', compute='_compute_purchase_progress', store=True)

    @api.depends('state', 'purchase_order_id', 'purchase_order_id.state',
                 'purchase_order_id.date_planned', 'purchase_order_id.receipt_status',
                 'purchase_order_id.invoice_ids.state', 'purchase_order_id.invoice_ids.move_type',
                 'purchase_order_id.invoice_ids.payment_state')
    def _compute_purchase_progress(self):
        for req in self:
            po = req.purchase_order_id
            bills = po.invoice_ids.filtered(lambda bill: bill.move_type == 'in_invoice' and bill.state != 'cancel')
            posted = bills.filtered(lambda bill: bill.state == 'posted')
            progress = 'approved'
            if po.state in ('purchase', 'done'):
                progress = 'ordered'
                if po.receipt_status == 'full':
                    progress = 'received'
                if bills and len(posted) == len(bills):
                    progress = 'billed'
            req.purchase_progress = progress if po else ('approved' if req.state in ('approved', 'ordered', 'received', 'billed') else False)
            req.expected_arrival = po.date_planned if po.state != 'cancel' else False
            req.partially_received = po.state in ('purchase', 'done') and po.receipt_status == 'partial'
            labels = dict(self.env['account.move']._fields['payment_state']._description_selection(self.env))
            req.bill_payment_status = ', '.join(sorted({labels.get(b.payment_state, b.payment_state) for b in posted if b.payment_state}))

    def _sync_purchase_progress(self):
        """Called by purchasing events, never by a scheduled job.

        Elevation is restricted to projecting safe progress onto requests: a
        warehouse operator/accountant need not have request approval rights.
        """
        for req in self.sudo():
            req._lock_workflow()
            po = req.purchase_order_id
            if not po or req.state in ('draft', 'to_approve', 'rejected', 'cancelled'):
                continue
            if po.state == 'cancel':
                req.write({'purchase_order_id': False, 'state': 'approved'})
                req._notify_requester(_('The RFQ for purchase request %s was cancelled. The request is Approved and a replacement RFQ can be created.', req.name))
                continue
            progress = req.purchase_progress
            if progress and req.state != progress:
                req.state = progress
                label = dict(req._fields['state']._description_selection(req.env))[progress]
                req._notify_requester(_('Purchase request %(request)s: %(status)s.', request=req.name, status=label))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not self._is_approver() and (
                vals.get('state', 'draft') != 'draft'
                or any(vals.get(key) for key in ('purchase_order_id', 'approver_id', 'approval_date'))
            ):
                raise AccessError(_('Only managers can set approval or RFQ information.'))
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'fitzone.purchase.request') or 'New'
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------
    def _is_approver(self):
        return (self.env.su or self.env.user.has_group('purchase.group_purchase_manager')
                or self.env.user.has_group('fitzone.group_fitzone_manager'))

    def _check_approver(self):
        if not self._is_approver():
            raise AccessError(_('Only Managers can approve or refuse requests.'))
        self.check_access('write')

    def write(self, vals):
        if not self.env.su and any(key in vals for key in ('purchase_progress', 'expected_arrival', 'partially_received', 'bill_payment_status')):
            raise AccessError(_('Purchase progress is determined by purchasing documents.'))
        if not self._is_approver():
            if any(key in vals for key in ('purchase_order_id', 'approver_id', 'approval_date', 'reject_reason')):
                raise AccessError(_('Only managers can set approval or RFQ information.'))
            if 'state' in vals and not all(
                (req.state == 'draft' and vals['state'] == 'to_approve')
                or (req.state == 'rejected' and vals['state'] == 'draft') for req in self
            ):
                raise AccessError(_('Only Managers can approve or refuse requests.'))
            if any(req.state not in ('draft', 'to_approve', 'rejected') for req in self):
                raise AccessError(_('Approved requests cannot be edited by the requester.'))
        if vals.get('state') == 'to_approve':
            for req in self:
                if not vals.get('department_id', req.department_id.id):
                    raise UserError(_('Select a department before submitting the purchase request.'))
                if not req.line_ids:
                    raise UserError(_('Add at least one product before submitting.'))
        return super().write(vals)

    def _get_managers(self):
        users = self.env['res.users'].sudo().search([('share', '=', False)])
        return users.filtered(lambda u: (
            u.has_group('fitzone.group_fitzone_manager')
            or u.has_group('purchase.group_purchase_manager'))
            and self.company_id in u.company_ids)

    def action_submit(self):
        for req in self.filtered(lambda r: r.state == 'draft'):
            req.state = 'to_approve'
            for manager in req._get_managers():
                req.activity_schedule(
                    'mail.mail_activity_data_todo', user_id=manager.id,
                    summary=_("Approve purchase request %s", req.name))

    def _lock_workflow(self):
        self.check_access('write')
        self.flush_recordset()
        self.env.cr.execute(
            'SELECT id FROM fitzone_purchase_request WHERE id IN %s ORDER BY id FOR UPDATE',
            [tuple(self.ids)])
        self.invalidate_recordset()

    def action_approve(self):
        self._check_approver()
        for req in self:
            req._lock_workflow()
            if req.state not in ('to_approve', 'approved'):
                continue
            if not req.vendor_id:
                raise UserError(_('Select a supplier before approving the purchase request.'))
            if req.state == 'to_approve':
                req.write({'state': 'approved', 'approver_id': self.env.uid,
                           'approval_date': fields.Datetime.now()})
                req._notify_requester(_('Purchase request %s approved. You can now create the RFQ.', req.name))
            req.activity_feedback(['mail.mail_activity_data_todo'])

    def _notify_requester(self, body):
        self.message_post(body=body, partner_ids=self.create_uid.partner_id.ids,
                          message_type='comment', subtype_xmlid='mail.mt_comment')

    def action_reject(self):
        self._check_approver()
        for req in self:
            req._lock_workflow()
            if req.state != 'to_approve':
                continue
            req.write({'state': 'rejected', 'approver_id': self.env.uid,
                       'approval_date': fields.Datetime.now()})
            req.activity_feedback(['mail.mail_activity_data_todo'])
            req._notify_requester(_('Purchase request %(name)s refused. Reason: %(reason)s',
                                    name=req.name, reason=req.reject_reason or _('No reason provided.')))

    def action_reset_draft(self):
        for req in self.filtered(lambda r: r.state == 'rejected'):
            vals = {'state': 'draft'}
            if req._is_approver():
                vals.update(approver_id=False, approval_date=False, reject_reason=False)
            req.write(vals)

    def _create_rfq(self):
        """Private, locked helper for explicit RFQ creation.

        RFQ creation uses the purchasing permissions of the acting user.
        Odoo computes supplier prices, discounts, taxes and delivery dates.
        """
        self.ensure_one()
        self._lock_workflow()
        if self.purchase_order_id:
            return
        if self.state != 'approved':
            raise UserError(_('Only approved requests can be converted to an RFQ.'))
        if not self.vendor_id:
            raise UserError(_('Select a supplier before creating the RFQ.'))
        if not self.line_ids:
            raise UserError(_('Add at least one product before creating the RFQ.'))
        po = self.env['purchase.order'].with_company(self.company_id).create({
            'partner_id': self.vendor_id.id,
            'company_id': self.company_id.id,
            'user_id': self.env.uid,
            'origin': self.name,
            'requested_by': self.requested_by.id,
            'department_id': self.department_id.id,
            'fz_request_id': self.id,
            'order_line': [(0, 0, {
                'product_id': line.product_id.id,
                'product_qty': line.qty,
                'product_uom_id': line.uom_id.id,
            }) for line in self.line_ids],
        })
        self.sudo().write({'purchase_order_id': po.id})
        po.message_post(body=_('Draft RFQ created from purchase request %s.', self.name))
        self._notify_requester(_('Draft RFQ created for purchase request %s.', self.name))

    def action_create_rfq(self):
        self.ensure_one()
        if not (self._is_approver() or self.env.user.has_group('purchase.group_purchase_user')):
            raise AccessError(_('Only purchasing users can create RFQs.'))
        self.check_access('write')
        self._create_rfq()
        return self.action_open_rfq()

    def action_open_rfq(self):
        self.ensure_one()
        self.check_access('read')
        self.purchase_order_id.check_access('read')
        return {'type': 'ir.actions.act_window', 'res_model': 'purchase.order',
                'res_id': self.purchase_order_id.id, 'view_mode': 'form'}

    @api.model
    def _recover_approved_rfqs(self):
        """Repair existing links only; upgrades never create purchasing documents."""
        for req in self.sudo().search([('state', '=', 'approved'), ('purchase_order_id', '=', False)]):
            existing = self.env['purchase.order'].sudo().search([
                ('fz_request_id', '=', req.id), ('state', '!=', 'cancel')], limit=1)
            if existing:
                req.write({'purchase_order_id': existing.id})
                req._sync_purchase_progress()
            else:
                _logger.info('FitZone: approved request %s awaits manual RFQ creation.', req.name)

    @api.model
    def _migrate_purchase_progress(self):
        """The old 'ordered' value meant RFQ Created; derive its real state.

        Cancellation is processed before recovery, which must not automatically
        replace a deliberately cancelled RFQ on every upgrade.
        """
        requests = self.sudo().search([('state', 'in', ('approved', 'ordered', 'received', 'billed'))])
        for req in requests:
            po = req.purchase_order_id
            if po:
                # Remove PO references from the previous generated requester notification.
                for message in req.message_ids.filtered(lambda m: 'Draft RFQ' in str(m.body) and po.name in str(m.body)):
                    message.sudo().write({'body': _('Purchase request %s approved. Purchasing will review the draft RFQ.', req.name)})
                req._sync_purchase_progress()
            elif req.state != 'approved':
                req.state = 'approved'


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
        if vals.get('request_id'):
            target = self.env['fitzone.purchase.request'].browse(vals['request_id'])
            target.check_access('write')
            if target.state not in ('draft', 'to_approve'):
                raise UserError(_('Lines can only be moved to draft or waiting requests.'))
        return super().write(vals)

    def unlink(self):
        self._check_request_editable()
        return super().unlink()
