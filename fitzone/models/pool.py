from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


def _hhmm(value):
    """9.5 -> '09:30'"""
    hours, minutes = divmod(round(value * 60), 60)
    return '%02d:%02d' % (hours, minutes)


class PoolSlot(models.Model):
    _name = 'fitzone.pool.slot'
    _description = 'Pool Slot'
    _order = 'day_of_week, start_time'

    day_of_week = fields.Selection(
        [
            ('0', 'Monday'),
            ('1', 'Tuesday'),
            ('2', 'Wednesday'),
            ('3', 'Thursday'),
            ('4', 'Friday'),
            ('5', 'Saturday'),
            ('6', 'Sunday'),
        ],
        required=True,
    )
    start_time = fields.Float(required=True, help="Hour of day, e.g. 9.5 = 09:30")
    end_time = fields.Float(required=True)
    capacity = fields.Integer()
    slot_type = fields.Selection(
        [
            ('free_swim', 'Free Swim'),
            ('lesson', 'Group Lesson'),
            ('private_pt', 'Private Session with a Trainer'),
        ],
        required=True,
        default='free_swim',
    )
    active = fields.Boolean(default=True)

    @api.depends('day_of_week', 'start_time', 'end_time', 'slot_type')
    def _compute_display_name(self):
        days = dict(self._fields['day_of_week'].selection)
        types = dict(self._fields['slot_type'].selection)
        for rec in self:
            rec.display_name = '%s %s-%s (%s)' % (
                days.get(rec.day_of_week, ''),
                _hhmm(rec.start_time),
                _hhmm(rec.end_time),
                types.get(rec.slot_type, ''),
            )

    @api.constrains('start_time', 'end_time', 'capacity')
    def _check_slot(self):
        for rec in self:
            if not (0.0 <= rec.start_time < 24.0) or not (0.0 < rec.end_time <= 24.0):
                raise ValidationError(_("Slot times must be between 00:00 and 24:00."))
            if rec.end_time <= rec.start_time:
                raise ValidationError(_("The end time must be after the start time."))
            if rec.capacity < 0:
                raise ValidationError(_("Capacity cannot be negative."))

    @api.constrains('day_of_week', 'start_time', 'end_time', 'slot_type')
    def _check_slot_overlap(self):
        for rec in self:
            domain = [
                ('id', '!=', rec.id),
                ('day_of_week', '=', rec.day_of_week),
                ('start_time', '<', rec.end_time),
                ('end_time', '>', rec.start_time),
            ]
            overlapping = self.search(domain)
            if overlapping:
                raise ValidationError(_("This time slot overlaps with another existing pool slot on the same day."))

  
    @api.model
    def _local_weekday_and_hour(self, when):
        """Slots are entered in LOCAL time, so convert using the user's timezone."""
        local = fields.Datetime.context_timestamp(self, when)
        return str(local.weekday()), local.hour + local.minute / 60.0

    @api.model
    def _find_open_slot(self, slot_type, when):
        """The slot of this type that is open at `when` (or an empty recordset)."""
        weekday, hour = self._local_weekday_and_hour(when)
        return self.search([
            ('slot_type', '=', slot_type),
            ('day_of_week', '=', weekday),
            ('start_time', '<=', hour),
            ('end_time', '>', hour),
        ], limit=1)

    @api.model
    def _today_hours_text(self, slot_type, when):
        """e.g. '08:00-10:00, 16:00-18:00' (empty string if none today)."""
        weekday, _hour = self._local_weekday_and_hour(when)
        slots = self.search([
            ('slot_type', '=', slot_type),
            ('day_of_week', '=', weekday),
        ], order='start_time')
        return ', '.join(
            '%s-%s' % (_hhmm(s.start_time), _hhmm(s.end_time)) for s in slots)