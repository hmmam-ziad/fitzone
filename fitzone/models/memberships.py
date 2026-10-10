from odoo import api, fields, models
from odoo.exceptions import ValidationError
from dateutil.relativedelta import relativedelta

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
            ('draft', 'Draft'),
            ('active', 'Active'),
            ('expired', 'Expired'),
            ('blocked', 'Blocked'),
            ('cancelled', 'Cancelled'),
        ],
        default='draft',
        required=True,
    )

    block_reason = fields.Char()

    total_sessions = fields.Integer(
        string='Total PT Sessions',
        related='package_id.total_sessions',
        store=True,
        readonly=True,
    )

    consumed_sessions = fields.Integer(
        string='Consumed PT Sessions',
        default=0,
        copy=False,
    )

    remaining_sessions = fields.Integer(
        string='Remaining PT Sessions',
        compute='_compute_remaining_sessions',
        store=True,
    )

    @api.depends('total_sessions', 'consumed_sessions')
    def _compute_remaining_sessions(self):
        for membership in self:
            membership.remaining_sessions = max(
                membership.total_sessions - membership.consumed_sessions,
                0,
            )

    all_inclusive = fields.Boolean(
        string='All-Inclusive',
        default=False,
        copy=False,
    )

    physio_sessions_consumed = fields.Integer(
        string='Physiotherapy Sessions Consumed',
        default=0,
        copy=False,
    )

    physio_sessions_total = fields.Integer(
        string='Total Physiotherapy Sessions',
        compute='_compute_medical_credits',
        store=True,
    )

    physio_sessions_remaining = fields.Integer(
        string='Remaining Physiotherapy Sessions',
        compute='_compute_medical_credits',
        store=True,
    )

    nutrition_sessions_consumed = fields.Integer(
        string='Nutrition Consultations Consumed',
        default=0,
        copy=False,
    )

    nutrition_sessions_total = fields.Integer(
        string='Total Nutrition Consultations',
        compute='_compute_medical_credits',
        store=True,
    )

    nutrition_sessions_remaining = fields.Integer(
        string='Remaining Nutrition Consultations',
        compute='_compute_medical_credits',
        store=True,
    )

    @api.depends(
        'all_inclusive',
        'package_id.duration_months',
        'physio_sessions_consumed',
        'nutrition_sessions_consumed',
    )
    def _compute_medical_credits(self):
        for membership in self:
            months = membership.package_id.duration_months or 0

            physio_total = months * 2 if membership.all_inclusive else 0
            nutrition_total = 1 if membership.all_inclusive else 0

            membership.physio_sessions_total = physio_total
            membership.physio_sessions_remaining = max(
                physio_total - membership.physio_sessions_consumed, 0
            )

            membership.nutrition_sessions_total = nutrition_total
            membership.nutrition_sessions_remaining = max(
                nutrition_total - membership.nutrition_sessions_consumed, 0
            )

    @api.onchange('package_id', 'date_start')
    def _onchange_package_or_date_start(self):
        for membership in self:
            if membership.package_id and membership.date_start:
                duration = membership.package_id.duration_months

                if duration > 0:
                    membership.date_end = (
                        membership.date_start
                        + relativedelta(months=duration)
                        - relativedelta(days=1)
                    )

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
        for vals in vals_list:
            # Generate the member's membership number if needed.
            member_id = vals.get('member_id')
            if member_id:
                member = self.env['res.partner'].browse(member_id)
                if not member.membership_no:
                    member.membership_no = self.env['ir.sequence'].next_by_code(
                        'fitzone.member'
                    )

            # Calculate the membership end date from its activation date.
            package_id = vals.get('package_id')
            if package_id:
                package = self.env['product.template'].browse(package_id)
                duration = package.duration_months

                if duration > 0:
                    date_start = fields.Date.to_date(
                        vals.get('date_start') or fields.Date.today()
                    )
                    vals['date_end'] = (
                        date_start
                        + relativedelta(months=duration)
                        - relativedelta(days=1)
                    )

        memberships = super().create(vals_list)
        memberships._sync_expiry_state()
        return memberships


    def write(self, vals):
        if (
            ('package_id' in vals or 'date_start' in vals)
            and not self.env.context.get('skip_duration_sync')
        ):
            for membership in self:
                record_vals = vals.copy()

                package_id = vals.get(
                    'package_id',
                    membership.package_id.id,
                )
                package = self.env['product.template'].browse(package_id)

                date_start = fields.Date.to_date(
                    vals.get('date_start', membership.date_start)
                )

                if package and date_start and package.duration_months > 0:
                    record_vals['date_end'] = (
                        date_start
                        + relativedelta(months=package.duration_months)
                        - relativedelta(days=1)
                    )

                super(Membership, membership).write(record_vals)
            result = True
        else:
            result = super().write(vals)

        if (
            not self.env.context.get('skip_expiry_sync')
            and ('date_end' in vals or 'state' in vals
                 or 'package_id' in vals or 'date_start' in vals)
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
