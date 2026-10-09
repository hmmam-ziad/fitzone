from odoo import fields, models
from odoo.exceptions import AccessError


class MaintenanceEquipment(models.Model):
    _inherit = 'maintenance.equipment'

    status = fields.Selection(
        [('in_service', 'In Service'), ('out_of_service', 'Out of Service')],
        default='in_service', required=True, tracking=True)
    vendor_id = fields.Many2one('res.partner', string='Default Vendor / Contract')
    # Preventive maintenance every 3 months by default (adjustable per device)
    period = fields.Integer(default=90)

    def write(self, vals):
        # Only the management button (context flag) can return a device to service
        if (vals.get('status') == 'in_service'
                and not self.env.context.get('fitzone_return_to_service')):
            raise AccessError("Only management can return equipment to service.")
        return super().write(vals)

    def action_return_to_service(self):
        if not self.env.user.has_group('fitzone.group_fitzone_manager'):
            raise AccessError("Only management can return equipment to service.")
        self.with_context(fitzone_return_to_service=True).write(
            {'status': 'in_service'})