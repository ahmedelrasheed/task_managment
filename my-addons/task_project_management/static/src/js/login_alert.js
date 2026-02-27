/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { Component, onMounted } from "@odoo/owl";

/**
 * Login Alert Service - checks for unseen task alerts on page load
 * and shows Odoo notification banners.
 */
class LoginAlertService extends Component {
    static template = "task_project_management.LoginAlertService";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");
        this._checked = false;

        onMounted(async () => {
            if (!this._checked) {
                this._checked = true;
                await this.checkAlerts();
            }
        });
    }

    async checkAlerts() {
        try {
            const result = await this.orm.call(
                "task.management.task", "get_login_alerts", []
            );

            // Member alerts: new task assignments
            if (result.member_alerts && result.member_alerts.length) {
                const count = result.member_alerts.length;
                const names = result.member_alerts
                    .map(a => a.assignment_name || a.project_name)
                    .slice(0, 3)
                    .join(", ");
                const suffix = count > 3 ? _t(" (+%s more)", count - 3) : "";

                const memberClose = this.notification.add(
                    _t("You have %s new task assignment(s): %s%s", count, names, suffix),
                    {
                        type: "info",
                        title: _t("New Assignments"),
                        sticky: false,
                        buttons: [
                            {
                                name: _t("View Assignments"),
                                onClick: async () => {
                                    memberClose();
                                    await this.orm.call(
                                        "task.management.task",
                                        "acknowledge_member_alerts",
                                        []
                                    );
                                    this.action.doAction("task_project_management.action_my_assignments");
                                },
                                primary: true,
                            },
                            {
                                name: _t("Dismiss"),
                                onClick: async () => {
                                    memberClose();
                                    await this.orm.call(
                                        "task.management.task",
                                        "acknowledge_member_alerts",
                                        []
                                    );
                                },
                            },
                        ],
                        onClose: async () => {
                            await this.orm.call(
                                "task.management.task",
                                "acknowledge_member_alerts",
                                []
                            );
                        },
                    }
                );
                // Auto-dismiss after 5 seconds
                setTimeout(() => memberClose(), 5000);
            }

            // PM alerts: new task submissions to review
            if (result.pm_alerts && result.pm_alerts.length) {
                const count = result.pm_alerts.length;
                const names = result.pm_alerts
                    .map(a => `${a.member_name} (${a.project_name})`)
                    .slice(0, 3)
                    .join(", ");
                const suffix = count > 3 ? _t(" (+%s more)", count - 3) : "";

                const pmClose = this.notification.add(
                    _t("%s new task submission(s) to review: %s%s", count, names, suffix),
                    {
                        type: "warning",
                        title: _t("Tasks Pending Review"),
                        sticky: false,
                        buttons: [
                            {
                                name: _t("Review Tasks"),
                                onClick: async () => {
                                    pmClose();
                                    await this.orm.call(
                                        "task.management.task",
                                        "acknowledge_pm_alerts",
                                        []
                                    );
                                    this.action.doAction("task_project_management.action_tasks_to_review");
                                },
                                primary: true,
                            },
                            {
                                name: _t("Dismiss"),
                                onClick: async () => {
                                    pmClose();
                                    await this.orm.call(
                                        "task.management.task",
                                        "acknowledge_pm_alerts",
                                        []
                                    );
                                },
                            },
                        ],
                        onClose: async () => {
                            await this.orm.call(
                                "task.management.task",
                                "acknowledge_pm_alerts",
                                []
                            );
                        },
                    }
                );
                // Auto-dismiss after 5 seconds
                setTimeout(() => pmClose(), 5000);
            }
        } catch (e) {
            // Silently fail - don't block user with alert errors
            console.warn("Login alert check failed:", e);
        }
    }
}

// Register as a systray component that runs on load
registry.category("systray").add(
    "task_project_management.LoginAlertService",
    { Component: LoginAlertService, props: {} },
    { sequence: 1000 }
);
