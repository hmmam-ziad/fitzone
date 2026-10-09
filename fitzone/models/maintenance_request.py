from datetime import timedelta

from odoo import api, fields, models


class MaintenanceRequest(models.Model):
    _inherit = 'maintenance.request'

    fault_id = fields.Many2one(
        'fitzone.fault.report',
        readonly=True,
        copy=False,
    )

    vendor_id = fields.Many2one(
        'res.partner',
        string='External Vendor',
    )

    estimated_cost = fields.Float()

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
                })

    @api.model
    def _cron_preventive_reminders(self):
        """Remind managers and the technician 7 days and 1 day before a
        scheduled preventive ticket."""
        today = fields.Date.context_today(self)
        managers = self.env.ref('fitzone.group_fitzone_manager').users

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