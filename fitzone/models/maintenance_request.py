from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError


class MaintenanceRequest(models.Model):
    _inherit = 'maintenance.request'

    fault_id = fields.Many2one(
        'fitzone.fault.report',
        readonly=True,
        copy=False,
        groups='fitzone.group_fitzone_manager',
    )

    vendor_id = fields.Many2one(
        'res.partner',
        string='External Vendor',
        groups='fitzone.group_fitzone_manager',
    )

    estimated_cost = fields.Float(groups='fitzone.group_fitzone_manager')
    description = fields.Html(groups='fitzone.group_fitzone_manager')
    preventive_approved = fields.Boolean(groups='fitzone.group_fitzone_manager')
    approved = fields.Boolean(compute='_compute_approved', store=True)

    @api.depends('fault_id.status', 'preventive_approved', 'maintenance_type')
    def _compute_approved(self):
        for rec in self:
            rec.approved = bool(rec.fault_id and rec.fault_id.status == 'approved') or (rec.maintenance_type == 'preventive' and rec.preventive_approved)

    def _check_management(self):
        if not self.env.su and not self.env.user.has_group('fitzone.group_fitzone_manager'):
            raise AccessError('Only management can create or delete tickets.')

    @api.model_create_multi
    def create(self, vals_list):
        self._check_management()
        if any('approved' in vals for vals in vals_list):
            raise AccessError('Approval comes from the fault report.')
        return super().create(vals_list)

    def unlink(self):
        self._check_management()
        return super().unlink()

    def write(self, vals):
        if 'approved' in vals:
            raise AccessError('Approval comes from the fault report.')
        if not self.env.su and not self.env.user.has_group('fitzone.group_fitzone_manager'):
            self.check_access('write')
            if not self.env.user.has_group('fitzone.group_fitzone_technician') or any(not r.approved for r in self):
                raise AccessError('Only approved tickets can be progressed.')
            if set(vals) - {'stage_id', 'kanban_state', 'close_date'}:
                raise AccessError('Maintenance may change progress only.')
            if vals.get('stage_id') == self._default_stage().id:
                raise AccessError('Maintenance cannot reset tickets to new.')
        return super().write(vals)

    _sql_constraints = [
        (
            'fault_unique',
            'unique(fault_id)',
            'A fault report can only have one maintenance ticket.',
        ),
    ]

    @api.model
    def _cron_create_preventive_requests(self):
        """Create preventive maintenance requests based on each equipment period."""
        today = fields.Date.context_today(self)
        Equipment = self.env['maintenance.equipment']

        equipments = Equipment.search([
            ('period', '>', 0),
        ])

        for equipment in equipments:
            last_preventive = self.search(
                [
                    ('equipment_id', '=', equipment.id),
                    ('maintenance_type', '=', 'preventive'),
                ],
                order='schedule_date desc',
                limit=1,
            )

            if last_preventive:
                last_date = last_preventive.schedule_date.date()
            else:
                last_date = equipment.create_date.date()

            next_date = last_date + timedelta(days=equipment.period)

            if next_date <= today:
                self.create({
                    'name': 'Preventive Maintenance: %s' % equipment.name,
                    'equipment_id': equipment.id,
                    'maintenance_type': 'preventive',
                    'schedule_date': fields.Datetime.to_datetime(next_date),
                    'description': 'Scheduled preventive maintenance.',
                    'preventive_approved': True,
                })

    @api.model
    def _cron_preventive_reminders(self):
        """Remind managers and the technician 7 days and 1 day before a
        scheduled preventive ticket."""
        today = fields.Date.context_today(self)
        managers = self.env.ref('fitzone.group_fitzone_manager').user_ids

        tickets = self.search([
            ('maintenance_type', '=', 'preventive'),
            ('stage_id.done', '=', False),
            ('schedule_date', '!=', False),
        ])

        for ticket in tickets:
            days_left = (ticket.schedule_date.date() - today).days

            if days_left in (7, 1):
                partners = (managers | ticket.user_id).partner_id

                ticket.message_post(
                    body="Preventive maintenance for %s is due in %s day(s)."
                    % (ticket.equipment_id.name, days_left),
                    partner_ids=partners.ids,
                    message_type='comment',
                    subtype_xmlid='mail.mt_comment',
                )