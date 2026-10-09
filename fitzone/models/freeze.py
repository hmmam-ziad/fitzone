
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class Freeze(models.Model):
    _name = 'fitzone.freeze'
    _description = 'Freeze'

    membership_id = fields.Many2one(
        'fitzone.membership',
        required=True,
    )

    start_date = fields.Date()
    end_date = fields.Date()

    days = fields.Integer(
        compute='_compute_days',
        store=True,
        readonly=True,
    )

    @api.depends('start_date', 'end_date')
    def _compute_days(self):
        for rec in self:
            if rec.start_date and rec.end_date:
                rec.days = (rec.end_date - rec.start_date).days
            else:
                rec.days = 0

    @api.constrains('start_date', 'end_date')
    def _check_freeze_dates(self):
        for rec in self:
            if (
                rec.start_date
                and rec.end_date
                and rec.end_date < rec.start_date
            ):
                raise ValidationError(
                    "Freeze end date cannot be earlier than start date."
                )