from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


class FaultReport(models.Model):
    _name = 'fitzone.fault.report'
    _description = 'Equipment Fault Report'
    _inherit = ['mail.thread']
    _rec_name = 'equipment_id'
    _order = 'id desc'

    equipment_id = fields.Many2one('maintenance.equipment', required=True)
    serial_no = fields.Char(related='equipment_id.serial_no', readonly=True)
    reported_by = fields.Many2one(
        'hr.employee', required=True,
        default=lambda self: self.env.user.employee_id)
    member_id = fields.Many2one('res.partner', string='Reported on behalf of member')
    report_date = fields.Datetime(default=fields.Datetime.now, readonly=True)
    description = fields.Text(required=True)
    status = fields.Selection(
        [('reported', 'Reported'), ('approved', 'Approved'), ('rejected', 'Rejected')],
        default='reported', required=True, tracking=True)

    # Management review
    technician_id = fields.Many2one(
        'res.users', string='Internal Technician', domain=[('share', '=', False)])
    vendor_id = fields.Many2one('res.partner', string='External Vendor')
    estimated_cost = fields.Float()
    expected_date = fields.Date()
    reject_reason = fields.Char()
    request_id = fields.Many2one(
        'maintenance.request', string='Maintenance Ticket', readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        managers = self.env.ref('fitzone.group_fitzone_manager').user_ids
        for rec in records:
            rec.equipment_id.sudo().write({'status': 'out_of_service'})
            rec.message_post(
                body="New fault report for %s (%s)."
                     % (rec.equipment_id.name, rec.serial_no or '-'),
                partner_ids=managers.partner_id.ids,
                message_type='comment',
                subtype_xmlid='mail.mt_comment')
        return records

    def _check_manager(self):
        if not self.env.user.has_group('fitzone.group_fitzone_manager'):
            raise AccessError("Only management can do this.")

    def action_approve(self):
        self._check_manager()
        Request = self.env['maintenance.request']
        for rec in self:
            if rec.status != 'reported':
                raise ValidationError("Only new reports can be approved.")
            if not (rec.technician_id or rec.vendor_id):
                raise ValidationError(
                    "Assign an internal technician or an external vendor first.")
            request = Request.create({
                'name': 'Fault: %s' % rec.equipment_id.name,
                'equipment_id': rec.equipment_id.id,
                'maintenance_type': 'corrective',
                'user_id': rec.technician_id.id,
                'vendor_id': rec.vendor_id.id,
                'estimated_cost': rec.estimated_cost,
                'schedule_date': rec.expected_date and fields.Datetime.to_datetime(rec.expected_date),
                'description': rec.description,
                'fault_id': rec.id,
            })
            rec.write({'status': 'approved', 'request_id': request.id})

    def action_reject(self):
        self._check_manager()
        for rec in self:
            if rec.status != 'reported':
                raise ValidationError("Only new reports can be rejected.")
            if not rec.reject_reason:
                raise ValidationError("Please enter a rejection reason.")
            rec.status = 'rejected'