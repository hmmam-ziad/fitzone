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
        'hr.employee',
        default=lambda self: self.env.user.employee_id)
    member_id = fields.Many2one('res.partner', string='Reported on behalf of member', groups='fitzone.group_fitzone_manager,fitzone.group_fitzone_reception')
    report_date = fields.Datetime(default=fields.Datetime.now, readonly=True)
    description = fields.Text(required=True)
    status = fields.Selection(
        [('reported', 'Reported'), ('approved', 'Approved'), ('rejected', 'Rejected')],
        default='reported', required=True)

    # Management review
    technician_id = fields.Many2one(
        'res.users', string='Internal Technician', domain=[('share', '=', False)])
    vendor_id = fields.Many2one('res.partner', string='External Vendor', groups='fitzone.group_fitzone_manager')
    estimated_cost = fields.Float(groups='fitzone.group_fitzone_manager')
    expected_date = fields.Date()
    reject_reason = fields.Char()
    request_id = fields.Many2one(
        'maintenance.request', string='Maintenance Ticket', readonly=True, groups='fitzone.group_fitzone_manager')

    @api.model_create_multi
    def create(self, vals_list):
        # New web forms send the default status explicitly; review is never a create.
        if any(vals.get('status', 'reported') != 'reported' or 'request_id' in vals
               for vals in vals_list):
            raise AccessError('Reports must be submitted before review.')
        if not self.env.su and not self.env.user.has_group('fitzone.group_fitzone_manager'):
            allowed = {'equipment_id', 'description', 'reported_by', 'member_id',
                       'status', 'report_date'}
            if any(set(vals) - allowed for vals in vals_list):
                raise AccessError("Employees can only submit a new fault report.")
        records = super().create(vals_list)
        if any(rec.status != 'reported' for rec in records):
            raise AccessError('Reports must be submitted before review.')
        records._mark_equipment_out_of_service()
        return records

    def _mark_equipment_out_of_service(self):
        # Elevation is limited to the equipment status after a valid report create.
        self.mapped('equipment_id').check_access('read')
        self.mapped('equipment_id').sudo().write({'status': 'out_of_service'})

    def write(self, vals):
        if not self.env.user.has_group('fitzone.group_fitzone_manager'):
            raise AccessError('Use the management review actions.')
        if 'status' in vals or 'request_id' in vals:
            raise AccessError("Use the management review actions.")
        return super().write(vals)

    def _create_approved_ticket(self):
        self.ensure_one()
        # Management has validated approval; elevate only the assigned ticket create.
        return self.env['maintenance.request'].sudo().create({
            'name': 'Fault: %s' % self.equipment_id.name, 'equipment_id': self.equipment_id.id,
            'maintenance_type': 'corrective', 'user_id': self.technician_id.id,
            'vendor_id': self.vendor_id.id, 'estimated_cost': self.estimated_cost,
            'schedule_date': self.expected_date and fields.Datetime.to_datetime(self.expected_date),
            'fault_id': self.id, 'description': self.description,
        }).id

    def _check_manager(self):
        if not self.env.user.has_group('fitzone.group_fitzone_manager'):
            raise AccessError("Only management can do this.")

    def action_approve(self):
        self._check_manager()
        for rec in self:
            if rec.status != 'reported':
                raise ValidationError(_("Only new reports can be approved."))
            if not (rec.technician_id or rec.vendor_id):
                raise ValidationError(_("Assign a technician or vendor first."))
            super(FaultReport, rec).write({'status': 'approved'})
            request_id = rec._create_approved_ticket()
            super(FaultReport, rec).write({'request_id': request_id})

    def action_reject(self):
        self._check_manager()
        for rec in self:
            if rec.status != 'reported':
                raise ValidationError(_("Only new reports can be rejected."))
            if not rec.reject_reason:
                raise ValidationError(_("Please enter a rejection reason."))
            super(FaultReport, rec).write({'status': 'rejected'})
