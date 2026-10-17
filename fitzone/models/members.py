from lxml import etree

from odoo import api, fields, models
from odoo.exceptions import AccessError
from odoo.fields import Domain

from .smart_button_helpers import (
    MEMBERSHIP_READERS, OPERATIONS, check_navigation, grouped_counts, related_action,
)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    fitzone_membership_count = fields.Integer(
        compute='_compute_fitzone_membership_count', compute_sudo=False,
        groups='fitzone.group_fitzone_manager,fitzone.group_fitzone_reception,fitzone.group_fitzone_trainer,fitzone.group_fitzone_physiotherapist,fitzone.group_fitzone_nutritionist',
    )
    fitzone_pt_session_count = fields.Integer(
        compute='_compute_fitzone_pt_session_count', compute_sudo=False,
        groups='fitzone.group_fitzone_manager,fitzone.group_fitzone_reception,fitzone.group_fitzone_trainer',
    )
    fitzone_class_booking_count = fields.Integer(
        compute='_compute_fitzone_class_booking_count', compute_sudo=False,
        groups='fitzone.group_fitzone_manager,fitzone.group_fitzone_reception,fitzone.group_fitzone_trainer',
    )

    @api.depends('membership_ids')
    @api.depends_context('uid', 'allowed_company_ids')
    def _compute_fitzone_membership_count(self):
        counts = grouped_counts(self, 'fitzone.membership', 'member_id', MEMBERSHIP_READERS)
        for member in self:
            member.fitzone_membership_count = counts.get(member.id, 0)

    @api.depends('pt_session_ids', 'pt_session_ids.trainer_id')
    @api.depends_context('uid', 'allowed_company_ids')
    def _compute_fitzone_pt_session_count(self):
        counts = grouped_counts(self, 'fitzone.pt.session', 'member_id', OPERATIONS)
        for member in self:
            member.fitzone_pt_session_count = counts.get(member.id, 0)

    def _fitzone_accessible_class_booking_ids(self):
        """Resolve only associations for caller-readable bookings and partners.

        Odoo 19 forbids Trainer domains/grouping on booking.member_id. The
        private elevated lookup is limited to IDs already readable by the
        caller, like the existing safe-identity helpers. Never expose its rows.
        """
        self.check_access('read')
        members = self.filtered(lambda record: record.id and isinstance(record.id, int))
        result = {member.id: [] for member in members}
        if not members:
            return result
        Booking = self.env['fitzone.class.booking']
        Booking.check_access('read')
        if Booking._has_field_access(Booking._fields['member_id'], 'read'):
            for member, ids in Booking._read_group(
                [('member_id', 'in', members.ids)], ['member_id'], ['id:array_agg'],
            ):
                result[member.id] = ids
        else:
            accessible_ids = Booking.search([]).ids
            links = Booking.sudo().search_fetch([
                ('id', 'in', accessible_ids), ('member_id', 'in', members.ids),
            ], ['member_id'])
            for booking in links:
                result[booking.member_id.id].append(booking.id)
        return result

    @api.depends('class_booking_ids', 'class_booking_ids.class_id.trainer_id')
    @api.depends_context('uid', 'allowed_company_ids')
    def _compute_fitzone_class_booking_count(self):
        ids_by_member = self._fitzone_accessible_class_booking_ids()
        all_ids = [booking_id for ids in ids_by_member.values() for booking_id in ids]
        accessible_ids = set(self.env['fitzone.class.booking'].search([
            ('id', 'in', all_ids),
        ]).ids)
        for member in self:
            # Batch recheck with ordinary ORM access, never count elevated rows.
            member.fitzone_class_booking_count = len(
                accessible_ids.intersection(ids_by_member.get(member.id, []))
            )

    def action_view_fitzone_memberships(self):
        check_navigation(self, MEMBERSHIP_READERS, 'fitzone.membership')
        return related_action(self, 'fitzone.action_fitzone_membership',
                              [('member_id', '=', self.id)], {'default_member_id': self.id})

    def action_view_fitzone_pt_sessions(self):
        check_navigation(self, OPERATIONS, 'fitzone.pt.session')
        return related_action(self, 'fitzone.action_fitzone_pt_session',
                              [('member_id', '=', self.id)], {'default_member_id': self.id})

    def action_view_fitzone_class_bookings(self):
        check_navigation(self, OPERATIONS, 'fitzone.class.booking')
        Booking = self.env['fitzone.class.booking']
        if Booking._has_field_access(Booking._fields['member_id'], 'read'):
            domain = [('member_id', '=', self.id)]
        else:
            domain = [('id', 'in', self._fitzone_accessible_class_booking_ids().get(self.id, []))]
        return related_action(self, 'fitzone.action_fitzone_class_booking', domain,
                              {'default_member_id': self.id})

    membership_no = fields.Char(copy=False, index=True, readonly=True)
    birth_date = fields.Date(
        groups='fitzone.group_fitzone_manager,fitzone.group_fitzone_reception',
    )

    emergency_contact_ids = fields.One2many(
        'fitzone.emergency.contact',
        'member_id',
        string='Emergency Contacts',
        groups='fitzone.group_fitzone_manager,fitzone.group_fitzone_reception',
    )
    class_booking_ids = fields.One2many(
        'fitzone.class.booking',
        'member_id',
        string='Class Bookings',
        groups='fitzone.group_fitzone_manager,fitzone.group_fitzone_reception,fitzone.group_fitzone_trainer',
    )

    membership_ids = fields.One2many(
        'fitzone.membership',
        'member_id',
        string='Memberships',
        groups='fitzone.group_fitzone_manager,fitzone.group_fitzone_reception,fitzone.group_fitzone_trainer,fitzone.group_fitzone_physiotherapist,fitzone.group_fitzone_nutritionist',
    )

    health_profile_ids = fields.One2many(
        'fitzone.health.profile',
        'member_id',
        string='Health Profile',
        groups='fitzone.group_fitzone_physiotherapist,fitzone.group_fitzone_nutritionist,fitzone.group_fitzone_manager',
    )

    pt_session_ids = fields.One2many(
        'fitzone.pt.session',
        'member_id',
        string='Personal Training Sessions',
        groups='fitzone.group_fitzone_manager,fitzone.group_fitzone_reception,fitzone.group_fitzone_trainer',
    )

    membership_status = fields.Char(
        compute='_compute_membership_status',
    )

    rehabilitation_ids = fields.One2many(
        'fitzone.rehabilitation',
        'member_id',
        string='Rehabilitation Files',
        groups='fitzone.group_fitzone_physiotherapist,fitzone.group_fitzone_manager',
    )
    active_rehab_id = fields.Many2one(
        'fitzone.rehabilitation',
        compute='_compute_active_rehab',
        string='Active Rehabilitation',
        groups='fitzone.group_fitzone_physiotherapist,fitzone.group_fitzone_manager',
        compute_sudo=False,
    )
    trainer_restriction_ids = fields.One2many(
        'fitzone.injury.type',
        'member_id',
        readonly=True,
        groups='fitzone.group_fitzone_physiotherapist,fitzone.group_fitzone_trainer,fitzone.group_fitzone_manager',
    )
    prohibited_exercises = fields.Text(
        compute='_compute_medical_restrictions',
        readonly=True,
        groups='fitzone.group_fitzone_physiotherapist,fitzone.group_fitzone_trainer,fitzone.group_fitzone_manager',
        compute_sudo=False,
    )
    movement_restrictions = fields.Text(
        compute='_compute_medical_restrictions',
        readonly=True,
        groups='fitzone.group_fitzone_physiotherapist,fitzone.group_fitzone_trainer,fitzone.group_fitzone_manager',
        compute_sudo=False,
    )
    progress_ids = fields.One2many(
        'fitzone.progress.tracking',
        'member_id',
        groups='fitzone.group_fitzone_manager,fitzone.group_fitzone_trainer',
    )
    visit_ids = fields.One2many('fitzone.visit', 'member_id', groups='fitzone.group_fitzone_manager,fitzone.group_fitzone_reception,fitzone.group_fitzone_trainer',)
    is_fitzone_member = fields.Boolean(string='FitZone Member', copy=False)

    freeze_history_ids = fields.One2many(
        'fitzone.freeze',
        'member_id',
        string='Freeze History',
        groups='fitzone.group_fitzone_manager,fitzone.group_fitzone_reception',
    )

    # ------------------------------------------------------------------
    # Compute methods
    # ------------------------------------------------------------------

    @api.depends_context('uid')
    @api.depends(
        'active_rehab_id',
        'rehabilitation_ids.prohibited_exercises',
        'rehabilitation_ids.movement_restrictions',
        'trainer_restriction_ids',
        'trainer_restriction_ids.restriction',
        'trainer_restriction_ids.prohibited_exercises',
        'class_booking_ids.status',
        'class_booking_ids.class_id.trainer_id.employee_id.user_id',
    )
    def _compute_medical_restrictions(self):
        allowed = any(self.env.user.has_group('fitzone.group_fitzone_' + role) for role in ('physiotherapist', 'manager'))
        for partner in self:
            rehab = partner.active_rehab_id if allowed else False
            if allowed:
                partner.prohibited_exercises = rehab.prohibited_exercises if rehab else False
                partner.movement_restrictions = rehab.movement_restrictions if rehab else False
            else:
                restrictions = self.env['fitzone.injury.type'].search([
                    ('member_id', '=', partner.id),
                ])
                partner.prohibited_exercises = '\n'.join(
                    filter(None, restrictions.mapped('prohibited_exercises'))
                ) or False
                partner.movement_restrictions = '\n'.join(
                    filter(None, restrictions.mapped('restriction'))
                ) or False

    @api.depends('rehabilitation_ids', 'rehabilitation_ids.state')
    def _compute_active_rehab(self):
        for partner in self:
            partner.active_rehab_id = partner.rehabilitation_ids.filtered(
                lambda rehab: rehab.state == 'in_progress'
            ).sorted('id', reverse=True)[:1]

    @api.depends('membership_no')
    def _compute_membership_status(self):
        for partner in self:
            partner.membership_status = partner._get_membership_status_value()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        if not self._fitzone_partner_chatter_allowed():
            self = self.with_context(tracking_disable=True)
        if self.env.context.get('fitzone_member'):
            for vals in vals_list:
                if not vals.get('membership_no'):
                    vals['membership_no'] = self.env['ir.sequence'].next_by_code(
                        'fitzone.member'
                    )
        records = super().create(vals_list)
        if any(vals.get('is_fitzone_member') or vals.get('parent_id') for vals in vals_list):
            self.env.registry.clear_cache()
        return records

    def write(self, vals):
        if not self._fitzone_partner_chatter_allowed():
            self = self.with_context(tracking_disable=True)
        result = super().write(vals)
        if {'is_fitzone_member', 'parent_id'} & vals.keys():
            self.env.registry.clear_cache()
        return result

    # ------------------------------------------------------------------
    # POS data loading
    # ------------------------------------------------------------------

    @api.model
    def _load_pos_data_fields(self, config):
        fields = super()._load_pos_data_fields(config)
        if self.env.user.has_group('fitzone.group_fitzone_sales'):
            return ['id', 'name', 'is_company', 'write_date']
        fields += ['membership_no', 'membership_status']
        return fields

    @api.model
    def _load_pos_data_domain(self, data, config):
        domain = super()._load_pos_data_domain(data, config)
        if self.env.user.has_group('fitzone.group_fitzone_sales'):
            return Domain.AND([domain, [('is_fitzone_member', '=', False)]])
        return domain

    @api.model
    def _load_pos_data_read(self, records, config):
        if self.env.user.has_group('fitzone.group_fitzone_sales'):
            records = records.filtered(lambda partner: not partner.is_fitzone_member)
        rows = super()._load_pos_data_read(records, config)
        if self.env.user.has_group('fitzone.group_fitzone_sales'):
            # Core downstream loaders require these keys, not customer accounting data.
            rows = [
                {key: row[key] for key in ('id', 'name', 'is_company', 'write_date')}
                | {'fiscal_position_id': False, 'property_account_receivable_id': False}
                for row in rows
            ]
        return rows

    @api.model
    def get_new_partner(self, config_id, domain, offset):
        if self.env.user.has_group('fitzone.group_fitzone_sales'):
            domain = list(Domain.AND([domain, [('is_fitzone_member', '=', False)]]))
        return super().get_new_partner(config_id, domain, offset)

    # ------------------------------------------------------------------
    # Membership helpers
    # ------------------------------------------------------------------

    def _get_membership_status_value(self):
        """Return only Active/Inactive, without exposing membership or freeze data."""
        self.ensure_one()
        self.check_access('read')
        today = fields.Date.today()
        # Internal callers need status without membership/freeze read permissions.
        memberships = self.env['fitzone.membership'].sudo().search([
            ('member_id', '=', self.id),
            ('state', 'not in', ['blocked', 'cancelled']),
        ])

        status = 'Inactive'

        for membership in memberships:
            if (
                membership.date_start
                and membership.date_end
                and membership.date_start <= today <= membership.date_end
            ):
                freeze = self.env['fitzone.freeze'].sudo().search([
                    ('membership_id', '=', membership.id),
                    ('start_date', '<=', today),
                    ('end_date', '>=', today),
                ], limit=1)

                if not freeze:
                    status = 'Active'
                    break

        return status

    def _assign_membership_number(self):
        """Assign only membership_no during an authorized membership sale."""
        self.ensure_one()
        self.check_access('read')
        self.env['fitzone.membership'].check_access('create')
        if not self.membership_no:
            number = self.env['ir.sequence'].next_by_code('fitzone.member')
            # Reception may sell memberships without general partner write access.
            self.sudo().write({'membership_no': number})

    @api.model
    def _sales_hidden_partner_ids(self):
        """Rule-only hierarchy lookup; return IDs, never partner values."""
        # Resolve member descendants without recursively applying the partner rule.
        partners = self.sudo().with_context(active_test=False)
        members = partners.search([('is_fitzone_member', '=', True)])
        return partners.search([('id', 'child_of', members.ids)]).ids

    def action_report_incident(self):
        self.ensure_one()
        self.check_access('read')
        trainer = self.env['fitzone.trainer'].search(
            [('employee_id.user_id', '=', self.env.uid)], limit=1,
        )
        report = self.env['fitzone.injury'].create({
            'member_id': self.id,
            'reported_by': trainer.employee_id.id,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'fitzone.injury',
            'view_mode': 'form',
            'res_id': report.id,
        }

    # ------------------------------------------------------------------
    # Chatter access control
    # ------------------------------------------------------------------

    @api.model
    def _fitzone_partner_chatter_allowed(self):
        return self.env.su or any(
            self.env.user.has_group('fitzone.group_fitzone_' + role)
            for role in ('manager', 'reception')
        )

    def _message_auto_subscribe(self, updated_values, followers_existing_policy='skip'):
        if self._fitzone_partner_chatter_allowed():
            return super()._message_auto_subscribe(updated_values, followers_existing_policy)

    def _message_subscribe(self, partner_ids=None, subtype_ids=None, customer_ids=None):
        if self._fitzone_partner_chatter_allowed():
            return super()._message_subscribe(partner_ids, subtype_ids, customer_ids)
        return False

    def message_subscribe(self, partner_ids=None, subtype_ids=None):
        if not self._fitzone_partner_chatter_allowed():
            raise AccessError('Partner chatter is available only to Manager and Reception.')
        return super().message_subscribe(partner_ids, subtype_ids)

    def _thread_to_store(self, store, fields, *, request_list=None):
        if not self._fitzone_partner_chatter_allowed():
            # Stale chatter clients must not initialize followers, activities or files.
            return
        return super()._thread_to_store(store, fields, request_list=request_list)

    def _message_followers_to_store(self, store, after=None, limit=100, filter_recipients=False, reset=False):
        if self._fitzone_partner_chatter_allowed():
            return super()._message_followers_to_store(store, after, limit, filter_recipients, reset)

    # ------------------------------------------------------------------
    # View / field access
    # ------------------------------------------------------------------

    @api.model
    def get_view(self, view_id=None, view_type='form', **options):
        # Core strips static field groups, but not our operation-aware price guard.
        # Apply it after the shared arch cache, preserving mixed-role access.
        result = super().get_view(view_id, view_type, **options)
        arch = etree.fromstring(result['arch'])
        if not self._has_field_access(self._fields['meeting_count'], 'read'):
            for node in arch.xpath(
                "//page[@name='sales_purchases'] "
                "| //button[@name='schedule_meeting' or @name='action_view_stock_serial']"
            ):
                node.getparent().remove(node)
        for node in arch.xpath('//field[@name]'):
            field = self._fields.get(node.get('name'))
            if field and not self._has_field_access(field, 'read'):
                # Embedded subview fields belong to their own model.
                if not node.xpath('ancestor::field'):
                    node.getparent().remove(node)
        result['arch'] = etree.tostring(arch, encoding='unicode')
        return result

    @api.model
    def _has_field_access(self, field, operation):
        if (
            field.name.startswith(('message_', 'activity_'))
            or field.name in {'has_message', 'my_activity_date_deadline'}
        ):
            if not self._fitzone_partner_chatter_allowed():
                return False

        if (
            field.name in {'property_product_pricelist', 'meeting_count', 'meeting_ids'}
            and not self.env.su
            and self.env.user.has_group('fitzone.group_fitzone_trainer')
            and not any(
                self.env.user.has_group('fitzone.group_fitzone_' + role)
                for role in ('manager', 'reception', 'sales', 'physiotherapist', 'nutritionist')
            )
        ):
            return False

        return super()._has_field_access(field, operation)
