from odoo import fields, models


class InjuryType(models.Model):
    _name = 'fitzone.injury.type'
    _inherit = 'fitzone.medical.audit.mixin'
    _rec_name = 'id'
    _description = 'Injury Type'

    injury_id = fields.Many2one('fitzone.injury', required=True, groups='fitzone.group_fitzone_physiotherapist,fitzone.group_fitzone_manager')
    member_id = fields.Many2one('res.partner', required=True)
    restriction = fields.Text()
    prohibited_exercises = fields.Text(string='Forbidden movements')
