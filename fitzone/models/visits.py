from odoo import fields, models


class Visit(models.Model):
    _name = 'fitzone.visit'
    _description = 'Visit'

    member_id = fields.Many2one('res.partner', required=True, domain="[('membership_ids', '!=', False)]")
    membership_id = fields.Many2one('fitzone.membership', required=True, domain="[('member_id', '=', member_id)]")
    visit_date = fields.Datetime()
    remaining_sessions = fields.Integer()
    status = fields.Char()