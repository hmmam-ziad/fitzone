from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    membership_no = fields.Char(copy=False, index=True, readonly=True)
    birth_date = fields.Date()

    emergency_contact_ids = fields.One2many(
        'fitzone.emergency.contact',
        'member_id',
        string='Emergency Contacts',
    )

    membership_ids = fields.One2many(
        'fitzone.membership',
        'member_id',
        string='Memberships',
    )

    health_profile_ids = fields.One2many(
        'fitzone.health.profile',
        'member_id',
        string='Health Profile',
        groups='fitzone.group_fitzone_clinic',
    )

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get('fitzone_member'):
            for vals in vals_list:
                if not vals.get('membership_no'):
                    vals['membership_no'] = self.env['ir.sequence'].next_by_code(
                        'fitzone.member'
                    )
        return super().create(vals_list)
