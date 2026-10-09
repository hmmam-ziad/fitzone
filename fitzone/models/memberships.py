from odoo import api, fields, models
from odoo.exceptions import ValidationError


class Membership(models.Model):
    _name = 'fitzone.membership'
    _description = 'Membership'
    _rec_name = 'member_id'

    member_id = fields.Many2one(
        'res.partner',
        required=True,
    )

    package_id = fields.Many2one(
        'product.template',
        required=True,
    )

    barcode = fields.Char()

    date_start = fields.Date(
        required=True,
        default=fields.Date.today,
    )

    date_end = fields.Date(
        required=True,
    )

    state = fields.Selection(
        [
            ('active', 'Active'),
            ('expired', 'Expired'),
            ('blocked', 'Blocked'),
            ('cancelled', 'Cancelled'),
        ],
        default='active',
        required=True,
    )

    block_reason = fields.Char()

    def _sync_expiry_state(self):
        today = fields.Date.context_today(self)

        for membership in self:
            if membership.state in ('blocked', 'cancelled'):
                continue

            if not membership.date_end:
                continue

            if membership.date_end < today:
                target_state = 'expired'
            else:
                target_state = 'active'

            if membership.state != target_state:
                membership.with_context(
                    skip_expiry_sync=True
                ).write({
                    'state': target_state,
                })

    @api.model_create_multi
    def create(self, vals_list):
        memberships = super().create(vals_list)
        memberships._sync_expiry_state()
        return memberships

    def write(self, vals):
        result = super().write(vals)

        if (
            not self.env.context.get('skip_expiry_sync')
            and ('date_end' in vals or 'state' in vals)
        ):
            self._sync_expiry_state()

        return result

    @api.onchange('date_end')
    def _onchange_date_end(self):
        today = fields.Date.context_today(self)

        for membership in self:
            if membership.state in ('blocked', 'cancelled'):
                continue

            if not membership.date_end:
                continue

            if membership.date_end < today:
                membership.state = 'expired'
            else:
                membership.state = 'active'

    def action_block(self):
        self.write({
            'state': 'blocked',
        })

    def action_unblock(self):
        for membership in self:
            membership.write({
                'state': 'active',
                'block_reason': False,
            })

    @api.model
    def action_expire_memberships(self):
        memberships = self.search([
            ('state', 'in', ['active', 'expired']),
        ])

        memberships._sync_expiry_state()

    @api.constrains('date_start', 'date_end')
    def _check_membership_dates(self):
        for membership in self:
            if (
                membership.date_start
                and membership.date_end
                and membership.date_end < membership.date_start
            ):
                raise ValidationError(
                    "Membership end date cannot be earlier than start date."
                )