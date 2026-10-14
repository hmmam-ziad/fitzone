"""SQL fragments used only after the manager gate, with explicit company predicates.

All amounts are company currency. Invoiced POS is excluded from revenue to avoid
counting it twice. Events include all POS usage, matching the original dashboard.
"""
# One row per source line. POs are attribution only, never an expense source.
# Bill balances already carry refund signs and posting-date FX in company currency.
# Manual entries are independent costs: clients must not re-enter vendor bills here.
FINANCIAL_ROWS = """
    SELECT m.company_id, m.invoice_date AS day, COALESCE(l.fitzone_department_id,t.fitzone_department,0) AS department,
           -l.balance AS revenue, 0::numeric AS manual_expenses, 0::numeric AS purchase_expenses,
           l.partner_id AS member_id
    FROM account_move_line l JOIN account_move m ON m.id=l.move_id
    LEFT JOIN product_product p ON p.id=l.product_id
    LEFT JOIN product_template t ON t.id=p.product_tmpl_id
    WHERE m.state='posted' AND m.move_type IN ('out_invoice','out_refund') AND l.display_type='product'
    UNION ALL
    SELECT o.company_id, (o.date_order AT TIME ZONE 'UTC' AT TIME ZONE (SELECT COALESCE(rp.tz,'UTC') FROM res_company rc JOIN res_partner rp ON rp.id=rc.partner_id WHERE rc.id=o.company_id))::date,
           COALESCE(t.fitzone_department,pc.fitzone_department_id,0),
           l.price_subtotal / COALESCE(NULLIF(o.currency_rate,0),1), 0, 0,
           COALESCE(o.fitzone_member_id,o.partner_id)
    FROM pos_order_line l JOIN pos_order o ON o.id=l.order_id
    JOIN product_product p ON p.id=l.product_id JOIN product_template t ON t.id=p.product_tmpl_id
    JOIN pos_config pc ON pc.id=o.config_id
    WHERE o.state IN ('paid','done','invoiced') AND o.account_move IS NULL
    UNION ALL
    SELECT company_id, date, COALESCE(department,0), 0, amount, 0, NULL
    FROM fitzone_management_expense
    UNION ALL
    SELECT m.company_id, m.date,
           COALESCE(CASE WHEN po.id IS NOT NULL THEN po.department_id ELSE m.fitzone_department_id END,0),
           0, 0, l.balance, NULL
    FROM account_move_line l JOIN account_move m ON m.id=l.move_id
    LEFT JOIN purchase_order_line pl ON pl.id=l.purchase_line_id
    LEFT JOIN purchase_order po ON po.id=pl.order_id AND po.company_id=m.company_id
    WHERE m.state='posted' AND m.move_type IN ('in_invoice','in_refund') AND l.display_type='product'
"""
EVENTS = """
    SELECT v.member_id, COALESCE(v.department_id,0) AS department FROM fitzone_visit v
    WHERE v.company_id=%(company)s AND v.visit_date >= %(begin)s AND v.visit_date < %(finish)s
    UNION
    SELECT s.member_id, COALESCE(s.department_id,0) FROM fitzone_pt_session s
    WHERE s.company_id=%(company)s AND s.state='completed'
      AND s.session_date >= %(begin)s AND s.session_date < %(finish)s
    UNION
    SELECT b.member_id, COALESCE(c.department_id,0) FROM fitzone_class_booking b
    JOIN fitzone_gym_class c ON c.id=b.class_id
    WHERE c.company_id=%(company)s AND b.company_id=%(company)s AND b.status='attended'
      AND c.start_datetime < %(finish)s AND c.end_datetime > %(begin)s
    UNION
    SELECT member_id, COALESCE(department_id,0) FROM fitzone_pool_booking
    WHERE company_id=%(company)s AND status='checked_in' AND session_date BETWEEN %(start)s AND %(end)s
    UNION
    SELECT member_id, COALESCE(department_id,0) FROM fitzone_rehabilitation
    WHERE company_id=%(company)s AND start_date BETWEEN %(start)s AND %(end)s
    UNION
    SELECT member_id, COALESCE(department_id,0) FROM fitzone_nutrition_consultation
    WHERE company_id=%(company)s AND consult_date BETWEEN %(start)s AND %(end)s
    UNION
    SELECT l.partner_id, COALESCE(l.fitzone_department_id,t.fitzone_department,0)
    FROM account_move_line l JOIN account_move m ON m.id=l.move_id
    LEFT JOIN product_product p ON p.id=l.product_id
    LEFT JOIN product_template t ON t.id=p.product_tmpl_id
    WHERE m.company_id=%(company)s AND m.state='posted' AND m.move_type IN ('out_invoice','out_refund')
      AND l.display_type='product' AND l.balance < 0 AND m.invoice_date BETWEEN %(start)s AND %(end)s
    UNION
    SELECT COALESCE(o.fitzone_member_id,o.partner_id), COALESCE(t.fitzone_department,pc.fitzone_department_id,0)
    FROM pos_order_line l JOIN pos_order o ON o.id=l.order_id
    JOIN product_product p ON p.id=l.product_id JOIN product_template t ON t.id=p.product_tmpl_id
    JOIN pos_config pc ON pc.id=o.config_id
    WHERE o.company_id=%(company)s AND o.state IN ('paid','done','invoiced') AND l.price_subtotal > 0
      AND o.date_order >= %(begin)s AND o.date_order < %(finish)s
"""
WORKLOAD = """
    SELECT t.employee_id, COALESCE(s.department_id,0) AS department, count(*) AS sessions
    FROM fitzone_pt_session s JOIN fitzone_trainer t ON t.id=s.trainer_id
    WHERE s.company_id=%(company)s AND s.state='completed'
      AND s.session_date >= %(begin)s AND s.session_date < %(finish)s GROUP BY t.employee_id, s.department_id
    UNION ALL
    SELECT t.employee_id, COALESCE(c.department_id,0), count(*) FROM fitzone_gym_class c
    JOIN fitzone_trainer t ON t.id=c.trainer_id
    WHERE c.company_id=%(company)s AND c.start_datetime < %(finish)s AND c.end_datetime > %(begin)s
    GROUP BY t.employee_id, c.department_id
    UNION ALL
    SELECT t.employee_id, COALESCE(b.department_id,0), count(DISTINCT (b.session_date,b.pool_slot_id))
    FROM fitzone_pool_booking b JOIN fitzone_trainer t ON t.id=b.trainer_id
    WHERE b.company_id=%(company)s AND b.status != 'cancelled' AND b.session_date BETWEEN %(start)s AND %(end)s
    GROUP BY t.employee_id, b.department_id
    UNION ALL
    SELECT physiotherapist_id, COALESCE(department_id,0), count(*) FROM fitzone_rehabilitation
    WHERE company_id=%(company)s AND start_date BETWEEN %(start)s AND %(end)s GROUP BY physiotherapist_id, department_id
    UNION ALL
    SELECT e.id, COALESCE(n.department_id,0), count(*) FROM fitzone_nutrition_consultation n
    JOIN hr_employee e ON e.user_id=n.nutritionist_id AND e.company_id=%(company)s
    WHERE n.company_id=%(company)s AND n.consult_date BETWEEN %(start)s AND %(end)s GROUP BY e.id, n.department_id
"""

