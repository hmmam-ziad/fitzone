from odoo import fields, models


class Injury(models.Model):
    _name = 'fitzone.injury'
    _description = 'Injury'
    _rec_name = 'member_id'

    member_id = fields.Many2one(
        'res.partner',
        required=True,
    )

    reported_by = fields.Many2one(
        'hr.employee',
        required=True,
    )

    physiotherapist_id = fields.Many2one(
        'hr.employee',
    )

    injury_date = fields.Date()

    cause = fields.Char()

    description = fields.Text()

    type_ids = fields.One2many(
        'fitzone.injury.type',
        'injury_id',
        string='Types',
    )