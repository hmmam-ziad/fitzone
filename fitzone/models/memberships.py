from odoo import api, fields, models


class Membership(models.Model):
    _name = 'fitzone.membership'
    _description = 'Membership'
    _rec_name = 'member_id'

    member_id = fields.Many2one('res.partner', required=True)
    package_id = fields.Many2one('product.template', required=True)
    barcode = fields.Char()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            member_id = vals.get('member_id')
            if member_id:
                member = self.env['res.partner'].browse(member_id)
                if not member.membership_no:
                    member.membership_no = self.env['ir.sequence'].next_by_code(
                        'fitzone.member'
                    )
        return super().create(vals_list)