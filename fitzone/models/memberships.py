from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    """Membership Package = product.template extended."""
    _inherit = 'product.template'

    package_type = fields.Char(string='Package Type')
    duration_months = fields.Integer(string='Duration (months)')
    total_sessions = fields.Integer(string='Total Sessions')


class Membership(models.Model):
    """Custom membership record (member + package + barcode)."""
    _name = 'fitzone.membership'
    _description = 'Membership'
    _order = 'start_date desc, id desc'

    member_id = fields.Many2one(
        'res.partner', string='Member', required=True, ondelete='restrict')
    package_id = fields.Many2one(
        'product.template', string='Package', required=True, ondelete='restrict')
    barcode = fields.Char(copy=False, index=True)
    start_date = fields.Date(default=fields.Date.context_today)
    end_date = fields.Date()
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('frozen', 'Frozen'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ], default='draft', required=True)
    freeze_ids = fields.One2many('fitzone.freeze', 'membership_id')

    _barcode_uniq = models.Constraint(
        'unique(barcode)', 'Barcode must be unique.')

    @api.depends('member_id.name', 'package_id.name')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = '%s - %s' % (
                rec.member_id.name or '', rec.package_id.name or '')

    @api.constrains('start_date', 'end_date')
    def _check_dates(self):
        for rec in self:
            if rec.start_date and rec.end_date and rec.end_date < rec.start_date:
                raise ValidationError('End date cannot be before start date.')


class Freeze(models.Model):
    _name = 'fitzone.freeze'
    _description = 'Membership Freeze'
    _order = 'start_date desc'

    ALLOWED_DAYS = (7, 14, 30)

    membership_id = fields.Many2one(
        'fitzone.membership', string='Membership', required=True, ondelete='cascade')
    start_date = fields.Date(required=True, default=fields.Date.context_today)
    end_date = fields.Date(required=True)
    days = fields.Integer(compute='_compute_days', store=True)

    @api.depends('start_date', 'end_date')
    def _compute_days(self):
        for rec in self:
            if rec.start_date and rec.end_date:
                rec.days = (rec.end_date - rec.start_date).days + 1
            else:
                rec.days = 0

    @api.constrains('start_date', 'end_date', 'days')
    def _check_freeze(self):
        for rec in self:
            if rec.end_date < rec.start_date:
                raise ValidationError('End date cannot be before start date.')
            if rec.days not in self.ALLOWED_DAYS:
                raise ValidationError(
                    'Freeze duration must be 7, 14 or 30 days.')