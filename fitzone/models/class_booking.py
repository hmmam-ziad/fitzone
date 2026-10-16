from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


class ClassBooking(models.Model):
    _name = 'fitzone.class.booking'
    _description = 'Class Booking'
    _rec_name = 'member_id'

    member_id = fields.Many2one(
        'res.partner',
        required=True,
        groups='fitzone.group_fitzone_manager,fitzone.group_fitzone_reception',
        domain="[('membership_ids', '!=', False)]",
    )
    membership_id = fields.Many2one(
        'fitzone.membership',
        readonly=True,
        groups='fitzone.group_fitzone_manager,fitzone.group_fitzone_reception',
    )
    member_name = fields.Char(compute='_compute_attendee_identity', compute_sudo=False)
    membership_number = fields.Char(compute='_compute_attendee_identity', compute_sudo=False)
    class_id = fields.Many2one('fitzone.gym.class', required=True)
    booking_date = fields.Datetime(default=fields.Datetime.now)
    status = fields.Selection(
        [('booked', 'Booked'), ('cancelled', 'Cancelled'), ('attended', 'Attended')],
        default='booked', required=True)

    def _attendee_identity(self):
        self.ensure_one()
        self.check_access('read')
        # Own-class readers need only these two identity strings, never a partner record.
        member = self.sudo().member_id
        return member.name, member.membership_no

    @api.depends('member_id')
    def _compute_attendee_identity(self):
        for booking in self:
            booking.member_name, booking.membership_number = booking._attendee_identity()

    @api.model
    def _check_entitlement(self, member_id, class_start, membership=None):
        """Validate membership status, freeze, day and time.
        Returns the membership or raises ValidationError with the reason."""
        local_dt = fields.Datetime.context_timestamp(self, class_start)
        class_date = local_dt.date()
        class_hour = local_dt.hour + local_dt.minute / 60.0
        Membership = self.env['fitzone.membership']

        if not membership:
            candidates = Membership.search([
                ('member_id', '=', member_id),
                ('date_start', '<=', class_date),
                ('date_end', '>=', class_date),
            ])
            if not candidates:
                if Membership.search_count([('member_id', '=', member_id)]):
                    raise ValidationError(_("Membership expired or does not cover the class date."))
                raise ValidationError(_("This member has no membership."))
            membership = candidates.filtered(lambda m: m.state == 'active')[:1]
            if not membership:
                state = candidates[0].state
                if state == 'blocked':
                    raise ValidationError(_("Membership is blocked."))
                if state == 'expired':
                    raise ValidationError(_("Membership expired."))
                raise ValidationError(_("Membership is not active (%s).") % state)

        if self.env['fitzone.freeze'].search_count([
            ('membership_id', '=', membership.id),
            ('start_date', '<=', class_date),
            ('end_date', '>=', class_date),
        ]):
            raise ValidationError(_("Membership is frozen on the class date."))

        package = membership.package_id
        if class_date.weekday() not in package.allowed_weekdays():
            raise ValidationError(_("Package does not include this day."))

        # Time covered by the package
        if not (package.allowed_from <= class_hour <= package.allowed_to):
            raise ValidationError(_("Package does not include this time."))

        return membership

    @api.model_create_multi
    def create(self, vals_list):
        records = self.browse()
        for vals in vals_list:
            gym_class = self.env['fitzone.gym.class'].browse(vals['class_id'])

            self.env.cr.execute(
                "SELECT id FROM fitzone_gym_class WHERE id = %s FOR UPDATE",
                (gym_class.id,))

            # 1) Status, freeze, day and time
            membership = self._check_entitlement(
                vals['member_id'], gym_class.start_datetime)

            if self.search_count([
                ('member_id', '=', vals['member_id']),
                ('class_id', '=', gym_class.id),
                ('status', 'in', ('booked', 'attended')),
            ]):
                raise ValidationError(_("This member has already booked this class."))

            booked = self.search_count([
                ('class_id', '=', gym_class.id),
                ('status', 'in', ('booked', 'attended')),
            ])
            if booked >= gym_class.room_id.capacity:
                raise ValidationError(_("The class is full."))

            vals['membership_id'] = membership.id
            booking = super().create([vals])
            self.env['fitzone.attendance']._ensure_booking_attendance(booking)
            records |= booking
        return records

    def write(self, vals):
        if 'class_id' in vals or 'member_id' in vals:
            raise ValidationError(_("Member and class cannot be changed. Cancel and create a new booking."))
        if vals.get('status') == 'booked' and any(r.status != 'booked' for r in self):
            raise ValidationError(_("A cancelled or attended booking cannot be reopened."))
        return super().write(vals)

    def action_cancel(self):
        for rec in self:
            if rec.status != 'booked':
                raise ValidationError(_("This booking cannot be cancelled."))
            rec.status = 'cancelled'

    @api.model
    def check_in_member(self, class_id, barcode):
        if (not self.env.su and self.env.user.has_group('fitzone.group_fitzone_trainer')
                and not any(self.env.user.has_group('fitzone.group_fitzone_' + role) for role in ('manager', 'reception'))):
            return self.env['fitzone.attendance']._trainer_check_in(class_id, barcode)
        membership = self.env['fitzone.membership'].search(
            [('barcode', '=', barcode)], limit=1)
        booking = self.browse()
        if membership:
            booking = self.search([
                ('class_id', '=', class_id),
                ('member_id', '=', membership.member_id.id),
                ('status', '=', 'booked'),
            ], limit=1)
        if not booking:
            raise ValidationError(_("Not pre-registered for this class (walk-ins are not allowed)."))

        if membership.state != 'active':
            raise ValidationError(
                _("Membership is %s. Check-in denied.") % membership.state)
        today = fields.Date.context_today(self)
        if self.env['fitzone.freeze'].search_count([
            ('membership_id', '=', membership.id),
            ('start_date', '<=', today),
            ('end_date', '>=', today),
        ]):
            raise ValidationError(_("Membership is frozen. Check-in denied."))

        booking.status = 'attended'
        self.env['fitzone.attendance']._ensure_booking_attendance(booking)

        self.env['fitzone.visit'].with_context(
            allow_barcode_checkin=True
        ).create({
            'member_id': booking.member_id.id,
            'membership_id': membership.id,
            'visit_date': fields.Datetime.now(),
            'status': 'Checked In',
            'remaining_sessions': membership.remaining_sessions,
        })

        return booking

    @api.depends('member_id')
    def _compute_display_name(self):
        if (not self.env.su and self.env.user.has_group('fitzone.group_fitzone_trainer')
                and not any(self.env.user.has_group('fitzone.group_fitzone_' + role) for role in ('manager', 'reception'))):
            for booking in self:
                booking.display_name = booking.member_name
        else:
            super()._compute_display_name()