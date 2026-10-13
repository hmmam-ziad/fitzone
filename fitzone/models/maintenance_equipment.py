from odoo import api, fields, models
from odoo.exceptions import AccessError


class MaintenanceEquipment(models.Model):
    _inherit = 'maintenance.equipment'

    status = fields.Selection(
        [('in_service', 'In Service'), ('out_of_service', 'Out of Service')],
        default='in_service', required=True, tracking=True)
    vendor_id = fields.Many2one('res.partner', string='Default Vendor / Contract', groups='fitzone.group_fitzone_manager')
    # Preventive maintenance every 3 months by default (adjustable per device)
    period = fields.Integer(default=90)

    cost = fields.Float(groups='fitzone.group_fitzone_manager')

    partner_id = fields.Many2one(groups='fitzone.group_fitzone_manager')
    partner_ref = fields.Char(groups='fitzone.group_fitzone_manager')
    note = fields.Html(groups='fitzone.group_fitzone_manager')

    @api.model_create_multi
    def create(self, vals_list):
        self._check_equipment_manager()
        return super().create(vals_list)

    def unlink(self):
        self._check_equipment_manager()
        return super().unlink()

    def _check_equipment_manager(self):
        if not self.env.su and not self.env.user.has_group('fitzone.group_fitzone_manager'):
            raise AccessError('Only management can edit equipment.')

    def write(self, vals):
        if not self.env.su and not self.env.user.has_group('fitzone.group_fitzone_manager'):
            raise AccessError('Only management can edit equipment.')
        # Return to service goes through the private method, never client context.
        if vals.get('status') == 'in_service':
            raise AccessError("Only management can return equipment to service.")
        return super().write(vals)

    def action_return_to_service(self):
        if not self.env.user.has_group('fitzone.group_fitzone_manager'):
            raise AccessError("Only management can return equipment to service.")
        self.check_access('write')
        self._return_to_service()

    def _return_to_service(self):
        super(MaintenanceEquipment, self).write({'status': 'in_service'})
