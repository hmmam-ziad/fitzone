from odoo import api, fields, models
from pytz import utc


class FitZoneEmployee(models.Model):
    _inherit = 'hr.employee'

    fitzone_employee_no = fields.Char(
        string='FitZone Employee No.',
        groups='hr.group_hr_user',
        readonly=True,
        copy=False,
        index=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('fitzone_employee_no'):
                vals['fitzone_employee_no'] = self.env['ir.sequence'].next_by_code(
                    'fitzone.employee'
                )
        return super().create(vals_list)

    def write(self, vals):
        vals.pop('fitzone_employee_no', None)
        return super().write(vals)

    def is_available_during(
        self,
        start_datetime,
        end_datetime,
        exclude_pt_id=False,
    ):
        self.ensure_one()

        if not self.resource_calendar_id or not self.resource_id:
            return False

        start = fields.Datetime.to_datetime(start_datetime)
        end = fields.Datetime.to_datetime(end_datetime)

        if not start or not end or end <= start:
            return False

        intervals = self.resource_calendar_id._work_intervals_batch(
            utc.localize(start),
            utc.localize(end),
            resources=self.resource_id,
        )[self.resource_id.id]

        worked_seconds = sum(
            (interval[1] - interval[0]).total_seconds()
            for interval in intervals
        )

        requested_seconds = (end - start).total_seconds()

        if worked_seconds < requested_seconds:
            return False

        trainer = self.env['fitzone.trainer'].search(
            [('employee_id', '=', self.id)],
            limit=1,
        )

        leave_busy = self.env['hr.leave'].search_count([
            ('employee_id', '=', self.id),
            ('state', '=', 'validate'),
            ('date_from', '<', end),
            ('date_to', '>', start),
        ])

        if leave_busy:
            return False

        if trainer:
            class_busy = self.env['fitzone.gym.class'].search_count([
                ('trainer_id', '=', trainer.id),
                ('start_datetime', '<', end),
                ('end_datetime', '>', start),
            ])

            pt_domain = [
                ('trainer_id', '=', trainer.id),
                ('status', '!=', 'cancelled'),
                ('session_date', '<', end),
                ('end_datetime', '>', start),
            ]

            if exclude_pt_id:
                pt_domain.append(('id', '!=', exclude_pt_id))

            pt_busy = self.env['fitzone.pt.session'].search_count(
                pt_domain
            )

            if class_busy or pt_busy:
                return False

        return True