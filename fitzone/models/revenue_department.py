"""Client-managed allocation; no department is added to payments."""
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class InvoiceLine(models.Model):
    _name = 'account.move.line'
    _inherit = ['account.move.line', 'fitzone.department.company.mixin']

    fitzone_department_id = fields.Many2one(
        'hr.department', string='Reporting Department', check_company=True, index=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        compute='_compute_fitzone_department', store=True, readonly=False, precompute=True, copy=True,
        help='Customer invoice/refund line override; otherwise the product department is used.')

    @api.depends('product_id', 'move_id.move_type', 'display_type', 'company_id')
    def _compute_fitzone_department(self):
        for line in self:
            line.fitzone_department_id = (
                line.product_id.fitzone_department
                if line.move_id.move_type in ('out_invoice', 'out_refund') and line.display_type == 'product'
                and (not line.product_id.fitzone_department.company_id
                     or line.product_id.fitzone_department.company_id == line.company_id) else False)

    @api.constrains('fitzone_department_id', 'move_id', 'display_type')
    def _check_fitzone_department(self):
        if any(line.fitzone_department_id and (
                line.move_id.move_type not in ('out_invoice', 'out_refund')
                or line.display_type != 'product') for line in self):
            raise ValidationError(_('Reporting Department is only available on customer invoice/refund product lines.'))


class PosConfig(models.Model):
    _name = 'pos.config'
    _inherit = ['pos.config', 'fitzone.department.company.mixin']

    fitzone_department_id = fields.Many2one(
        'hr.department', string='Default Department', check_company=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help='Reporting fallback when a sold product has no Reporting Department.')


class PosSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_fitzone_department_id = fields.Many2one(
        related='pos_config_id.fitzone_department_id', readonly=False,
        string='Default Department')
