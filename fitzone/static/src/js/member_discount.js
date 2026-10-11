/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { useService } from "@web/core/utils/hooks";
import { useEffect } from "@odoo/owl";

patch(PosOrder.prototype, {
    serializeForORM() {
        const data = super.serializeForORM(...arguments);
        data.fitzone_membership_number = this.uiState.fitzoneNumber || false;
        return data;
    },
});

patch(ProductScreen.prototype, {
    setup() {
        super.setup(...arguments);
        this.memberOrm = useService("orm");
        useEffect(() => { this.refreshMemberDiscount(); }, () => [
            this.currentOrder?.uuid,
            this.currentOrder?.uiState.fitzoneNumber,
            JSON.stringify(this.currentOrder?.getOrderlines().map(l =>
                [l.uuid, l.product_id.id, l.qty, l.price_unit, l.discount])),
        ]);
    },
    async checkMembership(event) {
        this.currentOrder.uiState.fitzoneNumber = event.target.value.trim();
        await this.refreshMemberDiscount();
    },
    async refreshMemberDiscount() {
        const order = this.currentOrder;
        if (!order) return;
        const number = order.uiState.fitzoneNumber;
        const revision = (order.uiState.fitzoneRevision || 0) + 1;
        order.uiState.fitzoneRevision = revision;
        const result = number ? await this.memberOrm.call("pos.order",
            "check_member_discount_eligibility",
            [number, order.getOrderlines().map(l => l.product_id.id)]) :
            { status: "inactive", eligible_product_ids: [] };
        if (order.uiState.fitzoneRevision !== revision) return;
        order.uiState.fitzoneStatus = result.status;
        for (const line of order.getOrderlines()) {
            const eligible = result.eligible_product_ids.includes(line.product_id.id);
            if (eligible) line.setDiscount(50);
            else if (line.discount === 50) line.setDiscount(0);
        }
    },
});
