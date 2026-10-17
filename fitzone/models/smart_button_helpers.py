"""Navigation helpers only; no models, stored fields, or workflow mutations."""

from odoo.exceptions import AccessError
from odoo.tools.safe_eval import safe_eval


OPERATIONS = ('manager', 'reception', 'trainer')
MEMBERSHIP_READERS = OPERATIONS + ('physiotherapist', 'nutritionist')
FINANCE_READERS = ('manager', 'reception')
MEDICAL_READERS = ('manager', 'physiotherapist')


def has_roles(env, roles):
    return env.su or any(
        env.user.has_group('fitzone.group_fitzone_' + role) for role in roles
    )


def check_navigation(records, roles, destination):
    records.ensure_one()
    records.check_access('read')
    if not has_roles(records.env, roles):
        raise AccessError(records.env._('You are not allowed to use this FitZone navigation.'))
    records.env[destination].check_access('read')


def check_trainer_owner(record, trainer):
    if (not record.env.su
            and record.env.user.has_group('fitzone.group_fitzone_trainer')
            and not has_roles(record.env, FINANCE_READERS)
            and trainer.employee_id.user_id != record.env.user):
        raise AccessError(record.env._('This navigation is limited to your own trainer assignments.'))


def grouped_counts(records, destination, inverse, roles, domain=()):
    """Batch counts under the caller's ACLs and record rules, never sudo."""
    counts = {}
    if has_roles(records.env, roles):
        records.check_access('read')
        ids = [record.id for record in records if record.id and isinstance(record.id, int)]
        if ids:
            counts = {
                parent.id: count
                for parent, count in records.env[destination]._read_group(
                    [(inverse, 'in', ids)] + list(domain), [inverse], ['__count'],
                )
            }
    return counts


def related_action(record, xmlid, domain, defaults=None):
    """Copy an existing action without leaking source-form search/default context."""
    action = record.env['ir.actions.actions']._for_xml_id(xmlid)
    context = action.get('context') or {}
    if isinstance(context, str):
        context = safe_eval(context, {
            'uid': record.env.uid, 'active_id': record.id,
            'active_ids': record.ids, 'context': dict(record.env.context),
        })
    context = {**record.env.context, **context}
    context = {
        key: value for key, value in context.items()
        if not key.startswith(('default_', 'search_default_'))
        and key not in ('active_id', 'active_ids', 'active_model', 'group_by')
    }
    context.update(defaults or {})
    action.update(domain=domain, context=context, target='current')
    return action
