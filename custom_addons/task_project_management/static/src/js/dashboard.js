/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart } from "@odoo/owl";

// ============================================================
// Member Dashboard
// ============================================================
export class MemberDashboard extends Component {
    static template = "task_project_management.MemberDashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            companyName: "",
            totalTasks: 0,
            assignedTasks: 0,
            pendingTasks: 0,
            approvedTasks: 0,
            rejectedTasks: 0,
            hoursToday: "0.00",
            hoursWeek: "0.00",
            hoursMonth: "0.00",
            dailyTarget: "8.00",
            weeklyTarget: "40.00",
            monthlyTarget: "0.00",
            dailyPerformance: 0,
            weeklyPerformance: 0,
            monthlyPerformance: 0,
            recentTasks: [],
        });
        onWillStart(async () => {
            await this.loadData();
        });
    }

    async loadData() {
        try {
            const [result, companies] = await Promise.all([
                this.orm.call("task.management.task", "get_member_dashboard_data", []),
                this.orm.call("res.company", "search_read", [[["id", "=", 1]], ["name"]], { limit: 1 }),
            ]);
            Object.assign(this.state, result);
            if (companies && companies.length) {
                this.state.companyName = companies[0].name;
            }
        } catch (e) {
            console.error("Failed to load member dashboard data:", e);
        }
    }
}

// ============================================================
// PM Dashboard
// ============================================================
export class PMDashboard extends Component {
    static template = "task_project_management.PMDashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            companyName: "",
            projects: [],
        });
        onWillStart(async () => {
            await this.loadData();
        });
    }

    async loadData() {
        try {
            const [result, companies] = await Promise.all([
                this.orm.call("task.management.task", "get_pm_dashboard_data", []),
                this.orm.call("res.company", "search_read", [[["id", "=", 1]], ["name"]], { limit: 1 }),
            ]);
            Object.assign(this.state, result);
            if (companies && companies.length) {
                this.state.companyName = companies[0].name;
            }
        } catch (e) {
            console.error("Failed to load PM dashboard data:", e);
        }
    }

    async onExportCSV() {
        const result = await this.orm.call("task.management.task", "export_pm_dashboard_csv", []);
        const link = document.createElement("a");
        link.href = "data:text/csv;base64," + result.file_content;
        link.download = result.filename;
        link.click();
    }

    async onExportImage() {
        const result = await this.orm.call("task.management.task", "export_pm_dashboard_png", []);
        const link = document.createElement("a");
        link.href = "data:image/png;base64," + result.file_content;
        link.download = result.filename;
        link.click();
    }
}

// ============================================================
// Admin Dashboard
// ============================================================
export class AdminDashboard extends Component {
    static template = "task_project_management.AdminDashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            companyName: "",
            totalProjects: 0,
            totalMembers: 0,
            totalHours: "0.00",
            totalLateEntries: 0,
            projects: [],
        });
        onWillStart(async () => {
            await this.loadData();
        });
    }

    async loadData() {
        try {
            const [result, companies] = await Promise.all([
                this.orm.call("task.management.task", "get_admin_dashboard_data", []),
                this.orm.call("res.company", "search_read", [[["id", "=", 1]], ["name"]], { limit: 1 }),
            ]);
            Object.assign(this.state, result);
            if (companies && companies.length) {
                this.state.companyName = companies[0].name;
            }
        } catch (e) {
            console.error("Failed to load admin dashboard data:", e);
        }
    }

    async onExportCSV() {
        const result = await this.orm.call("task.management.task", "export_admin_dashboard_csv", []);
        const link = document.createElement("a");
        link.href = "data:text/csv;base64," + result.file_content;
        link.download = result.filename;
        link.click();
    }

    async onExportImage() {
        const result = await this.orm.call("task.management.task", "export_admin_dashboard_png", []);
        const link = document.createElement("a");
        link.href = "data:image/png;base64," + result.file_content;
        link.download = result.filename;
        link.click();
    }
}

// Register client actions
registry.category("actions").add("task_project_management.member_dashboard", MemberDashboard);
registry.category("actions").add("task_project_management.pm_dashboard", PMDashboard);
registry.category("actions").add("task_project_management.admin_dashboard", AdminDashboard);
