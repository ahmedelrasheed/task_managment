/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { Layout } from "@web/search/layout";
import { _t } from "@web/core/l10n/translation";
import { loadBundle } from "@web/core/assets";

// ============================================================
// Member Dashboard
// ============================================================
export class MemberDashboard extends Component {
    static template = "task_project_management.MemberDashboard";
    static components = { Layout };

    setup() {
        this._t = _t;
        this.orm = useService("orm");
        this.action = useService("action");
        this.display = { controlPanel: {} };
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
            upcomingMeetings: [],
            meetingsToday: 0,
            meetingsThisWeek: 0,
        });
        onWillStart(async () => {
            await this.loadData();
        });
    }

    async loadData() {
        try {
            const [result, companies, meetingData] = await Promise.all([
                this.orm.call("task.management.task", "get_member_dashboard_data", []),
                this.orm.call("res.company", "search_read", [[["id", "=", 1]], ["name"]], { limit: 1 }),
                this.orm.call("task.management.meeting", "get_member_meeting_data", []),
            ]);
            Object.assign(this.state, result);
            if (companies && companies.length) {
                this.state.companyName = companies[0].name;
            }
            if (meetingData) {
                Object.assign(this.state, meetingData);
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
    static components = { Layout };

    setup() {
        this._t = _t;
        this.orm = useService("orm");
        this.action = useService("action");
        this.display = { controlPanel: {} };
        this.state = useState({
            companyName: "",
            projects: [],
            meetingsByProject: [],
        });
        onWillStart(async () => {
            await this.loadData();
        });
    }

    async loadData() {
        try {
            const [result, companies, meetingData] = await Promise.all([
                this.orm.call("task.management.task", "get_pm_dashboard_data", []),
                this.orm.call("res.company", "search_read", [[["id", "=", 1]], ["name"]], { limit: 1 }),
                this.orm.call("task.management.meeting", "get_pm_meeting_data", []),
            ]);
            Object.assign(this.state, result);
            if (companies && companies.length) {
                this.state.companyName = companies[0].name;
            }
            if (meetingData) {
                Object.assign(this.state, meetingData);
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

    async onExportPDF() {
        const result = await this.orm.call("task.management.task", "export_pm_dashboard_pdf", []);
        const link = document.createElement("a");
        link.href = "data:application/pdf;base64," + result.file_content;
        link.download = result.filename;
        link.click();
    }
}

// ============================================================
// Admin Dashboard
// ============================================================
export class AdminDashboard extends Component {
    static template = "task_project_management.AdminDashboard";
    static components = { Layout };

    setup() {
        this._t = _t;
        this.orm = useService("orm");
        this.action = useService("action");
        this.display = { controlPanel: {} };
        this.chartRef = useRef("adminChart");
        this.chart = null;
        this.state = useState({
            companyName: "",
            totalProjects: 0,
            totalMembers: 0,
            totalHours: "0.00",
            projects: [],
            period: "month",
            dateFrom: "",
            dateTo: "",
            loading: false,
        });
        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            await this.loadData();
        });
        onMounted(() => {
            this.renderChart();
        });
        onWillUnmount(() => {
            if (this.chart) {
                this.chart.destroy();
                this.chart = null;
            }
        });
    }

    async loadData() {
        this.state.loading = true;
        try {
            const [result, companies] = await Promise.all([
                this.orm.call("task.management.task", "get_admin_dashboard_data", [
                    this.state.period, this.state.dateFrom || false, this.state.dateTo || false,
                ]),
                this.orm.call("res.company", "search_read", [[["id", "=", 1]], ["name"]], { limit: 1 }),
            ]);
            Object.assign(this.state, result);
            this.state.dateFrom = result.date_from || "";
            this.state.dateTo = result.date_to || "";
            if (companies && companies.length) {
                this.state.companyName = companies[0].name;
            }
        } catch (e) {
            console.error("Failed to load admin dashboard data:", e);
        }
        this.state.loading = false;
        setTimeout(() => this.renderChart(), 0);
    }

    renderChart() {
        if (!this.chartRef.el) return;
        if (this.chart) {
            this.chart.destroy();
            this.chart = null;
        }
        const projects = this.state.projects || [];
        if (!projects.length) return;

        const labels = projects.map(p => p.name);
        const expected = projects.map(p => parseFloat(p.expected_hours) || 0);
        const actual = projects.map(p => parseFloat(p.project_hours) || 0);

        this.chart = new Chart(this.chartRef.el, {
            type: "bar",
            data: {
                labels,
                datasets: [
                    {
                        label: _t("Expected Hours"),
                        data: expected,
                        backgroundColor: "#0B3D91",
                        borderRadius: 4,
                        barPercentage: 0.7,
                        categoryPercentage: 0.6,
                    },
                    {
                        label: _t("Project Hours"),
                        data: actual,
                        backgroundColor: "#1E5BBF",
                        borderRadius: 4,
                        barPercentage: 0.7,
                        categoryPercentage: 0.6,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: "top" },
                    title: {
                        display: true,
                        text: _t("Project Hours Comparison"),
                        font: { size: 16, weight: "bold" },
                        color: "#0B3D91",
                    },
                },
                layout: {
                    padding: { bottom: 20 },
                },
                scales: {
                    x: {
                        ticks: {
                            maxRotation: 45,
                            minRotation: 0,
                            autoSkip: false,
                        },
                    },
                    y: {
                        beginAtZero: true,
                        title: { display: true, text: _t("Hours") },
                    },
                },
            },
        });
    }

    async onPeriodChange(period) {
        this.state.period = period;
        if (period !== "custom") {
            this.state.dateFrom = "";
            this.state.dateTo = "";
            await this.loadData();
        }
    }

    onDateFromChange(ev) {
        this.state.dateFrom = ev.target.value;
    }

    onDateToChange(ev) {
        this.state.dateTo = ev.target.value;
    }

    async onApplyCustom() {
        if (this.state.dateFrom && this.state.dateTo) {
            this.state.period = "custom";
            await this.loadData();
        }
    }

    _periodArgs() {
        return [
            this.state.period, this.state.dateFrom || false, this.state.dateTo || false,
        ];
    }

    async onExportCSV() {
        const result = await this.orm.call("task.management.task", "export_admin_dashboard_csv", this._periodArgs());
        const link = document.createElement("a");
        link.href = "data:text/csv;base64," + result.file_content;
        link.download = result.filename;
        link.click();
    }

    async onExportImage() {
        const result = await this.orm.call("task.management.task", "export_admin_dashboard_png", this._periodArgs());
        const link = document.createElement("a");
        link.href = "data:image/png;base64," + result.file_content;
        link.download = result.filename;
        link.click();
    }

    async onExportPDF() {
        const result = await this.orm.call("task.management.task", "export_admin_dashboard_pdf", this._periodArgs());
        const link = document.createElement("a");
        link.href = "data:application/pdf;base64," + result.file_content;
        link.download = result.filename;
        link.click();
    }
}

// ============================================================
// Overall Performance Dashboard
// ============================================================
export class OverallPerformanceDashboard extends Component {
    static template = "task_project_management.OverallPerformanceDashboard";
    static components = { Layout };

    setup() {
        this._t = _t;
        this.orm = useService("orm");
        this.action = useService("action");
        this.display = { controlPanel: {} };
        this.state = useState({
            companyName: "",
            members: [],
            period: "month",
            dateFrom: "",
            dateTo: "",
            loading: false,
        });
        onWillStart(async () => {
            await this.loadData();
        });
    }

    async loadData() {
        this.state.loading = true;
        try {
            const [result, companies] = await Promise.all([
                this.orm.call("task.management.task", "get_overall_performance_data", [
                    this.state.period, this.state.dateFrom || false, this.state.dateTo || false,
                ]),
                this.orm.call("res.company", "search_read", [[["id", "=", 1]], ["name"]], { limit: 1 }),
            ]);
            this.state.members = result.members || [];
            this.state.dateFrom = result.date_from || "";
            this.state.dateTo = result.date_to || "";
            if (companies && companies.length) {
                this.state.companyName = companies[0].name;
            }
        } catch (e) {
            console.error("Failed to load overall performance data:", e);
        }
        this.state.loading = false;
    }

    async onPeriodChange(period) {
        this.state.period = period;
        if (period !== "custom") {
            this.state.dateFrom = "";
            this.state.dateTo = "";
            await this.loadData();
        }
    }

    onDateFromChange(ev) {
        this.state.dateFrom = ev.target.value;
    }

    onDateToChange(ev) {
        this.state.dateTo = ev.target.value;
    }

    async onApplyCustom() {
        if (this.state.dateFrom && this.state.dateTo) {
            this.state.period = "custom";
            await this.loadData();
        }
    }

    async onExportCSV() {
        const result = await this.orm.call("task.management.task", "export_overall_performance_csv", [
            this.state.period, this.state.dateFrom || false, this.state.dateTo || false,
        ]);
        const link = document.createElement("a");
        link.href = "data:text/csv;base64," + result.file_content;
        link.download = result.filename;
        link.click();
    }

    async onExportImage() {
        const result = await this.orm.call("task.management.task", "export_overall_performance_png", [
            this.state.period, this.state.dateFrom || false, this.state.dateTo || false,
        ]);
        const link = document.createElement("a");
        link.href = "data:image/png;base64," + result.file_content;
        link.download = result.filename;
        link.click();
    }

    async onExportPDF() {
        const result = await this.orm.call("task.management.task", "export_overall_performance_pdf", [
            this.state.period, this.state.dateFrom || false, this.state.dateTo || false,
        ]);
        const link = document.createElement("a");
        link.href = "data:application/pdf;base64," + result.file_content;
        link.download = result.filename;
        link.click();
    }

    onMemberClick(memberId) {
        const ctx = {
            default_member_id: memberId,
        };
        if (this.state.period === "custom" && this.state.dateFrom && this.state.dateTo) {
            ctx.default_period = "custom";
            ctx.default_date_from = this.state.dateFrom;
            ctx.default_date_to = this.state.dateTo;
        } else if (this.state.period === "today") {
            ctx.default_period = "today";
        } else if (this.state.period === "week") {
            ctx.default_period = "week";
        } else {
            ctx.default_period = "month";
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "task.management.member.performance.report",
            views: [[false, "form"]],
            target: "current",
            context: ctx,
        });
    }
}

// Register client actions
registry.category("actions").add("task_project_management.member_dashboard", MemberDashboard);
registry.category("actions").add("task_project_management.pm_dashboard", PMDashboard);
registry.category("actions").add("task_project_management.admin_dashboard", AdminDashboard);
registry.category("actions").add("task_project_management.overall_performance_dashboard", OverallPerformanceDashboard);
