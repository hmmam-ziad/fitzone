from dateutil.relativedelta import relativedelta
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Original freeze data must remain unchanged in the history.
PROTECTED_FIELDS = {
    'membership_id',
    'start_date',
    'end_date',
    'days',
    'allowed_days',
    'remaining_days',
    'previous_end_date',
    'new_end_date',
    'processed_by',
    'state',
    'cancelled_by',
    'cancelled_at',
}


class Freeze(models.Model):
    _name = 'fitzone.freeze'
    _description = 'Freeze'
    _order = 'start_date desc, id desc'

    membership_id = fields.Many2one(
        'fitzone.membership',
        required=True,
        ondelete='restrict',
        index=True,
    )

    member_id = fields.Many2one(
        related='membership_id.member_id',
        store=True,
        index=True,
        string='Member',
    )

    start_date = fields.Date(required=True)
    end_date = fields.Date(required=True)

    days = fields.Integer(
        compute='_compute_days',
        store=True,
        readonly=True,
    )

    allowed_days = fields.Integer(
        readonly=True,
        copy=False,
    )

    remaining_days = fields.Integer(
        readonly=True,
        copy=False,
        help="Freeze days remaining after this freeze was created.",
    )

    previous_end_date = fields.Date(
        readonly=True,
        copy=False,
    )

    new_end_date = fields.Date(
        readonly=True,
        copy=False,
    )

    processed_by = fields.Many2one(
        'res.users',
        default=lambda self: self.env.user,
        readonly=True,
        copy=False,
        string='Processed By',
    )

    state = fields.Selection(
        [
            ('active', 'Active'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='active',
        required=True,
        readonly=True,
        copy=False,
    )

    cancelled_by = fields.Many2one(
        'res.users',
        string='Cancelled By',
        readonly=True,
        copy=False,
    )

    cancelled_at = fields.Datetime(
        string='Cancellation Date',
        readonly=True,
        copy=False,
    )

    @api.depends('start_date', 'end_date')
    def _compute_days(self):
        for rec in self:
            if rec.start_date and rec.end_date:
                # Count both the start date and end date.
                rec.days = (rec.end_date - rec.start_date).days + 1
            else:
                rec.days = 0

    @api.constrains('start_date', 'end_date')
    def _check_freeze_dates(self):
        for rec in self:
            if (
                rec.start_date
                and rec.end_date
                and rec.end_date < rec.start_date
            ):
                raise ValidationError(
                    _("Freeze end date cannot be earlier than start date.")
                )

    @api.model
    def _check_request(self, membership, start, end):
        """Validate a freeze request and return its inclusive day count."""
        if membership.state != 'active':
            raise ValidationError(
                _("Only an active membership can be frozen.")
            )

        if end < start:
            raise ValidationError(
                _("Freeze end date cannot be earlier than start date.")
            )

        if (
            not membership.date_start
            or not membership.date_end
            or start < membership.date_start
            or start > membership.date_end
        ):
            raise ValidationError(_(
                "The freeze must start inside the membership period "
                "(%(start)s to %(end)s).",
                start=membership.date_start,
                end=membership.date_end,
            ))

        # Both dates count as freeze days.
        days = (end - start).days + 1

        allowed = membership._freeze_limit()

        # Cancelled freezes no longer consume the package allowance.
        active_freezes = self.search([
            ('membership_id', '=', membership.id),
            ('state', '=', 'active'),
        ])
        used = sum(active_freezes.mapped('days'))

        if used + days > allowed:
            raise ValidationError(_(
                "Freeze rejected: %(days)s day(s) requested, but this "
                "package allows %(allowed)s freeze days in total "
                "(already used: %(used)s, remaining: %(left)s).",
                days=days,
                allowed=allowed,
                used=used,
                left=max(allowed - used, 0),
            ))

        # Cancelled records must not block a new freeze period.
        overlap = self.search_count([
            ('membership_id', '=', membership.id),
            ('state', '=', 'active'),
            ('start_date', '<=', end),
            ('end_date', '>=', start),
        ])

        if overlap:
            raise ValidationError(
                _("This period overlaps with an existing active freeze.")
            )

        return days

    @api.model_create_multi
    def create(self, vals_list):
        records = self.browse()

        for vals in vals_list:
            vals = dict(vals)

            membership = self.env['fitzone.membership'].browse(
                vals.get('membership_id')
            )

            start = fields.Date.to_date(vals.get('start_date'))
            end = fields.Date.to_date(vals.get('end_date'))

            if not (membership.exists() and start and end):
                raise ValidationError(
                    _("Membership, start date and end date are required.")
                )

            # Do not let a caller create a record already marked cancelled
            # or provide its own audit information.
            if vals.get('state', 'active') != 'active':
                raise ValidationError(
                    _("A new freeze must start with Active status.")
                )

            vals.pop('cancelled_by', None)
            vals.pop('cancelled_at', None)

            days = self._check_request(membership, start, end)
            allowed = membership._freeze_limit()

            active_freezes = self.search([
                ('membership_id', '=', membership.id),
                ('state', '=', 'active'),
            ])
            used = sum(active_freezes.mapped('days'))

            previous_end = membership.date_end
            new_end = previous_end + relativedelta(days=days)

            vals.update({
                'allowed_days': allowed,
                'remaining_days': allowed - used - days,
                'previous_end_date': previous_end,
                'new_end_date': new_end,
                'processed_by': self.env.user.id,
            })

            record = super().create([vals])

            # Extend the membership end date by this freeze's day count.
            membership.sudo().with_context(
                allow_membership_dates=True,
                skip_expiry_sync=True,
            ).write({
                'date_end': new_end,
            })

            membership.sudo()._sync_expiry_state()

            records |= record

        return records

    def action_cancel_freeze(self):
        """Cancel the freeze, restore its allowance and retain its history."""
        for freeze in self:
            if freeze.state == 'cancelled':
                raise ValidationError(
                    _("This freeze has already been cancelled.")
                )

            membership = freeze.membership_id

            if not membership.date_end:
                raise ValidationError(
                    _("The membership has no end date.")
                )

            if not freeze.days or freeze.days < 1:
                raise ValidationError(
                    _("The freeze has no valid number of days.")
                )

            # Reverse the extension originally added by this freeze.
            restored_end_date = (
                membership.date_end - relativedelta(days=freeze.days)
            )

            if (
                membership.date_start
                and restored_end_date < membership.date_start
            ):
                raise ValidationError(_(
                    "The cancellation would make the membership end "
                    "before its activation date."
                ))

            membership.sudo().with_context(
                allow_membership_dates=True,
                skip_expiry_sync=True,
            ).write({
                'date_end': restored_end_date,
            })

            membership.sudo()._sync_expiry_state()

            # Bypass the protected-field guard only for this controlled action.
            super(Freeze, freeze).write({
                'state': 'cancelled',
                'cancelled_by': self.env.user.id,
                'cancelled_at': fields.Datetime.now(),
            })

        return True

    def write(self, vals):
        if PROTECTED_FIELDS.intersection(vals):
            raise ValidationError(_(
                "Freeze history fields cannot be edited directly."
            ))

        return super().write(vals)

    def unlink(self):
        raise ValidationError(_(
            "Freeze records are permanent history entries and cannot be deleted."
        ))