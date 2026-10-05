from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    """Member = res.partner extended (name, phone, email are standard)."""
    _inherit = 'res.partner'

    membership_no = fields.Char(string='Membership No.', copy=False, index=True)
    birth_date = fields.Date(string='Birth Date')
    emergency_contact_ids = fields.One2many(
        'fitzone.emergency.contact', 'member_id', string='Emergency Contacts')
    health_profile_ids = fields.One2many(
        'fitzone.health.profile', 'member_id', string='Health Profile')

    _membership_no_uniq = models.Constraint(
        'unique(membership_no)', 'Membership number must be unique.')


class EmergencyContact(models.Model):
    _name = 'fitzone.emergency.contact'
    _description = 'Emergency Contact'

    member_id = fields.Many2one(
        'res.partner', string='Member', required=True, ondelete='cascade')
    name = fields.Char(required=True)
    phone = fields.Char(required=True)
    relationship = fields.Char()


class HealthProfile(models.Model):
    _name = 'fitzone.health.profile'
    _description = 'Health Profile'

    member_id = fields.Many2one(
        'res.partner', string='Member', required=True, ondelete='cascade')
    age = fields.Integer()
    weight = fields.Float(help='kg')
    height = fields.Float(help='cm')

    _member_uniq = models.Constraint(
        'unique(member_id)', 'A member can only have one health profile.')

    @api.constrains('age', 'weight', 'height')
    def _check_values(self):
        for rec in self:
            if rec.age < 0 or rec.weight < 0 or rec.height < 0:
                raise ValidationError('Age, weight and height cannot be negative.')


class ProgressTracking(models.Model):
    _name = 'fitzone.progress.tracking'
    _description = 'Progress Tracking'
    _order = 'record_date desc'

    member_id = fields.Many2one(
        'res.partner', string='Member', required=True, ondelete='cascade')
    trainer_id = fields.Many2one(
        'fitzone.trainer', string='Trainer', required=True)
    record_date = fields.Date(default=fields.Date.context_today)
    weight = fields.Float(help='kg')
    notes = fields.Text()