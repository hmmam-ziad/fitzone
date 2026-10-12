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
        string='Trainer',
        help="Required for Group and Private Sessions; not used for Free Swim.",
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

    is_free_swim = fields.Boolean(
        compute='_compute_is_free_swim',
    )

    @api.depends('pool_slot_id', 'pool_slot_id.slot_type')
    def _compute_is_free_swim(self):
        for rec in self:
            rec.is_free_swim = (
                rec.pool_slot_id.slot_type == 'free_swim'
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
            if not rec.pool_slot_id:
                continue

            slot_type = rec.pool_slot_id.slot_type

            if slot_type in ('lesson', 'private_pt') and not rec.trainer_id:
                raise ValidationError(
                    _("A trainer is required for Group and Private Sessions.")
                )

            if slot_type == 'free_swim' and rec.trainer_id:
                raise ValidationError(
                    _("Free Swim bookings must not have a trainer.")
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
                or rec.status == 'cancelled'
            ):
                continue

            duplicates = self.search([
                ('id', '!=', rec.id),
                ('member_id', '=', rec.member_id.id),
                ('pool_slot_id', '=', rec.pool_slot_id.id),
                ('status', '!=', 'cancelled'),
            ])

            if duplicates:
                raise ValidationError(
                    _(
                        "You have already booked this pool slot. "
                        "Duplicate bookings are not allowed."
                    )
                )
