from odoo import fields, models


class FaultReport(models.Model):
    _name = 'fitzone.fault.report'
    _description = 'Fault Report'
    _rec_name = 'equipment_id'

    equipment_id = fields.Many2one('maintenance.equipment', required=True)
    reported_by = fields.Many2one('hr.employee', required=True)
    report_date = fields.Datetime()
    description = fields.Text()
    status = fields.Char()