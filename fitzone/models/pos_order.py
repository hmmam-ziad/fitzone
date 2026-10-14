from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


# An RPC context cannot manufacture this identity.
_VERIFIED_ORDER = object()


class PosOrder(models.Model):
    _inherit = 'pos.order'

    fitzone_member_id = fields.Many2one(
        'res.partner', readonly=True, copy=False,
        groups='fitzone.group_fitzone_manager,fitzone.group_fitzone_reception',
    )

    def _check_member_discount_role(self):
        if not (self.env.user.has_group('fitzone.group_fitzone_sales') or
                self.env.user.has_group('fitzone.group_fitzone_manager')):
            raise AccessError('Member status is restricted to Sales and Manager.')

    def _active_member_id(self, number=None, member_id=None):
        """Private verification: return only the active member ID for server storage."""
        # Elevation permits status verification without granting member browsing.
        partners = self.env['res.partner'].sudo()
        member = partners.browse(member_id).exists() if member_id else partners.search([
            ('is_fitzone_member', '=', True), ('membership_no', '=', number or False),
        ], limit=1) if number else partners.browse()
        if not member and number:
            member = self.env['fitzone.membership'].sudo().search([
                ('barcode', '=', number), ('member_id.is_fitzone_member', '=', True),
            ], limit=1).member_id
        return member.id if member and member._get_membership_status_value() == 'Active' else False

    def _supplement_ids(self, product_ids):
        category = self.env.ref('fitzone.product_category_supplements', raise_if_not_found=False)
        return self.env['product.product'].search([
            ('id', 'in', product_ids), ('categ_id', 'child_of', category.id),
        ]).ids if category else []

    @api.model
    def check_member_discount_eligibility(self, membership_no, product_ids):
        self._check_member_discount_role()
        active = bool(self._active_member_id(membership_no))
        return {'status': 'active' if active else 'inactive',
                'eligible_product_ids': self._supplement_ids(product_ids) if active else []}

    def _should_log_order_data(self):
        # Membership verification input must not enter core full-payload logs.
        return False

    def _check_retail_partner(self, vals):
        if vals.get('partner_id') and self.env.user.has_group('fitzone.group_fitzone_sales'):
            partner = self.env['res.partner'].browse(vals['partner_id'])
            partner.check_access('read')
            if partner.is_fitzone_member:
                raise AccessError('Select a nonmember retail customer.')

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get('_fitzone_verified_order') is not _VERIFIED_ORDER:
            if any(vals.get('fitzone_member_id') for vals in vals_list):
                raise AccessError('Member link is server-managed.')
        for vals in vals_list:
            self._check_retail_partner(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._check_retail_partner(vals)
        if 'fitzone_member_id' in vals and self.env.context.get('_fitzone_verified_order') is not _VERIFIED_ORDER:
            raise AccessError('Member link is server-managed.')
        return super().write(vals)

    def _process_order(self, order, existing_order):
        order = dict(order)
        number = order.pop('fitzone_membership_number', None)
        order.pop('fitzone_member_id', None)
        if number:
            self._check_member_discount_role()
        member_id = self._active_member_id(number)
        # Protected field is supplied only by this verified server path.
        verified = self.with_context(_fitzone_verified_order=_VERIFIED_ORDER)
        result = super(PosOrder, verified)._process_order(order, existing_order)
        record = self.browse(result)
        record._store_verified_member(member_id)
        record._validate_member_discount()
        return result

    def _store_verified_member(self, member_id):
        """Private server-only storage of the freshly verified link."""
        # Elevation writes only the protected D1 link after order processing.
        self.with_context(_fitzone_verified_order=_VERIFIED_ORDER).sudo().write({'fitzone_member_id': member_id})

    def _validate_member_discount(self):
        for order in self:
            discounted = order.lines.filtered(lambda line: line.discount == 50)
            if not discounted:
                continue
            member_id = order._verified_member_link()
            eligible = set(self._supplement_ids(discounted.product_id.ids))
            if not member_id or any(line.product_id.id not in eligible for line in discounted):
                raise ValidationError('A 50% member discount requires active membership and supplement products.')

    def _verified_member_link(self):
        """Return only the revalidated link; never expose it through RPC."""
        self.ensure_one()
        # Elevation reads only the protected order link for discount validation.
        return self._active_member_id(member_id=self.sudo().fitzone_member_id.id)


class PosOrderLine(models.Model):
    _inherit = 'pos.order.line'

    @api.constrains('discount', 'product_id', 'order_id')
    def _check_fitzone_member_discount(self):
        if self.env.context.get('_fitzone_verified_order') is not _VERIFIED_ORDER:
            self.order_id._validate_member_discount()
