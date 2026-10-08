from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ClassBooking(models.Model):
    _name = 'fitzone.class.booking'
    _description = 'Class Booking'
    _rec_name = 'member_id'

    member_id = fields.Many2one(
        'res.partner',
        required=True,
    )

    membership_id = fields.Many2one(
        'fitzone.membership',
        readonly=True,
    )

    class_id = fields.Many2one(
        'fitzone.gym.class',
        required=True,
    )

    booking_date = fields.Datetime(
        default=fields.Datetime.now,
    )

    status = fields.Selection(
        [
            ('booked', 'Booked'),
            ('cancelled', 'Cancelled'),
            ('attended', 'Attended'),
        ],
        default='booked',
        required=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = self.browse()

        for vals in vals_list:
            gym_class = self.env['fitzone.gym.class'].browse(
                vals['class_id']
            )

            # Lock the class row so two people cannot book
            # the last seat at the same time.
            self.env.cr.execute(
                "SELECT id FROM fitzone_gym_class WHERE id = %s FOR UPDATE",
                (gym_class.id,),
            )

            class_date = fields.Datetime.context_timestamp(
                self,
                gym_class.start_datetime,
            ).date()

            # 1) Active membership
            membership = self.env['fitzone.membership'].search(
                [
                    ('member_id', '=', vals['member_id']),
                    ('state', '=', 'active'),
                    ('date_start', '<=', class_date),
                    ('date_end', '>=', class_date),
                ],
                limit=1,
            )

            if not membership:
                raise ValidationError(
                    "This member has no active membership "
                    "on the class date."
                )

            # 2) Class day is covered by the package
            if class_date.weekday() not in (
                membership.package_id.allowed_weekdays()
            ):
                raise ValidationError(
                    "Your package does not include this day."
                )

            # 3) Member cannot book the same class twice
            if self.search_count(
                [
                    ('member_id', '=', vals['member_id']),
                    ('class_id', '=', gym_class.id),
                    ('status', 'in', ('booked', 'attended')),
                ]
            ):
                raise ValidationError(
                    "This member has already booked this class."
                )

            # 4) Room capacity
            booked = self.search_count(
                [
                    ('class_id', '=', gym_class.id),
                    ('status', 'in', ('booked', 'attended')),
                ]
            )

            if booked >= gym_class.room_id.capacity:
                raise ValidationError(
                    "The class is full."
                )

            vals['membership_id'] = membership.id

            records |= super().create([vals])

        return records

    def action_cancel(self):
        # The cancelled seat becomes vacant.
        # There is no waiting list or automatic transfer.
        for rec in self:
            if rec.status != 'booked':
                raise ValidationError(
                    "This booking cannot be cancelled."
                )

            rec.status = 'cancelled'

    @api.model
    def check_in_member(self, class_id, barcode):
        """Check-in screen: only pre-registered members can check in."""

        membership = self.env['fitzone.membership'].search(
            [
                ('barcode', '=', barcode),
            ],
            limit=1,
        )

        booking = self.browse()

        if membership:
            booking = self.search(
                [
                    ('class_id', '=', class_id),
                    ('member_id', '=', membership.member_id.id),
                    ('status', '=', 'booked'),
                ],
                limit=1,
            )

        # Walk-ins are not allowed.
        if not booking:
            raise ValidationError(
                "Not pre-registered for this class "
                "(walk-ins are not allowed)."
            )

        # Create attendance record if it does not exist.
        attendance = self.env['fitzone.attendance'].search(
            [
                ('booking_id', '=', booking.id),
            ],
            limit=1,
        )

        if attendance:
            attendance.attended = True
        else:
            self.env['fitzone.attendance'].create(
                {
                    'booking_id': booking.id,
                    'attended': True,
                }
            )

        # Mark the booking as attended.
        booking.status = 'attended'

        return booking