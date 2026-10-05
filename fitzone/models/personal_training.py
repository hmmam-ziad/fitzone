from odoo import api, fields, models
from odoo.exceptions import ValidationError


class PTSession(models.Model):
    _name = 'fitzone.pt.session'
    _description = 'Personal Training Session'
    _order = 'session_date desc'

    member_id = fields.Many2one(
        'res.partner', string='Member', required=True, ondelete='restrict')
    trainer_id = fields.Many2one('fitzone.trainer', required=True)
    membership_id = fields.Many2one(
        'fitzone.membership', string='Membership', required=True)
    package_id = fields.Many2one(
        'product.template', string='Package', required=True)
    session_date = fields.Datetime(required=True)
    end_datetime = fields.Datetime(required=True)
    status = fields.Selection([
        ('scheduled', 'Scheduled'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], default='scheduled', required=True)

    @api.constrains('session_date', 'end_datetime', 'trainer_id')
    def _check_session(self):
        for rec in self:
            if rec.end_datetime <= rec.session_date:
                raise ValidationError('End time must be after start time.')
            overlap = self.search([
                ('id', '!=', rec.id),
                ('trainer_id', '=', rec.trainer_id.id),
                ('status', '!=', 'cancelled'),
                ('session_date', '<', rec.end_datetime),
                ('end_datetime', '>', rec.session_date),
            ], limit=1)
            if overlap:
                raise ValidationError(
                    'Trainer %s is already booked at this time.'
                    % rec.trainer_id.name)


class CommissionRule(models.Model):
    _name = 'fitzone.commission.rule'
    _description = 'Commission Rule'
    _order = 'effective_from desc'

    name = fields.Char(required=True)
    rate = fields.Float(help='Percentage', required=True)
    active = fields.Boolean(default=True)
    effective_from = fields.Date()
    effective_to = fields.Date()

    @api.constrains('rate', 'effective_from', 'effective_to')
    def _check_rule(self):
        for rec in self:
            if not 0 <= rec.rate <= 100:
                raise ValidationError('Rate must be between 0 and 100.')
            if (rec.effective_from and rec.effective_to
                    and rec.effective_to < rec.effective_from):
                raise ValidationError('Effective-to cannot be before effective-from.')


class TrainerCommission(models.Model):
    _name = 'fitzone.trainer.commission'
    _description = 'Trainer Commission'

    trainer_id = fields.Many2one('fitzone.trainer', required=True)
    pt_session_id = fields.Many2one(
        'fitzone.pt.session', string='PT Session', required=True, ondelete='cascade')
    commission_rule_id = fields.Many2one(
        'fitzone.commission.rule', string='Commission Rule', required=True)
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id)
    amount = fields.Monetary(currency_field='currency_id')