from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.fields import Domain


class MedicalAuditLog(models.Model):
    _name = 'fitzone.medical.audit.log'
    _description = 'Medical Mutation Audit (field names only)'
    _order = 'id desc'

    user_id = fields.Many2one('res.users', required=True, readonly=True)
    event_time = fields.Datetime(required=True, readonly=True)
    model_name = fields.Char(required=True, readonly=True)
    record_id = fields.Integer(required=True, readonly=True)
    operation = fields.Selection([(op, op) for op in ('create', 'write', 'unlink')], required=True, readonly=True)
    field_names = fields.Char(readonly=True)


class MedicalAuditMixin(models.AbstractModel):
    _name = 'fitzone.medical.audit.mixin'
    _description = 'Medical Mutation Audit'

    def _audit_medical_mutation(self, operation, names):
        # Elevate only append-only audit metadata; never pass medical values.
        self.env['fitzone.medical.audit.log'].sudo().create([{
            'user_id': self.env.uid, 'event_time': fields.Datetime.now(),
            'model_name': self._name, 'record_id': rec.id,
            'operation': operation, 'field_names': ','.join(sorted(names)),
        } for rec in self])

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record, vals in zip(records, vals_list):
            record._audit_medical_mutation('create', vals.keys())
        return records

    def write(self, vals):
        result = super().write(vals)
        self._audit_medical_mutation('write', vals.keys())
        return result

    def unlink(self):
        self.check_access('unlink')
        self._audit_medical_mutation('unlink', [])
        return super().unlink()


class NutritionConsultation(models.Model):
    _name = 'fitzone.nutrition.consultation'
    _inherit = 'fitzone.medical.audit.mixin'
    _description = 'Nutrition Consultation'
    _rec_name = 'id'

    member_id = fields.Many2one('res.partner', required=True)
    consult_date = fields.Date(default=fields.Date.context_today, required=True)
    goal = fields.Char()
    notes = fields.Text()
    nutritionist_id = fields.Many2one('res.users', default=lambda self: self.env.user, required=True)


MEDICAL_MODELS = frozenset({
    'fitzone.health.profile', 'fitzone.nutrition.consultation',
    'fitzone.rehabilitation', 'fitzone.injury', 'fitzone.injury.type',
    'fitzone.injury.cause',
})


class MedicalAttachment(models.Model):
    _inherit = 'ir.attachment'

    @api.constrains('res_model', 'public', 'access_token')
    def _check_medical_sharing(self):
        for attachment in self:
            if attachment.res_model in MEDICAL_MODELS and (attachment.public or attachment.access_token):
                raise ValidationError('Medical attachments cannot be public or shared by access token.')

    def _has_medical_parent_access(self, operation):
        self.ensure_one()
        # Elevate attachment routing metadata only; return a boolean, never file contents.
        routing = self.sudo().read(['res_model', 'res_id'])[0]
        if not self.env.su and routing['res_model'] == 'fitzone.injury.type' and not any(self.env.user.has_group('fitzone.group_fitzone_' + role) for role in ('physiotherapist', 'manager')):
            return False
        if routing['res_model'] not in MEDICAL_MODELS:
            return True
        if not routing['res_id']:
            return False
        mode = 'write' if operation in ('create', 'unlink') else operation
        return self.env[routing['res_model']].browse(routing['res_id']).has_access(mode)

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None, *, active_test=True, bypass_access=False):
        if not self.env.su and not bypass_access:
            # Legacy public/orphan medical attachments must not leak search metadata.
            domain = Domain(domain) & (
                Domain('res_model', 'not in', tuple(MEDICAL_MODELS))
                | (Domain('public', '=', False) & Domain('res_id', '!=', False))
            )
        return super()._search(domain, offset, limit, order,
                               active_test=active_test, bypass_access=bypass_access)

    def _check_access(self, operation):
        result = super()._check_access(operation)
        if self.env.su:
            return result
        forbidden = self.filtered(lambda attachment: not attachment._has_medical_parent_access(operation))
        if forbidden:
            if result:
                forbidden |= result[0]
            return forbidden, lambda: AccessError('Medical attachments require access to their parent record.')
        return result


class MedicalBinary(models.AbstractModel):
    _inherit = 'ir.binary'

    def _find_record(self, xmlid=None, res_model='ir.attachment', res_id=None,
                     access_token=None, field=None):
        record = self.env.ref(xmlid, False) if xmlid else (
            self.env[res_model].browse(res_id).exists()
            if res_id is not None and res_model in self.env else False
        )
        # Check before core's public/token elevation, including historical attachments.
        if record and record._name == 'ir.attachment' and not record._has_medical_parent_access('read'):
            raise AccessError('Medical attachments require access to their parent record.')
        return super()._find_record(xmlid, res_model, res_id, access_token, field)
