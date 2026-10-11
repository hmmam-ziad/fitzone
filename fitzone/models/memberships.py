import base64
import io

from PIL import Image, ImageDraw, ImageFont
from reportlab.graphics.barcode.code128 import Code128
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
    barcode_image = fields.Binary(
        string='Barcode Image',
        compute='_compute_barcode_image',
    )

    @api.depends('barcode')
    def _compute_barcode_image(self):
        for membership in self:
            if not membership.barcode:
                membership.barcode_image = False
                continue

            barcode = Code128(membership.barcode)
            barcode.validate()
            barcode.encode()
            pattern = barcode.decompose()

            scale = 3
            quiet_zone = 30
            bar_height = 70
            text_height = 25

            def module_width(char):
                base = ord('A') if char.isupper() else ord('a')
                return ord(char) - base + 1

            pattern_width = sum(
                module_width(char) for char in pattern
            ) * scale

            image = Image.new(
                'RGB',
                (
                    pattern_width + 2 * quiet_zone,
                    bar_height + text_height,
                ),
                'white',
            )
            draw = ImageDraw.Draw(image)
            x = quiet_zone

            for char in pattern:
                width = module_width(char) * scale
                if char.isupper():
                    draw.rectangle(
                        (x, 0, x + width - 1, bar_height - 1),
                        fill='black',
                    )
                x += width

            font = ImageFont.load_default()
            text = membership.barcode
            text_width = draw.textbbox((0, 0), text, font=font)[2]
            draw.text(
                ((image.width - text_width) // 2, bar_height + 4),
                text,
                fill='black',
                font=font,
            )

            output = io.BytesIO()
            image.save(output, format='PNG')
            membership.barcode_image = base64.b64encode(
                output.getvalue()
            )

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

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Generate a membership number when needed.
            member_id = vals.get('member_id')
            if member_id:
                member = self.env['res.partner'].browse(member_id)
                if member.exists() and not member.membership_no:
                    member.membership_no = (
                        self.env['ir.sequence'].next_by_code(
                            'fitzone.member'
                        )
                    )

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

            plans = self.env['fitzone.installment.plan'].search([
                ('membership_id', '=', membership.id),
            ])
            if plans:
                first_installment = plans[0].installment_ids.sorted(
                    lambda installment: (installment.due_date, installment.id)
                )[:1]
                if not first_installment:
                    raise ValidationError(
                        'The first installment must be paid before activation.'
                    )

                first_installment = first_installment[0]
                payment = first_installment.payment_id
                if (
                    first_installment.status != 'paid'
                    or not payment
                    or payment.state not in ('paid', 'in_process')
                    or payment.move_id.state != 'posted'
                ):
                    raise ValidationError(
                        'The first installment must have a successful payment '
                        'before activating this membership.'
                    )

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

            values = {
                'date_start': activation_date,
                'date_end': end_date,
                'state': 'active',
            }

            if not membership.barcode:
                barcode = self.env['ir.sequence'].next_by_code(
                    'fitzone.membership.barcode'
                )
                if not barcode:
                    raise ValidationError(
                        'Unable to generate a membership barcode.'
                    )
                values['barcode'] = barcode

            membership.with_context(
                allow_membership_dates=True,
                allow_membership_activation=True,
                skip_expiry_sync=True,
            ).write(values)

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