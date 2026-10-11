from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models


class FreezeRequestWizard(models.TransientModel):
    """Reception screen: request a freeze on ONE package of a member."""
    _name = 'fitzone.freeze.request.wizard'
    _description = 'Freeze Request'

    member_id = fields.Many2one('res.partner', string='Member', required=True)
    membership_id = fields.Many2one(
        'fitzone.membership',
        string='Package to Freeze',
        required=True,
        domain="[('member_id', '=', member_id), ('state', '=', 'active')]",
    )
    start_date = fields.Date(required=True, default=fields.Date.context_today)
    end_date = fields.Date(required=True)

    days = fields.Integer(compute='_compute_preview', string='Requested Days')
    allowed_days = fields.Integer(compute='_compute_preview')
    used_days = fields.Integer(compute='_compute_preview')
    remaining_days = fields.Integer(
        compute='_compute_preview', string='Remaining Before Request')
    current_end_date = fields.Date(compute='_compute_preview')
    new_end_date = fields.Date(compute='_compute_preview')

    @api.onchange('member_id')
    def _onchange_member_id(self):
        if self.membership_id and self.membership_id.member_id != self.member_id:
            self.membership_id = False
        if self.member_id and not self.membership_id:
            active = self.env['fitzone.membership'].search([
                ('member_id', '=', self.member_id.id),
                ('state', '=', 'active'),
            ])
            if len(active) == 1:
                self.membership_id = active

    @api.depends('membership_id', 'start_date', 'end_date')
    def _compute_preview(self):
        for rec in self:
            membership = rec.membership_id
            days = 0
            if rec.start_date and rec.end_date and rec.end_date >= rec.start_date:
                days = (rec.end_date - rec.start_date).days + 1
            rec.days = days
            rec.allowed_days = membership.freeze_allowed_days if membership else 0
            rec.used_days = membership.freeze_used_days if membership else 0
            rec.remaining_days = membership.freeze_remaining_days if membership else 0
            rec.current_end_date = membership.date_end if membership else False
            rec.new_end_date = (
                membership.date_end + relativedelta(days=days)
                if membership and membership.date_end else False)

    def action_request_freeze(self):
        """Create the freeze (all validations run there) and open its record."""
        self.ensure_one()
        freeze = self.env['fitzone.freeze'].create({
            'membership_id': self.membership_id.id,
            'start_date': self.start_date,
            'end_date': self.end_date,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Freeze'),
            'res_model': 'fitzone.freeze',
            'res_id': freeze.id,
            'view_mode': 'form',
            'target': 'current',
        }