from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    membership_no = fields.Char()
    birth_date = fields.Date()