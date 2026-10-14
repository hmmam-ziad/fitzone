"""Friendly validation for company-owned department allocations.

Products deliberately allow any accessible department. Reports treat a resolved
allocation belonging to another company as Unassigned, without falling back.
"""
from odoo import api, models, _
from odoo.exceptions import ValidationError


class DepartmentCompanyMixin(models.AbstractModel):
    _name = 'fitzone.department.company.mixin'
    _description = 'Company department consistency'
    _check_company_auto = True

    def _fitzone_department_fields(self):
        return [name for name, field in self._fields.items()
                if field.type == 'many2one' and field.comodel_name == 'hr.department'
                and not field.related]

    @api.onchange('company_id')
    def _onchange_fitzone_department_company(self):
        for record in self:
            for name in record._fitzone_department_fields():
                department = record[name]
                if department.company_id and department.company_id != record.company_id:
                    record[name] = False

    def _check_company(self, fnames=None):
        for record in self:
            for name in record._fitzone_department_fields():
                department = record[name]
                if department.company_id and department.company_id != record.company_id:
                    raise ValidationError(_(
                        'Please choose a department belonging to %(company)s, or a shared department.',
                        company=record.company_id.display_name))
        return super()._check_company(fnames)
