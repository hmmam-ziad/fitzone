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

    pt_session_ids = fields.One2many(
        'fitzone.pt.session', 'member_id', string='Personal Training Sessions',
    )

    membership_status = fields.Char(
        compute='_compute_membership_status',
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

    @api.model
    def _load_pos_data_fields(self, config):
        fields = super()._load_pos_data_fields(config)
        fields += ['membership_no', 'membership_status']
        return fields

    @api.depends('membership_no')
    def _compute_membership_status(self):
        today = fields.Date.today()

        for partner in self:
            memberships = self.env['fitzone.membership'].search([
                ('member_id', '=', partner.id),
            ])

            status = 'Inactive'

            for membership in memberships:
                if (
                    membership.date_start
                    and membership.date_end
                    and membership.date_start <= today <= membership.date_end
                ):
                    freeze = self.env['fitzone.freeze'].search([
                        ('membership_id', '=', membership.id),
                        ('start_date', '<=', today),
                        ('end_date', '>=', today),
                    ], limit=1)

                    if not freeze:
                        status = 'Active'
                        break

            partner.membership_status = status