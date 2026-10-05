from odoo import fields, models


class ProgressTracking(models.Model):
    _name = 'fitzone.progress.tracking'
    _description = 'Progress Tracking'

    member_id = fields.Many2one('res.partner', required=True)
    trainer_id = fields.Many2one('fitzone.trainer', required=True)
    record_date = fields.Date()
    weight = fields.Float()
    notes = fields.Text()