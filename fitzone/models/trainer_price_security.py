from odoo import api, models


class TrainerProductPriceSecurity(models.Model):
    _inherit = 'product.template'

    @api.model
    def _has_field_access(self, field, operation):
        # Odoo 19's field-access hook preserves all existing non-Trainer price readers.
        if (field.name in {'list_price', 'standard_price', 'price', 'pricelist_item_ids'}
                and not self.env.su and self.env.user.has_group('fitzone.group_fitzone_trainer')
                and not any(self.env.user.has_group('fitzone.group_fitzone_' + role)
                            for role in ('manager', 'reception', 'sales', 'physiotherapist', 'nutritionist'))):
            return False
        return super()._has_field_access(field, operation)


class TrainerVariantPriceSecurity(models.Model):
    _inherit = 'product.product'

    @api.model
    def _has_field_access(self, field, operation):
        if (field.name in {'lst_price', 'list_price', 'standard_price', 'price', 'price_extra', 'pricelist_item_ids'}
                and not self.env.su and self.env.user.has_group('fitzone.group_fitzone_trainer')
                and not any(self.env.user.has_group('fitzone.group_fitzone_' + role)
                            for role in ('manager', 'reception', 'sales', 'physiotherapist', 'nutritionist'))):
            return False
        return super()._has_field_access(field, operation)


class TrainerTemplateAttributePriceSecurity(models.Model):
    _inherit = 'product.template.attribute.value'

    @api.model
    def _has_field_access(self, field, operation):
        if (field.name == 'price_extra' and not self.env.su
                and self.env.user.has_group('fitzone.group_fitzone_trainer')
                and not any(self.env.user.has_group('fitzone.group_fitzone_' + role)
                            for role in ('manager', 'reception', 'sales', 'physiotherapist', 'nutritionist'))):
            return False
        return super()._has_field_access(field, operation)


class TrainerAttributePriceSecurity(models.Model):
    _inherit = 'product.attribute.value'

    @api.model
    def _has_field_access(self, field, operation):
        if (field.name == 'default_extra_price' and not self.env.su
                and self.env.user.has_group('fitzone.group_fitzone_trainer')
                and not any(self.env.user.has_group('fitzone.group_fitzone_' + role)
                            for role in ('manager', 'reception', 'sales', 'physiotherapist', 'nutritionist'))):
            return False
        return super()._has_field_access(field, operation)
