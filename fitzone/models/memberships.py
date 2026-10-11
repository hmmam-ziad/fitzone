from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from dateutil.relativedelta import relativedelta


class Membership(models.Model):
    _name = 'fitzone.membership'
    _description = 'Membership'
    _rec_name = 'member_id'

    member_id = fields.Many2one(
        'res.partner',
        required=True,
        domain=[('is_fitzone_member', '=', True)]
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

    # Dates are assigned when the membership is activated.
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

    block_reason = fields.Char(groups='fitzone.group_fitzone_manager,fitzone.group_fitzone_reception,fitzone.group_fitzone_physiotherapist,fitzone.group_fitzone_nutritionist', )

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
        groups='fitzone.group_fitzone_manager,fitzone.group_fitzone_reception,fitzone.group_fitzone_physiotherapist,fitzone.group_fitzone_nutritionist',
        string='Base Price',
        related='package_id.list_price',
        readonly=True,
    )

    final_price = fields.Float(
        groups='fitzone.group_fitzone_manager,fitzone.group_fitzone_reception,fitzone.group_fitzone_physiotherapist,fitzone.group_fitzone_nutritionist',
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

    physio_sessions_consumed = fields.Integer(groups='fitzone.group_fitzone_manager,fitzone.group_fitzone_reception,fitzone.group_fitzone_physiotherapist,fitzone.group_fitzone_nutritionist',
        string='Physiotherapy Sessions Consumed',
        default=0,
        copy=False,
    )

    physio_sessions_total = fields.Integer(groups='fitzone.group_fitzone_manager,fitzone.group_fitzone_reception,fitzone.group_fitzone_physiotherapist,fitzone.group_fitzone_nutritionist',
        string='Total Physiotherapy Sessions',
        compute='_compute_medical_credits',
        store=True,
    )

    physio_sessions_remaining = fields.Integer(groups='fitzone.group_fitzone_manager,fitzone.group_fitzone_reception,fitzone.group_fitzone_physiotherapist,fitzone.group_fitzone_nutritionist',
        string='Remaining Physiotherapy Sessions',
        compute='_compute_medical_credits',
        store=True,
    )

    nutrition_sessions_consumed = fields.Integer(groups='fitzone.group_fitzone_manager,fitzone.group_fitzone_reception,fitzone.group_fitzone_physiotherapist,fitzone.group_fitzone_nutritionist',
        string='Nutrition Consultations Consumed',
        default=0,
        copy=False,
    )

    nutrition_sessions_total = fields.Integer(groups='fitzone.group_fitzone_manager,fitzone.group_fitzone_reception,fitzone.group_fitzone_physiotherapist,fitzone.group_fitzone_nutritionist',
        string='Total Nutrition Consultations',
        compute='_compute_medical_credits',
        store=True,
    )

    nutrition_sessions_remaining = fields.Integer(groups='fitzone.group_fitzone_manager,fitzone.group_fitzone_reception,fitzone.group_fitzone_physiotherapist,fitzone.group_fitzone_nutritionist',
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

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Generate a membership number when needed.
            member_id = vals.get('member_id')
            if member_id:
                member = self.env['res.partner'].browse(member_id)
                if member.exists() and not member.membership_no:
                    member._assign_membership_number()

            # A draft membership has no activation dates.
            if vals.get('state', 'draft') == 'draft':
                vals['date_start'] = False
                vals['date_end'] = False

            # Explicitly created active memberships need valid dates.
            elif vals.get('state') == 'active':
                package_id = vals.get('package_id')
                if not package_id:
                    raise ValidationError(
                        'Please select a package before activation.'
                    )

                package = self.env['product.template'].browse(package_id)
                duration = package.duration_months

                if not package.exists() or duration <= 0:
                    raise ValidationError(
                        'The package must have a valid duration.'
                    )

                activation_date = fields.Date.to_date(
                    vals.get('date_start') or fields.Date.today()
                )
                vals['date_start'] = activation_date
                vals['date_end'] = (
                    activation_date
                    + relativedelta(months=duration)
                    - relativedelta(days=1)
                )

        return super().create(vals_list)

    def write(self, vals):
        # Do not allow users or other code to edit dates directly.
        if (
            {'date_start', 'date_end'} & vals.keys()
            and not self.env.context.get('allow_membership_dates')
        ):
            raise ValidationError(
                'Membership dates are managed automatically by activation.'
            )

        # A draft membership cannot be activated by changing its state directly
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
            # Draft memberships must remain drafts until activated.
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
        raise AccessError('Auto-Block cannot be overridden manually.')

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