
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


FREEZE_GRACE_MONTHS = 2


class FitzoneMembership(models.Model):
    """Freeze balance and history on a membership."""
    _inherit = 'fitzone.membership'

    freeze_ids = fields.One2many(
        'fitzone.freeze',
        'membership_id',
        string='Freeze History',
    )

    freeze_allowed_days = fields.Integer(
        compute='_compute_freeze_balance',
    )

    freeze_used_days = fields.Integer(
        compute='_compute_freeze_balance',
    )

    freeze_remaining_days = fields.Integer(
        compute='_compute_freeze_balance',
    )

    freeze_grace_end = fields.Date(
        compute='_compute_freeze_balance',
        string='Freeze Grace Period Ends',
    )

    def _freeze_limit(self):
        """Return the maximum freeze days allowed by the package."""
        self.ensure_one()

        months = self.package_id.duration_months or 0

        if months <= 1:
            return 7

        if months <= 3:
            return 14

        return 30

    @api.depends(
        'package_id.duration_months',
        'freeze_ids.days',
        'freeze_ids.state',
        'date_end',
    )
    def _compute_freeze_balance(self):
        for rec in self:
            allowed = rec._freeze_limit() if rec.package_id else 0

            # Only active freezes consume the package allowance.
            active_freezes = rec.freeze_ids.filtered(
                lambda freeze: freeze.state == 'active'
            )

            used = sum(active_freezes.mapped('days'))

            rec.freeze_allowed_days = allowed
            rec.freeze_used_days = used
            rec.freeze_remaining_days = max(allowed - used, 0)

            rec.freeze_grace_end = (
                rec.date_end + relativedelta(
                    months=FREEZE_GRACE_MONTHS
                )
                if rec.date_end
                else False
            )

    @api.depends('member_id.name', 'package_id.name')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = '%s - %s' % (
                rec.member_id.name or '',
                rec.package_id.name or '',
            )
