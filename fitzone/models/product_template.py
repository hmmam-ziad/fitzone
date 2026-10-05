from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    package_type = fields.Char()
    duration_months = fields.Integer()
    total_sessions = fields.Integer()