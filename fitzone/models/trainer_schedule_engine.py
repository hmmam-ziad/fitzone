from odoo import _, fields, models
from odoo.exceptions import ValidationError

ACTIVITY_LABELS = {
    'class': 'Group Class',
    'pt': 'Personal Training',
    'pool': 'Pool Private Session',
    
}


class Trainer(models.Model):
    """Double-booking engine: ONE place that knows every activity of a trainer."""
    _inherit = 'fitzone.trainer'

    def _find_conflicts(self, start, end, exclude=None):
        """Activities of this trainer overlapping [start, end).

        exclude = (model_name, record_id) of the record being saved, so it
        doesn't conflict with itself.
        """
        self.ensure_one()
        self.env.flush_all()   # make sure pending changes are in the database
        domain = [
            ('trainer_id', '=', self.id),
            ('start_datetime', '<', end),
            ('end_datetime', '>', start),
        ]
        if exclude and exclude[1]:
            domain += ['!', '&',
                       ('res_model', '=', exclude[0]),
                       ('res_id', '=', exclude[1])]
        # sudo: conflicts must be detected even if the current user's record
        # rules hide other people's rows
        return self.env['fitzone.trainer.schedule'].sudo().search(
            domain, order='start_datetime')

    def _check_available(self, start, end, exclude=None):
        """Raise a clear alert if the trainer is already busy in [start, end)."""
        if not (start and end):
            return
        for trainer in self:
            conflicts = trainer._find_conflicts(start, end, exclude)
            if not conflicts:
                continue
            lines = []
            for item in conflicts:
                begin = fields.Datetime.context_timestamp(
                    self, item.start_datetime).strftime('%d/%m %H:%M')
                finish = fields.Datetime.context_timestamp(
                    self, item.end_datetime).strftime('%H:%M')
                lines.append('- %s: %s (%s - %s)' % (
                    ACTIVITY_LABELS.get(item.activity_type, item.activity_type),
                    item.name, begin, finish))
            raise ValidationError(_(
                "Schedule conflict: %(trainer)s is already booked at this time:\n"
                "%(lines)s\nPlease choose another time or another trainer.",
                trainer=trainer.employee_id.name or trainer.display_name,
                lines='\n'.join(lines)))