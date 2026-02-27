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

// Hide apps grid icon for non-admin users (only admins need to switch apps)
registry.category("services").add("apps_menu_visibility", {
    dependencies: ["user"],
    start(env, { user }) {
        user.hasGroup("task_project_management.group_admin_manager").then(isAdmin => {
            if (!isAdmin) {
                document.body.classList.add("o_hide_apps_menu");
            }
        });
    },
});
