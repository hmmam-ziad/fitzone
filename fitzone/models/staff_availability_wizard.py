from odoo import fields, models


class StaffAvailabilityWizard(models.TransientModel):
    _name = 'fitzone.staff.availability.wizard'
    _description = 'Find Available Staff'

    department_id = fields.Many2one(
        'hr.department',
        string='Department',
    )

    job_id = fields.Many2one(
        'hr.job',
        string='Job Position',
    )

    start_datetime = fields.Datetime(
        string='Start',
        required=True,
    )

    end_datetime = fields.Datetime(
        string='End',
        required=True,
    )

    employee_ids = fields.Many2many(
        'hr.employee',
        string='Available Staff',
        readonly=True,
    )

    def action_search(self):
        self.ensure_one()

        domain = []

        if self.department_id:
            domain.append(
                ('department_id', '=', self.department_id.id)
            )

        if self.job_id:
            domain.append(
                ('job_id', '=', self.job_id.id)
            )

        employees = self.env['hr.employee'].search(domain)

        available_employees = employees.filtered(
            lambda employee: employee.is_available_during(
                self.start_datetime,
                self.end_datetime,
            )
        )

        self.employee_ids = [(6, 0, available_employees.ids)]

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }
