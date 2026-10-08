from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    allow_mon = fields.Boolean('Monday')
    allow_tue = fields.Boolean('Tuesday')
    allow_wed = fields.Boolean('Wednesday')
    allow_thu = fields.Boolean('Thursday')
    allow_fri = fields.Boolean('Friday')
    allow_sat = fields.Boolean('Saturday')
    allow_sun = fields.Boolean('Sunday')

    def allowed_weekdays(self):
        """Python weekday(): Monday = 0 ... Sunday = 6"""
        self.ensure_one()
        flags = [
            self.allow_mon, self.allow_tue, self.allow_wed, self.allow_thu,
            self.allow_fri, self.allow_sat, self.allow_sun
        ]
        return [i for i, f in enumerate(flags) if f]


class Membership(models.Model):
    _name = 'fitzone.membership'
    _description = 'Membership'
    _rec_name = 'member_id'

    member_id = fields.Many2one('res.partner', required=True)
    package_id = fields.Many2one('product.template', required=True)
    barcode = fields.Char()
    date_start = fields.Date(required=True, default=fields.Date.today)
    date_end = fields.Date(required=True)
    state = fields.Selection(
        [('active', 'Active'), ('expired', 'Expired'), ('cancelled', 'Cancelled')],
        default='active', required=True
    )