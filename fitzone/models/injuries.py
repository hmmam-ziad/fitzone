from odoo import api, fields, models
from odoo.exceptions import ValidationError


class Injury(models.Model):
    _name = 'fitzone.injury'
    _description = 'Injury'
    _order = 'injury_date desc'

    member_id = fields.Many2one(
        'res.partner', string='Member', required=True, ondelete='restrict')
    reported_by = fields.Many2one(
        'hr.employee', string='Reported By', required=True)
    physiotherapist_id = fields.Many2one(
        'hr.employee', string='Physiotherapist',
        help='Empty until auto-assigned')
    injury_date = fields.Date(default=fields.Date.context_today)
    cause = fields.Char()
    description = fields.Text()
    type_ids = fields.One2many('fitzone.injury.type', 'injury_id')


class InjuryType(models.Model):
    _name = 'fitzone.injury.type'
    _description = 'Injury Classification / Restriction'

    injury_id = fields.Many2one(
        'fitzone.injury', string='Injury', required=True, ondelete='cascade')
    member_id = fields.Many2one(
        'res.partner', string='Member', required=True)
    restriction = fields.Text(help='Restrictions and forbidden movements')


class Rehabilitation(models.Model):
    _name = 'fitzone.rehabilitation'
    _description = 'Rehabilitation'

    member_id = fields.Many2one(
        'res.partner', string='Member', required=True, ondelete='restrict')
    injury_id = fields.Many2one(
        'fitzone.injury', string='Injury', required=True, ondelete='cascade')
    physiotherapist_id = fields.Many2one(
        'hr.employee', string='Physiotherapist', required=True)
    start_date = fields.Date()
    end_date = fields.Date()
    status = fields.Selection([
        ('ongoing', 'Ongoing'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], default='ongoing')
    notes = fields.Text()

    @api.constrains('start_date', 'end_date')
    def _check_dates(self):
        for rec in self:
            if rec.start_date and rec.end_date and rec.end_date < rec.start_date:
                raise ValidationError('End date cannot be before start date.')