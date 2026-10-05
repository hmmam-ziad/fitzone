from odoo import fields, models


class PTSession(models.Model):
    _name = 'fitzone.pt.session'
    _description = 'Personal Training Session'
    _rec_name = 'member_id'

    member_id = fields.Many2one('res.partner', required=True)
    trainer_id = fields.Many2one('fitzone.trainer', required=True)
    membership_id = fields.Many2one('fitzone.membership', required=True)
    package_id = fields.Many2one('product.template', required=True)
    session_date = fields.Datetime()
    end_datetime = fields.Datetime()
    status = fields.Char()