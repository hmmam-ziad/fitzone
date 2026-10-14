"""Explicit ownership for live operational reporting; existing role rules are unchanged."""
from odoo import fields, models


class DashboardCompany0(models.Model):
    _inherit = 'fitzone.membership'

    company_id = fields.Many2one(
        'res.company', required=True, index=True, default=lambda self: self.env.company)


class DashboardCompany1(models.Model):
    _inherit = 'fitzone.room'

    company_id = fields.Many2one(
        'res.company', required=True, index=True, default=lambda self: self.env.company)


class DashboardCompany2(models.Model):
    _name = 'fitzone.gym.class'
    _inherit = ['fitzone.gym.class', 'fitzone.department.company.mixin']

    department_id = fields.Many2one('hr.department', check_company=True, index=True, domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]")

    company_id = fields.Many2one(
        'res.company', required=True, index=True, default=lambda self: self.env.company)


class DashboardCompany3(models.Model):
    _inherit = 'fitzone.class.booking'

    company_id = fields.Many2one(
        'res.company', required=True, index=True, default=lambda self: self.env.company)


class DashboardCompany4(models.Model):
    _name = 'fitzone.pt.session'
    _inherit = ['fitzone.pt.session', 'fitzone.department.company.mixin']

    department_id = fields.Many2one('hr.department', check_company=True, index=True, domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]")

    company_id = fields.Many2one(
        'res.company', required=True, index=True, default=lambda self: self.env.company)


class DashboardCompany5(models.Model):
    _name = 'fitzone.pool.booking'
    _inherit = ['fitzone.pool.booking', 'fitzone.department.company.mixin']

    department_id = fields.Many2one('hr.department', check_company=True, index=True, domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]")

    company_id = fields.Many2one(
        'res.company', required=True, index=True, default=lambda self: self.env.company)


class DashboardCompany6(models.Model):
    _name = 'fitzone.visit'
    _inherit = ['fitzone.visit', 'fitzone.department.company.mixin']

    department_id = fields.Many2one('hr.department', check_company=True, index=True, domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]")

    company_id = fields.Many2one(
        'res.company', required=True, index=True, default=lambda self: self.env.company)


class DashboardCompany7(models.Model):
    _name = 'fitzone.rehabilitation'
    _inherit = ['fitzone.rehabilitation', 'fitzone.department.company.mixin']

    department_id = fields.Many2one('hr.department', check_company=True, index=True, domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]")

    company_id = fields.Many2one(
        'res.company', required=True, index=True, default=lambda self: self.env.company)


class DashboardCompany8(models.Model):
    _name = 'fitzone.nutrition.consultation'
    _inherit = ['fitzone.nutrition.consultation', 'fitzone.department.company.mixin']

    department_id = fields.Many2one('hr.department', check_company=True, index=True, domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]")

    company_id = fields.Many2one(
        'res.company', required=True, index=True, default=lambda self: self.env.company)


class DashboardCompany9(models.Model):
    _name = 'fitzone.injury'
    _inherit = ['fitzone.injury', 'fitzone.department.company.mixin']

    department_id = fields.Many2one('hr.department', check_company=True, index=True, domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]")

    company_id = fields.Many2one(
        'res.company', required=True, index=True, default=lambda self: self.env.company)

