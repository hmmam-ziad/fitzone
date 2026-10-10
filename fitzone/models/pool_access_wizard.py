from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .res_partner_pool import POOL_MIN_AGE


class PoolAccessWizard(models.TransientModel):
    """Reception screen: may this member enter the pool right now?"""
    _name = 'fitzone.pool.access.wizard'
    _description = 'Pool Access Check'

    barcode = fields.Char(string='Membership Barcode')
    member_id = fields.Many2one('res.partner', string='Member')
    usage_type = fields.Selection(
        [
            ('free_swim', 'Free Swim'),
            ('lesson', 'Group Lesson'),
            ('private_pt', 'Private Session'),
        ],
        default='free_swim',
        required=True,
    )
    state = fields.Selection(
        [
            ('new', 'New'),
            ('allowed', 'Allowed'),
            ('denied', 'Denied'),
            ('registered', 'Entry Registered'),
        ],
        default='new',
        readonly=True,
    )
    message = fields.Text(readonly=True)
    fee = fields.Float(string='Fee (JOD)', readonly=True)
    membership_id = fields.Many2one('fitzone.membership', readonly=True)
    slot_id = fields.Many2one('fitzone.pool.slot', readonly=True)
    booking_id = fields.Many2one('fitzone.pool.booking', readonly=True)

    @api.onchange('barcode')
    def _onchange_barcode(self):
        if self.barcode:
            membership = self.env['fitzone.membership'].search(
                [('barcode', '=', self.barcode.strip())], limit=1)
            if membership:
                self.member_id = membership.member_id


    def _evaluate(self):
        """Apply the pool rules and return the values to write on the wizard."""
        self.ensure_one()
        Membership = self.env['fitzone.membership']
        Slot = self.env['fitzone.pool.slot']
        Booking = self.env['fitzone.pool.booking']
        now = fields.Datetime.now()
        today = fields.Date.context_today(self)

        member = self.member_id
        if not member and self.barcode:
            member = Membership.search(
                [('barcode', '=', self.barcode.strip())], limit=1).member_id

        def denied(message, **extra):
            return dict(
                state='denied', message=message, fee=0.0,
                member_id=member.id if member else False, **extra)

        if not member:
            return denied(_("Select a member or scan a membership barcode."))

        # 1. Minimum age (applies to EVERY membership type and service)
        age = member._fz_age_years()
        if age is None:
            return denied(_(
                "Birth date is missing, so the minimum age (%s) cannot be "
                "verified. Update the member profile first.", POOL_MIN_AGE))
        if age < POOL_MIN_AGE:
            return denied(_(
                "ENTRY DENIED: members under %s years old are not allowed in "
                "the pool (member age: %s).", POOL_MIN_AGE, age))

        membership = Membership.search([
            ('member_id', '=', member.id),
            ('state', '=', 'active'),
            ('date_start', '<=', today),
            ('date_end', '>=', today),
        ], limit=1)
        if not membership:
            return denied(_("ENTRY DENIED: the member has no active membership."))

        slot = Slot._find_open_slot(self.usage_type, now)

        if self.usage_type == 'free_swim':
            if not slot:
                hours = Slot._today_hours_text('free_swim', now)
                if hours:
                    msg = _("ENTRY DENIED: free swim is not available now. "
                            "Today's free-swim hours: %s.", hours)
                else:
                    msg = _("ENTRY DENIED: no free-swim session is scheduled today.")
                return denied(msg, membership_id=membership.id)
            return dict(
                state='allowed', fee=0.0,
                message=_("ACCESS GRANTED: free swim is included in the active "
                          "membership at no extra cost (0 JOD)."),
                member_id=member.id, membership_id=membership.id, slot_id=slot.id)

        # Group lesson / private session: needs a confirmed booking in the open slot
        label = dict(self._fields['usage_type'].selection)[self.usage_type]
        booking = Booking.browse()
        if slot:
            booking = Booking.search([
                ('member_id', '=', member.id),
                ('pool_slot_id', '=', slot.id),
                ('status', '=', 'confirmed'),
            ], limit=1)
        if not booking:
            return denied(
                _("ENTRY DENIED: no confirmed %s booking for the current time.", label),
                membership_id=membership.id)
        return dict(
            state='allowed', fee=0.0,
            message=_("ACCESS GRANTED: %s booking confirmed.", label),
            member_id=member.id, membership_id=membership.id,
            slot_id=slot.id, booking_id=booking.id)

    
    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_check(self):
        self.ensure_one()
        self.write(self._evaluate())
        return self._reopen()

    def action_register_entry(self):
        """Log the entry (free swim creates a booking row; lessons check in)."""
        self.ensure_one()
        if self.state != 'allowed':
            raise UserError(_("Only an allowed access can be registered."))
        if self.usage_type == 'free_swim':
            booking = self.env['fitzone.pool.booking'].create({
                'member_id': self.member_id.id,
                'membership_id': self.membership_id.id,
                'pool_slot_id': self.slot_id.id,
                'status': 'checked_in',
            })
        else:
            booking = self.booking_id
            booking.status = 'checked_in'
        self.write({
            'state': 'registered',
            'booking_id': booking.id,
            'message': _("Entry registered."),
        })
        return self._reopen()

    def action_new_check(self):
        self.ensure_one()
        self.write({
            'barcode': False, 'member_id': False, 'state': 'new',
            'message': False, 'fee': 0.0, 'membership_id': False,
            'slot_id': False, 'booking_id': False,
        })
        return self._reopen()