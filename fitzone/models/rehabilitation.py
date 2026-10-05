from odoo import fields, models


class Rehabilitation(models.Model):
    _name = 'fitzone.rehabilitation'
    _description = 'Rehabilitation'

    member_id = fields.Many2one('res.partner', required=True)
    injury_id = fields.Many2one('fitzone.injury', required=True)
    physiotherapist_id = fields.Many2one('hr.employee', required=True)
    start_date = fields.Date()
    end_date = fields.Date()
    status = fields.Char()
    notes = fields.Text()