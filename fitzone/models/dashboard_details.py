"""Manager-only, read-only transaction projections for dashboard navigation.

Financial projections consume the very same line/allocation queries as the
aggregate reports. Operational projections retain source IDs, never snapshots.
"""
from datetime import datetime, time, timedelta

import logging

import pytz
from odoo import api, fields, models, tools, _
from odoo.exceptions import AccessError
from .dashboard_queries import FINANCIAL_DETAIL_ROWS, COLLECTED_DETAIL_ROWS


_logger = logging.getLogger(__name__)

# Explicit IDs: installation tests validate every entry, including optional views.
DETAIL_VIEWS = {
    'financial': {'list': 'fitzone.financial_list', 'search': 'fitzone.financial_detail_search', 'pivot': 'fitzone.financial_detail_pivot', 'graph': 'fitzone.financial_detail_graph'},
    'collected': {'list': 'fitzone.collected_list', 'search': 'fitzone.collected_detail_search', 'pivot': 'fitzone.collected_detail_pivot', 'graph': 'fitzone.collected_detail_graph'},
    'operational_membership': {'list': 'fitzone.operational_membership_list', 'search': 'fitzone.operational_detail_search', 'pivot': 'fitzone.operational_detail_pivot', 'graph': 'fitzone.operational_detail_graph'},
    'operational_installment': {'list': 'fitzone.operational_installment_list', 'search': 'fitzone.operational_detail_search', 'pivot': 'fitzone.operational_detail_pivot', 'graph': 'fitzone.operational_detail_graph'},
    'operational_injury': {'list': 'fitzone.operational_injury_list', 'search': 'fitzone.operational_detail_search', 'pivot': 'fitzone.operational_detail_pivot', 'graph': 'fitzone.operational_detail_graph'},
    'operational_class': {'list': 'fitzone.operational_class_list', 'search': 'fitzone.operational_detail_search', 'pivot': 'fitzone.operational_detail_pivot', 'graph': 'fitzone.operational_detail_graph'},
    'operational_session': {'list': 'fitzone.operational_session_list', 'search': 'fitzone.operational_detail_search', 'pivot': 'fitzone.operational_detail_pivot', 'graph': 'fitzone.operational_detail_graph'},
    'operational_member': {'list': 'fitzone.operational_member_list', 'search': 'fitzone.operational_detail_search', 'pivot': 'fitzone.operational_detail_pivot', 'graph': 'fitzone.operational_detail_graph'},
    'manual': {'list': 'fitzone.manual_list', 'search': 'fitzone.manual_detail_search'},
}


class DashboardDetailAccess(models.AbstractModel):
    _name = 'fitzone.dashboard.detail.access'
    _description = 'Management detail access gate'

    def _check_access(self, operation):
        result = super()._check_access(operation)
        if not self.env.user.has_group('fitzone.group_fitzone_manager') or operation != 'read':
            return self, lambda: AccessError(_('Only Managers may read dashboard details.'))
        return result

    def _search(self, domain, *args, **kwargs):
        self.env['fitzone.management.dashboard']._check_management()
        return super()._search(domain, *args, **kwargs)

    @api.model
    def get_view(self, view_id=None, view_type='form', **options):
        self.env['fitzone.management.dashboard']._check_management()
        if view_type == 'form':
            raise AccessError(_('Dashboard details are available as lists, pivots and graphs.'))
        return super().get_view(view_id, view_type, **options)


