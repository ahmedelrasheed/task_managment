/** @odoo-module **/
import { registry } from "@web/core/registry";

const userMenuRegistry = registry.category("user_menuitems");

// Remove unwanted items, keep only "My Account" (profile) and "Log out"
const itemsToRemove = [
    "documentation",
    "support",
    "shortcuts",
    "separator",
    "odoo_account",
];

for (const item of itemsToRemove) {
    if (userMenuRegistry.contains(item)) {
        userMenuRegistry.remove(item);
    }
}
