"""Live management reporting. No stored snapshots or scheduled refreshes."""
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class DashboardProduct(models.Model):
    _inherit = 'product.template'

    fitzone_department = fields.Many2one(
        'hr.department', string='Reporting Department',
        domain="['|', ('company_id', '=', False), ('company_id', 'in', allowed_company_ids)]",
        help='Revenue attribution; empty products report as Unassigned.')

    def _auto_init(self):
        from .department_migration import preserve_selection
        preserve_selection(self.env.cr, 'product_template', 'fitzone_department')
        return super()._auto_init()


class DashboardEmployee(models.Model):
    _inherit = 'hr.employee'

    fitzone_monthly_session_quota = fields.Float(
        string='Monthly Session Quota', default=0,
        groups='fitzone.group_fitzone_manager',
        help='Zero means no target. Reporting prorates this target over calendar days.')

    @api.constrains('fitzone_monthly_session_quota')
    def _check_fitzone_quota(self):
        if any(employee.fitzone_monthly_session_quota < 0 for employee in self):
            raise ValidationError(_('Session quotas cannot be negative.'))


class ManagementExpense(models.Model):
    _name = 'fitzone.management.expense'
    _inherit = ['fitzone.department.company.mixin']
    _description = 'FitZone Manual Management Expense'
    _order = 'date desc, id desc'
    _check_company_auto = True

    name = fields.Char(required=True)
    date = fields.Date(required=True, default=fields.Date.context_today)
    company_id = fields.Many2one('res.company', required=True,
                                default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    department = fields.Many2one('hr.department', check_company=True, index=True, domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]")
    amount = fields.Monetary(required=True)
    notes = fields.Text(help='Manual management expenses only; do not duplicate vendor bills.')

    def _auto_init(self):
        from .department_migration import preserve_selection
        preserve_selection(self.env.cr, 'fitzone_management_expense', 'department')
        return super()._auto_init()

    def _check_access(self, operation):
        result = super()._check_access(operation)
        if not self.env.su and not self.env.user.has_group('fitzone.group_fitzone_manager'):
            return self, lambda: AccessError(self.env._('Only FitZone Managers may access financial reports.'))
        return result

    @api.constrains('amount')
    def _check_amount(self):
        if any(record.amount <= 0 for record in self):
            raise ValidationError(_('Expense amounts must be positive.'))


class ManagementDashboard(models.AbstractModel):
    _name = 'fitzone.management.dashboard'
    _description = 'Live FitZone Management Dashboard'

    @api.model
    def get_dashboard_data(self, date_from=None, date_to=None, department=None):
        """One read-only RPC; no persisted dashboard or report records.

        Memberships are evaluated as of period end (within the selected cohort);
        installments use the period end as the aging date and the period length
        as the upcoming window. Historical states are reconstructed from dates,
        using today's uncancelled memberships and currently pending installments.
        This is a live report, not an accounting snapshot.
        """
        self._check_management()
        end = fields.Date.to_date(date_to) if date_to else fields.Date.context_today(self)
        start = fields.Date.to_date(date_from) if date_from else end.replace(day=1)
        if not start or not end or start > end:
            raise ValidationError(_('Choose a valid date range.'))
        if department is not None and department is not False and department != '':
            try:
                department = int(department)
            except (TypeError, ValueError):
                raise ValidationError(_('Unknown department.'))
            if department and not self.env['hr.department'].sudo().with_context(active_test=False).search_count([
                    ('id', '=', department), '|', ('company_id', '=', False),
                    ('company_id', '=', self.env.company.id)]):
                raise ValidationError(_('Unknown department.'))
        else:
            department = None
        days = (end-start).days + 1
        if days > 3660:
            raise ValidationError(_('Select a date range of ten years or less.'))
        # Force pending ORM changes to SQL before aggregation (also important in tests).
        self.env.flush_all()
        data = self._period(start, end, department)
        previous = self._period(start-timedelta(days=days), start-timedelta(days=1), department)
        data['previous'] = previous['kpis']
        data['trends'] = {
            key: self._trend(value, previous['kpis'][key])
            for key, value in data['kpis'].items()
        }
        data.update(currency=self.env.company.currency_id.name,
                    currency_digits=self.env.company.currency_id.decimal_places,
                    company={'id': self.env.company.id, 'name': self.env.company.name},
                    date_from=str(start), date_to=str(end), department=department,
                    previous_from=str(start-timedelta(days=days)),
                    previous_to=str(start-timedelta(days=1)),
                    refreshed_at=fields.Datetime.to_string(fields.Datetime.now()))
        return data

    def _check_management(self):
        # Check the actual user even under sudo: direct action loading uses sudo.
        if not self.env.user.has_group('fitzone.group_fitzone_manager'):
            raise AccessError(_('Only FitZone Managers may access the Management Dashboard.'))

    @staticmethod
    def _trend(current, previous):
        return round(100 * (current-previous) / abs(previous), 1) if previous else (0.0 if not current else None)

    def _query(self, query, params):
        self.env.cr.execute(query, params)
        return self.env.cr.dictfetchall()

    def _period(self, start, end, department):
        from .dashboard_queries import FINANCIAL, EVENTS, WORKLOAD, TAX_ROWS, COLLECTED_ROWS
        import calendar
        company = self.env.company
        tz = pytz.timezone(company.partner_id.tz or 'UTC')
        begin = tz.localize(datetime.combine(start, time.min)).astimezone(pytz.utc).replace(tzinfo=None)
        finish = tz.localize(datetime.combine(end+timedelta(days=1), time.min)).astimezone(pytz.utc).replace(tzinfo=None)
        days = (end-start).days+1
        params = dict(company=company.id, start=start, end=end, begin=begin, finish=finish,
                      department=department, tz=tz.zone, horizon=end+timedelta(days=days),
                      bucket='week' if days > 45 else 'day')
        finances = self._query('WITH f AS ('+FINANCIAL+''')
            SELECT department, sum(revenue) AS revenue, sum(expenses) AS expenses, sum(manual_expenses) AS manual_expenses,
                   sum(purchase_expenses) AS purchase_expenses
            FROM f WHERE (%(department)s IS NULL OR department=%(department)s) GROUP BY department
        ''', params)
        tax_rows = self._query('SELECT COALESCE(sum(tax),0) AS tax FROM ('+TAX_ROWS+''') t WHERE company_id=%(company)s AND day BETWEEN %(start)s AND %(end)s
            AND (%(department)s IS NULL OR department=%(department)s)''', params)
        tax_collected = float(tax_rows[0]['tax'])
        cash_rows = self._query('SELECT department, sum(collected_cash) AS collected_cash FROM ('+COLLECTED_ROWS+''') c WHERE company_id=%(company)s AND day BETWEEN %(start)s AND %(end)s
            AND (%(department)s IS NULL OR department=%(department)s) GROUP BY department''', params)
        cash_by_dept = {row['department']: float(row['collected_cash']) for row in cash_rows}
        by_dept = {row['department']: row for row in finances}
        departments = []
        choices = [(d.id, d.name) for d in self.env['hr.department'].sudo().with_context(active_test=False).search([
            '|', ('company_id', '=', False), ('company_id', '=', company.id)], order='name,id')]
        choices.append((0, _('Unassigned')))
        for key, label in choices:
            if department is not None and key != department:
                continue
            row = by_dept.get(key, {'revenue': 0, 'expenses': 0})
            rev, exp = float(row['revenue']), float(row['expenses'])
            departments.append(dict(key=key, name=label, revenue=rev, expenses=exp,
                                    manual_expenses=float(row.get('manual_expenses', 0)),
                                    purchase_expenses=float(row.get('purchase_expenses', 0)),
                                    total_expenses=exp, net_revenue=rev-exp, net=rev-exp, margin=100*(rev-exp)/rev if rev else 0))
        collected = [dict(key=row['key'], name=row['name'], collected_cash=cash_by_dept.get(row['key'], 0))
                     for row in departments]
        trend = self._query('WITH f AS ('+FINANCIAL+''')
            SELECT date_trunc(%(bucket)s,day)::date AS day, sum(revenue) AS revenue, sum(expenses) AS expenses
            FROM f WHERE (%(department)s IS NULL OR department=%(department)s)
            GROUP BY 1 ORDER BY 1
        ''', params)
        trend_map = {row['day']: row for row in trend}
        first = start-timedelta(days=start.weekday()) if days > 45 else start
        trend = []
        day = first
        while day <= end:
            row = trend_map.get(day, {})
            trend.append(dict(day=str(day), revenue=float(row.get('revenue', 0)), expenses=float(row.get('expenses', 0))))
            day += timedelta(days=7 if days > 45 else 1)
        # Group seats before joining classes, so capacity is counted once per class.
        halls = self._query('''
            WITH bookings AS (
                SELECT class_id, count(*) AS seats FROM fitzone_class_booking
                WHERE company_id=%(company)s AND status IN ('booked','attended') GROUP BY class_id
            ), scheduled AS (
                SELECT c.room_id, sum(COALESCE(b.seats,0)) AS booked_seats,
                    sum(r.capacity) AS offered_seats,
                    range_agg(tsrange(GREATEST(c.start_datetime,%(begin)s),
                        LEAST(c.end_datetime,%(finish)s))) AS intervals
                FROM fitzone_gym_class c JOIN fitzone_room r ON r.id=c.room_id
                LEFT JOIN bookings b ON b.class_id=c.id
                WHERE c.company_id=%(company)s AND r.company_id=%(company)s
                    AND c.start_datetime < %(finish)s AND c.end_datetime > %(begin)s
                    AND (%(department)s IS NULL OR COALESCE((SELECT id FROM hr_department WHERE id=c.department_id AND (company_id IS NULL OR company_id=%(company)s)),0)=%(department)s) GROUP BY c.room_id
            ) SELECT r.id AS room_id, r.name, COALESCE(s.booked_seats,0) AS booked_seats,
                COALESCE(s.offered_seats,0) AS offered_seats,
                COALESCE((SELECT sum(extract(epoch FROM upper(i)-lower(i))/3600)
                          FROM unnest(s.intervals) i),0) AS scheduled_hours
            FROM fitzone_room r LEFT JOIN scheduled s ON s.room_id=r.id
            WHERE r.company_id=%(company)s ORDER BY r.name, r.id
        ''', params)
        for row in halls:
            row['booked_seats'] = int(row['booked_seats'])
            row['offered_seats'] = int(row['offered_seats'])
            row['scheduled_hours'] = float(row['scheduled_hours'])
            row['occupancy_percent'] = 100*row['booked_seats']/row['offered_seats'] if row['offered_seats'] else 0
            row['utilization_percent'] = min(100,100*row['scheduled_hours']/(16*days))
            row['flag'] = None
        used_halls = [h for h in halls if h['offered_seats']]
        if used_halls:
            max(used_halls, key=lambda h:h['occupancy_percent'])['flag'] = 'Most utilized'
            if len(used_halls)>1:
                min(used_halls, key=lambda h:h['occupancy_percent'])['flag'] = 'Least utilized'
        quota_factor = 0
        day = start
        while day <= end:
            quota_factor += 1/calendar.monthrange(day.year,day.month)[1]
            day += timedelta(days=1)
        params['quota_factor'] = quota_factor
        workload = self._query('WITH w AS ('+WORKLOAD+''')
            SELECT e.id, e.name, COALESCE(sum(w.sessions),0) AS sessions,
                   e.fitzone_monthly_session_quota * %(quota_factor)s AS quota
            FROM hr_employee e LEFT JOIN w ON w.employee_id=e.id
                AND (%(department)s IS NULL OR w.department=%(department)s)
            WHERE e.company_id=%(company)s
            GROUP BY e.id HAVING sum(w.sessions)>0 OR e.fitzone_monthly_session_quota>0
            ORDER BY sessions DESC,e.id
        ''', params)
        # Retain specialists linked only to a user, without an employee record.
        workload += self._query("""SELECT 'user:' || u.id AS id, p.name, count(*) AS sessions, 0 AS quota
            FROM fitzone_nutrition_consultation n JOIN res_users u ON u.id=n.nutritionist_id
            JOIN res_partner p ON p.id=u.partner_id
            WHERE n.company_id=%(company)s AND n.consult_date BETWEEN %(start)s AND %(end)s
                AND (%(department)s IS NULL OR COALESCE((SELECT id FROM hr_department WHERE id=n.department_id AND (company_id IS NULL OR company_id=%(company)s)),0)=%(department)s)
                AND NOT EXISTS (SELECT 1 FROM hr_employee e WHERE e.user_id=u.id AND e.company_id=%(company)s)
            GROUP BY u.id,p.name ORDER BY sessions DESC,u.id""", params)
        for row in workload:
            row['sessions'] = int(row['sessions'])
            row['quota'] = float(row['quota'] or 0)
            row['completion_percent'] = 100*row['sessions']/row['quota'] if row['quota'] else None
        # Conversion denominator includes all used departments, even with a filter.
        event_cte = 'WITH events AS ('+EVENTS+'''), members AS (
            SELECT e.member_id, array_agg(DISTINCT e.department) AS departments
            FROM events e JOIN res_partner p ON p.id=e.member_id WHERE p.is_fitzone_member AND e.department<>0
            GROUP BY e.member_id
        ) '''
        conversion = self._query(event_cte+'''
            SELECT count(*) AS members, count(*) FILTER (WHERE cardinality(departments)>1) AS converted,
                   array_agg(member_id) FILTER (WHERE cardinality(departments)>1) AS ids
            FROM members WHERE (%(department)s IS NULL OR %(department)s=ANY(departments))
        ''', params)[0]
        matrix = self._query(event_cte+'''
            SELECT a.department AS source, b.department AS target, count(DISTINCT a.member_id) AS count
            FROM events a JOIN events b ON b.member_id=a.member_id
            JOIN members m ON m.member_id=a.member_id
            WHERE a.department<>0 AND b.department<>0 AND (%(department)s IS NULL OR %(department)s=ANY(m.departments))
            GROUP BY a.department,b.department
        ''', params)
        injury_where = '''i.company_id=%(company)s AND i.injury_date BETWEEN %(start)s AND %(end)s
                          AND (%(department)s IS NULL OR COALESCE((SELECT id FROM hr_department WHERE id=i.department_id AND (company_id IS NULL OR company_id=%(company)s)),0)=%(department)s)'''
        causes = self._query('''SELECT c.id, COALESCE(c.name,'Unspecified') AS name, count(*) AS count
            FROM fitzone_injury i LEFT JOIN fitzone_injury_cause c ON c.id=i.injury_cause_id
            WHERE '''+injury_where+' GROUP BY c.id,c.name ORDER BY count DESC', params)
        sports = self._query('''SELECT COALESCE(NULLIF(r.sport_type,''),'Unspecified') AS name,
                count(DISTINCT i.id) AS count FROM fitzone_injury i
            LEFT JOIN fitzone_rehabilitation r ON r.injury_id=i.id AND r.company_id=%(company)s
            WHERE '''+injury_where+' GROUP BY 1 ORDER BY count DESC', params)
        # Restrict stock KPIs to memberships overlapping the period or expiring in it.
        # Thus a completely empty historical period is consistently zero.
        membership_domain = [('company_id','=',company.id), ('state','in',['active','expired']),
                             ('date_start','<=',str(end))]
        package_dept = "COALESCE((SELECT id FROM hr_department WHERE id=t.fitzone_department AND (company_id IS NULL OR company_id=%(company)s)),0)"
        if department is not None:
            membership_domain += ([('package_id.fitzone_department','=',department)] if department else [
                '|', ('package_id.fitzone_department','=',False), '&',
                ('package_id.fitzone_department.company_id','!=',False),
                ('package_id.fitzone_department.company_id','!=',company.id)])
        memberships = self._query('''SELECT
                count(*) FILTER (WHERE m.date_end >= %(end)s) AS active,
                count(*) FILTER (WHERE m.date_end BETWEEN %(start)s AND %(end)s AND m.date_end < %(end)s) AS expired
            FROM fitzone_membership m JOIN product_template t ON t.id=m.package_id
            WHERE m.company_id=%(company)s AND m.state IN ('active','expired') AND m.date_start<=%(end)s
                AND (%(department)s IS NULL OR '''+package_dept+'''=%(department)s)
        ''', params)[0]
        new_members = self._query('''WITH joined AS (
            SELECT member_id,min(date_start) AS joined FROM fitzone_membership
            WHERE company_id=%(company)s AND state IN ('active','expired') GROUP BY member_id
        ) SELECT count(*) AS count, array_agg(j.member_id) AS ids FROM joined j
          WHERE j.joined BETWEEN %(start)s AND %(end)s AND (%(department)s IS NULL OR EXISTS (
            SELECT 1 FROM fitzone_membership m JOIN product_template t ON t.id=m.package_id
            WHERE m.company_id=%(company)s AND m.member_id=j.member_id AND '''+package_dept+'''=%(department)s))
        ''', params)[0]
        installment_base = [('status','=','pending'), ('plan_id.invoice_id.company_id','=',company.id),
                            ('plan_id.membership_id.company_id','=',company.id)]
        if department is not None:
            installment_base += [('plan_id.membership_id.'+leaf[0], *leaf[1:]) if isinstance(leaf, tuple) else leaf
                                 for leaf in membership_domain[3:]]
        upcoming_domain = installment_base+[('due_date','>=',str(end)), ('due_date','<=',str(params['horizon']))]
        overdue_domain = installment_base+[('due_date','>=',str(start)), ('due_date','<',str(end))]
        def installments(upcoming):
            rows = self._query("""SELECT a.currency_id, count(*) AS count, sum(i.amount) AS amount
                FROM fitzone_installment i JOIN fitzone_installment_plan p ON p.id=i.plan_id
                JOIN account_move a ON a.id=p.invoice_id JOIN fitzone_membership m ON m.id=p.membership_id
                JOIN product_template t ON t.id=m.package_id
                WHERE i.status='pending' AND a.company_id=%(company)s AND m.company_id=%(company)s
                    AND (%(department)s IS NULL OR """+package_dept+"""=%(department)s)
                    AND """+("i.due_date BETWEEN %(end)s AND %(horizon)s" if upcoming else
                              "i.due_date >= %(start)s AND i.due_date < %(end)s")+" GROUP BY a.currency_id", params)
            return dict(count=sum(row['count'] for row in rows), amount=sum(
                self.env['res.currency'].browse(row['currency_id'])._convert(
                    row['amount'],company.currency_id,company,end) for row in rows))
        upcoming, overdue = installments(True), installments(False)
        top = self.env['fitzone.installment'].sudo().search(overdue_domain, order='due_date,id', limit=5)
        top_overdue = [dict(id=item.id, name=item.plan_id.membership_id.member_id.name,
            due_date=str(item.due_date), amount=item.plan_id.invoice_id.currency_id._convert(
                item.amount,company.currency_id,company,end)) for item in top]
        revenue = sum(row['revenue'] for row in departments)
        expenses = sum(row['expenses'] for row in departments)
        offered = sum(row['offered_seats'] for row in halls)
        kpis = dict(total_revenue=revenue, total_expenses=expenses, net_revenue=revenue-expenses,
            net_margin_percent=100*(revenue-expenses)/revenue if revenue else 0,
            active_memberships=memberships['active'], expired_memberships=memberships['expired'],
            new_members=new_members['count'], overall_occupancy_percent=100*sum(row['booked_seats'] for row in halls)/offered if offered else 0,
            upcoming_installments_count=upcoming['count'], upcoming_installments_amount=upcoming['amount'],
            overdue_installments_count=overdue['count'], overdue_installments_amount=overdue['amount'],
            injuries_count=sum(row['count'] for row in causes),
            cross_conversion_percent=100*conversion['converted']/conversion['members'] if conversion['members'] else 0)
        def action(name, model, domain):
            return dict(type='ir.actions.act_window',name=name,res_model=model,views=[[False,'list'],[False,'form']],
                        domain=domain,context={'create':False,'edit':False})
        financial_domain = [('company_id','=',company.id), ('parent_state','=','posted'),
            ('move_id.move_type','in',['out_invoice','out_refund']), ('display_type','=','product'),
            ('move_id.invoice_date','>=',str(start)), ('move_id.invoice_date','<=',str(end))]
        expense_domain = [('company_id','=',company.id),('date','>=',str(start)),('date','<=',str(end))]
        if department is not None:
            expense_domain.append(('department','=',department or False))
        report_domain = [('company_id','=',company.id), ('date','>=',str(start)), ('date','<=',str(end))]
        if department is not None:
            report_domain.append(('department_id','=',department or False))
        drills = dict(
            total_revenue=action('Accrual revenue','fitzone.financial.analysis',report_domain+[('revenue','!=',0)]),
            total_expenses=action('Financial Analysis','fitzone.financial.analysis',report_domain),
            manual_expenses=action('Manual expenses','fitzone.management.expense',expense_domain),
            purchase_expenses=action('Purchase expenses','fitzone.financial.analysis',report_domain+[('purchase_expenses','!=',0)]),
            active_memberships=action('Active memberships','fitzone.membership',membership_domain+[('date_end','>=',str(end))]),
            expired_memberships=action('Expired memberships','fitzone.membership',membership_domain+[('date_end','>=',str(start)),('date_end','<',str(end))]),
            new_members=action('New members','res.partner',[('id','in',new_members['ids'] or [])]),
            overall_occupancy_percent=action('Scheduled classes','fitzone.gym.class',[
                ('company_id','=',company.id),('start_datetime','<',fields.Datetime.to_string(finish)),
                ('end_datetime','>',fields.Datetime.to_string(begin))]+([('department_id','=',department or False)] if department is not None else [])),
            upcoming_installments_amount=action('Upcoming installments','fitzone.installment',upcoming_domain),
            overdue_installments_amount=action('Overdue installments','fitzone.installment',overdue_domain),
            injuries_count=action('Injuries','fitzone.injury',[('company_id','=',company.id),('injury_date','>=',str(start)),('injury_date','<=',str(end))]+([('department_id','=',department or False)] if department is not None else [])))
        # Revenue can have two sources; expose both, never hide POS from the drill-down.
        pos_domain = [('company_id','=',company.id),('state','in',['paid','done','invoiced']),
                      ('account_move','=',False),('date_order','>=',fields.Datetime.to_string(begin)),
                      ('date_order','<',fields.Datetime.to_string(finish))]
        drills['pos_revenue'] = (action('Accrual revenue by department', 'fitzone.financial.analysis', report_domain+[('revenue','!=',0)])
                                 if department is not None else action('Uninvoiced POS sales','pos.order',pos_domain))
        drills['collected_cash'] = action('Collected by Department (Cash basis)', 'fitzone.collected.department', report_domain)
        drills['cross_conversion_percent'] = action('Members using multiple departments', 'res.partner', [('id','in',conversion['ids'] or [])])
        drills['upcoming_installments_count'] = drills['upcoming_installments_amount']
        drills['overdue_installments_count'] = drills['overdue_installments_amount']
        drills['net_revenue'] = drills['total_revenue']
        drills['net_margin_percent'] = drills['total_revenue']
        return dict(kpis=kpis, tax_collected=tax_collected, total_incl_tax=revenue+tax_collected,
                    reporting_timezone=tz.zone, collected=collected, collected_cash=sum(r['collected_cash'] for r in collected),
                    department_options=choices, departments=departments, trend=trend, halls=halls, workload=workload,
                    injuries_by_cause=causes, injuries_by_sport=sports, conversion_matrix=matrix,
                    conversion_members=conversion['members'], memberships=memberships,
                    upcoming=upcoming, overdue=overdue, top_overdue=top_overdue, drilldowns=drills,
                    basis='Revenue is invoiced/accrual and excludes tax; posted invoices + uninvoiced POS. Tax collected and Total incl. tax appear below Total revenue (invoice/POS tax, not cash-basis tax). Cash basis is a separate receipt allocation using tax-exclusive line weights; collected cash includes tax. POS dates use company contact timezone (UTC if unset). Expenses: manual entries plus posted vendor bill/refund product lines in company currency, excluding tax; no PO totals. '
                          'Memberships: active at range end or expired within range. New members: first membership start. '
                          'Installments: currently pending, overdue within range; upcoming within one equal-length period after range end. '
                          'Occupancy: booked/attended seats ÷ offered seats; hall hours merge overlapping classes (16 hours/day). '
                          'Workload: completed PT, scheduled classes/pool sessions, rehab starts and nutrition consultations. '
                          'Conversion: distinct members using or purchasing in more than one assigned department; matrix counts shared members. '
                          'Historical comparisons use current states, without snapshots.')


class DashboardClientAction(models.Model):
    _inherit = 'ir.actions.client'

    def read(self, fields=None, load='_classic_read'):
        if any(action.tag == 'fitzone_management_dashboard' for action in self):
            self.env['fitzone.management.dashboard']._check_management()
        return super().read(fields=fields, load=load)
