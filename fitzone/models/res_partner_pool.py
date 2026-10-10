from dateutil.relativedelta import relativedelta

from odoo import fields, models

POOL_MIN_AGE = 15   # operational policy: nobody under 15 may use the pool


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def _fz_age_years(self):
        """Age in full years, or None when the birth date is unknown."""
        self.ensure_one()
        if not self.birth_date:
            return None
        today = fields.Date.context_today(self)
        return relativedelta(today, self.birth_date).years 