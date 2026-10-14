"""Optional demo fixture, loaded exclusively through the manifest's demo key."""
from datetime import datetime, time, timedelta

from odoo import api, fields, models


class ManagementDashboardDemo(models.AbstractModel):
    _inherit = 'fitzone.management.dashboard'

    @api.model
    def _load_dashboard_demo(self):
        # Stable XML IDs make the fixture safe across upgrades. Never touch real data.
        if self.env.ref('fitzone.dashboard_demo_member_0', raise_if_not_found=False):
            return
        env = self.sudo().with_context(tracking_disable=True, mail_create_nosubscribe=True, tz='UTC').env
        company = env.company
        today = fields.Date.context_today(self)

        def make(model, key, values):
            record = env[model].create(values)
            env['ir.model.data'].create(dict(module='fitzone', name='dashboard_demo_'+key,
                model=model, res_id=record.id, noupdate=True))
            return record

        # All fixture products are services, so demo POS never moves real inventory.
        income = env['account.account'].search([('company_ids','in',company.id),('account_type','=','income')],limit=1)
        if not income:
            income = make('account.account','income',dict(name='Demo FitZone Revenue',code='FZDREV',
                account_type='income',company_ids=[(6,0,company.ids)]))
        journal = env['account.journal'].search([('company_id','=',company.id),('type','=','sale')],limit=1)
        if not journal:
            journal = make('account.journal','journal',dict(name='Demo FitZone Sales',code='FZDS',type='sale',company_id=company.id))
        receivable = env['account.account'].search([('company_ids','in',company.id),('account_type','=','asset_receivable')],limit=1)
        if not receivable:
            receivable = make('account.account','receivable',dict(name='Demo FitZone Receivable',code='FZDREC',account_type='asset_receivable',reconcile=True,company_ids=[(6,0,company.ids)]))
        products = {}
        for key,name,price in [('gym','Gym membership',180),('pool','Swimming coaching',45),
                               ('physio','Physiotherapy',65),('nutrition','Nutrition consultation',35),('retail','Wellness supplement consultation',22)]:
            values = dict(company_id=company.id, name='Demo · '+name,type='service',list_price=price,fitzone_department=env.ref('fitzone.dashboard_demo_department_'+key).id,
                          taxes_id=[(5,0,0)],property_account_income_id=income.id)
            if key=='gym':
                values.update(package_type='general',duration_months=6,
                    **{'allow_'+day:True for day in ('mon','tue','wed','thu','fri','sat','sun')})
            products[key]=make('product.template','product_'+key,values)
        staff=[]
        for i,name in enumerate(['Lina Haddad','Omar Nasser','Sara Khalil']):
            employee=make('hr.employee','employee_'+str(i),dict(name='Demo · '+name,
                company_id=company.id,fitzone_monthly_session_quota=20+i*8,resource_calendar_id=False))
            staff.append(make('fitzone.trainer','trainer_'+str(i),dict(employee_id=employee.id)))
            employee.resource_id.calendar_id=False
        rooms=[env.ref('fitzone.room_studio_1'),env.ref('fitzone.room_studio_2')]
        # Separate pool slots avoid changing real schedules.
        slots=[]
        for weekday in range(7):
            slot=env['fitzone.pool.slot'].search([('day_of_week','=',str(weekday)),('slot_type','=','free_swim')],limit=1)
            if not slot:
                slot=make('fitzone.pool.slot','slot_'+str(weekday),dict(day_of_week=str(weekday),start_time=6,end_time=7,capacity=20,slot_type='free_swim'))
            slots.append(slot)
        members=[]
        memberships=[]
        names=['Ahmad','Rana','Yousef','Nour','Khaled','Hala','Tariq','Dina','Sami','Leen','Fadi','Maya']
        for i,name in enumerate(names):
            member=make('res.partner','member_'+str(i),dict(name='Demo · '+name+' Mansour',
                is_fitzone_member=True,company_id=company.id,birth_date='1992-05-15'))
            member.with_company(company).property_account_receivable_id = receivable
            members.append(member)
            start=today-timedelta(days=89-i*7)
            membership=env['fitzone.membership'].with_context(allow_membership_activation=True).create(dict(
                member_id=member.id,package_id=products['gym'].id,state='active',company_id=company.id,
                date_start=start,date_end=today+timedelta(days=90)))
            memberships.append(membership)
            if i>=9:
                # Historical expired subscriptions are not used for current bookings.
                env['fitzone.membership'].create(dict(member_id=member.id,package_id=products['gym'].id,
                    state='expired',company_id=company.id,date_start=today-timedelta(days=180),date_end=today-timedelta(days=3+i)))
        causes=[make('fitzone.injury.cause','cause_'+str(i),dict(name=name)) for i,name in enumerate(
            ['Demo · Overtraining','Demo · Poor technique','Demo · Inadequate warm-up'])]
        config=make('pos.config','pos_config',dict(name='Demo · FitZone Dashboard',company_id=company.id,
            payment_method_ids=[(6,0,[env.ref('fitzone.payment_method_card').id])]))
        session=make('pos.session','pos_session',dict(config_id=config.id,user_id=env.uid))
        # Transactions and sessions span the last ninety days without backdating a cron.
        for week in range(13):
            day=today-timedelta(days=week*7)
            for j,(dept,product) in enumerate(products.items()):
                member=members[(week+j)%len(members)]
                invoice=make('account.move',f'invoice_{week}_{dept}',dict(move_type='out_invoice',
                    company_id=company.id,journal_id=journal.id,partner_id=member.id,invoice_date=day,
                    invoice_line_ids=[(0,0,dict(product_id=product.product_variant_id.id,
                        account_id=income.id,quantity=2 if dept=='gym' else 1,price_unit=product.list_price+(week%3)*5,tax_ids=[(5,0,0)]))]))
                invoice.action_post()
                amount=product.list_price/2
                order=make('pos.order',f'order_{week}_{dept}',dict(session_id=session.id,partner_id=member.id,
                    date_order=datetime.combine(day,time(17)),amount_total=amount,amount_tax=0,amount_paid=0,amount_return=0,
                    lines=[(0,0,dict(product_id=product.product_variant_id.id,name=product.name,qty=1,
                        price_unit=amount,price_subtotal=amount,price_subtotal_incl=amount,tax_ids=[(5,0,0)]))]))
                order.add_payment(dict(pos_order_id=order.id,payment_method_id=env.ref('fitzone.payment_method_card').id,amount=amount))
                order.action_pos_order_paid()
                make('fitzone.management.expense',f'expense_{week}_{dept}',dict(name='Demo · '+dept+' operations',
                    date=day,department=product.fitzone_department.id,amount=round(product.list_price*.3+(week%4)*3,2),company_id=company.id))
            for room_index,room in enumerate(rooms):
                trainer=staff[room_index]
                when=datetime.combine(day,time(10+room_index*2))
                gym_class=make('fitzone.gym.class',f'class_{week}_{room_index}',dict(name='Demo · '+('Strength' if room_index==0 else 'Pilates'),
                    trainer_id=trainer.id,room_id=room.id,department_id=products['gym'].fitzone_department.id,start_datetime=when,end_datetime=when+timedelta(hours=1),company_id=company.id))
                for index in range(8-room_index*3):
                    if memberships[index].date_start>day:
                        continue
                    booking=make('fitzone.class.booking',f'booking_{week}_{room_index}_{index}',dict(
                        member_id=members[index].id,class_id=gym_class.id,status='attended',company_id=company.id))
                    # Booking creation already creates its unique attendance row.
            for index in range(3):
                if memberships[index].date_start>day:
                    continue
                pt=make('fitzone.pt.session',f'pt_{week}_{index}',dict(member_id=members[index].id,
                    trainer_id=staff[index].id,membership_id=memberships[index].id,package_id=products['gym'].id,
                    session_date=datetime.combine(day,time(15+index)),session_price=30,department_id=products['gym'].fitzone_department.id,company_id=company.id))
                pt.action_complete_session()
                make('fitzone.pool.booking',f'pool_{week}_{index}',dict(member_id=members[index].id,
                    membership_id=memberships[index].id,department_id=products['pool'].fitzone_department.id,pool_slot_id=slots[day.weekday()].id,session_date=day,status='checked_in',company_id=company.id))
            injury=make('fitzone.injury',f'injury_{week}',dict(member_id=members[week%12].id,reported_by=staff[0].employee_id.id,
                department_id=products['physio'].fitzone_department.id,injury_cause_id=causes[week%3].id,injury_date=day,company_id=company.id))
            make('fitzone.rehabilitation',f'rehab_{week}',dict(member_id=injury.member_id.id,injury_id=injury.id,
                department_id=products['physio'].fitzone_department.id,physiotherapist_id=staff[2].employee_id.id,start_date=day,sport_type=['Weightlifting','Swimming','Running'][week%3],company_id=company.id))
            make('fitzone.nutrition.consultation',f'nutrition_{week}',dict(member_id=members[week%12].id,
                department_id=products['nutrition'].fitzone_department.id,consult_date=day,nutritionist_id=env.uid,company_id=company.id))
        for i,membership in enumerate(memberships[:8]):
            # Use an invoice belonging to this member, not the weekly rotating customer.
            invoice=env['account.move'].search([('partner_id','=',membership.member_id.id),('company_id','=',company.id),
                                               ('id','in',[env.ref(f'fitzone.dashboard_demo_invoice_{w}_gym').id for w in range(13)])],limit=1)
            plan=make('fitzone.installment.plan','plan_'+str(i),dict(membership_id=membership.id,invoice_id=invoice.id,down_payment=50))
            for j,offset in enumerate([-18-i,-4-i,6+i,20+i]):
                make('fitzone.installment',f'installment_{i}_{j}',dict(plan_id=plan.id,due_date=today+timedelta(days=offset),amount=45+i*4))

        # One separately billed purchase demonstrates automatic purchase expenses.
        payable = env['account.account'].search([('company_ids','in',company.id),('account_type','=','liability_payable')],limit=1)
        if not payable:
            payable = make('account.account','payable',dict(name='Demo FitZone Payable',code='FZDPAY',account_type='liability_payable',reconcile=True,company_ids=[(6,0,company.ids)]))
        cost = env['account.account'].search([('company_ids','in',company.id),('account_type','=','expense')],limit=1)
        if not cost:
            cost = make('account.account','cost',dict(name='Demo FitZone Costs',code='FZDCST',account_type='expense',company_ids=[(6,0,company.ids)]))
        purchases = env['account.journal'].search([('company_id','=',company.id),('type','=','purchase')],limit=1)
        if not purchases:
            purchases = make('account.journal','purchase_journal',dict(name='Demo FitZone Purchases',code='FZDP',type='purchase',company_id=company.id))
        vendor = make('res.partner','vendor',dict(name='Demo · Wellness supplier',company_id=company.id))
        vendor.with_company(company).property_account_payable_id = payable
        supply = make('product.product','supply',dict(name='Demo · Facility service',type='service',company_id=company.id,purchase_method='purchase',supplier_taxes_id=[(5,0,0)],property_account_expense_id=cost.id))
        purchase = make('purchase.order','purchase',dict(partner_id=vendor.id,company_id=company.id,department_id=products['gym'].fitzone_department.id,
            order_line=[(0,0,dict(product_id=supply.id,product_qty=1,price_unit=75,tax_ids=[(5,0,0)]))]))
        purchase.button_confirm()
        if purchase.state == 'to approve':
            purchase.button_approve()
        bill = make('account.move','purchase_bill',dict(move_type='in_invoice',company_id=company.id,journal_id=purchases.id,partner_id=vendor.id,invoice_date=today,date=today,
            invoice_line_ids=[(0,0,dict(product_id=supply.id,quantity=1,price_unit=75,account_id=cost.id,purchase_line_id=purchase.order_line.id,tax_ids=[(5,0,0)]))]))
        bill.action_post()
