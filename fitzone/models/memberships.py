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

    package_type = fields.Selection(
        related='package_id.package_type',
        string='Package Type',
        readonly=True,
    )

    barcode = fields.Char()

    date_start = fields.Date(
        string='Activation Date',
        readonly=True,
        copy=False,
    )

    date_end = fields.Date(
        string='End Date',
        readonly=True,
        copy=False,
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
        copy=False,
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

    base_price = fields.Float(
        string='Base Price',
        related='package_id.list_price',
        readonly=True,
    )

    final_price = fields.Float(
        string='Final Price',
        compute='_compute_final_price',
        store=True,
    )

    @api.depends('base_price', 'all_inclusive')
    def _compute_final_price(self):
        for membership in self:
            membership.final_price = (
                membership.base_price + 20
                if membership.all_inclusive
                else membership.base_price
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

            physio_total = (
                months * 2 if membership.all_inclusive else 0
            )
            nutrition_total = 1 if membership.all_inclusive else 0

            membership.physio_sessions_total = physio_total
            membership.physio_sessions_remaining = max(
                physio_total - membership.physio_sessions_consumed,
                0,
            )

            membership.nutrition_sessions_total = nutrition_total
            membership.nutrition_sessions_remaining = max(
                nutrition_total - membership.nutrition_sessions_consumed,
                0,
            )

    @api.constrains('package_id', 'all_inclusive')
    def _check_all_inclusive_package(self):
        for membership in self:
            if (
                membership.all_inclusive
                and membership.package_id.package_type != 'general'
            ):
                raise ValidationError(
                    'All-Inclusive can only be added to a General Membership.'
                )

    def _check_package_period_available(
        self, member_id, package_id, start_date, end_date
    ):
        """Prevent overlapping memberships for the same member and package."""
        if not all([member_id, package_id, start_date, end_date]):
            return

        domain = [
            ('member_id', '=', member_id),
            ('package_id', '=', package_id),
            ('state', 'in', ['active', 'blocked']),
            ('date_start', '<=', end_date),
            ('date_end', '>=', start_date),
        ]

        if self.ids:
            domain.append(('id', 'not in', self.ids))

        existing_membership = self.search(domain, limit=1)

        if existing_membership:
            raise ValidationError(
                'This member already has an active or blocked membership '
                'for the same package during this period. '
                'The package can be purchased again after the current '
                'membership period ends.'
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals = dict(vals)

            member_id = vals.get('member_id')

            if member_id:
                member = self.env['res.partner'].browse(member_id)

                if member.exists() and not member.membership_no:
                    member.membership_no = (
                        self.env['ir.sequence'].next_by_code(
                            'fitzone.member'
                        )
                    )

            if vals.get('state', 'draft') == 'draft':
                vals['date_start'] = False
                vals['date_end'] = False

            elif vals.get('state') == 'active':
                package_id = vals.get('package_id')

                if not package_id:
                    raise ValidationError(
                        'Please select a package before activation.'
                    )

                package = self.env['product.template'].browse(package_id)
                duration = package.duration_months if package.exists() else 0

                if duration <= 0:
                    raise ValidationError(
                        'The package must have a valid duration.'
                    )

                activation_date = fields.Date.to_date(
                    vals.get('date_start') or fields.Date.today()
                )

                end_date = (
                    activation_date
                    + relativedelta(months=duration)
                    - relativedelta(days=1)
                )

                vals['date_start'] = activation_date
                vals['date_end'] = end_date

                self._check_package_period_available(
                    member_id=member_id,
                    package_id=package_id,
                    start_date=activation_date,
                    end_date=end_date,
                )

        return super().create(vals_list)

    def write(self, vals):
        if (
            {'date_start', 'date_end'} & vals.keys()
            and not self.env.context.get('allow_membership_dates')
        ):
            raise ValidationError(
                'Membership dates are managed automatically by activation.'
            )

        if (
            vals.get('state') == 'active'
            and not self.env.context.get('allow_membership_activation')
        ):
            raise ValidationError(
                'Use the Activate action to activate a membership.'
            )

        result = super().write(vals)

        if (
            not self.env.context.get('skip_expiry_sync')
            and ('date_end' in vals or 'state' in vals)
        ):
            self._sync_expiry_state()

        return result

    def _sync_expiry_state(self):
        today = fields.Date.context_today(self)

        for membership in self:
            if membership.state in ('draft', 'blocked', 'cancelled'):
                continue

            if not membership.date_end:
                continue

            target_state = (
                'expired'
                if membership.date_end < today
                else 'active'
            )

            if membership.state != target_state:
                membership.with_context(
                    skip_expiry_sync=True,
                    allow_membership_activation=True,
                ).write({
                    'state': target_state,
                })

    def action_activate(self):
        for membership in self:
            if membership.state != 'draft':
                continue

            if not membership.package_id:
                raise ValidationError('Please select a package.')

            if membership.package_id.package_type == 'all_inclusive':
                raise ValidationError(
                    'All-Inclusive must be added to a General Membership.'
                )

            duration = membership.package_id.duration_months

            if duration <= 0:
                raise ValidationError(
                    'The package must have a valid duration.'
                )

            activation_date = fields.Date.context_today(membership)

            end_date = (
                activation_date
                + relativedelta(months=duration)
                - relativedelta(days=1)
            )

            membership._check_package_period_available(
                member_id=membership.member_id.id,
                package_id=membership.package_id.id,
                start_date=activation_date,
                end_date=end_date,
            )

            membership.with_context(
                allow_membership_dates=True,
                allow_membership_activation=True,
                skip_expiry_sync=True,
            ).write({
                'date_start': activation_date,
                'date_end': end_date,
                'state': 'active',
            })

    def action_block(self):
        self.write({
            'state': 'blocked',
        })

    def action_unblock(self):
        today = fields.Date.context_today(self)

        for membership in self:
            if not membership.date_start or not membership.date_end:
                raise ValidationError(
                    'This membership has no activation dates.'
                )

            if membership.date_end < today:
                membership.write({
                    'state': 'expired',
                    'block_reason': False,
                })
            else:
                membership.with_context(
                    allow_membership_activation=True,
                ).write({
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
                    'Membership end date cannot be earlier than start date.'
                )