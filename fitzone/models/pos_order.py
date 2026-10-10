from odoo import api, models


class PosOrder(models.Model):
    _inherit = 'pos.order'

    @api.model
    def check_member_discount_eligibility(self, membership_no, product_ids):
        empty = {
            'eligible': False,
            'member_name': False,
            'membership_status': 'Inactive',
            'eligible_product_ids': [],
        }

        if not membership_no:
            return empty

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
            return empty

        status = member.membership_status
        eligible_product_ids = []

        if status == 'Active':
            # Replace `your_module` with your actual module technical name
            supplements_categ = self.env.ref(
                'fitzone.product_category_supplements',
                raise_if_not_found=False,
            )

            if supplements_categ:
                products = self.env['product.product'].sudo().browse(product_ids)

                for product in products:
                    categ = product.product_tmpl_id.categ_id
                    # child_of so subcategories also qualify
                    if categ and (
                        categ == supplements_categ
                        or categ.parent_path.startswith(supplements_categ.parent_path)
                    ):
                        eligible_product_ids.append(product.id)

        return {
            'eligible': status == 'Active',
            'member_name': member.name,
            'membership_status': status,
            'eligible_product_ids': eligible_product_ids,
        }