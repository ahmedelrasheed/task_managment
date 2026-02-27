/** @odoo-module **/
import { registry } from "@web/core/registry";

const systrayRegistry = registry.category("systray");

// Remove Activity Menu (clock icon), Switch Company Menu (building icon),
// and Burger Menu (toggle icon)
const itemsToRemove = [
    "mail.activity_menu",
    "SwitchCompanyMenu",
    "burger_menu",
];

for (const item of itemsToRemove) {
    if (systrayRegistry.contains(item)) {
        systrayRegistry.remove(item);
    }
}
