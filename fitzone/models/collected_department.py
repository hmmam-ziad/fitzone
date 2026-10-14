"""Live cash-basis allocation, separate from tax-exclusive accrual revenue."""
from odoo import _, api, fields, models, tools
from odoo.exceptions import AccessError
from .dashboard_queries import COLLECTED_ROWS


class CollectedDepartment(models.Model):
    _name = 'fitzone.collected.department'
    _description = 'Collected by Department (Cash basis)'
    _auto = False
    _order = 'date desc, department_id'
    _rec_name = 'department_name'

    date = fields.Date(readonly=True, string='Collection date')
    company_id = fields.Many2one('res.company', readonly=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    department_id = fields.Many2one('hr.department', readonly=True)
    department_name = fields.Char(readonly=True, string='Department name')
    collected_cash = fields.Monetary(readonly=True, string='Collected cash (Cash basis)')

    def _check_access(self, operation):
        result = super()._check_access(operation)
        if not self.env.user.has_group('fitzone.group_fitzone_manager'):
            return self, lambda: AccessError(self.env._('Only FitZone Managers may access financial reports.'))
        return result

    def _search(self, domain, *args, **kwargs):
        if not self.env.user.has_group('fitzone.group_fitzone_manager'):
            raise AccessError(self.env._('Only FitZone Managers may access financial reports.'))
        return super()._search(domain, *args, **kwargs)

    @api.model
    def get_view(self, view_id=None, view_type='form', **options):
        if view_type == 'form':
            raise AccessError(_('Aggregate reports are available as lists, pivots and graphs.'))
        return super().get_view(view_id, view_type, **options)

    def init(self):
        """Allocate gross company-currency receipts using tax-exclusive weights.

        Each partial reconciliation to a customer invoice/refund contributes
        signed reconciled amount * line balance / sum(product-line balances).
        Thus a 60 cash receipt on net lines 100/200 allocates 20/40, including
        the receipt's tax portion but using net weights. Negative payments reduce
        collections. Invoice credits and FX adjustments are not cash payments.
        Unmatched cash and invoices with zero/no net lines go to Unassigned.
        Dates are payment accounting dates, independent of invoice dates and the
        date reconciliation was performed. Unreconciliation updates history live.
        POS uses signed payment * net line subtotal / order net subtotal, converted
        at order currency_rate, on payment date in the company contact timezone.
        Pay-later POS entries are receivables, not cash. POS cash is counted once:
        POS accounting payments are excluded; subsequent real payments on
        pay-later invoices are allocated through reconciliation as usual.
        Account payments without a journal entry also go to Unassigned.
        """
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute('''CREATE VIEW fitzone_collected_department AS
            SELECT row_number() OVER (ORDER BY s.company_id,s.day,s.department)::integer AS id,
                s.company_id, s.day AS date, NULLIF(s.department,0) AS department_id,
                COALESCE(d.name->>'en_US','Unassigned') AS department_name,
                sum(s.collected_cash) AS collected_cash
            FROM (''' + COLLECTED_ROWS + ''') s
            LEFT JOIN hr_department d ON d.id=s.department
            GROUP BY s.company_id,s.day,s.department,d.name''')
