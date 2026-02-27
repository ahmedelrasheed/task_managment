/** @odoo-module **/
import { registry } from "@web/core/registry";

const systrayRegistry = registry.category("systray");

// Remove Activity Menu (clock icon) and Switch Company Menu (building icon)
// Keep burger_menu — needed on mobile for user profile + app navigation
const itemsToRemove = [
    "mail.activity_menu",
    "SwitchCompanyMenu",
];

for (const item of itemsToRemove) {
    if (systrayRegistry.contains(item)) {
        systrayRegistry.remove(item);
    }
}
