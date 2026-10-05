from odoo import fields, models


class MaintenanceEquipment(models.Model):
    _inherit = 'maintenance.equipment'

    status = fields.Selection([
        ('available', 'Available'),
        ('out_of_service', 'Out of Service'),
    ], default='available')


class FaultReport(models.Model):
    _name = 'fitzone.fault.report'
    _description = 'Equipment Fault Report'
    _order = 'report_date desc'

    equipment_id = fields.Many2one(
        'maintenance.equipment', string='Equipment', required=True)
    reported_by = fields.Many2one(
        'hr.employee', string='Reported By', required=True)
    report_date = fields.Datetime(default=fields.Datetime.now)
    description = fields.Text()
    status = fields.Selection([
        ('reported', 'Reported'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('resolved', 'Resolved'),
    ], default='reported', required=True)


class MaintenanceRequest(models.Model):
    _inherit = 'maintenance.request'

    fault_id = fields.Many2one('fitzone.fault.report', string='Fault Report')

    _fault_uniq = models.Constraint(
        'unique(fault_id)', 'This fault report already has a maintenance request.')