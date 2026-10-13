
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class Visit(models.Model):
    _name = 'fitzone.visit'
    _description = 'Visit'
    _order = 'visit_date desc, id desc'

    member_id = fields.Many2one(
        'res.partner',
        required=True,
        domain="[('membership_ids', '!=', False)]",
    )

    member_number = fields.Char(
        related='member_id.membership_no',
        string='Member ID',
        store=True,
        index=True,
        readonly=True,
    )

    membership_id = fields.Many2one(
        'fitzone.membership',
        required=True,
        domain="[('member_id', '=', member_id)]",
    )

    visit_date = fields.Datetime(
        required=True,
        default=fields.Datetime.now,
    )

    remaining_sessions = fields.Integer(readonly=True)

    status = fields.Char(
        default='Checked In',
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('allow_barcode_checkin'):
            raise ValidationError(
                'Visits can only be created through barcode check-in.'
            )
        return super().create(vals_list)

    @api.model
    def check_in_by_barcode(self, barcode):
        barcode = (barcode or '').strip()

        if not barcode:
            raise ValidationError(
                'Please scan or enter a member barcode.'
            )

        membership = self.env['fitzone.membership'].search([
            ('barcode', '=', barcode),
        ], limit=1)

        if not membership:
            raise ValidationError(
                'No membership found for this barcode.'
            )

        today = fields.Date.context_today(self)

        if membership.state == 'blocked':
            raise ValidationError(
                'Check-in denied: membership is blocked.'
            )

        if membership.state == 'cancelled':
            raise ValidationError(
                'Check-in denied: membership is cancelled.'
            )

        if membership.state == 'draft':
            raise ValidationError(
                'Check-in denied: membership is not activated.'
            )

        if membership.state == 'expired':
            raise ValidationError(
                'Check-in denied: membership has expired.'
            )

        if not membership.date_start or not membership.date_end:
            raise ValidationError(
                'Check-in denied: membership dates are missing.'
            )

        if today < membership.date_start or today > membership.date_end:
            raise ValidationError(
                'Check-in denied: membership is not valid today.'
            )

        freeze = self.env['fitzone.freeze'].search_count([
            ('membership_id', '=', membership.id),
            ('start_date', '<=', today),
            ('end_date', '>=', today),
        ])

        if freeze:
            raise ValidationError(
                'Check-in denied: membership is frozen.'
            )

        if (
            membership.package_type == 'private'
            and membership.total_sessions > 0
            and membership.remaining_sessions <= 0
        ):
            raise ValidationError(
                'Check-in denied: no sessions remaining.'
            )

        overdue_installment = self.env['fitzone.installment'].search([
            ('plan_id.membership_id', '=', membership.id),
            ('due_date', '<=', today),
            ('status', '=', 'pending'),
        ], limit=1)

        if overdue_installment:
            raise ValidationError(
                'Check-in denied: an installment is overdue. '
                'Please settle the outstanding payment.'
            )

        if (
            membership.package_type == 'private'
            and membership.total_sessions > 0
        ):
            membership.consumed_sessions += 1

        visit = self.with_context(
            allow_barcode_checkin=True
        ).create({
            'member_id': membership.member_id.id,
            'membership_id': membership.id,
            'visit_date': fields.Datetime.now(),
            'status': 'Checked In',
            'remaining_sessions': membership.remaining_sessions,
        })

        return visit
