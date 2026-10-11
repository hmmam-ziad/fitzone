
from odoo import fields, models


class CheckinWizard(models.TransientModel):
    _name = 'fitzone.checkin.wizard'
    _description = 'FitZone Reception Check-in'

    barcode = fields.Char(
        string='Member Barcode',
        required=True,
    )
    class_id = fields.Many2one(
        'fitzone.gym.class',
        string='Class (Optional)',
    )

    def action_check_in(self):
        self.ensure_one()
        barcode = (self.barcode or '').strip()

        if self.class_id:
            booking = self.env[
                'fitzone.class.booking'
            ].check_in_member(self.class_id.id, barcode)

            message = '%s checked in for the class.' % (
                booking.member_id.name
            )
        else:
            visit = self.env[
                'fitzone.visit'
            ].check_in_by_barcode(barcode)

            if visit.membership_id.package_type == 'private':
                message = (
                    '%s checked in successfully. Remaining sessions: %s'
                ) % (
                    visit.member_id.name,
                    visit.remaining_sessions,
                )
            else:
                message = '%s checked in successfully.' % (
                    visit.member_id.name
                )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Check-in successful',
                'message': message,
                'type': 'success',
                'sticky': False,
            },
        }
