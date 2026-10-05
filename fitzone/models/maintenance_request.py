from odoo import fields, models


class MaintenanceRequest(models.Model):
    _inherit = 'maintenance.request'

    fault_id = fields.Many2one('fitzone.fault.report')