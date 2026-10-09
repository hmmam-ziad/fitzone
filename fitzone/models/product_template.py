# ------------------------------------------------------------
# Modified By   : HmMam Alsukhni
# Modified       : 07-10-2026 | 03:01 PM (GMT+3)
# ------------------------------------------------------------

import logging
from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

# Product types whose stock is tracked (lots + expiry dates + FEFO + reorder alerts).
TRACKED_TYPES = ('supplement', 'health')


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    package_type = fields.Selection(
        [
            ('general', 'General'),
            ('private', 'Private'),
            ('all_inclusive', 'All-Inclusive'),
        ],
        string='Package Type',
    )

    duration_months = fields.Integer(
        string='Duration (Months)',
    )

    total_sessions = fields.Integer(
        string='Total Sessions',
    )

    # --- Allowed weekdays / time window for class attendance ---
    allow_mon = fields.Boolean('Monday')
    allow_tue = fields.Boolean('Tuesday')
    allow_wed = fields.Boolean('Wednesday')
    allow_thu = fields.Boolean('Thursday')
    allow_fri = fields.Boolean('Friday')
    allow_sat = fields.Boolean('Saturday')
    allow_sun = fields.Boolean('Sunday')

    # Time window in which the package allows class attendance (24h float)
    allowed_from = fields.Float('Allowed From', default=0.0)
    allowed_to = fields.Float('Allowed To', default=24.0)

    def allowed_weekdays(self):
        """Python weekday(): Monday = 0 ... Sunday = 6"""
        self.ensure_one()
        flags = [self.allow_mon, self.allow_tue, self.allow_wed, self.allow_thu,
                 self.allow_fri, self.allow_sat, self.allow_sun]
        return [i for i, f in enumerate(flags) if f]

    # --- Inventory & procurement scope ---
    fz_product_type = fields.Selection(
        [
            ('supplement', 'Dietary Supplement'),
            ('health', 'Health Product'),
            ('juice', 'Fresh Juice (made-to-order)'),
            ('snack', 'Snack (made-to-order)'),
            ('ingredient', 'Juice Ingredient'),
            ('other', 'Other / Service'),
        ],
        string='FitZone Product Type',
        default='other',
        required=True,
        help="Only Dietary Supplements and Health Products are tracked in "
             "inventory. Juices, snacks and juice ingredients are sold from "
             "the POS as made-to-order items and never deduct stock.",
    )
    fz_min_stock_level = fields.Float(
        string='Minimum Stock Level',
        digits='Product Unit',
        help="Reorder point. When the usable (non-expired) quantity reaches "
             "this level, administrators are alerted and a purchase request "
             "is created automatically. 0 = alert disabled.",
    )
    fz_reorder_qty = fields.Float(
        string='Suggested Reorder Quantity',
        digits='Product Unit',
        help="Quantity pre-filled in automatic purchase requests. If empty, "
             "the minimum stock level is used. Management can edit it "
             "before approving.",
    )
    fz_usable_qty = fields.Float(
        string='Usable Qty (non-expired)',
        digits='Product Unit',
        compute='_compute_fz_usable_qty',
        help="On-hand quantity in internal locations excluding expired lots.",
    )
    fz_low_stock = fields.Boolean(
        string='Low Stock',
        readonly=True,
        copy=False,
        help="Set automatically when usable stock is at or below the "
             "minimum level.",
    )

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------
    @api.depends_context('company')
    def _compute_fz_usable_qty(self):
        real = self.filtered(lambda t: isinstance(t.id, int))
        totals = defaultdict(float)
        if real:
            variants = self.env['product.product'].with_context(
                active_test=False).search([('product_tmpl_id', 'in', real.ids)])
            now = fields.Datetime.now()
            domain = [
                ('product_id', 'in', variants.ids),
                ('location_id.usage', '=', 'internal'),
                '|', '|',
                ('lot_id', '=', False),
                ('lot_id.expiration_date', '=', False),
                ('lot_id.expiration_date', '>', now),
            ]
            groups = self.env['stock.quant']._read_group(
                domain, ['product_id'], ['quantity:sum'])
            for product, qty in groups:
                totals[product.product_tmpl_id.id] += qty
        for tmpl in self:
            tmpl.fz_usable_qty = totals.get(tmpl.id, 0.0)

    # ------------------------------------------------------------------
    # Onchange / constraints
    # ------------------------------------------------------------------
    @api.onchange('fz_product_type')
    def _onchange_fz_product_type(self):
        categ_supp = self.env.ref(
            'fitzone.product_category_supplements', raise_if_not_found=False)
        categ_mto = self.env.ref(
            'fitzone.product_category_made_to_order', raise_if_not_found=False)
        for tmpl in self:
            if tmpl.fz_product_type in TRACKED_TYPES:
                tmpl.type = 'consu'
                tmpl.is_storable = True
                tmpl.tracking = 'lot'
                tmpl.use_expiration_date = True
                if categ_supp:
                    tmpl.categ_id = categ_supp
            else:
                tmpl.is_storable = False
                tmpl.tracking = 'none'
                tmpl.use_expiration_date = False
                tmpl.fz_min_stock_level = 0.0
                if categ_mto and tmpl.fz_product_type in (
                        'juice', 'snack', 'ingredient'):
                    tmpl.categ_id = categ_mto

    @api.constrains('is_storable', 'fz_product_type', 'tracking',
                    'use_expiration_date')
    def _check_fz_inventory_scope(self):
        for tmpl in self:
            tracked = tmpl.fz_product_type in TRACKED_TYPES
            if tmpl.is_storable and not tracked:
                raise ValidationError(_(
                    "'%s' cannot be tracked in inventory. Only Dietary "
                    "Supplements and Health Products are stock-tracked; "
                    "juices, snacks and juice ingredients are made-to-order "
                    "and must not deduct stock.", tmpl.display_name))
            if tracked:
                if not tmpl.is_storable:
                    raise ValidationError(_(
                        "'%s' is a supplement/health product and must have "
                        "'Track Inventory' enabled.", tmpl.display_name))
                if tmpl.tracking != 'lot' or not tmpl.use_expiration_date:
                    raise ValidationError(_(
                        "'%s' must be tracked 'By Lots' with expiration "
                        "dates enabled (required for FEFO).",
                        tmpl.display_name))

    @api.constrains('fz_min_stock_level', 'fz_reorder_qty')
    def _check_fz_quantities(self):
        for tmpl in self:
            if tmpl.fz_min_stock_level < 0 or tmpl.fz_reorder_qty < 0:
                raise ValidationError(
                    _("Minimum stock level and reorder quantity cannot be negative."))

    def write(self, vals):
        res = super().write(vals)
        if 'fz_min_stock_level' in vals:
            self._fz_check_low_stock()
        return res

    # ------------------------------------------------------------------
    # Low stock detection, alerts and automatic purchase requests
    # ------------------------------------------------------------------
    @api.model
    def _cron_fz_check_low_stock(self):
        """Scheduled check (also catches lots that just expired)."""
        self.search([
            ('is_storable', '=', True),
            ('fz_product_type', 'in', list(TRACKED_TYPES)),
        ])._fz_check_low_stock()

    def _fz_check_low_stock(self):
        candidates = self.filtered(
            lambda t: t.is_storable and t.fz_product_type in TRACKED_TYPES)
        candidates.invalidate_recordset(['fz_usable_qty'])
        newly_low = self.browse()
        for tmpl in candidates:
            is_low = (tmpl.fz_min_stock_level > 0
                      and tmpl.fz_usable_qty <= tmpl.fz_min_stock_level)
            if is_low and not tmpl.fz_low_stock:
                newly_low |= tmpl
            elif not is_low and tmpl.fz_low_stock:
                tmpl.fz_low_stock = False
        if newly_low:
            newly_low.fz_low_stock = True
            newly_low._fz_notify_low_stock()
            newly_low._fz_create_auto_purchase_requests()

    @api.model
    def _fz_get_alert_users(self):
        users = self.env['res.users'].sudo().search([('share', '=', False)])
        return users.filtered(
            lambda u: u.has_group('base.group_system')
            or u.has_group('stock.group_stock_manager'))

    def _fz_notify_low_stock(self):
        recipients = self._fz_get_alert_users().partner_id
        for tmpl in self:
            tmpl.message_post(
                subject=_("Low stock: %s", tmpl.display_name),
                body=_(
                    "Low stock alert: %(name)s has %(qty)s usable units "
                    "(minimum level: %(min)s). A purchase request has been "
                    "created for management approval.",
                    name=tmpl.display_name,
                    qty=tmpl.fz_usable_qty,
                    min=tmpl.fz_min_stock_level),
                partner_ids=recipients.ids,
                message_type='notification',
                subtype_xmlid='mail.mt_comment',
            )

    def _fz_create_auto_purchase_requests(self):
        Request = self.env['fitzone.purchase.request']
        Line = self.env['fitzone.purchase.request.line']
        by_vendor = defaultdict(lambda: self.browse())
        for tmpl in self:
            already_requested = Line.search_count([
                ('product_tmpl_id', '=', tmpl.id),
                ('request_id.state', 'in', ('draft', 'to_approve', 'approved')),
            ])
            if already_requested:
                continue
            vendor = tmpl.seller_ids[:1].partner_id
            by_vendor[vendor.id] |= tmpl
        for vendor_id, tmpls in by_vendor.items():
            request = Request.create({
                'source': 'auto',
                'vendor_id': vendor_id or False,
                'requested_by': False,
                'notes': _("Created automatically: stock reached the minimum level."),
                'line_ids': [(0, 0, {
                    'product_id': t.product_variant_id.id,
                    'qty': t.fz_reorder_qty or t.fz_min_stock_level or 1.0,
                }) for t in tmpls],
            })
            request.action_submit()