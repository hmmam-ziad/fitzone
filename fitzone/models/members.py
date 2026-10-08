from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    membership_no = fields.Char()
    birth_date = fields.Date()

    membership_status = fields.Char(
        compute='_compute_membership_status',
    )

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