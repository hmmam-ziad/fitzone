# import logging

# _logger = logging.getLogger(__name__)


# def pre_init_hook(env):
#     company = env.ref('base.main_company')
#     jo = env.ref('base.jo')
#     jod = env.ref('base.JOD')

#     if company._existing_accounting():
#         _logger.info(
#             "FitZone: company '%s' already has accounting entries; "
#             "currency/chart were NOT switched to Jordan.", company.name)
#         return

#     jod.active = True
#     company.write({
#         'name': 'FitZone',
#         'country_id': jo.id,
#         'currency_id': jod.id,
#     })

#     if company.chart_template != 'jo_standard':
#         env['account.chart.template'].try_loading('jo_standard', company)

#     if hasattr(env.registry, '_auto_install_template'):
#         del env.registry._auto_install_template


# def post_init_hook(env):
#     """Install-time opt-in for unused, active percentage sales taxes only.

#     Odoo 19 computes price_include from price_include_override. Do not change
#     the company default: that would affect purchases and taxes created later.
#     Posted base lines AND tax lines count as usage. Per-tax savepoints leave
#     accounting untouched on failure; missing charts/taxes are harmless.
#     """
#     try:
#         with env.cr.savepoint():
#             companies = env['res.company'].sudo().search([])
#             for company in companies:
#                 try:
#                     with env.cr.savepoint():
#                         _include_company_sales_taxes(env, company)
#                 except Exception:
#                     _logger.warning('FitZone: could not configure sales taxes for company %s; skipped.',
#                                     company.id, exc_info=True)
#     except Exception:
#         _logger.warning('FitZone: sales tax installation setup skipped.', exc_info=True)


# def _include_company_sales_taxes(env, company):
#     if not company.chart_template:
#         _logger.info('FitZone: company %s has no chart; sales taxes unchanged.', company.name)
#         return
#     taxes = env['account.tax'].sudo().with_company(company).search([
#         ('company_id', '=', company.id), ('active', '=', True),
#         ('type_tax_use', '=', 'sale'), ('amount_type', '=', 'percent'),
#     ])
#     if not taxes:
#         _logger.info('FitZone: company %s has no eligible sales taxes.', company.name)
#         return
#     for tax in taxes:
#         try:
#             with env.cr.savepoint():
#                 xmlid = tax.get_external_id().get(tax.id) or '(no XML ID)'
#                 used = env['account.move.line'].sudo().search_count([
#                     ('parent_state', '=', 'posted'),
#                     '|', ('tax_ids', 'in', tax.ids), ('tax_line_id', '=', tax.id),
#                 ], limit=1)
#                 if used:
#                     _logger.info('FitZone: used sales tax %s / %s [%s] skipped.',
#                                  company.name, tax.name, xmlid)
#                 elif not tax.price_include:
#                     tax.write({'price_include_override': 'tax_included'})
#                     _logger.info('FitZone: sales tax %s / %s [%s] now includes tax in price.',
#                                  company.name, tax.name, xmlid)
#         except Exception:
#             _logger.warning('FitZone: sales tax %s in company %s skipped after a configuration error.',
#                             tax.id, company.id, exc_info=True)


import logging

_logger = logging.getLogger(__name__)


def pre_init_hook(env):
    company = env.ref('base.main_company')
    jo = env.ref('base.jo')
    jod = env.ref('base.JOD')

    if company._existing_accounting():
        _logger.info(
            "FitZone: company '%s' already has accounting entries; "
            "currency/chart were NOT switched to Jordan.", company.name)
        return

    jod.active = True
    company.write({
        'name': 'FitZone',
        'country_id': jo.id,
        'currency_id': jod.id,
    })

    if company.chart_template != 'jo_standard':
        env['account.chart.template'].try_loading('jo_standard', company)

    if hasattr(env.registry, '_auto_install_template'):
        del env.registry._auto_install_template


def post_init_hook(env):
    """Install-time: make unused, active percentage sales taxes Tax Excluded.

    Odoo 19 computes price_include from price_include_override. Do not change
    the company default: that would affect purchases and taxes created later.
    Posted base lines AND tax lines count as usage. Per-tax savepoints leave
    accounting untouched on failure; missing charts/taxes are harmless.
    """
    try:
        with env.cr.savepoint():
            companies = env['res.company'].sudo().search([])
            for company in companies:
                try:
                    with env.cr.savepoint():
                        _exclude_company_sales_taxes(env, company)
                except Exception:
                    _logger.warning(
                        'FitZone: could not configure sales taxes for company %s; skipped.',
                        company.id, exc_info=True)
    except Exception:
        _logger.warning('FitZone: sales tax installation setup skipped.', exc_info=True)


def _exclude_company_sales_taxes(env, company):
    if not company.chart_template:
        _logger.info('FitZone: company %s has no chart; sales taxes unchanged.', company.name)
        return
    taxes = env['account.tax'].sudo().with_company(company).search([
        ('company_id', '=', company.id), ('active', '=', True),
        ('type_tax_use', '=', 'sale'), ('amount_type', '=', 'percent'),
    ])
    if not taxes:
        _logger.info('FitZone: company %s has no eligible sales taxes.', company.name)
        return
    for tax in taxes:
        try:
            with env.cr.savepoint():
                xmlid = tax.get_external_id().get(tax.id) or '(no XML ID)'
                used = env['account.move.line'].sudo().search_count([
                    ('parent_state', '=', 'posted'),
                    '|', ('tax_ids', 'in', tax.ids), ('tax_line_id', '=', tax.id),
                ], limit=1)
                if used:
                    _logger.info('FitZone: used sales tax %s / %s [%s] skipped.',
                                 company.name, tax.name, xmlid)
                elif tax.price_include:
                    tax.write({'price_include_override': 'tax_excluded'})
                    _logger.info('FitZone: sales tax %s / %s [%s] now excludes tax from price.',
                                 company.name, tax.name, xmlid)
        except Exception:
            _logger.warning(
                'FitZone: sales tax %s in company %s skipped after a configuration error.',
                tax.id, company.id, exc_info=True)