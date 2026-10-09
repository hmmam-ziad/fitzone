from odoo import api, fields, models


class Trainer(models.Model):
    _name = 'fitzone.trainer'
    _description = 'Trainer'
    _rec_name = 'employee_id'

    employee_id = fields.Many2one('hr.employee', required=True)
    specialty = fields.Char()

    def is_available_during(self, start_datetime, end_datetime):
        self.ensure_one()

        if not self.employee_id.resource_calendar_id:
            return True

        calendar = self.employee_id.resource_calendar_id

        start = fields.Datetime.to_datetime(start_datetime)
        end = fields.Datetime.to_datetime(end_datetime)

        if not start or not end or end <= start:
            return False

        start_hours = calendar.get_work_hours_count(start, end)

        total_hours = (end - start).total_seconds() / 3600

        return abs(start_hours - total_hours) < 0.0001