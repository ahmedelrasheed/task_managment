/** @odoo-module **/

import { ControlPanel } from "@web/search/control_panel/control_panel";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { onMounted, onPatched } from "@odoo/owl";

// Models whose form breadcrumb should show a fixed label instead of record name
const FORM_BREADCRUMB_LABELS = {
    'task.management.project': _t('Project Report'),
    'task.management.member.performance.report': _t('Member Performance Report'),
    'task.management.project.performance.report': _t('Project Performance Report'),
};

// Models where the "New" button should be hidden for non-admin users
const HIDE_CREATE_MODELS_NON_ADMIN = [
    'task.management.project',
];

// Models where the "Duplicate" action should be hidden
const HIDE_DUPLICATE_MODELS = [
    'task.management.archive',
    'task.management.task',
    'task.management.project',
    'task.management.member',
    'task.management.complaint',
];

patch(ControlPanel.prototype, {
    setup() {
        super.setup(...arguments);
        try {
            this.menuService = useService("menu");
        } catch (_e) {
            this.menuService = null;
        }
        try {
            this.userService = useService("user");
        } catch (_e) {
            this.userService = null;
        }
        onMounted(() => this._enhanceBreadcrumb());
        onPatched(() => this._enhanceBreadcrumb());
    },

    _enhanceBreadcrumb() {
        if (!this.menuService) return;

        requestAnimationFrame(() => {
            const cpEl = document.querySelector('.o_action_manager .o_control_panel');
            if (!cpEl) return;

            const breadcrumbOl = cpEl.querySelector('.breadcrumb');
            if (!breadcrumbOl) return;

            const resModel = this.env?.config?.resModel || '';

            // Hide "New" button for specific models (non-admin only)
            if (HIDE_CREATE_MODELS_NON_ADMIN.includes(resModel)) {
                const isAdmin = this.userService &&
                    this.userService.hasGroup('task_project_management.group_admin_manager');
                if (isAdmin && isAdmin.then) {
                    isAdmin.then(result => {
                        if (!result) {
                            const btns = cpEl.querySelectorAll(
                                '.o_form_button_create, .o_list_button_add'
                            );
                            btns.forEach(btn => btn.style.display = 'none');
                        }
                    });
                } else if (!isAdmin) {
                    const createButtons = cpEl.querySelectorAll(
                        '.o_form_button_create, .o_list_button_add'
                    );
                    createButtons.forEach(btn => btn.style.display = 'none');
                }
            }

            // Hide "Duplicate" action menu item for specific models
            if (HIDE_DUPLICATE_MODELS.includes(resModel)) {
                const actionMenus = cpEl.querySelectorAll(
                    '.o_cp_action_menus .dropdown-menu .dropdown-item, .o_cp_action_menus .o_menu_item'
                );
                actionMenus.forEach(item => {
                    const text = item.textContent.trim().toLowerCase();
                    if (text === 'duplicate' || text === 'نسخ') {
                        item.style.display = 'none';
                    }
                });
            }

            // Otherwise show breadcrumb and inject section name
            breadcrumbOl.style.display = '';

            // Replace the active breadcrumb item with a fixed label for specific models
            const viewType = this.env?.config?.viewType || '';
            const formLabel = FORM_BREADCRUMB_LABELS[resModel];
            if (formLabel && viewType === 'form') {
                const activeItem = breadcrumbOl.querySelector('.breadcrumb-item.active');
                if (activeItem && activeItem.textContent.trim() !== formLabel) {
                    activeItem.textContent = formLabel;
                }
            }

            // Remove previously injected section to avoid duplicates
            const existing = breadcrumbOl.querySelector('.o_breadcrumb_section');
            if (existing) existing.remove();

            const sectionName = this._getMenuSectionName();
            if (!sectionName) return;

            // Create non-clickable section breadcrumb item
            const li = document.createElement('li');
            li.className = 'breadcrumb-item o_breadcrumb_section';
            li.textContent = sectionName;
            breadcrumbOl.insertBefore(li, breadcrumbOl.firstChild);
        });
    },

    _getMenuSectionName() {
        if (!this.menuService) return null;

        const currentApp = this.menuService.getCurrentApp();
        if (!currentApp || !currentApp.childrenTree) return null;

        // Read menu_id from the URL hash
        const hash = window.location.hash;
        const match = hash.match(/menu_id=(\d+)/);
        if (!match) return null;
        const menuId = parseInt(match[1]);

        // Walk the menu tree: sections are direct children of the app
        for (const section of currentApp.childrenTree) {
            if (section.id === menuId) {
                return section.name;
            }
            if (section.childrenTree) {
                for (const child of section.childrenTree) {
                    if (child.id === menuId) {
                        return section.name;
                    }
                }
            }
        }
        return null;
    },
});
