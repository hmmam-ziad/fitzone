/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { NavBar } from "@web/webclient/navbar/navbar";
import { useService } from "@web/core/utils/hooks";
import { onMounted, onWillUnmount, useState } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";

patch(NavBar.prototype, {
    setup() {
        super.setup(...arguments);
        const orm = useService("orm");
        const bus = useService("bus_service");
        this.fitzoneBadge = useState({ count: 0 });

        const refresh = async () => {
            try {
                this.fitzoneBadge.count = await orm.call(
                    "fitzone.injury", "get_pending_injury_count", []
                );
            } catch (e) {
                console.error("FitZone badge error:", e);
                this.fitzoneBadge.count = 0;
            }
        };

        // refresh after any RPC that touches fitzone.injury
        const rpcListener = (ev) => {
            const { data, settings } = ev.detail || {};
            if (data?.params?.model === "fitzone.injury" && settings !== undefined) {
                setTimeout(refresh, 300);
            }
        };

        let timer;
        onMounted(() => {
            refresh();
            timer = setInterval(refresh, 10000);
            this.env.bus.addEventListener("RPC:RESPONSE", rpcListener);
        });
        onWillUnmount(() => {
            clearInterval(timer);
            this.env.bus.removeEventListener("RPC:RESPONSE", rpcListener);
        });
    },
});