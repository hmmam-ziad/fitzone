from odoo import api, models


class PosOrder(models.Model):
    _inherit = 'pos.order'

    @api.model
    def check_member_discount_eligibility(self, membership_no, product_ids):
        if not membership_no:
            return {
                'eligible': False,
                'member_name': False,
                'membership_status': 'Inactive',
                'eligible_product_ids': [],
            }

        Partner = self.env['res.partner'].sudo()

        member = Partner.search([
            ('membership_no', '=', membership_no),
        ], limit=1)

        # Also allow the membership barcode.
        if not member:
            membership = self.env['fitzone.membership'].sudo().search([
                ('barcode', '=', membership_no),
            ], limit=1)

            member = membership.member_id if membership else False

        if not member:
            return {
                'eligible': False,
                'member_name': False,
                'membership_status': 'Inactive',
                'eligible_product_ids': [],
            }

        status = member.membership_status
        eligible_product_ids = []

        if status == 'Active':
            products = self.env['product.product'].sudo().browse(product_ids)

            for product in products:
                category = product.product_tmpl_id.categ_id

                if category.name == 'Dietary Supplements':
                    eligible_product_ids.append(product.id)

        return {
            'eligible': status == 'Active',
            'member_name': member.name,
            'membership_status': status,
            'eligible_product_ids': eligible_product_ids,
        }