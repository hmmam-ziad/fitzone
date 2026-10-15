from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class InstallmentPlan(models.Model):
    _name = 'fitzone.installment.plan'
    _description = 'Installment Plan'
    _rec_name = 'membership_id'

    membership_id = fields.Many2one(
        'fitzone.membership', string='Membership',
        required=True, ondelete='restrict',
    )
    invoice_id = fields.Many2one(
        'account.move', string='Customer Invoice',
        readonly=True, copy=False, ondelete='restrict',
    )
    total_amount = fields.Float(
        string='Total Amount Including Tax',
        compute='_compute_total_amount', store=True, readonly=True,
    )
    down_payment = fields.Float(
        string='Down Payment',
        required=True,
        default=50.0,
    )
    installment_ids = fields.One2many(
        'fitzone.installment', 'plan_id',
        string='Installments', copy=False,
    )
    status = fields.Selection([
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], default='draft', required=True, copy=False)

    @api.depends(
        'membership_id.final_price',
        'membership_id.package_id.taxes_id',
        'membership_id.member_id',
        'membership_id.company_id',
        'membership_id.package_id.taxes_id.price_include_override',
        'membership_id.package_id.taxes_id.amount',
        'membership_id.company_id.account_price_include',
    )
    def _compute_total_amount(self):
        for plan in self:
            membership = plan.membership_id
            if not membership or not membership.package_id:
                plan.total_amount = 0.0
                continue

            company = membership.company_id
            taxes = membership.package_id.taxes_id.filtered(
                lambda tax: tax.company_id == company
            )
            result = taxes.compute_all(
                membership.final_price,
                currency=company.currency_id,
                quantity=1.0,
                product=membership.package_id.product_variant_id,
                partner=membership.member_id,
            )
            plan.total_amount = result['total_included']

    @api.constrains('membership_id', 'down_payment')
    def _check_installment_plan(self):
        for plan in self:
            membership = plan.membership_id
            if not membership:
                continue
            if membership.package_type != 'general':
                raise ValidationError(_('Installments are only available for General Memberships.'))
            if membership.package_id.duration_months < 3:
                raise ValidationError(_('Installments require a membership of at least 3 months.'))
            if plan.down_payment < 50:
                raise ValidationError(_('The down payment must be at least JD 50.'))
            if plan.down_payment > plan.total_amount:
                raise ValidationError(_('The down payment cannot exceed the total membership price.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            membership_id = vals.get('membership_id')
            if membership_id and self.search(
                [('membership_id', '=', membership_id)], limit=1
            ):
                raise ValidationError(_('This membership already has an installment plan.'))
        return super().create(vals_list)

    def action_generate_schedule(self):
        for plan in self:
            if plan.status != 'draft':
                raise ValidationError(_('A schedule can only be generated for a draft plan.'))
            if plan.installment_ids or plan.invoice_id:
                raise ValidationError(_('An installment schedule or invoice already exists.'))

            membership = plan.membership_id
            package = membership.package_id
            duration = package.duration_months

            if membership.state != 'draft':
                raise ValidationError(_('Create the installment plan before activating the membership.'))
            if not membership.member_id:
                raise ValidationError(_('Select a customer for the membership.'))
            if (
                package.package_type != 'general'
                or duration < 3
            ):
                raise ValidationError(_('Installment plans are available only for General '
                    'Membership packages of three months or more.'))
            if duration <= 1:
                raise ValidationError(_('The package duration must allow multiple installments.'))
            if plan.total_amount <= 0:
                raise ValidationError(_('The installment plan total must be greater than zero.'))
            if (
                plan.down_payment <= 0
                or plan.down_payment >= plan.total_amount
            ):
                raise ValidationError(_('The down payment must be greater than zero and '
                    'less than the plan total.'))

            company = membership.company_id
            currency = company.currency_id

            expected_total = package.taxes_id.filtered(
                lambda tax: tax.company_id == company
            ).compute_all(
                membership.final_price,
                currency=currency,
                quantity=1.0,
                product=package.product_variant_id,
                partner=membership.member_id,
            )['total_included']

            if currency.compare_amounts(
                plan.total_amount, expected_total
            ) != 0:
                raise ValidationError(_('The installment plan total must match the membership price including tax.'))

            invoice = membership.invoice_id

            if invoice:
                if invoice.state != 'posted':
                    raise ValidationError(_('The linked membership invoice must be posted.'))
                if invoice.move_type != 'out_invoice':
                    raise ValidationError(_('The linked document must be a customer invoice.'))
                if invoice.partner_id != membership.member_id:
                    raise ValidationError(_('The invoice customer must match the membership customer.'))
                if invoice.currency_id != currency:
                    raise ValidationError(_('The invoice currency must match the plan currency.'))
                if currency.compare_amounts(
                    invoice.amount_total, plan.total_amount
                ) != 0:
                    raise ValidationError(_('The invoice total must match the installment plan total.'))
                if currency.compare_amounts(
                    invoice.amount_residual, plan.total_amount
                ) != 0:
                    raise ValidationError(_('The linked invoice already has a payment or adjustment. '
                        'Review it before creating this installment schedule.'))
            else:
                product = package.product_variant_id
                taxes = package.taxes_id.filtered(
                    lambda tax: tax.company_id == company
                )

                invoice = self.env['account.move'].with_company(company).create({
                    'move_type': 'out_invoice',
                    'partner_id': membership.member_id.id,
                    'company_id': company.id,
                    'invoice_date': fields.Date.context_today(plan),
                    'currency_id': currency.id,
                    'invoice_line_ids': [(0, 0, {
                        'product_id': product.id,
                        'name': package.name,
                        'quantity': 1.0,
                        'price_unit': membership.final_price,
                        'tax_ids': [(6, 0, taxes.ids)],
                    })],
                })
                invoice.action_post()
                membership.invoice_id = invoice.id

            plan.invoice_id = invoice.id

            remaining = plan.total_amount - plan.down_payment
            monthly = remaining / (duration - 1)
            start_date = fields.Date.context_today(plan)
            values = [{
                'plan_id': plan.id,
                'due_date': start_date,
                'amount': plan.down_payment,
            }]
            allocated = plan.down_payment

            for month in range(1, duration - 1):
                amount = currency.round(monthly)
                allocated += amount
                values.append({
                    'plan_id': plan.id,
                    'due_date': start_date + relativedelta(months=month),
                    'amount': amount,
                })

            values.append({
                'plan_id': plan.id,
                'due_date': start_date + relativedelta(months=duration - 1),
                'amount': plan.total_amount - allocated,
            })

            self.env['fitzone.installment'].create(values)
            plan.status = 'scheduled'
