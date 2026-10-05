from odoo import fields, models


class InjuryType(models.Model):
    _name = 'fitzone.injury.type'
    _description = 'Injury Type'

    injury_id = fields.Many2one('fitzone.injury', required=True)
    member_id = fields.Many2one('res.partner', required=True)
    restriction = fields.Text()