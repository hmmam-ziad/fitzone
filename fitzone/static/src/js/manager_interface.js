/** @odoo-module **/

import { session } from "@web/session";
import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";
import { ResConfigDevTool } from "@web/webclient/settings_form_view/widgets/res_config_dev_tool";
import "@web/core/debug/debug_providers";

patch(ResConfigDevTool.prototype, {
    get fitzoneHideAdminUI() {
        return Boolean(session.fitzone_hide_admin_ui);
    },
});

// Presentation only: URL debug activation and all backend privileges stay native.
if (session.fitzone_hide_admin_ui) {
    const providers = registry.category("command_provider");
    providers.add("debug", { provide: () => [] }, { force: true });
    const items = registry.category("user_menuitems");
    for (const key of ["debug", "debug_mode", "activate_debug", "developer_mode"]) {
        if (items.contains(key)) {
            items.remove(key);
        }
    }
}
