from odoo import api, fields, models
from odoo.exceptions import AccessError


class ProgressTracking(models.Model):
    _name = 'fitzone.progress.tracking'
    _description = 'Progress Tracking'

    member_id = fields.Many2one('res.partner', required=True, domain="[('membership_ids', '!=', False)]")
    trainer_id = fields.Many2one('fitzone.trainer', required=True,
        default=lambda self: self.env['fitzone.trainer'].search([('employee_id.user_id', '=', self.env.uid)], limit=1))
    record_date = fields.Date()
    weight = fields.Float()
    notes = fields.Text()

    def _validate_trainer_assignment(self):
        if self.env.su or self.env.user.has_group('fitzone.group_fitzone_manager'):
            return
        self.check_access('read')
        for record in self:
            if (record.trainer_id.employee_id.user_id != self.env.user
                    or not self.env['fitzone.pt.session'].search_count([
                        ('member_id', '=', record.member_id.id),
                        ('trainer_id.employee_id.user_id', '=', self.env.uid)])):
                raise AccessError('Progress is limited to your own trainees and trainer assignment.')

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._validate_trainer_assignment()
        return records

    def write(self, vals):
        self.check_access('write')
        self._validate_trainer_assignment()
        if (not self.env.su and not self.env.user.has_group('fitzone.group_fitzone_manager')
                and {'member_id', 'trainer_id'} & vals.keys()):
            raise AccessError('Progress assignments cannot be changed after creation.')
        result = super().write(vals)
        self._validate_trainer_assignment()
        return result
