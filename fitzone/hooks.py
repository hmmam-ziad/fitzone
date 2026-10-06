from odoo import SUPERUSER_ID


def post_init_hook(env):
    company = env['res.company'].browse(1).with_user(SUPERUSER_ID)

    env['account.chart.template'].try_loading(
        'jo_standard',
        company=company,
    )

    company.write({
        'name': 'FitZone',
        'country_id': env.ref('base.jo').id,
        'account_fiscal_country_id': env.ref('base.jo').id,
        'domestic_fiscal_position_id': env.ref(
            'account.1_account_fiscal_position_jordan'
        ).id,
    })