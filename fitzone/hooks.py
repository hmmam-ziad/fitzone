import logging

_logger = logging.getLogger(__name__)


def pre_init_hook(env):
    company = env.ref('base.main_company')
    jo = env.ref('base.jo')
    jod = env.ref('base.JOD')

    if company._existing_accounting():
        _logger.warning(
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