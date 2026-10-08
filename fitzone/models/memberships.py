from odoo import fields, models


class Membership(models.Model):
    _name = 'fitzone.membership'
    _description = 'Membership'
    _rec_name = 'member_id'

    member_id = fields.Many2one('res.partner', required=True)
    package_id = fields.Many2one('product.template', required=True)
    barcode = fields.Char()

    start_date = fields.Date()
    end_date = fields.Date()