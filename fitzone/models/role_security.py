from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        info = super().session_info()
        user = self.env.user
        info['fitzone_hide_admin_ui'] = (
            user.has_group('fitzone.group_fitzone_manager')
            and not user.has_group('fitzone.group_fitzone_full_admin_ui')
        )
        return info
