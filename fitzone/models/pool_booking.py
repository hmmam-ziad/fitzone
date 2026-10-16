from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .res_partner_pool import POOL_MIN_AGE


class PoolBooking(models.Model):
    _name = 'fitzone.pool.booking'
    _description = 'Pool Booking'

    member_id = fields.Many2one(
        'res.partner',
        string='Member',
        required=True,
        groups='fitzone.group_fitzone_manager,fitzone.group_fitzone_reception',
        domain="[('membership_ids', '!=', False)]",
    )
    membership_id = fields.Many2one(
        'fitzone.membership',
        required=True,
        groups='fitzone.group_fitzone_manager,fitzone.group_fitzone_reception',
        domain="[('member_id', '=', member_id), ('state', '==', 'active')]"
    )
    pool_slot_id = fields.Many2one('fitzone.pool.slot', required=True)
    trainer_id = fields.Many2one(
        'fitzone.trainer',
        string='Trainer',
        help="Required for Group and Private Sessions; not used for Free Swim.",
    )
    # The actual day the session takes place
    session_date = fields.Date(
        string='Session Date',
        required=True,
        default=fields.Date.context_today,
    )
    # When the booking was created (not the session time)
    booking_date = fields.Datetime(default=fields.Datetime.now)
    status = fields.Selection(
        [
            ('confirmed', 'Confirmed'),
            ('checked_in', 'Checked In'),
            ('cancelled', 'Cancelled'),
        ],
        default='confirmed',
    )
    is_free_swim = fields.Boolean(compute='_compute_is_free_swim')
    member_name = fields.Char(compute='_compute_booking_identity', compute_sudo=False)
    membership_number = fields.Char(compute='_compute_booking_identity', compute_sudo=False)

    @api.constrains('pool_slot_id', 'session_date', 'status')
    def _check_pool_slot_capacity(self):
        for booking in self:
            if booking.status != 'cancelled' and booking.pool_slot_id and booking.pool_slot_id.capacity > 0:
                existing_bookings_count = self.search_count([
                    ('id', '!=', booking.id),
                    ('pool_slot_id', '=', booking.pool_slot_id.id),
                    ('session_date', '=', booking.session_date),
                    ('status', '!=', 'cancelled'),
                ])

                if existing_bookings_count >= booking.pool_slot_id.capacity:
                    raise ValidationError(
                        _(
                            "Cannot confirm booking! The selected pool slot has reached its maximum capacity of %(capacity)d members for %(date)s."
                        ) % {
                            'capacity': booking.pool_slot_id.capacity,
                            'date': booking.session_date,
                        }
                    )

    def _booking_identity(self):
        self.ensure_one()
        self.check_access('read')
        # Assigned pool-booking readers need only minimal identity, never unrestricted partner data.
        member = self.sudo().member_id
        return member.name, member.membership_no

    @api.depends('member_id')
    def _compute_booking_identity(self):
        for booking in self:
            booking.member_name, booking.membership_number = booking._booking_identity()

    @api.depends('pool_slot_id', 'pool_slot_id.slot_type')
    def _compute_is_free_swim(self):
        for rec in self:
            rec.is_free_swim = rec.pool_slot_id.slot_type == 'free_swim'

    def action_cancel(self):
        for rec in self:
            if rec.status != 'confirmed':
                raise ValidationError(_("Only confirmed bookings can be cancelled."))
            rec.status = 'cancelled'

    # ---------- helpers ----------
    def _slot_datetimes_utc(self):
        """(start, end) of the session in UTC: session_date + local slot time."""
        self.ensure_one()
        tz = pytz.timezone(self.env.user.tz or 'Asia/Amman')
        slot = self.pool_slot_id

        def _to_utc(hours):
            local = tz.localize(datetime.combine(
                self.session_date,
                time(int(hours) % 24, round((hours % 1) * 60) % 60),
            ))
            return local.astimezone(pytz.utc).replace(tzinfo=None)

        start = _to_utc(slot.start_time)
        # end_time = 24.0 means end of day
        if slot.end_time >= 24.0:
            end = _to_utc(0.0) + timedelta(days=1)
        else:
            end = _to_utc(slot.end_time)
        return start, end

    # ---------- constraints ----------
    @api.constrains('trainer_id', 'pool_slot_id')
    def _check_trainer(self):
        for rec in self:
            if not rec.pool_slot_id:
                continue
            slot_type = rec.pool_slot_id.slot_type
            if slot_type in ('lesson', 'private_pt') and not rec.trainer_id:
                raise ValidationError(
                    _("A trainer is required for Group and Private Sessions."))
            if slot_type == 'free_swim' and rec.trainer_id:
                raise ValidationError(
                    _("Free Swim bookings must not have a trainer."))

    @api.constrains('pool_slot_id', 'session_date')
    def _check_session_date_matches_slot(self):
        for rec in self:
            if not rec.pool_slot_id or not rec.session_date:
                continue
            if str(rec.session_date.weekday()) != rec.pool_slot_id.day_of_week:
                raise ValidationError(
                    _("The session date does not fall on the day of the selected pool slot."))

    @api.constrains('member_id')
    def _check_min_age(self):
        for rec in self:
            age = rec.member_id._fz_age_years()
            if age is not None and age < POOL_MIN_AGE:
                raise ValidationError(
                    _("Members under %s years old cannot use the pool.", POOL_MIN_AGE))

    @api.constrains('member_id', 'membership_id', 'session_date')
    def _check_active_membership(self):
        for rec in self:
            membership = rec.membership_id
            day = rec.session_date

            if not membership:
                raise ValidationError(_("A membership is required to book the pool."))
            if membership.member_id != rec.member_id:
                raise ValidationError(
                    _("The selected membership does not belong to this member."))
            if membership.state != 'active':
                raise ValidationError(
                    _("Cannot book the pool: the membership is not active."))
            if membership.date_start and day and membership.date_start > day:
                raise ValidationError(
                    _("Cannot book the pool: the membership has not started yet."))
            if membership.date_end and day and membership.date_end < day:
                raise ValidationError(
                    _("Cannot book the pool: the membership has expired."))

    @api.constrains('member_id', 'pool_slot_id', 'session_date', 'status')
    def _check_duplicate_booking(self):
        for rec in self:
            if not rec.member_id or not rec.pool_slot_id or rec.status == 'cancelled':
                continue
            duplicates = self.search([
                ('id', '!=', rec.id),
                ('member_id', '=', rec.member_id.id),
                ('pool_slot_id', '=', rec.pool_slot_id.id),
                ('session_date', '=', rec.session_date),
                ('status', '!=', 'cancelled'),
            ], limit=1)
            if duplicates:
                raise ValidationError(
                    _("You have already booked this pool slot. "
                      "Duplicate bookings are not allowed."))

    @api.constrains('trainer_id', 'pool_slot_id', 'session_date', 'status')
    def _fz_check_trainer_schedule(self):
        for rec in self:
            if (
                not rec.trainer_id
                or not rec.session_date
                or not rec.pool_slot_id
                or rec.status == 'cancelled'
                or rec.pool_slot_id.slot_type == 'free_swim'
            ):
                continue

            start, end = rec._slot_datetimes_utc()

            if rec.pool_slot_id.slot_type == 'lesson':
                # Group lesson appears in the schedule view as ONE row tied
                # to the slot, so exclude it to avoid members clashing together
                exclude = ('fitzone.pool.slot', rec.pool_slot_id.id)
            else:
                exclude = (rec._name, rec.id)

            rec.trainer_id._check_available(start, end, exclude=exclude)

    @api.constrains('membership_id', 'session_date')
    def _check_membership_not_frozen(self):
        for record in self:
            if record.membership_id:
                current_date = record.session_date or fields.Date.today()
                frozen_records = self.env['fitzone.freeze'].search([
                    ('membership_id', '=', record.membership_id.id),
                    ('state', '=', 'active'),  # التأكد أن حالة التجميد active
                    ('start_date', '<=', current_date),
                    ('end_date', '>=', current_date),
                ])
                if frozen_records:
                    raise ValidationError(
                        _("Cannot create a booking! The selected membership is currently frozen.")
                    )

    @api.constrains('member_id', 'pool_slot_id', 'session_date', 'status')
    def _check_no_pt_overlap(self):
        for rec in self.sudo():
            if rec.status == 'cancelled' or not (rec.member_id and rec.pool_slot_id and rec.session_date):
                continue
            start, end = rec._slot_datetimes_utc()
            clash = self.env['fitzone.pt.session'].sudo().search_count([
                ('member_id', '=', rec.member_id.id),
                ('state', '!=', 'cancelled'),
                ('session_date', '<', end),
                ('end_datetime', '>', start),
            ])
            if clash:
                raise ValidationError(
                    _("This member already has a PT session that overlaps with this pool booking."))