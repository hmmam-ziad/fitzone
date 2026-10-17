from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


def reception_only(env):
    return (not env.su and env.user.has_group('fitzone.group_fitzone_reception')
            and not env.user.has_group('account.group_account_invoice'))


def checked(record):
    record.ensure_one()
    record.check_access('write')
    membership = record if record._name == 'fitzone.membership' else record.membership_id
    if membership.company_id not in record.env.companies:
        raise AccessError(_('The membership is outside your allowed companies.'))
    return record.sudo().with_context({
        'allowed_company_ids': record.env.companies.ids,
        'lang': record.env.lang,
    })


class Membership(models.Model):
    _inherit = 'fitzone.membership'

    @api.model_create_multi
    def create(self, vals_list):
        if reception_only(self.env) and any(vals.get('invoice_id') for vals in vals_list):
            raise AccessError(_('Use the membership invoicing workflow.'))
        return super().create(vals_list)

    def action_create_invoice(self):
        if reception_only(self.env):
            super(Membership, checked(self)).action_create_invoice()
            return self.action_membership_payment()
        return super().action_create_invoice()

    def action_activate(self):
        if reception_only(self.env):
            for record in self:
                super(Membership, checked(record)).action_activate()
            return True
        return super().action_activate()

    def write(self, vals):
        if reception_only(self.env) and 'invoice_id' in vals:
            raise AccessError(_('The membership invoice is assigned by the invoicing workflow.'))
        return super().write(vals)

    def action_membership_payment(self):
        checked(self)
        return {
            'type': 'ir.actions.act_window', 'name': _('Membership Payment'),
            'res_model': 'fitzone.membership.payment', 'view_mode': 'form',
            'target': 'new', 'context': {'default_membership_id': self.id},
        }


class InstallmentPlan(models.Model):
    _inherit = 'fitzone.installment.plan'

    @api.model_create_multi
    def create(self, vals_list):
        if reception_only(self.env) and any(vals.get('invoice_id') for vals in vals_list):
            raise AccessError(_('Use the installment scheduling workflow.'))
        return super().create(vals_list)

    def action_generate_schedule(self):
        if reception_only(self.env):
            for plan in self:
                super(InstallmentPlan, checked(plan)).action_generate_schedule()
            return True
        return super().action_generate_schedule()

    def write(self, vals):
        if reception_only(self.env) and 'invoice_id' in vals:
            raise AccessError(_('The plan invoice is assigned by the scheduling workflow.'))
        return super().write(vals)


class Installment(models.Model):
    _inherit = 'fitzone.installment'

    def action_register_payment(self):
        if reception_only(self.env):
            self.ensure_one()
            self.check_access('write')
            checked(self.plan_id)
            return {
                'type': 'ir.actions.act_window', 'name': _('Membership Payment'),
                'res_model': 'fitzone.membership.payment', 'view_mode': 'form',
                'target': 'new', 'context': {
                    'default_membership_id': self.plan_id.membership_id.id,
                    'default_installment_id': self.id,
                },
            }
        return super().action_register_payment()


class MembershipPayment(models.TransientModel):
    _name = 'fitzone.membership.payment'
    _description = 'Scoped Membership Payment'

    membership_id = fields.Many2one('fitzone.membership', required=True, readonly=True)
    installment_id = fields.Many2one('fitzone.installment', readonly=True)
    journal = fields.Selection(selection='_journals', required=True, string='Payment Journal')
    payment_date = fields.Date(required=True, default=fields.Date.context_today)

    @api.model
    def _journals(self):
        journals = self.env['account.journal'].sudo().search([
            ('company_id', 'in', self.env.companies.ids),
            ('type', 'in', ['bank', 'cash']),
            ('inbound_payment_method_line_ids', '!=', False),
        ])
        return [(str(j.id), j.display_name) for j in journals]

    def action_pay(self):
        self.ensure_one()
        self.check_access('write')
        if not (self.env.user.has_group('fitzone.group_fitzone_reception')
                or self.env.user.has_group('fitzone.group_fitzone_manager')):
            raise AccessError(_('Membership payment access is required.'))
        membership = checked(self.membership_id)
        invoice = membership.invoice_id
        context = {'allowed_company_ids': self.env.companies.ids,
                   'active_model': 'account.move', 'active_ids': invoice.ids}
        amount = invoice.amount_residual
        if self.installment_id:
            self.installment_id.check_access('write')
            installment = self.installment_id.sudo()
            if installment.plan_id.membership_id != membership:
                raise AccessError(_('The installment does not belong to this membership.'))
            # Reuse all existing residual, state and receivable validations.
            installment.action_register_payment()
            invoice = installment.plan_id.invoice_id
            context['active_ids'] = invoice.ids
            context['fitzone_installment_id'] = installment.id
            amount = installment.amount
        elif self.env['fitzone.installment.plan'].search_count([
                ('membership_id', '=', membership.id)]):
            raise ValidationError(_('Register this payment from the pending installment.'))
        if (not invoice or invoice.state != 'posted' or invoice.move_type != 'out_invoice'
                or invoice.company_id != membership.company_id
                or invoice.partner_id != membership.member_id or amount <= 0):
            raise ValidationError(_('A posted, unpaid membership customer invoice is required.'))
        journal = self.env['account.journal'].sudo().browse(int(self.journal)).exists()
        if (not journal or journal.company_id != invoice.company_id
                or journal.type not in ('bank', 'cash')):
            raise AccessError(_('Choose a cash or bank journal in the membership company.'))
        method = journal.inbound_payment_method_line_ids[:1]
        if not method:
            raise ValidationError(_('Configure an inbound payment method on this journal.'))
        wizard = self.env['account.payment.register'].sudo().with_context(context).create({
            'journal_id': journal.id, 'payment_method_line_id': method.id,
            'payment_date': self.payment_date, 'amount': amount,
        })
        # Existing FitZone installment override validates posting, reconciliation,
        # currency and amount, and activates after the first installment.
        payments = wizard._create_payments()
        payments.sudo().write({'membership_id': membership.id})
        if not self.installment_id:
            membership.action_activate()
        return {'type': 'ir.actions.act_window_close'}
