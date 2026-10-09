from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class TrainerCommissionWizard(models.TransientModel):
    _name = 'fitzone.trainer.commission.wizard'
    _description = 'Trainer Commission Statement'

    trainer_id = fields.Many2one(
        'fitzone.trainer', required=True,
        default=lambda self: self.env['fitzone.trainer'].search([
            ('employee_id.user_id', '=', self.env.uid),
        ], limit=1),
    )
    date_from = fields.Date(
        required=True, default=lambda self: fields.Date.context_today(self).replace(day=1),
    )
    date_to = fields.Date(required=True, default=fields.Date.context_today)

    @api.constrains('date_from', 'date_to')
    def _check_period(self):
        for wizard in self:
            if wizard.date_from > wizard.date_to:
                raise ValidationError(_('The start date must not follow the end date.'))

    def _get_sessions(self):
        self.ensure_one()
        self._check_period()
        # Date inputs describe local days; session datetimes are stored in UTC.
        timezone = pytz.timezone(self.env.context.get('tz') or self.env.user.tz or 'UTC')
        start = timezone.localize(datetime.combine(self.date_from, time.min))
        end = timezone.localize(datetime.combine(self.date_to + timedelta(days=1), time.min))
        return self.env['fitzone.pt.session'].search([
            ('trainer_id', '=', self.trainer_id.id),
            ('state', '=', 'completed'),
            ('session_date', '>=', fields.Datetime.to_string(start.astimezone(pytz.UTC))),
            ('session_date', '<', fields.Datetime.to_string(end.astimezone(pytz.UTC))),
        ], order='session_date, id')

    def action_print_report(self):
        self.ensure_one()
        self._check_period()
        return self.env.ref('fitzone.action_report_trainer_commission_statement').report_action(self)
