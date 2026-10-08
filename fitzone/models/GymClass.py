from odoo import api, fields, models
from odoo.exceptions import ValidationError


class GymClass(models.Model):
    _name = 'fitzone.gym.class'
    _description = 'Group Class'

    trainer_id = fields.Many2one('fitzone.trainer', required=True)
    room_id = fields.Many2one('fitzone.room', required=True)
    name = fields.Char()
    capacity = fields.Integer()
    start_datetime = fields.Datetime()
    end_datetime = fields.Datetime()

    @api.constrains('trainer_id', 'start_datetime', 'end_datetime')
    def _check_trainer_working_hours(self):
        for record in self:
            if not record.trainer_id or not record.start_datetime or not record.end_datetime:
                continue

            if not record.trainer_id.is_available_during(
                record.start_datetime,
                record.end_datetime,
            ):
                raise ValidationError(
                    "The trainer is not available during the selected working hours."
                )