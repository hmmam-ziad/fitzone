from odoo import fields, models


class EmergencyContact(models.Model):
    _name = 'fitzone.emergency.contact'
    _description = 'Emergency Contact'

    member_id = fields.Many2one('res.partner', required=True)
    name = fields.Char()
    phone = fields.Char()
    relationship = fields.Char()