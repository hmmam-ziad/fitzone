from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

from .smart_button_helpers import (
    OPERATIONS, FINANCE_READERS, check_navigation, check_trainer_owner,
    has_roles, related_action,
)


class Trainer(models.Model):
    _name = 'fitzone.trainer'
    _description = 'Trainer'
    _rec_name = 'employee_id'

    ACTIVITY_LABELS = {
    'class': 'Group Class',
    'pt': 'Personal Training',
    'pool': 'Pool Session',
}

    employee_id = fields.Many2one(
        'hr.employee',
        required=True,
    )
    specialty = fields.Char()

    trainee_count = fields.Integer(
        compute='_compute_trainee_count', compute_sudo=False,
        groups='fitzone.group_fitzone_manager,fitzone.group_fitzone_reception,fitzone.group_fitzone_trainer',
    )
    can_view_assignments = fields.Boolean(compute='_compute_can_view_assignments', compute_sudo=False)

    @api.depends('employee_id', 'employee_id.user_id')
    @api.depends_context('uid')
    def _compute_can_view_assignments(self):
        for trainer in self:
            trainer.can_view_assignments = has_roles(self.env, FINANCE_READERS) or (
                has_roles(self.env, ('trainer',)) and trainer.employee_id.user_id == self.env.user
            )

    def _trainee_domain(self):
        self.ensure_one()
        return ['|',
                ('pt_session_ids', 'any', [('trainer_id', '=', self.id)]),
                ('class_booking_ids', 'any', [
                    ('class_id.trainer_id', '=', self.id), ('status', '!=', 'cancelled'),
                ])]

    @api.depends_context('uid', 'allowed_company_ids')
    def _compute_trainee_count(self):
        for trainer in self:
            trainer.trainee_count = 0
            if trainer.id and isinstance(trainer.id, int) and trainer.can_view_assignments:
                trainer.check_access('read')
                trainer.trainee_count = self.env['res.partner'].with_context(active_test=False).search_count(
                    trainer._trainee_domain())

    def action_view_schedule(self):
        check_navigation(self, OPERATIONS, 'fitzone.trainer.schedule')
        check_trainer_owner(self, self)
        return related_action(self, 'fitzone.action_fitzone_trainer_schedule',
                              [('trainer_id', '=', self.id)])

    def action_view_trainees(self):
        check_navigation(self, OPERATIONS, 'res.partner')
        check_trainer_owner(self, self)
        return related_action(self, 'fitzone.action_fitzone_members', self._trainee_domain(),
                              {'active_test': False})

    def is_available_during(self, start_datetime, end_datetime):
        """Check whether the trainer is within working hours."""
        self.ensure_one()

        if not self.employee_id.resource_calendar_id:
            return True

        calendar = self.employee_id.resource_calendar_id
        start = fields.Datetime.to_datetime(start_datetime)
        end = fields.Datetime.to_datetime(end_datetime)

        if not start or not end or end <= start:
            return False

        start_hours = calendar.get_work_hours_count(start, end)
        total_hours = (end - start).total_seconds() / 3600

        return abs(start_hours - total_hours) < 0.0001

    def _find_conflicts(self, start, end, exclude=None):
        """Find existing activities that overlap the requested time."""
        self.ensure_one()

        start = fields.Datetime.to_datetime(start)
        end = fields.Datetime.to_datetime(end)

        if not start or not end or end <= start:
            return self.env['fitzone.trainer.schedule']

        self.env.flush_all()

        domain = [
            ('trainer_id', '=', self.id),
            ('start_datetime', '<', end),
            ('end_datetime', '>', start),
        ]

        # Exclude the current record when editing an existing activity.
        if exclude and exclude[1]:
            domain += [
                '!',
                '&',
                ('res_model', '=', exclude[0]),
                ('res_id', '=', exclude[1]),
            ]

        return self.env['fitzone.trainer.schedule'].sudo().search(
            domain,
            order='start_datetime',
        )

    def _check_available(self, start, end, exclude=None):
        """Raise an error when the trainer already has an activity."""
        start = fields.Datetime.to_datetime(start)
        end = fields.Datetime.to_datetime(end)

        if not start or not end:
            return

        if end <= start:
            raise ValidationError(
                _("The activity end time must be after its start time.")
            )

        for trainer in self:
            conflicts = trainer._find_conflicts(
                start,
                end,
                exclude=exclude,
            )

            if not conflicts:
                continue

            lines = []

            for item in conflicts:
                begin = fields.Datetime.context_timestamp(
                    trainer, item.start_datetime
                ).strftime('%d/%m %H:%M')

                finish = fields.Datetime.context_timestamp(
                    trainer, item.end_datetime
                ).strftime('%H:%M')

                activity_label = trainer.ACTIVITY_LABELS.get(
                    item.activity_type,
                    item.activity_type,
                )

                lines.append(
                    '- %s: %s (%s - %s)'
                    % (activity_label, item.name, begin, finish)
                )

            raise ValidationError(
                _(
                    "Schedule conflict: %(trainer)s is already booked "
                    "at this time:\n%(lines)s\n"
                    "Please choose another time or another trainer.",
                    trainer=trainer.employee_id.name
                    or trainer.display_name,
                    lines='\n'.join(lines),
                )
            )
