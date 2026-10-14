/** @odoo-module **/
import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListArchParser } from "@web/views/list/list_arch_parser";

class ReadonlyDetailArchParser extends ListArchParser {
    parse(...args) {
        return { ...super.parse(...args), noOpen: true };
    }
}

registry.category("views").add("fitzone_readonly_detail_list", {
    ...listView,
    ArchParser: ReadonlyDetailArchParser,
});
