from odoo import api, models
from odoo.exceptions import ValidationError


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        installment_id = self.env.context.get("fitzone_installment_id")
        if installment_id:
            installment = self.env["fitzone.installment"].browse(
                installment_id
            ).exists()
            if installment and installment.status == "pending":
                amount = installment.amount
                currency = installment.plan_id.invoice_id.currency_id
                if "amount" in fields_list:
                    values["amount"] = amount
                if "custom_user_amount" in fields_list:
                    values["custom_user_amount"] = amount
                if "custom_user_currency_id" in fields_list:
                    values["custom_user_currency_id"] = currency.id
                if "currency_id" in fields_list:
                    values["currency_id"] = currency.id
        return values

    def _create_payments(self):
        payments = super()._create_payments()

        installment_id = self.env.context.get('fitzone_installment_id')
        if not installment_id:
            return payments

        installment = self.env['fitzone.installment'].browse(
            installment_id
        ).exists()
        if not installment or installment.status != 'pending':
            raise ValidationError(
                'The installment is no longer pending.'
            )

        currency = installment.plan_id.invoice_id.currency_id
        posted_payments = payments.filtered(
            lambda payment:
                payment.state in ('paid', 'in_process')
                and payment.move_id.state == 'posted'
        )
        paid_amount = sum(posted_payments.mapped('amount'))

        if currency.compare_amounts(paid_amount, installment.amount) != 0:
            raise ValidationError(
                'The registered payment amount does not match '
                'the installment amount. The installment was not marked paid.'
            )

        if not posted_payments:
            raise ValidationError(
                'No successfully posted payment was found.'
            )

        installment.write({
            'status': 'paid',
            'payment_id': posted_payments[0].id,
        })

        plan = installment.plan_id
        pending = plan.installment_ids.filtered(
            lambda item: item.status == 'pending'
        )

        if not pending:
            plan.status = 'completed'
        else:
            plan.status = 'active'

        # Activate the membership only after its down payment is paid.
        first_installment = plan.installment_ids.sorted(
            lambda item: (item.due_date, item.id)
        )[:1]

        if (
            first_installment
            and first_installment.id == installment.id
            and plan.membership_id.state == 'draft'
        ):
            plan.membership_id.action_activate()

        return payments
