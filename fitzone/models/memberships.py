from odoo import fields, models


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

    def action_block(self):
        self.write({
            'state': 'blocked',
        })

    def action_unblock(self):
        today = fields.Date.context_today(self)

        for membership in self:
            if membership.date_end < today:
                membership.write({
                    'state': 'expired',
                    'block_reason': False,
                })
            else:
                membership.write({
                    'state': 'active',
                    'block_reason': False,
                })

    def action_expire_memberships(self):
        today = fields.Date.context_today(self)

        memberships = self.search([
            ('date_end', '<', today),
            ('state', '=', 'active'),
        ])

        memberships.write({
            'state': 'expired',
        })