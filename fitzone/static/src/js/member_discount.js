/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { useService } from "@web/core/utils/hooks";

patch(ProductScreen.prototype, {
    setup() {
        super.setup(...arguments);
        this.orm = useService("orm");
    },

    async _applyMemberDiscount() {
        const order = this.currentOrder;
        const lines = order?.getOrderlines() || [];

        // No member selected: clear any existing discount.
        const partner = order?.getPartner();

        if (!partner || !partner.membership_no) {
            for (const line of lines) {
                line.setDiscount(0);
            }
            return;
        }

        const productIds = lines.map((line) => line.product_id.id);

        const result = await this.orm.call(
            "pos.order",
            "check_member_discount_eligibility",
            [partner.membership_no, productIds]
        );

        for (const line of lines) {
            if (
                result.eligible &&
                result.eligible_product_ids.includes(line.product_id.id)
            ) {
                line.setDiscount(50);
            } else {
                line.setDiscount(0);
            }
        }
    },

    async _barcodePartnerAction(code) {
        const result = await super._barcodePartnerAction(...arguments);
        await this._applyMemberDiscount();
        return result;
    },

    async addProductToOrder(product) {
        const result = await super.addProductToOrder(product);
        await this._applyMemberDiscount();
        return result;
    },
});