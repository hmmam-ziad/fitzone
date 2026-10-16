from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class Installment(models.Model):
    _name = 'fitzone.installment'
    _description = 'Installment'
    _order = 'due_date, id'

    plan_id = fields.Many2one(
        'fitzone.installment.plan', required=True, ondelete='restrict'
    )
    due_date = fields.Date(required=True)
    amount = fields.Float(required=True)
    payment_id = fields.Many2one(
        'account.payment', string='Registered Payment',
        readonly=True, copy=False,
    )
    status = fields.Selection([
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='pending', required=True, copy=False)

    is_overdue = fields.Boolean(
        string='Overdue', compute='_compute_is_overdue'
    )

    @api.depends('due_date', 'status')
    def _compute_is_overdue(self):
        today = fields.Date.context_today(self)
        for installment in self:
            installment.is_overdue = bool(
                installment.due_date
                and installment.due_date <= today
                and installment.status == 'pending'
            )

    def action_register_payment(self):
        self.ensure_one()

        if self.status != 'pending':
            raise UserError('Only pending installments can be paid.')

        invoice = self.plan_id.invoice_id
        if not invoice or invoice.state != 'posted':
            raise ValidationError(_('A posted customer invoice is required before payment.'))

        if invoice.currency_id.compare_amounts(
            invoice.amount_residual, self.amount
        ) < 0:
            raise ValidationError(_('The invoice residual is less than this installment amount.'))

        receivable_lines = invoice.line_ids.filtered(
            lambda line:
                line.account_id.account_type == 'asset_receivable'
                and not line.reconciled
        )
        if not receivable_lines:
            raise ValidationError(_('No outstanding receivable balance was found on the invoice.'))

        action = invoice.action_register_payment()
        context = dict(action.get('context', {}))
        context.update({
            'fitzone_installment_id': self.id,
            'default_custom_user_amount': self.amount,
            'default_custom_user_currency_id': invoice.currency_id.id,
            'default_amount': self.amount,
        })
        action['context'] = context
        return action

    def write(self, vals):
        if 'payment_id' in vals:
            for installment in self:
                if (
                    installment.payment_id
                    and vals['payment_id'] != installment.payment_id.id
                ):
                    raise UserError(
                        'The registered payment of an installment cannot be changed.'
                    )

                if vals['payment_id'] and vals.get('status') != 'paid':
                    raise UserError(
                        'A payment can only be assigned when confirming the installment.'
                    )

        if vals.get('status') == 'paid':
            for installment in self:
                if installment.status == 'paid':
                    continue

                payment_id = vals.get(
                    'payment_id',
                    installment.payment_id.id,
                )
                payment = self.env['account.payment'].browse(
                    payment_id
                ).exists()

                if not payment:
                    raise UserError(
                        'A valid registered payment is required.'
                    )

                invoice = installment.plan_id.invoice_id
                if not invoice or invoice.state != 'posted':
                    raise ValidationError(_('A posted installment-plan invoice is required.'))

                if (
                    payment.state not in ('paid', 'in_process')
                    or not payment.move_id
                    or payment.move_id.state != 'posted'
                ):
                    raise ValidationError(_('The payment must be successfully processed and posted.'))

                if payment.partner_id != invoice.partner_id:
                    raise ValidationError(_('The payment customer does not match the invoice customer.'))

                if payment.currency_id != invoice.currency_id:
                    raise ValidationError(_('The payment currency does not match the invoice currency.'))

                if invoice not in payment.reconciled_invoice_ids:
                    raise ValidationError(_('The payment must be reconciled with the installment-plan invoice.'))

                if invoice.currency_id.compare_amounts(
                    payment.amount, installment.amount
                ) != 0:
                    raise ValidationError(_('The payment amount does not match the installment amount.'))

                duplicate = self.search_count([
                    ('payment_id', '=', payment.id),
                    ('id', '!=', installment.id),
                    ('status', '=', 'paid'),
                ])
                if duplicate:
                    raise ValidationError(_('This payment has already been used for another installment.'))

        elif 'status' in vals:
            for installment in self:
                if (
                    installment.status == 'paid'
                    and vals['status'] != 'paid'
                ):
                    raise UserError(
                        'A paid installment cannot be reopened or cancelled.'
                    )

        return super().write(vals)
