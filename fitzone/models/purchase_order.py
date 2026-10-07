# ------------------------------------------------------------
# Modified By   : HmMam Alsukhni
# Modified       : 07-10-2026 | 03:45 PM (GMT+3)
# ------------------------------------------------------------
from odoo import _, fields, models
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    requested_by = fields.Many2one('hr.employee')
    fz_request_id = fields.Many2one('fitzone.purchase.request', string='Purchase Request', readonly=True, copy=False)

    def action_rfq_send(self):
        """Nothing goes to the supplier before management approval.

        The company is configured with two-step PO validation (threshold 0),
        so every PO reaches state 'purchase' only after a Purchase Manager
        approves it. Until then sending is blocked.
        """
        unapproved = self.filtered(lambda po: po.state not in ('purchase', 'done'))
        if unapproved:
            raise UserError(_(
                "Purchase orders cannot be sent to the supplier before "
                "management approval. Confirm the order and wait for a "
                "Purchase Manager to approve it first.\n\nOrders: %s",
                ', '.join(unapproved.mapped('name'))))
        return super().action_rfq_send()