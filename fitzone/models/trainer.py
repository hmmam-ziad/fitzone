from odoo import fields, models


class Trainer(models.Model):
    _name = 'fitzone.trainer'
    _description = 'Trainer'
    _rec_name = 'employee_id'

    employee_id = fields.Many2one('hr.employee', required=True)
    specialty = fields.Char()