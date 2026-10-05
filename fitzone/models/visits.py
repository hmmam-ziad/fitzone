from odoo import fields, models


class Visit(models.Model):
    _name = 'fitzone.visit'
    _description = 'Visit'
    _order = 'visit_date desc'

    member_id = fields.Many2one(
        'res.partner', string='Member', required=True, ondelete='restrict')
    membership_id = fields.Many2one(
        'fitzone.membership', string='Membership', required=True, ondelete='restrict')
    visit_date = fields.Datetime(default=fields.Datetime.now)
    remaining_sessions = fields.Integer()
    status = fields.Selection([
        ('allowed', 'Allowed'),
        ('blocked', 'Blocked'),
    ], default='allowed')