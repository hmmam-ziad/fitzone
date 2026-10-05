from odoo import fields, models


class TrainerCommission(models.Model):
    _name = 'fitzone.trainer.commission'
    _description = 'Trainer Commission'

    trainer_id = fields.Many2one('fitzone.trainer', required=True)
    pt_session_id = fields.Many2one('fitzone.pt.session', required=True)
    commission_rule_id = fields.Many2one('fitzone.commission.rule', required=True)
    amount = fields.Float()