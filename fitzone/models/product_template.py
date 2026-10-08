from odoo import fields, models
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = 'product.template'
    
    package_type = fields.Selection(
        [
            ('general', 'General'),
            ('private', 'Private'),
            ('all_inclusive', 'All-Inclusive'),
        ],
        string='Package Type',
    )

    duration_months = fields.Integer(
        string='Duration (Months)',
    )

    total_sessions = fields.Integer(
        string='Total Sessions',
    )
    allow_mon = fields.Boolean('Monday')
    allow_tue = fields.Boolean('Tuesday')
    allow_wed = fields.Boolean('Wednesday')
    allow_thu = fields.Boolean('Thursday')
    allow_fri = fields.Boolean('Friday')
    allow_sat = fields.Boolean('Saturday')
    allow_sun = fields.Boolean('Sunday')

    # Time window in which the package allows class attendance (24h float)
    allowed_from = fields.Float('Allowed From', default=0.0)
    allowed_to = fields.Float('Allowed To', default=24.0)

    def allowed_weekdays(self):
        """Python weekday(): Monday = 0 ... Sunday = 6"""
        self.ensure_one()
        flags = [self.allow_mon, self.allow_tue, self.allow_wed, self.allow_thu,
                 self.allow_fri, self.allow_sat, self.allow_sun]
        return [i for i, f in enumerate(flags) if f]