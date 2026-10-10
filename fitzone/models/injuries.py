from odoo import _, api, fields, models
from odoo.exceptions import UserError


class FitzoneInjuryCause(models.Model):
    _name = 'fitzone.injury.cause'
    _description = 'Injury Cause Master'

    name = fields.Char(string='Cause Name', required=True)


class Injury(models.Model):
    _name = 'fitzone.injury'
    _description = 'Injury'
    _rec_name = 'member_id'

    member_id = fields.Many2one(
        'res.partner',
        required=True,
    )

    reported_by = fields.Many2one(
        'hr.employee',
        required=True,
    )

    physiotherapist_id = fields.Many2one(
        'hr.employee',
    )

    injury_date = fields.Date()

    cause = fields.Char()

    description = fields.Text()

    type_ids = fields.One2many(
        'fitzone.injury.type',
        'injury_id',
        string='Types',
    )

    injury_cause_id = fields.Many2one(
        'fitzone.injury.cause', string='Cause of Injury',
    )
    state = fields.Selection(
        [('draft', 'Draft'), ('submitted', 'Submitted to Clinic'),
         ('processed', 'In Rehab')],
        default='draft', required=True, copy=False,
    )

    def action_submit(self):
        self.write({'state': 'submitted'})
        return True

    def action_create_rehab_file(self):
        self.ensure_one()
        if not self.physiotherapist_id:
            raise UserError(_('Assign a physiotherapist before creating a rehab file.'))
        rehabilitation = self.env['fitzone.rehabilitation'].create({
            'member_id': self.member_id.id,
            'injury_id': self.id,
            'physiotherapist_id': self.physiotherapist_id.id,
            'sport_type': self.env.context.get('default_sport_type') or _('To be specified'),
        })
        self.write({'state': 'processed'})
        return {
            'type': 'ir.actions.act_window',
            'name': _('Rehabilitation'),
            'res_model': 'fitzone.rehabilitation',
            'view_mode': 'form',
            'res_id': rehabilitation.id,
            'target': 'current',
        }

    @api.model
    def get_pending_injury_count(self):
        # Only clinic users get a count; everyone else gets 0
        if not self.env.user.has_group('fitzone.group_fitzone_clinic'):
            return 0
        return self.search_count([('state', '=', 'submitted')])