class FinancialDetail(models.Model):
    _name = 'fitzone.financial.detail'
    _inherit = 'fitzone.dashboard.detail.access'
    _description = 'Revenue vs Expenses — Transactions'
    _auto = False
    _order = 'date desc, id'
    _rec_name = 'reference'

    date = fields.Date(readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    department_id = fields.Many2one('hr.department', readonly=True)
    type = fields.Char(readonly=True)
    source = fields.Char(readonly=True)
    type_label = fields.Char(compute='_compute_display_labels')
    source_label = fields.Char(compute='_compute_display_labels')
    origin_model = fields.Char(readonly=True)
    origin_id = fields.Integer(readonly=True)
    reference = fields.Char(readonly=True, string='Document / Expense')
    partner_id = fields.Many2one('res.partner', readonly=True, string='Customer / Vendor')
    product_id = fields.Many2one('product.product', readonly=True)
    quantity = fields.Float(readonly=True)
    account_id = fields.Many2one('account.account', readonly=True)
    purchase_order_id = fields.Many2one('purchase.order', readonly=True)
    amount = fields.Monetary(readonly=True, string='Untaxed amount')
    signed_amount = fields.Monetary(readonly=True, string='Signed amount / Net')

    @api.depends('type', 'source')
    def _compute_display_labels(self):
        type_labels = {
            'Revenue': _('Revenue'),
            'Manual expense': _('Manual expense'),
            'Purchase expense': _('Purchase expense'),
        }
        source_labels = {
            'POS': _('POS'),
            'Manual': _('Manual'),
            'Invoice': _('Invoice'),
            'Credit note': _('Credit note'),
            'Vendor bill': _('Vendor bill'),
            'Vendor credit note': _('Vendor credit note'),
        }
        for record in self:
            record.type_label = type_labels.get(record.type, record.type or '')
            record.source_label = source_labels.get(record.source, record.source or '')

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute('''CREATE VIEW fitzone_financial_detail AS
            SELECT (origin_id::bigint*4 + CASE WHEN source='POS' THEN 1
                WHEN type='Manual expense' THEN 2 ELSE 0 END) AS id,
                company_id, day AS date, NULLIF(department,0) AS department_id,
                type, source, origin_model, origin_id, reference, partner_id, product_id,
                quantity, account_id, purchase_order_id,
                revenue+manual_expenses+purchase_expenses AS amount,
                revenue-manual_expenses-purchase_expenses AS signed_amount
            FROM (''' + FINANCIAL_DETAIL_ROWS + ''') s''')


class CollectedDetail(models.Model):
    _name = 'fitzone.collected.detail'
    _inherit = 'fitzone.dashboard.detail.access'
    _description = 'Collected Cash — Payment Allocations'
    _auto = False
    _order = 'date desc, id'
    _rec_name = 'reference'

    date = fields.Date(readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    department_id = fields.Many2one('hr.department', readonly=True)
    source = fields.Char(readonly=True)
    source_label = fields.Char(compute='_compute_display_labels')
    origin_model = fields.Char(readonly=True)
    origin_id = fields.Integer(readonly=True)
    reference = fields.Char(readonly=True, string='Payment / Receipt')
    invoice_id = fields.Many2one('account.move', readonly=True)
    pos_order_id = fields.Many2one('pos.order', readonly=True)
    partner_id = fields.Many2one('res.partner', readonly=True)
    allocation_line_id = fields.Integer(readonly=True, string='Settled product line ID')
    reconcile_id = fields.Integer(readonly=True, string='Reconciliation ID')
    amount = fields.Monetary(readonly=True, string='Allocated cash (includes tax)')

    @api.depends('source')
    def _compute_display_labels(self):
        source_labels = {
            'Invoice payment': _('Invoice payment'),
            'POS': _('POS'),
            'Manual': _('Manual'),
        }
        for record in self:
            record.source_label = source_labels.get(record.source, record.source or '')

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute('''CREATE VIEW fitzone_collected_detail AS
            SELECT row_number() OVER (ORDER BY s.company_id,s.origin_model,s.origin_id,
                    s.reconcile_id,s.allocation_line_id) AS id,
                s.company_id, s.day AS date, NULLIF(s.department,0) AS department_id,
                s.source, s.origin_model, s.origin_id, s.invoice_id, s.pos_order_id,
                s.allocation_line_id, s.reconcile_id, s.collected_cash AS amount,
                COALESCE(m.name,ap.name,po.name) AS reference,
                COALESCE(m.partner_id,ap.partner_id,po.partner_id) AS partner_id
            FROM (''' + COLLECTED_DETAIL_ROWS + ''') s
            LEFT JOIN account_move_line ml ON s.origin_model='account.move.line' AND ml.id=s.origin_id
            LEFT JOIN account_move m ON m.id=ml.move_id
            LEFT JOIN account_payment ap ON s.origin_model='account.payment' AND ap.id=s.origin_id
            LEFT JOIN pos_payment pp ON s.origin_model='pos.payment' AND pp.id=s.origin_id
            LEFT JOIN pos_order po ON po.id=pp.pos_order_id''')


class OperationalDetail(models.Model):
    _name = 'fitzone.operational.detail'
    _inherit = 'fitzone.dashboard.detail.access'
    _description = 'Management Operational Records'
    _auto = False
    _order = 'date desc, id'
    _rec_name = 'reference'

    company_id = fields.Many2one('res.company', readonly=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    department_id = fields.Many2one('hr.department', readonly=True)
    type = fields.Char(readonly=True)
    source = fields.Char(readonly=True)
    type_label = fields.Char(compute='_compute_display_labels')
    source_label = fields.Char(compute='_compute_display_labels')
    origin_id = fields.Integer(readonly=True)
    reference = fields.Char(readonly=True)
    date = fields.Date(readonly=True)
    date_end = fields.Date(readonly=True)
    start_datetime = fields.Datetime(readonly=True)
    end_datetime = fields.Datetime(readonly=True)
    member_id = fields.Many2one('res.partner', readonly=True)
    product_id = fields.Many2one('product.template', readonly=True, string='Plan / Package')
    plan_id = fields.Many2one('fitzone.installment.plan', readonly=True)
    status = fields.Char(readonly=True)
    amount = fields.Monetary(readonly=True)
    original_amount = fields.Float(readonly=True)
    original_currency_id = fields.Many2one('res.currency', readonly=True)
    cause_id = fields.Many2one('fitzone.injury.cause', readonly=True)
    sport = fields.Char(readonly=True)
    room_id = fields.Many2one('fitzone.room', readonly=True)
    employee_id = fields.Many2one('hr.employee', readonly=True, string='Trainer / Specialist')
    user_id = fields.Many2one('res.users', readonly=True, string='Specialist user')
    booked_seats = fields.Integer(readonly=True)
    offered_seats = fields.Integer(readonly=True)
    sessions = fields.Integer(readonly=True)
    converted = fields.Integer(readonly=True)

    @api.depends('type', 'source')
    def _compute_display_labels(self):
        type_labels = {
            'Membership': _('Membership'),
            'Installment': _('Installment'),
            'Injury': _('Injury'),
            'Injury sport': _('Injury sport'),
            'Class': _('Class'),
            'Session': _('Session'),
            'Member': _('Member'),
        }
        source_labels = {
            'fitzone.membership': _('Membership'),
            'fitzone.installment': _('Installment'),
            'fitzone.injury': _('Injury'),
            'fitzone.injury.sport': _('Injury sport'),
            'fitzone.gym.class': _('Class'),
            'fitzone.pt.session': _('PT Session'),
            'fitzone.pool.booking': _('Pool Booking'),
            'fitzone.rehabilitation': _('Rehabilitation'),
            'fitzone.nutrition.consultation': _('Nutrition Consultation'),
            'res.partner': _('Member'),
        }
        for record in self:
            record.type_label = type_labels.get(record.type, record.type or '')
            record.source_label = source_labels.get(record.source, record.source or '')

    @property
    def _table_query(self):
        # Period context is carried by every action, including pivot/export RPCs.
        company = self.env.company
        end = fields.Date.to_date(self.env.context.get('dashboard_date_to')) or fields.Date.context_today(self)
        start = fields.Date.to_date(self.env.context.get('dashboard_date_from')) or end.replace(day=1)
        tz = pytz.timezone(company.partner_id.tz or 'UTC')
        begin = tz.localize(datetime.combine(start, time.min)).astimezone(pytz.utc).replace(tzinfo=None)
        finish = tz.localize(datetime.combine(end+timedelta(days=1), time.min)).astimezone(pytz.utc).replace(tzinfo=None)
        params = dict(company=company.id, start=start, end=end, begin=begin, finish=finish)
        def literal(value):
            return self.env.cr.mogrify('%s', (value,)).decode()
        columns = dict(company_id='NULL::integer', department_id='NULL::integer', type="''::varchar",
            source="''::varchar", origin_id='0::integer', reference="''::varchar", date='NULL::date',
            date_end='NULL::date', start_datetime='NULL::timestamp', end_datetime='NULL::timestamp', member_id='NULL::integer', product_id='NULL::integer',
            plan_id='NULL::integer', status="''::varchar", amount='0::numeric',
            original_amount='0::numeric', original_currency_id='NULL::integer',
            cause_id='NULL::integer', sport="''::varchar", room_id='NULL::integer',
            employee_id='NULL::integer', user_id='NULL::integer', booked_seats='0::integer',
            offered_seats='0::integer', sessions='0::integer', converted='0::integer')
        queries = []
        def add(source, table, **values):
            values['source'] = literal(source)
            row = dict(columns, **values)
            queries.append('SELECT '+','.join(f'{value} AS {key}' for key, value in row.items())+' FROM '+table)
        add('fitzone.membership', 'fitzone_membership m JOIN product_template t ON t.id=m.package_id',
            company_id='m.company_id', department_id='t.fitzone_department', type="'Membership'",
            origin_id='m.id', reference="'Membership #'||m.id", date='m.date_start', date_end='m.date_end',
            member_id='m.member_id', product_id='m.package_id', status='m.state')
        # Allocate conversion rounding cumulatively within each aging bucket and
        # currency: the footer equals conversion of the grouped dashboard amount.
        rates = self.env['res.currency'].sudo().with_context(active_test=False).search([])
        rate_case = 'CASE a.currency_id '+ ' '.join(
            f'WHEN {c.id} THEN {c._convert(1, company.currency_id, company, end, round=False)!r}' for c in rates)+' ELSE 1 END'
        dept = self.env.context.get('dashboard_department')
        dept_where = '' if dept is None or dept is False or dept == '' else ' AND COALESCE((SELECT id FROM hr_department WHERE id=t.fitzone_department AND (company_id IS NULL OR company_id=m.company_id)),0)='+str(int(dept))
        partition = "PARTITION BY a.company_id,a.currency_id,CASE WHEN i.due_date<"+literal(start)+" THEN 0 WHEN i.due_date<"+literal(end)+" THEN 1 WHEN i.due_date<="+literal(end+timedelta(days=(end-start).days+1))+" THEN 2 ELSE 3 END ORDER BY i.id"
        cumulative = f'sum(i.amount*({rate_case})) OVER ({partition})'
        digits = company.currency_id.decimal_places
        add('fitzone.installment', '''fitzone_installment i JOIN fitzone_installment_plan p ON p.id=i.plan_id
            JOIN fitzone_membership m ON m.id=p.membership_id JOIN product_template t ON t.id=m.package_id
            JOIN account_move a ON a.id=p.invoice_id WHERE a.company_id=m.company_id AND i.status='pending' '''+dept_where,
            company_id='m.company_id', department_id='t.fitzone_department', type="'Installment'",
            origin_id='i.id', reference="'Installment #'||i.id", date='i.due_date', member_id='m.member_id',
            product_id='m.package_id', plan_id='p.id', status='i.status', original_amount='i.amount', original_currency_id='a.currency_id',
            amount=f'round(({cumulative})::numeric,{digits})-round((({cumulative})-i.amount*({rate_case}))::numeric,{digits})')
        add('fitzone.injury', 'fitzone_injury i', company_id='i.company_id', department_id='i.department_id',
            type="'Injury'", origin_id='i.id', reference="'Injury #'||i.id", date='i.injury_date',
            member_id='i.member_id', cause_id='i.injury_cause_id', status='i.state',
            sport="COALESCE((SELECT string_agg(DISTINCT NULLIF(r.sport_type,''),', ' ORDER BY NULLIF(r.sport_type,'')) FROM fitzone_rehabilitation r WHERE r.injury_id=i.id AND r.company_id=i.company_id),'Unspecified')")
        add('fitzone.injury.sport', """fitzone_injury i LEFT JOIN
            (SELECT DISTINCT injury_id, company_id, COALESCE(NULLIF(sport_type,''),'Unspecified') AS sport
             FROM fitzone_rehabilitation) r ON r.injury_id=i.id AND r.company_id=i.company_id""",
            company_id='i.company_id', department_id='i.department_id', type="'Injury sport'",
            origin_id='i.id', reference="'Injury #'||i.id", date='i.injury_date', member_id='i.member_id',
            cause_id='i.injury_cause_id', sport="COALESCE(r.sport,'Unspecified')", status='i.state')
        add('fitzone.gym.class', '''fitzone_gym_class c JOIN fitzone_room r ON r.id=c.room_id AND r.company_id=c.company_id
            LEFT JOIN fitzone_trainer t ON t.id=c.trainer_id''',
            company_id='c.company_id', department_id='c.department_id', type="'Class'", origin_id='c.id',
            reference='c.name', date="(c.start_datetime AT TIME ZONE 'UTC' AT TIME ZONE "+literal(tz.zone)+")::date",
            date_end="(c.end_datetime AT TIME ZONE 'UTC' AT TIME ZONE "+literal(tz.zone)+")::date",
            start_datetime='c.start_datetime', end_datetime='c.end_datetime', room_id='c.room_id', employee_id='t.employee_id', offered_seats='r.capacity', sessions='1',
            booked_seats="(SELECT count(*) FROM fitzone_class_booking b WHERE b.class_id=c.id AND b.company_id=c.company_id AND b.status IN ('booked','attended'))")
        add('fitzone.pt.session', "fitzone_pt_session s JOIN fitzone_trainer t ON t.id=s.trainer_id WHERE s.state='completed'",
            company_id='s.company_id', department_id='s.department_id', type="'Session'", origin_id='s.id', reference="'PT #'||s.id",
            date="(s.session_date AT TIME ZONE 'UTC' AT TIME ZONE "+literal(tz.zone)+")::date", start_datetime='s.session_date', member_id='s.member_id', employee_id='t.employee_id', sessions='1')
        add('fitzone.pool.booking', '''(SELECT b.company_id,b.department_id,b.trainer_id,b.session_date,b.pool_slot_id,min(b.id) AS id
            FROM fitzone_pool_booking b WHERE b.status!='cancelled'
            GROUP BY b.company_id,b.department_id,b.trainer_id,b.session_date,b.pool_slot_id) b
            JOIN fitzone_trainer t ON t.id=b.trainer_id''', company_id='b.company_id', department_id='b.department_id', type="'Session'",
            origin_id='b.id', reference="'Pool slot #'||b.pool_slot_id", date='b.session_date', employee_id='t.employee_id', sessions='1')
        add('fitzone.rehabilitation', 'fitzone_rehabilitation r', company_id='r.company_id', department_id='r.department_id', type="'Session'",
            origin_id='r.id', reference="'Rehabilitation #'||r.id", date='r.start_date', member_id='r.member_id', employee_id='r.physiotherapist_id', sessions='1')
        add('fitzone.nutrition.consultation', '''fitzone_nutrition_consultation n LEFT JOIN hr_employee e
            ON e.user_id=n.nutritionist_id AND e.company_id=n.company_id''', company_id='n.company_id', department_id='n.department_id', type="'Session'",
            origin_id='n.id', reference="'Consultation #'||n.id", date='n.consult_date', member_id='n.member_id', employee_id='e.id', user_id='n.nutritionist_id', sessions='1')
        from .dashboard_queries import EVENTS
        events = self.env.cr.mogrify(EVENTS, params).decode()
        add('res.partner', '''res_partner p LEFT JOIN (SELECT member_id,count(DISTINCT department) AS departments
            FROM ('''+events+''') ev WHERE department<>0 GROUP BY member_id) usage ON usage.member_id=p.id
            ''', company_id=str(company.id), type="'Member'", origin_id='p.id', reference='p.name', member_id='p.id',
            converted='CASE WHEN usage.departments>1 THEN 1 ELSE 0 END')
        return '''SELECT row_number() OVER (ORDER BY s.source,s.origin_id,s.employee_id,s.sport) AS id,
            '''+','.join('s.'+key if key != 'department_id' else
                'CASE WHEN d.company_id IS NULL OR d.company_id=s.company_id THEN s.department_id ELSE NULL END AS department_id'
                for key in columns)+''' FROM ('''+ ' UNION ALL '.join(queries)+''') s
            LEFT JOIN hr_department d ON d.id=s.department_id'''


class DashboardDetailActions(models.AbstractModel):
    _inherit = 'fitzone.management.dashboard'

    def _detail_actions(self, start, end, department, begin, finish, new_members, conversion):
        company = self.env.company
        department_label = (_('Unassigned') if department == 0 else
            self.env['hr.department'].sudo().browse(department).name if department else _('All departments'))
        period = start.strftime('%b %Y') if start.day == 1 and (end+timedelta(days=1)).day == 1 else f'{start} – {end}'
        context = dict(self.env.context, create=False, edit=False, delete=False,
            dashboard_date_from=str(start), dashboard_date_to=str(end), dashboard_department=department,
            allowed_company_ids=[company.id])
        base = [('company_id', '=', company.id)]
        dept_domain = [('department_id', '=', department or False)] if department is not None else []
        period_domain = [('date', '>=', str(start)), ('date', '<=', str(end))]
        def action(label, model, domain, view, groups=()):
            safe = dict(type='ir.actions.act_window', name=f'{label} - {department_label} - {period}',
                res_model=model, view_mode='list', views=[[False, 'list']],
                domain=[('id', '=', 0)], context=dict(context), target='current')
            try:
                # Roll back database errors for this drill without poisoning the RPC.
                with self.env.cr.savepoint():
                    resolved = {}
                    for mode, xmlid in DETAIL_VIEWS[view].items():
                        record = self.env.ref(xmlid, raise_if_not_found=False)
                        # Only view metadata needs elevation; transaction access stays with the Manager.
                        record = record.sudo() if record else record
                        if record and (record._name != 'ir.ui.view' or record.model != model or record.type != mode):
                            raise ValueError(f'Invalid {mode} view {xmlid} for {model}')
                        if not record:
                            _logger.warning('Dashboard %s missing %s view %s; using automatic view', label, mode, xmlid)
                        resolved[mode] = record.id if record else False
                    modes = [mode for mode in ('list', 'pivot', 'graph') if mode in resolved]
                    result = dict(safe, view_mode=','.join(modes),
                        views=[[resolved[mode], mode] for mode in modes], domain=domain,
                        context=dict(context, group_by=list(groups)))
                    if resolved.get('search'):
                        result['search_view_id'] = [resolved['search'], '']
                    return result
            except Exception:
                _logger.exception('Cannot build dashboard drill %s (%s); returning an empty list', label, view)
                return safe
        def finance(label, kinds, groups=('source', 'product_id')):
            return action(label, 'fitzone.financial.detail', base+dept_domain+period_domain+[('type','in',kinds)],
                          'financial', groups)
        def operational(label, domain, view, groups=()):
            return action(label, 'fitzone.operational.detail', base+domain, view, groups)
        membership = dept_domain+[('type','=','Membership'), ('status','in',['active','expired']), ('date','<=',str(end))]
        installment = dept_domain+[('type','=','Installment'), ('status','=','pending')]
        classes = dept_domain+[('type','=','Class'), ('start_datetime','<',str(finish)), ('end_datetime','>',str(begin))]
        actions = dict(
            total_revenue=finance(_('Revenue'), ['Revenue']),
            purchase_expenses=finance(_('Purchase expenses'), ['Purchase expense']),
            total_expenses=finance(_('Revenue vs Expenses — Expenses'), ['Manual expense','Purchase expense'], ('type',)),
            net_revenue=finance(_('Revenue vs Expenses'), ['Revenue','Manual expense','Purchase expense'], ('type',)),
            manual_expenses=action(_('Manual expenses'), 'fitzone.management.expense',
                base+period_domain+([('department','=',department or False)] if department is not None else []), 'manual'),
            collected_cash=action(_('Collected cash'), 'fitzone.collected.detail',base+dept_domain+period_domain,'collected',('source',)),
            active_memberships=operational(_('Active memberships'),membership+[('date_end','>=',str(end))],'operational_membership'),
            expired_memberships=operational(_('Expired memberships'),membership+[('date_end','>=',str(start)),('date_end','<',str(end))],'operational_membership'),
            upcoming_installments_amount=operational(_('Upcoming installments'),installment+[('date','>=',str(end)),('date','<=',str(end+timedelta(days=(end-start).days+1)))],'operational_installment'),
            overdue_installments_amount=operational(_('Overdue installments'),installment+[('date','>=',str(start)),('date','<',str(end))],'operational_installment'),
            injuries_count=operational(_('Injuries'),dept_domain+period_domain+[('type','=','Injury')],'operational_injury',('cause_id',)),
            injuries_sport=operational(_('Injuries by sport'),dept_domain+period_domain+[('type','=','Injury sport')],'operational_injury',('sport',)),
            overall_occupancy_percent=operational(_('Occupancy — Classes and booked seats'),classes,'operational_class',('room_id',)),
            workload=operational(_('Workload — Sessions'),dept_domain+['|','&',('type','=','Class'),'&',('start_datetime','<',str(finish)),('end_datetime','>',str(begin)),
                '&',('type','=','Session'),'|','&',('source','=','fitzone.pt.session'),'&',('start_datetime','>=',str(begin)),('start_datetime','<',str(finish)),
                '&',('source','!=','fitzone.pt.session'),'&',('date','>=',str(start)),('date','<=',str(end))],'operational_session',('employee_id','source')),
            new_members=operational(_('New members'),[('type','=','Member'),('member_id','in',new_members['ids'] or [])],'operational_member'),
            cross_conversion_percent=operational(_('Conversion — Members counted'),[('type','=','Member'),('member_id','in',conversion['all_ids'] or [])],'operational_member'),
        )
        actions['pos_revenue'] = finance(_('POS revenue'), ['Revenue'])
        actions['pos_revenue']['domain'].append(('source','=','POS'))
        actions['net_margin_percent'] = actions['net_revenue']
        actions['upcoming_installments_count'] = actions['upcoming_installments_amount']
        actions['overdue_installments_count'] = actions['overdue_installments_amount']
        return actions

    @api.model
    def get_dashboard_action(self, metric, date_from=None, date_to=None, department=None,
                             cause=None, sport=None, room=None, trainer=None, installment=None,
                             matrix_source=None, matrix_target=None):
        """Resolve clicks server-side; caller cannot supply an arbitrary domain."""
        data = self.get_dashboard_data(date_from, date_to, department)
        if metric not in data['drilldowns']:
            raise AccessError(_('Unknown dashboard metric.'))
        action = data['drilldowns'][metric]
        domain = action['domain']
        if metric == 'injuries_count' and cause is not None:
            domain.append(('cause_id','=',int(cause) or False))
        if metric == 'injuries_sport' and sport is not None:
            domain.append(('sport','=',sport))
        if metric == 'overall_occupancy_percent' and room is not None:
            domain.append(('room_id','=',int(room)))
        if metric == 'workload' and trainer is not None:
            if str(trainer).startswith('user:'):
                domain += [('employee_id','=',False),('user_id','=',int(str(trainer).split(':')[1]))]
            else:
                domain.append(('employee_id','=',int(trainer)))
        if metric.startswith(('upcoming_installments','overdue_installments')) and installment is not None:
            domain.append(('origin_id','=',int(installment)))
        if metric == 'cross_conversion_percent' and matrix_source is not None and matrix_target is not None:
            from .dashboard_queries import EVENTS
            start, end = fields.Date.to_date(data['date_from']), fields.Date.to_date(data['date_to'])
            tz = pytz.timezone(data['reporting_timezone'])
            params = dict(company=self.env.company.id, start=start,end=end,
                begin=tz.localize(datetime.combine(start,time.min)).astimezone(pytz.utc).replace(tzinfo=None),
                finish=tz.localize(datetime.combine(end+timedelta(days=1),time.min)).astimezone(pytz.utc).replace(tzinfo=None),
                source=int(matrix_source), target=int(matrix_target))
            rows = self._query('WITH events AS ('+EVENTS+''') SELECT DISTINCT a.member_id FROM events a
                JOIN events b ON b.member_id=a.member_id WHERE a.department=%(source)s AND b.department=%(target)s
                AND a.department<>0 AND b.department<>0''',params)
            domain.append(('member_id','in',[r['member_id'] for r in rows]))
        return action
