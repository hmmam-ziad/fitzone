from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class Rehabilitation(models.Model):
    _name = 'fitzone.rehabilitation'
    _inherit = 'fitzone.medical.audit.mixin'
    _rec_name = 'id'
    _description = 'Rehabilitation'

    member_id = fields.Many2one('res.partner', required=True)
    injury_id = fields.Many2one('fitzone.injury', required=True)
    physiotherapist_id = fields.Many2one('hr.employee', required=True)
    start_date = fields.Date()
    end_date = fields.Date()
    status = fields.Char()
    notes = fields.Text()

    injury_cause_id = fields.Many2one(
        'fitzone.injury.cause',
        string='Cause of Injury',
        related='injury_id.injury_cause_id',
        store=True,
        readonly=True,
    )
    sport_type = fields.Char(string='Sport / Exercise Type', required=True)
    prohibited_exercises = fields.Text(string='Prohibited Exercises')
    movement_restrictions = fields.Text(string='Movement Restrictions')
    medical_notes = fields.Text(
        string='Confidential Medical Notes',
        groups='fitzone.group_fitzone_physiotherapist,fitzone.group_fitzone_manager',
    )
    state = fields.Selection(
        [('draft', 'Draft'), ('in_progress', 'In Progress'),
         ('completed', 'Completed')],
        default='draft', required=True, copy=False,
    )

    @api.constrains('start_date', 'end_date')
    def _check_dates(self):
        for rec in self:
            if rec.start_date and rec.end_date and rec.end_date < rec.start_date:
                raise ValidationError(_("End date cannot be earlier than start date!"))

    @api.constrains('member_id', 'injury_id')
    def _check_member_injury_match(self):
        for rec in self:
            if rec.injury_id and rec.member_id != rec.injury_id.member_id:
                raise ValidationError(_("The selected member must match the member in the linked injury report!"))

    def action_start(self):
        for rec in self:
            if not rec.start_date:
                rec.start_date = fields.Date.context_today(rec)
            rec.state = 'in_progress'

    def action_complete(self):
        for rec in self:
            if not rec.end_date:
                rec.end_date = fields.Date.context_today(rec)
            rec.state = 'completed'

    def action_reset_draft(self):
        self.write({'state': 'draft'})

