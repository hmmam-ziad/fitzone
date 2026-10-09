# ------------------------------------------------------------
# Auther        : HmMam Alsukhni
# Created       : 07-10-2026 | 04:30 PM (GMT+3)
# ------------------------------------------------------------

import logging

from odoo import models

_logger = logging.getLogger(__name__)


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _action_done(self, cancel_backorder=False):
        moves = super()._action_done(cancel_backorder=cancel_backorder)
        templates = moves.filtered(
            lambda m: m.state == 'done').product_id.product_tmpl_id
        if templates:
            # An alert problem must never block a sale or a receipt.
            try:
                with self.env.cr.savepoint():
                    templates.sudo()._fz_check_low_stock()
            except Exception:
                _logger.exception("FitZone: low-stock check failed")
        return moves
