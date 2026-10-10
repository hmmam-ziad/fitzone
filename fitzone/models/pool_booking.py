
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
    )
    membership_id = fields.Many2one(
        'fitzone.membership',
        required=True,
    )
    pool_slot_id = fields.Many2one(
        'fitzone.pool.slot',
        required=True,
    )
    trainer_id = fields.Many2one(
        'fitzone.trainer',
        help="Only for Private Session slots.",
    )
    booking_date = fields.Datetime(
        default=fields.Datetime.now,
    )
    status = fields.Selection(
        [
            ('confirmed', 'Confirmed'),
            ('checked_in', 'Checked In'),
            ('cancelled', 'Cancelled'),
        ],
        default='confirmed',
    )

    def action_cancel(self):
        for rec in self:
            if rec.status != 'confirmed':
                raise ValidationError(
                    _("Only confirmed bookings can be cancelled.")
                )
            rec.status = 'cancelled'

    @api.constrains('trainer_id', 'pool_slot_id')
    def _check_trainer(self):
        for rec in self:
            is_private = (
                rec.pool_slot_id.slot_type == 'private_pt'
            )

            if is_private and not rec.trainer_id:
                raise ValidationError(
                    _("A private session needs a trainer.")
                )

            if not is_private and rec.trainer_id:
                raise ValidationError(
                    _(
                        "A trainer can only be set on "
                        "Private Session slots."
                    )
                )

    @api.constrains('member_id')
    def _check_min_age(self):
        # Reception re-checks at the door; here we block known under-age members.
        for rec in self:
            age = rec.member_id._fz_age_years()

            if age is not None and age < POOL_MIN_AGE:
                raise ValidationError(
                    _(
                        "Members under %s years old cannot use the pool.",
                        POOL_MIN_AGE,
                    )
                )

    @api.constrains(
        'member_id', 'membership_id', 'booking_date'
    )
    def _check_active_membership(self):
        today = fields.Date.context_today(self)

        for rec in self:
            membership = rec.membership_id

            if not membership:
                raise ValidationError(
                    _("A membership is required to book the pool.")
                )

            if membership.member_id != rec.member_id:
                raise ValidationError(
                    _(
                        "The selected membership does not belong "
                        "to this member."
                    )
                )

            if membership.state != 'active':
                raise ValidationError(
                    _(
                        "Cannot book the pool: the membership "
                        "is not active."
                    )
                )

            if membership.date_start and membership.date_start > today:
                raise ValidationError(
                    _(
                        "Cannot book the pool: the membership "
                        "has not started yet."
                    )
                )

            if membership.date_end and membership.date_end < today:
                raise ValidationError(
                    _(
                        "Cannot book the pool: the membership "
                        "has expired."
                    )
                )

    @api.constrains(
        'member_id', 'pool_slot_id', 'booking_date', 'status'
    )
    def _check_duplicate_booking(self):
        for rec in self:
            if (
                not rec.member_id
                or not rec.pool_slot_id
                or not rec.booking_date
                or rec.status == 'cancelled'
            ):
                continue

            booking_day = fields.Datetime.to_datetime(
                rec.booking_date
            ).date()

            duplicates = self.search([
                ('id', '!=', rec.id),
                ('member_id', '=', rec.member_id.id),
                ('pool_slot_id', '=', rec.pool_slot_id.id),
                ('status', '!=', 'cancelled'),
            ])

            for booking in duplicates:
                if not booking.booking_date:
                    continue

                existing_day = fields.Datetime.to_datetime(
                    booking.booking_date
                ).date()

                if existing_day == booking_day:
                    raise ValidationError(
                        _(
                            "This member already has a booking "
                            "for the same pool slot on this date."
                        )
                    )
