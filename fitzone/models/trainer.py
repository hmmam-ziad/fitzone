from odoo import fields, models


class Trainer(models.Model):
    """Trainer = custom record linked 1:1 to an hr.employee."""
    _name = 'fitzone.trainer'
    _description = 'Trainer'
    _rec_name = 'name'

    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True, ondelete='cascade')
    name = fields.Char(related='employee_id.name', store=True)
    specialty = fields.Char()

    _employee_uniq = models.Constraint(
        'unique(employee_id)', 'This employee is already registered as a trainer.')