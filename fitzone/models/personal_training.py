from odoo import api, fields, models
from odoo.exceptions import ValidationError


class PTSession(models.Model):
    _name = 'fitzone.pt.session'
    _description = 'Personal Training Session'
    _rec_name = 'member_id'

    member_id = fields.Many2one('res.partner', required=True)
    trainer_id = fields.Many2one('fitzone.trainer', required=True)
    membership_id = fields.Many2one('fitzone.membership', required=True)
    package_id = fields.Many2one('product.template', required=True)
    session_date = fields.Datetime()
    end_datetime = fields.Datetime()
    status = fields.Char()

    @api.constrains('trainer_id', 'session_date', 'end_datetime', 'status')
    def _check_trainer_availability(self):
        for record in self:
            if (
                not record.trainer_id
                or not record.session_date
                or not record.end_datetime
            ):
                continue

            if record.status == 'cancelled':
                continue

            if not record.trainer_id.employee_id.is_available_during(
                record.session_date,
                record.end_datetime,
                exclude_pt_id=record.id,
            ):
                raise ValidationError(
                    "The trainer is not available during the selected time."
                )