# Same sources and dates as accrual revenue; line tax follows its department.
# Invoice tax is the posted company-currency tax-line balance, allocated using
# each product line's tax weight. Scaling preserves accounting/global tax rounding.
TAX_ROWS = """
    SELECT m.company_id, m.invoice_date AS day,
           COALESCE(l.fitzone_department_id,t.fitzone_department,0) AS department,
           COALESCE(tax_totals.tax,0) * COALESCE(
               (l.price_total-l.price_subtotal) / NULLIF(sum(l.price_total-l.price_subtotal) OVER (PARTITION BY m.id),0),
               l.balance / NULLIF(sum(l.balance) OVER (PARTITION BY m.id),0), 0) AS tax
    FROM account_move_line l JOIN account_move m ON m.id=l.move_id
    LEFT JOIN product_product p ON p.id=l.product_id
    LEFT JOIN product_template t ON t.id=p.product_tmpl_id
    LEFT JOIN LATERAL (SELECT sum(-tl.balance) AS tax FROM account_move_line tl
        WHERE tl.move_id=m.id AND tl.display_type='tax') tax_totals ON TRUE
    WHERE m.state='posted' AND m.move_type IN ('out_invoice','out_refund') AND l.display_type='product'
    UNION ALL
    SELECT o.company_id,
           (o.date_order AT TIME ZONE 'UTC' AT TIME ZONE
             (SELECT COALESCE(rp.tz,'UTC') FROM res_company rc JOIN res_partner rp ON rp.id=rc.partner_id WHERE rc.id=o.company_id))::date,
           COALESCE(t.fitzone_department,pc.fitzone_department_id,0),
           (l.price_subtotal_incl-l.price_subtotal) / COALESCE(NULLIF(o.currency_rate,0),1)
    FROM pos_order_line l JOIN pos_order o ON o.id=l.order_id
    JOIN pos_config pc ON pc.id=o.config_id
    JOIN product_product p ON p.id=l.product_id JOIN product_template t ON t.id=p.product_tmpl_id
    WHERE o.state IN ('paid','done','invoiced') AND o.account_move IS NULL
"""

