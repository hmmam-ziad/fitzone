from odoo import fields, models


class HealthProfile(models.Model):
    _name = 'fitzone.health.profile'
    _inherit = 'fitzone.medical.audit.mixin'
    _rec_name = 'id'
    _description = 'Health Profile'

    member_id = fields.Many2one('res.partner', required=True)
    age = fields.Integer()
    weight = fields.Float()
    height = fields.Float()