from odoo import api, fields, models
from odoo.exceptions import ValidationError


class CommissionRule(models.Model):
    _name = 'fitzone.commission.rule'
    _description = 'Commission Rule'

    name = fields.Char()
    trainer_id = fields.Many2one('fitzone.trainer', index=True)
    session_type = fields.Char(default='personal_training', required=True)
    rate = fields.Float(default=50.0, required=True)
    active = fields.Boolean(default=True)
    effective_from = fields.Date()
    effective_to = fields.Date()

    @api.constrains('rate', 'effective_from', 'effective_to')
    def _check_rule_values(self):
        for rule in self:
            if not 0 <= rule.rate <= 100:
                raise ValidationError("Commission rate must be between 0 and 100 percent.")
            if (rule.effective_from and rule.effective_to
                    and rule.effective_to < rule.effective_from):
                raise ValidationError("The commission end date cannot precede its start date.")