COLLECTED_ROWS = """
    WITH payment_lines AS (
        SELECT l.id, l.company_id, m.date AS day, l.balance
        FROM account_move_line l JOIN account_move m ON m.id=l.move_id
        JOIN account_account a ON a.id=l.account_id
        LEFT JOIN account_payment ap ON ap.id=m.origin_payment_id
        WHERE m.state='posted' AND a.account_type='asset_receivable'
          AND (m.statement_line_id IS NOT NULL OR (ap.partner_type='customer'
               AND ap.pos_payment_method_id IS NULL AND ap.pos_session_id IS NULL))
          AND NOT EXISTS (SELECT 1 FROM pos_payment pp WHERE pp.account_move_id=m.id)
    ), matches AS (
        SELECT pay.id AS payment_line_id, pay.company_id, pay.day,
               -sign(pay.balance)*pr.amount AS amount, inv.id AS invoice_id
        FROM payment_lines pay
        JOIN account_partial_reconcile pr ON pr.credit_move_id=pay.id OR pr.debit_move_id=pay.id
        JOIN account_move_line il ON il.id=CASE WHEN pr.credit_move_id=pay.id THEN pr.debit_move_id ELSE pr.credit_move_id END
        JOIN account_move inv ON inv.id=il.move_id AND inv.company_id=pay.company_id
        WHERE inv.state='posted' AND inv.move_type IN ('out_invoice','out_refund')
    ), weights AS (
        SELECT l.move_id, l.id, COALESCE(l.fitzone_department_id,t.fitzone_department,0) AS department,
               l.balance, sum(l.balance) OVER (PARTITION BY l.move_id) AS total
        FROM account_move_line l
        LEFT JOIN product_product p ON p.id=l.product_id
        LEFT JOIN product_template t ON t.id=p.product_tmpl_id
        WHERE l.display_type='product'
    )
    SELECT mt.company_id, mt.day, w.department, mt.amount*w.balance/w.total AS collected_cash
    FROM matches mt JOIN weights w ON w.move_id=mt.invoice_id AND w.total<>0
    UNION ALL
    SELECT mt.company_id, mt.day, 0, mt.amount
    FROM matches mt
    WHERE NOT EXISTS (SELECT 1 FROM weights w WHERE w.move_id=mt.invoice_id AND w.total<>0)
    UNION ALL
    SELECT pay.company_id, pay.day, 0, -pay.balance-COALESCE(sum(mt.amount),0)
    FROM payment_lines pay LEFT JOIN matches mt ON mt.payment_line_id=pay.id
    GROUP BY pay.id,pay.company_id,pay.day,pay.balance
    HAVING abs(-pay.balance-COALESCE(sum(mt.amount),0))>0.0000001
    UNION ALL
    SELECT ap.company_id, ap.date, 0, ap.amount_company_currency_signed
    FROM account_payment ap
    WHERE ap.move_id IS NULL AND ap.state IN ('in_process','paid') AND ap.partner_type='customer'
      AND ap.pos_payment_method_id IS NULL AND ap.pos_session_id IS NULL
    UNION ALL
    SELECT o.company_id,
           (pp.payment_date AT TIME ZONE 'UTC' AT TIME ZONE
             (SELECT COALESCE(rp.tz,'UTC') FROM res_company rc JOIN res_partner rp ON rp.id=rc.partner_id WHERE rc.id=o.company_id))::date,
           CASE WHEN totals.net<>0 THEN COALESCE(t.fitzone_department,pc.fitzone_department_id,0) ELSE 0 END,
           pp.amount / COALESCE(NULLIF(o.currency_rate,0),1)
             * CASE WHEN totals.net<>0 THEN l.price_subtotal/totals.net ELSE 1 END
    FROM pos_payment pp JOIN pos_order o ON o.id=pp.pos_order_id
    JOIN pos_payment_method pm ON pm.id=pp.payment_method_id
    JOIN account_journal pj ON pj.id=pm.journal_id AND pj.type IN ('cash','bank')
    JOIN pos_config pc ON pc.id=o.config_id
    LEFT JOIN LATERAL (SELECT sum(price_subtotal) AS net FROM pos_order_line WHERE order_id=o.id) totals ON TRUE
    LEFT JOIN pos_order_line l ON l.order_id=o.id AND totals.net<>0
    LEFT JOIN product_product p ON p.id=l.product_id LEFT JOIN product_template t ON t.id=p.product_tmpl_id
    WHERE o.state IN ('paid','done','invoiced')
"""


def company_departments(source, company_expression='s.company_id'):
    """Cross-company resolved departments become Unassigned (no second fallback).

    SQL never emits another company's department ID/name; the caller additionally
    restricts source companies to the user's allowed companies.
    """
    return ("SELECT s.*, CASE WHEN d.company_id IS NULL OR d.company_id="
            + company_expression + " THEN s.department ELSE 0 END AS safe_department FROM ("
            + source + ") s LEFT JOIN hr_department d ON d.id=s.department")


def normalize(source, columns, company_expression='s.company_id'):
    return "SELECT " + columns + " FROM (" + company_departments(source, company_expression) + ") guarded"


FINANCIAL_ROWS = normalize(FINANCIAL_ROWS, 'company_id, day, safe_department AS department, revenue, manual_expenses, purchase_expenses, member_id')
FINANCIAL = "SELECT *, manual_expenses+purchase_expenses AS expenses FROM (" + FINANCIAL_ROWS + ") sources WHERE company_id=%(company)s AND day BETWEEN %(start)s AND %(end)s"
TAX_ROWS = normalize(TAX_ROWS, 'company_id, day, safe_department AS department, tax')
COLLECTED_ROWS = normalize(COLLECTED_ROWS, 'company_id, day, safe_department AS department, collected_cash')
EVENTS = normalize(EVENTS, 'member_id, safe_department AS department', '%(company)s')
WORKLOAD = normalize(WORKLOAD, 'employee_id, safe_department AS department, sessions', '%(company)s')
