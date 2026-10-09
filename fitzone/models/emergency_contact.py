import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class EmergencyContact(models.Model):
    _name = 'fitzone.emergency.contact'
    _description = 'Emergency Contact'

    member_id = fields.Many2one('res.partner', required=True)
    name = fields.Char()
    phone = fields.Char()
    relationship = fields.Char()

    @api.constrains('phone')
    def _check_phone(self):
        for contact in self:
            if contact.phone and not re.fullmatch(r'[0-9]{10}', contact.phone):
                raise ValidationError(
                    "Emergency contact phone number must contain exactly 10 digits."
                )
