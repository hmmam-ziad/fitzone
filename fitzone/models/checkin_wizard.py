from odoo import fields, models


class CheckinWizard(models.TransientModel):
    _name = 'fitzone.checkin.wizard'
    _description = 'Class Check-in'

    class_id = fields.Many2one('fitzone.gym.class', required=True)
    barcode = fields.Char(string='Member Barcode', required=True)

    def action_check_in(self):
        self.ensure_one()
        booking = self.env['fitzone.class.booking'].check_in_member(
            self.class_id.id, (self.barcode or '').strip())
        self.barcode = False
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Check-in successful',
                'message': '%s checked in.' % booking.member_id.name,
                'type': 'success',
                'sticky': False,
            },
        }