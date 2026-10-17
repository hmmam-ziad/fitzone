import base64
import io

from PIL import Image, ImageDraw, ImageFont
from reportlab.graphics.barcode.code128 import Code128
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import email_normalize
from dateutil.relativedelta import relativedelta

from .smart_button_helpers import (
    FINANCE_READERS, check_navigation, grouped_counts, has_roles, related_action,
)


class Membership(models.Model):
    _name = 'fitzone.membership'
    _inherit = ['mail.thread']
    _description = 'Membership'
    _rec_name = 'member_id'

    def _check_badge_access(self):
        self.check_access('read')
        if not (self.env.su or self.env.user.has_group('base.group_system')
                or has_roles(self.env, ('manager', 'reception'))):
            raise AccessError(_('Only administrators and receptionists can issue membership badges.'))

    def action_print_badge(self):
        self.ensure_one()
        self._check_badge_access()
        return self.env.ref('fitzone.action_report_membership_badge').report_action(self)

    def action_send_badge_email(self):
        self.ensure_one()
        self._check_badge_access()
        self.check_access('write')
        recipient = email_normalize(self.member_id.email or '')
        if not recipient:
            raise UserError(_('Please enter a valid email address on the member before sending the badge.'))
        if not self.barcode or not self.date_start or not self.date_end:
            raise UserError(_('Activate the membership before sending its badge.'))

        # The template generates a fresh PDF each time, including renewed dates.
        template = self.env.ref('fitzone.mail_template_membership_badge')
        mail_id = template.with_company(self.company_id).with_context(
            lang=self.member_id.lang or self.env.lang,
        ).send_mail(
            self.id, force_send=True, raise_exception=True,
            email_values={
                'email_to': recipient,
                'email_cc': False,
                'recipient_ids': [(5, 0, 0)],
                'auto_delete': False,
            },
        )
        # mail.template creates mail as sudo; inspect only this dispatch result.
        mail = self.env['mail.mail'].sudo().browse(mail_id)
        if mail.state != 'sent':
            raise UserError(_('The badge email was not sent. Please check the outgoing mail configuration.'))
        self.message_post(
            body=_('Membership badge sent by email to %s.', recipient),
            subtype_xmlid='mail.mt_note',
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Membership Badge'),
                'message': _('Badge email sent to %s.', recipient),
                'type': 'success',
                'sticky': False,
            },
        }

    installment_plan_count = fields.Integer(
        compute='_compute_installment_plan_count', compute_sudo=False,
        groups='fitzone.group_fitzone_manager,fitzone.group_fitzone_reception',
    )
    due_installment_count = fields.Integer(
        compute='_compute_due_installment_count', compute_sudo=False,
        groups='fitzone.group_fitzone_manager,fitzone.group_fitzone_reception',
    )

    @api.depends_context('uid', 'allowed_company_ids')
    def _compute_installment_plan_count(self):
        counts = grouped_counts(self, 'fitzone.installment.plan', 'membership_id', FINANCE_READERS)
        for membership in self:
            membership.installment_plan_count = counts.get(membership.id, 0)

    def _due_installment_domain(self):
        return [
            ('plan_id.membership_id', 'in', self.ids),
            ('status', '=', 'pending'),
            ('due_date', '<=', fields.Date.context_today(self)),
        ]

    @api.depends_context('uid', 'allowed_company_ids', 'tz')
    def _compute_due_installment_count(self):
        counts = {}
        persisted = self.filtered(lambda record: record.id and isinstance(record.id, int))
        if persisted and has_roles(self.env, FINANCE_READERS):
            persisted.check_access('read')
            plans = self.env['fitzone.installment.plan'].search([
                ('membership_id', 'in', persisted.ids),
            ])
            memberships = {plan.id: plan.membership_id.id for plan in plans}
            for plan, count in self.env['fitzone.installment']._read_group(
                persisted._due_installment_domain() + [('plan_id', 'in', plans.ids)],
                ['plan_id'], ['__count'],
            ):
                membership_id = memberships[plan.id]
                counts[membership_id] = counts.get(membership_id, 0) + count
        for membership in self:
            membership.due_installment_count = counts.get(membership.id, 0)

    def action_view_installment_plans(self):
        check_navigation(self, FINANCE_READERS, 'fitzone.installment.plan')
        return related_action(self, 'fitzone.action_fitzone_installment_plan',
                              [('membership_id', '=', self.id)],
                              {'default_membership_id': self.id})

    def action_view_due_installments(self):
        check_navigation(self, FINANCE_READERS, 'fitzone.installment')
        plans = self.env['fitzone.installment.plan'].search([('membership_id', '=', self.id)])
        return related_action(self, 'fitzone.action_fitzone_installment',
                              self._due_installment_domain() + [('plan_id', 'in', plans.ids)])

    def action_view_membership_invoice(self):
        check_navigation(self, FINANCE_READERS, 'account.move')
        invoice = self.invoice_id
        if not invoice:
            return False
        invoice.check_access('read')
        # Reception's existing ACL covers linked moves, not move lines/journals.
        native = self.env.su or has_roles(self.env, ('manager',)) or any(
            self.env.user.has_group(group) for group in (
                'account.group_account_invoice', 'account.group_account_readonly',
            )
        )
        view = self.env.ref(
            'account.view_move_form' if native else 'fitzone.view_membership_invoice_readonly'
        )
        return {
            'type': 'ir.actions.act_window', 'name': _('Invoice'),
            'res_model': 'account.move', 'res_id': invoice.id,
            'view_mode': 'form', 'views': [(view.id, 'form')],
            'target': 'current',
            'context': {'create': False, 'edit': False} if not native else {},
        }

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

    invoice_id = fields.Many2one(
        'account.move',
        string='Customer Invoice',
        readonly=True,
        copy=False,
        ondelete='restrict',
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
                    _('All-Inclusive can only be added to a General Membership.')
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
                _('This member already has an active or blocked membership '
                'for the same package during this period. '
                'The package can be purchased again after the current '
                'membership period ends.')
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals = dict(vals)

            if (
                vals.get('state') == 'active'
                and not self.env.context.get('allow_membership_activation')
            ):
                raise ValidationError(
                    _('Create memberships as Draft and use the Activate action '
                    'after the required payment.')
                )
            # Generate a membership number when needed.
            member_id = vals.get('member_id')

            if member_id:
                member = self.env['res.partner'].browse(member_id)

                if member.exists() and not member.membership_no:
                    member._assign_membership_number()

            if vals.get('state', 'draft') == 'draft':
                vals['date_start'] = False
                vals['date_end'] = False

            elif vals.get('state') == 'active':
                package_id = vals.get('package_id')

                if not package_id:
                    raise ValidationError(
                        _('Please select a package before activation.')
                    )

                package = self.env['product.template'].browse(package_id)
                duration = package.duration_months if package.exists() else 0

                if duration <= 0:
                    raise ValidationError(
                        _('The package must have a valid duration.')
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
                _('Membership dates are managed automatically by activation.')
            )

        if (
            vals.get('state') == 'active'
            and not self.env.context.get('allow_membership_activation')
        ):
            raise ValidationError(
                _('Use the Activate action to activate a membership.')
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

    def action_create_invoice(self):
        self.ensure_one()

        if self.state != 'draft':
            raise ValidationError(
                _('An invoice can only be created for a draft membership.')
            )
        if (
            self.package_id.package_type == 'general'
            and self.package_id.duration_months >= 3
        ):
            raise ValidationError(
                _('This package requires an installment plan. '
                'Create the installment plan instead of a regular invoice.')
            )

        if self.invoice_id:
            raise ValidationError(
                _('An invoice is already linked to this membership.')
            )

        plan = self.env['fitzone.installment.plan'].search(
            [('membership_id', '=', self.id)],
            limit=1,
        )
        if plan:
            raise ValidationError(
                _('This membership has an installment plan. '
                'Use the plan to manage its invoice and payments.')
            )

        if not self.member_id or not self.package_id:
            raise ValidationError(
                _('Select a member and package before creating an invoice.')
            )

        company = self.company_id
        product = self.package_id.product_variant_id
        taxes = self.package_id.taxes_id.filtered(
            lambda tax: tax.company_id == company
        )

        invoice = self.env['account.move'].with_company(company).create({
            'move_type': 'out_invoice',
            'partner_id': self.member_id.id,
            'company_id': company.id,
            'invoice_date': fields.Date.context_today(self),
            'currency_id': company.currency_id.id,
            'invoice_line_ids': [(0, 0, {
                'product_id': product.id,
                'name': self.package_id.name,
                'quantity': 1.0,
                'price_unit': self.final_price,
                'tax_ids': [(6, 0, taxes.ids)],
            })],
        })
        invoice.action_post()
        self.invoice_id = invoice.id

        return {
            'type': 'ir.actions.act_window',
            'name': 'Membership Invoice',
            'res_model': 'account.move',
            'res_id': invoice.id,
            'view_mode': 'form',
            'target': 'current',
        }

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
                        _('The first installment must be paid before activation.')
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
                        _('The first installment must have a successful payment '
                        'before activating this membership.')
                    )

            if not plans:
                invoice = membership.invoice_id
                if not invoice or invoice.state != 'posted':
                    raise ValidationError(
                        _('Create and post the membership invoice, then '
                        'register the full payment before activation.')
                    )
                if not invoice.currency_id.is_zero(invoice.amount_residual):
                    raise ValidationError(
                        _('The membership invoice must be fully paid '
                        'before activation.')
                    )

            if not membership.package_id:
                raise ValidationError(_('Please select a package.'))

            if membership.package_id.package_type == 'all_inclusive':
                raise ValidationError(
                    _('All-Inclusive must be added to a General Membership.')
                )

            duration = membership.package_id.duration_months

            if duration <= 0:
                raise ValidationError(
                    _('The package must have a valid duration.')
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
                        _('Unable to generate a membership barcode.')
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
                    _('Membership end date cannot be earlier than start date.')
                )
