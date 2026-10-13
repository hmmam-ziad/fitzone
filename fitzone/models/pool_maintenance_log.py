from odoo import fields, models


class PoolMaintenanceLog(models.Model):
    _name = 'fitzone.pool.maintenance.log'
    _description = 'Pool Cleaning and Maintenance Log'
    _rec_name = 'task'

    date = fields.Date(required=True, default=fields.Date.context_today)
    task = fields.Char(required=True)
    done_by = fields.Many2one('res.users', required=True, default=lambda self: self.env.user)
    notes = fields.Text()
