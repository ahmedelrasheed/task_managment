import base64
import csv
import io
import subprocess
import tempfile

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import timedelta


class MemberPerformanceReport(models.TransientModel):
    _name = 'task.management.member.performance.report'
    _description = 'Member Performance Report'

    member_id = fields.Many2one(
        'task.management.member', string='Member', required=True,
        domain=[('role', '!=', 'manager')],
    )
    period = fields.Selection([
        ('today', 'Today'),
        ('week', 'This Week'),
        ('month', 'This Month'),
        ('custom', 'Custom Range'),
    ], string='Period', default='month', required=True)
    date_from = fields.Date(string='Date From')
    date_to = fields.Date(string='Date To')

    # Computed stats
    total_tasks = fields.Integer(
        string='Total Tasks', compute='_compute_stats')
    approved_tasks = fields.Integer(
        string='Approved Tasks', compute='_compute_stats')
    assigned_approved_tasks = fields.Integer(
        string='Assigned Approved', compute='_compute_stats')
    rejected_tasks = fields.Integer(
        string='Rejected Tasks', compute='_compute_stats')
    assigned_rejected_tasks = fields.Integer(
        string='Assigned Rejected', compute='_compute_stats')
    pending_tasks = fields.Integer(
        string='Pending Tasks', compute='_compute_stats')
    assigned_pending_tasks = fields.Integer(
        string='Assigned Pending', compute='_compute_stats')
    total_hours = fields.Float(
        string='Total Hours', compute='_compute_stats')
    approved_hours = fields.Float(
        string='Approved Hours', compute='_compute_stats')
    approval_rate = fields.Float(
        string='Approval Rate (%)', compute='_compute_stats')
    late_entries = fields.Integer(
        string='Late Entries', compute='_compute_stats')
    avg_hours_per_day = fields.Float(
        string='Avg Hours/Day', compute='_compute_stats')
    daily_target = fields.Float(
        string='Daily Target', compute='_compute_stats')
    weekly_target = fields.Float(
        string='Weekly Target', compute='_compute_stats')
    daily_performance = fields.Float(
        string='Daily Performance (%)', compute='_compute_stats')
    weekly_performance = fields.Float(
        string='Weekly Performance (%)', compute='_compute_stats')
    monthly_target = fields.Float(
        string='Monthly Target', compute='_compute_stats')
    monthly_performance = fields.Float(
        string='Monthly Performance (%)', compute='_compute_stats')
    project_count = fields.Integer(
        string='Projects Worked On', compute='_compute_stats')

    # Task detail lines
    task_line_ids = fields.One2many(
        'task.management.member.performance.line', 'report_id',
        string='Task Details', compute='_compute_stats')

    # Project breakdown lines
    project_line_ids = fields.One2many(
        'task.management.member.performance.project', 'report_id',
        string='Project Breakdown', compute='_compute_stats')

    # Export fields
    report_file = fields.Binary(string='Report File', readonly=True)
    report_filename = fields.Char(string='Filename')

    def _get_date_range(self):
        """Return (date_from, date_to) based on selected period."""
        today = fields.Date.context_today(self)
        if self.period == 'today':
            return today, today
        elif self.period == 'week':
            week_start = today - timedelta(days=today.weekday())
            week_end = week_start + timedelta(days=6)
            return week_start, week_end
        elif self.period == 'month':
            month_start = today.replace(day=1)
            # Last day of month
            if today.month == 12:
                month_end = today.replace(day=31)
            else:
                month_end = today.replace(
                    month=today.month + 1, day=1) - timedelta(days=1)
            return month_start, month_end
        else:
            return self.date_from or today, self.date_to or today

    @api.depends('member_id', 'period', 'date_from', 'date_to')
    def _compute_stats(self):
        TaskLine = self.env['task.management.member.performance.line']
        ProjectLine = self.env['task.management.member.performance.project']
        for report in self:
            if not report.member_id:
                report.total_tasks = 0
                report.approved_tasks = 0
                report.assigned_approved_tasks = 0
                report.rejected_tasks = 0
                report.assigned_rejected_tasks = 0
                report.pending_tasks = 0
                report.assigned_pending_tasks = 0
                report.total_hours = 0.0
                report.approved_hours = 0.0
                report.approval_rate = 0.0
                report.late_entries = 0
                report.avg_hours_per_day = 0.0
                report.daily_target = 0.0
                report.weekly_target = 0.0
                report.daily_performance = 0.0
                report.weekly_performance = 0.0
                report.monthly_target = 0.0
                report.monthly_performance = 0.0
                report.project_count = 0
                report.task_line_ids = TaskLine
                report.project_line_ids = ProjectLine
                continue

            d_from, d_to = report._get_date_range()
            tasks = self.env['task.management.task'].search([
                ('member_id', '=', report.member_id.id),
                ('date', '>=', d_from),
                ('date', '<=', d_to),
            ], order='date desc, id desc')

            approved = tasks.filtered(
                lambda t: t.approval_status == 'approved')
            assigned_approved = tasks.filtered(
                lambda t: t.approval_status == 'assigned_approved')
            rejected = tasks.filtered(
                lambda t: t.approval_status == 'rejected')
            assigned_rejected = tasks.filtered(
                lambda t: t.approval_status == 'assigned_rejected')
            pending = tasks.filtered(
                lambda t: t.approval_status == 'pending')
            assigned_pending = tasks.filtered(
                lambda t: t.approval_status == 'assigned_pending')
            late = tasks.filtered(lambda t: t.is_late_entry)

            all_approved = approved | assigned_approved
            total = len(tasks)
            report.total_tasks = total
            report.approved_tasks = len(approved)
            report.assigned_approved_tasks = len(assigned_approved)
            report.rejected_tasks = len(rejected)
            report.assigned_rejected_tasks = len(assigned_rejected)
            report.pending_tasks = len(pending)
            report.assigned_pending_tasks = len(assigned_pending)
            report.total_hours = sum(tasks.mapped('duration_hours'))
            report.approved_hours = sum(all_approved.mapped('duration_hours'))
            report.approval_rate = round(
                (len(all_approved) / total * 100) if total else 0, 1)
            report.late_entries = len(late)

            # Avg hours per day (unique working days)
            unique_days = len(set(tasks.mapped('date')))
            report.avg_hours_per_day = round(
                report.total_hours / unique_days if unique_days else 0, 2)

            # Daily / Weekly targets and performance
            daily_tgt = float(self.env['ir.config_parameter'].sudo().get_param(
                'task_project_management.daily_hours_average', '8.0'))
            weekly_tgt = float(self.env['ir.config_parameter'].sudo().get_param(
                'task_project_management.weekly_hours_average', '40.0'))
            report.daily_target = daily_tgt
            report.weekly_target = weekly_tgt

            unique_weeks = max(1, unique_days / 5)
            actual_daily_avg = report.total_hours / unique_days if unique_days else 0
            actual_weekly_avg = report.total_hours / unique_weeks if unique_weeks else 0
            report.daily_performance = round(
                (actual_daily_avg / daily_tgt * 100) if daily_tgt else 0, 1)
            report.weekly_performance = round(
                (actual_weekly_avg / weekly_tgt * 100) if weekly_tgt else 0, 1)

            # Monthly target and performance
            import calendar
            today = fields.Date.context_today(self)
            cal = calendar.Calendar()
            working_days = sum(
                1 for d in cal.itermonthdays2(today.year, today.month)
                if d[0] != 0 and d[1] < 5
            )
            monthly_tgt = daily_tgt * working_days
            report.monthly_target = monthly_tgt
            # Monthly hours = hours in current month
            month_start = today.replace(day=1)
            month_tasks = self.env['task.management.task'].search([
                ('member_id', '=', report.member_id.id),
                ('date', '>=', month_start),
                ('date', '<=', today),
            ])
            hours_month = sum(month_tasks.mapped('duration_hours'))
            report.monthly_performance = round(
                (hours_month / monthly_tgt * 100) if monthly_tgt else 0, 1)

            # Projects worked on
            projects = tasks.mapped('project_id')
            report.project_count = len(projects)

            # Task detail lines (virtual records)
            task_lines = []
            for task in tasks:
                task_lines.append((0, 0, {
                    'date': task.date,
                    'project_name': task.project_id.name,
                    'description': (task.description or '')[:80],
                    'time_from': task.time_from,
                    'time_to': task.time_to,
                    'duration_hours': task.duration_hours,
                    'approval_status': task.approval_status,
                    'is_late_entry': task.is_late_entry,
                }))
            report.task_line_ids = task_lines or TaskLine

            # Project breakdown lines
            project_lines = []
            for proj in projects:
                p_tasks = tasks.filtered(
                    lambda t, p=proj: t.project_id == p)
                p_approved = p_tasks.filtered(
                    lambda t: t.approval_status in ('approved', 'assigned_approved'))
                p_total = len(p_tasks)
                project_lines.append((0, 0, {
                    'project_name': proj.name,
                    'task_count': p_total,
                    'total_hours': sum(
                        p_tasks.mapped('duration_hours')),
                    'approved_hours': sum(
                        p_approved.mapped('duration_hours')),
                    'approval_rate': round(
                        (len(p_approved) / p_total * 100)
                        if p_total else 0, 1),
                    'late_entries': len(
                        p_tasks.filtered(lambda t: t.is_late_entry)),
                }))
            report.project_line_ids = project_lines or ProjectLine


    def action_export_csv(self):
        """Export the performance report as CSV."""
        self.ensure_one()
        if not self.member_id:
            return
        d_from, d_to = self._get_date_range()
        tasks = self.env['task.management.task'].search([
            ('member_id', '=', self.member_id.id),
            ('date', '>=', d_from),
            ('date', '<=', d_to),
        ], order='date desc, id desc')

        output = io.StringIO()
        writer = csv.writer(output)
        company = self.env.company.name

        # ── Report Header ──
        writer.writerow(['MEMBER PERFORMANCE REPORT'])
        writer.writerow([])
        writer.writerow(['Company:', company])
        writer.writerow(['Member:', self.member_id.name])
        writer.writerow(['Period:', f'{d_from}  to  {d_to}'])
        writer.writerow([])

        # ── Performance Summary ──
        writer.writerow(['PERFORMANCE SUMMARY'])
        writer.writerow([])
        writer.writerow(['', 'Metric', 'Value'])
        writer.writerow(['', 'Total Tasks', self.total_tasks])
        writer.writerow(['', 'Approved', self.approved_tasks])
        writer.writerow(['', 'Assigned Approved', self.assigned_approved_tasks])
        writer.writerow(['', 'Rejected', self.rejected_tasks])
        writer.writerow(['', 'Assigned Rejected', self.assigned_rejected_tasks])
        writer.writerow(['', 'Pending', self.pending_tasks])
        writer.writerow(['', 'Assigned Pending', self.assigned_pending_tasks])
        writer.writerow(['', 'Total Hours', f'{self.total_hours:.2f}'])
        writer.writerow(['', 'Approved Hours', f'{self.approved_hours:.2f}'])
        writer.writerow(['', 'Approval Rate', f'{self.approval_rate:.1f}%'])
        writer.writerow(['', 'Late Entries', self.late_entries])
        writer.writerow(['', 'Avg Hours/Day', f'{self.avg_hours_per_day:.2f}'])
        writer.writerow(['', 'Projects Worked On', self.project_count])
        writer.writerow([])

        # ── Target vs Actual ──
        writer.writerow(['TARGET vs ACTUAL'])
        writer.writerow([])
        writer.writerow(['', 'Period', 'Target (hrs)', 'Actual (hrs)',
                          'Performance'])
        writer.writerow(['', 'Daily', f'{self.daily_target:.2f}',
                          '', f'{self.daily_performance:.1f}%'])
        writer.writerow(['', 'Weekly', f'{self.weekly_target:.2f}',
                          '', f'{self.weekly_performance:.1f}%'])
        writer.writerow(['', 'Monthly', f'{self.monthly_target:.2f}',
                          '', f'{self.monthly_performance:.1f}%'])
        writer.writerow([])

        # ── Project Breakdown ──
        writer.writerow(['PROJECT BREAKDOWN'])
        writer.writerow([])
        writer.writerow(['', 'No.', 'Project', 'Tasks', 'Total Hours',
                          'Approved Hours', 'Approval Rate', 'Late Entries'])
        projects = tasks.mapped('project_id')
        grand_tasks = 0
        grand_hours = 0.0
        grand_approved_hrs = 0.0
        grand_late = 0
        for pi, proj in enumerate(projects, 1):
            p_tasks = tasks.filtered(lambda t, p=proj: t.project_id == p)
            p_approved = p_tasks.filtered(
                lambda t: t.approval_status in ('approved', 'assigned_approved'))
            p_total = len(p_tasks)
            p_hrs = sum(p_tasks.mapped('duration_hours'))
            p_app_hrs = sum(p_approved.mapped('duration_hours'))
            p_late = len(p_tasks.filtered(lambda t: t.is_late_entry))
            writer.writerow([
                '', pi, proj.name, p_total,
                f'{p_hrs:.2f}', f'{p_app_hrs:.2f}',
                f'{round((len(p_approved) / p_total * 100) if p_total else 0, 1)}%',
                p_late,
            ])
            grand_tasks += p_total
            grand_hours += p_hrs
            grand_approved_hrs += p_app_hrs
            grand_late += p_late
        writer.writerow(['', '', 'TOTAL', grand_tasks,
                          f'{grand_hours:.2f}', f'{grand_approved_hrs:.2f}',
                          '', grand_late])
        writer.writerow([])

        # ── Task Details ──
        writer.writerow(['TASK DETAILS'])
        writer.writerow([])
        writer.writerow(['', 'No.', 'Date', 'Project', 'Description',
                          'From', 'To', 'Hours', 'Status', 'Late'])
        total_hrs = 0.0
        for i, task in enumerate(tasks, 1):
            writer.writerow([
                '', i, str(task.date), task.project_id.name,
                (task.description or '')[:80],
                self._float_to_time(task.time_from),
                self._float_to_time(task.time_to),
                f'{task.duration_hours:.2f}',
                task.approval_status.replace('_', ' ').title(),
                'Yes' if task.is_late_entry else '',
            ])
            total_hrs += task.duration_hours
        writer.writerow(['', '', '', '', 'TOTAL', '', '',
                          f'{total_hrs:.2f}', '', ''])
        writer.writerow([])
        writer.writerow(['END OF REPORT'])

        csv_data = output.getvalue().encode('utf-8-sig')
        self.report_file = base64.b64encode(csv_data)
        member_name = self.member_id.name.replace(' ', '_')
        self.report_filename = (
            f'performance_{member_name}_{d_from}_{d_to}.csv')
        return {
            'type': 'ir.actions.act_url',
            'url': (
                f'/web/content?model={self._name}'
                f'&id={self.id}'
                f'&field=report_file'
                f'&filename_field=report_filename'
                f'&download=true'
            ),
            'target': 'new',
        }

    def action_export_png(self):
        """Export the performance report as PNG image."""
        self.ensure_one()
        if not self.member_id:
            return

        d_from, d_to = self._get_date_range()
        tasks = self.env['task.management.task'].search([
            ('member_id', '=', self.member_id.id),
            ('date', '>=', d_from),
            ('date', '<=', d_to),
        ], order='date desc, id desc')

        projects = tasks.mapped('project_id')

        # Build project breakdown rows
        project_rows = ''
        for proj in projects:
            p_tasks = tasks.filtered(lambda t, p=proj: t.project_id == p)
            p_approved = p_tasks.filtered(
                lambda t: t.approval_status in ('approved', 'assigned_approved'))
            p_total = len(p_tasks)
            p_total_hrs = sum(p_tasks.mapped('duration_hours'))
            p_approved_hrs = sum(p_approved.mapped('duration_hours'))
            p_late = p_tasks.filtered(lambda t: t.is_late_entry)
            rate = round(
                (len(p_approved) / p_total * 100) if p_total else 0, 1)
            project_rows += f'''<tr>
                <td>{proj.name}</td>
                <td>{p_total}</td>
                <td>{p_total_hrs:.2f}</td>
                <td>{p_approved_hrs:.2f}</td>
                <td>{rate}%</td>
                <td>{len(p_late)}</td>
            </tr>'''

        # Build task detail rows
        task_rows = ''
        total_hours = 0
        for task in tasks:
            status_color = {
                'pending': '#f0ad4e',
                'approved': '#5cb85c',
                'rejected': '#d9534f',
                'assigned_pending': '#f0ad4e',
                'assigned_approved': '#5cb85c',
                'assigned_rejected': '#d9534f',
            }.get(task.approval_status, '#999')
            task_rows += f'''<tr>
                <td>{task.date}</td>
                <td>{task.project_id.name}</td>
                <td>{(task.description or "")[:60]}</td>
                <td>{self._float_to_time(task.time_from)}</td>
                <td>{self._float_to_time(task.time_to)}</td>
                <td>{task.duration_hours:.2f}</td>
                <td style="color:{status_color};font-weight:bold;">
                    {task.approval_status.replace('_', ' ').title()}</td>
                <td>{"Yes" if task.is_late_entry else ""}</td>
            </tr>'''
            total_hours += task.duration_hours

        # Get company logo
        company = self.env.company
        logo_html = ''
        if company.logo:
            logo_b64 = company.logo.decode() if isinstance(company.logo, bytes) else company.logo
            logo_html = f'<img src="data:image/png;base64,{logo_b64}" class="logo"/>'

        html = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"/>
<style>
    body {{ font-family: Arial, sans-serif; margin: 20px; background: #fff; }}
    .header {{ display: flex; align-items: center; gap: 15px;
               border-bottom: 3px solid #714B67; padding-bottom: 15px; margin-bottom: 20px; }}
    .logo {{ height: 60px; width: auto; }}
    .header-text h1 {{ color: #714B67; margin: 0; font-size: 24px; }}
    .header-text p {{ color: #666; margin: 3px 0 0 0; font-size: 13px; }}
    h2 {{ color: #714B67; margin-top: 20px; border-bottom: 2px solid #714B67;
          padding-bottom: 5px; font-size: 16px; }}
    .meta {{ color: #666; margin-bottom: 15px; font-size: 13px; }}
    .kpi-grid {{ display: flex; flex-wrap: wrap; gap: 10px; margin: 15px 0; }}
    .kpi {{ background: #f3edf2; border: 1px solid #ddd; border-radius: 8px;
            padding: 10px 15px; text-align: center; min-width: 110px; }}
    .kpi-value {{ font-size: 20px; font-weight: bold; color: #714B67; }}
    .kpi-label {{ font-size: 10px; color: #666; text-transform: uppercase; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
    th {{ background: #714B67; color: white; padding: 8px; text-align: left; font-size: 12px; }}
    td {{ padding: 6px 8px; border-bottom: 1px solid #ddd; font-size: 12px; }}
    tr:nth-child(even) {{ background: #f9f9f9; }}
    .total {{ font-weight: bold; margin-top: 10px; font-size: 14px; color: #714B67; }}
    .footer {{ margin-top: 20px; padding-top: 10px; border-top: 1px solid #ddd;
               color: #999; font-size: 10px; text-align: center; }}
</style></head><body>
    <div class="header">
        {logo_html}
        <div class="header-text">
            <h1>Member Performance Report</h1>
            <p>{company.name} | {self.member_id.name} | Period: {d_from} to {d_to}</p>
        </div>
    </div>

    <div class="kpi-grid">
        <div class="kpi"><div class="kpi-value">{self.total_tasks}</div>
            <div class="kpi-label">Total Tasks</div></div>
        <div class="kpi"><div class="kpi-value" style="color:#5cb85c">
            {self.approved_tasks}</div>
            <div class="kpi-label">Approved</div></div>
        <div class="kpi"><div class="kpi-value" style="color:#5cb85c">
            {self.assigned_approved_tasks}</div>
            <div class="kpi-label">Asgn Approved</div></div>
        <div class="kpi"><div class="kpi-value" style="color:#d9534f">
            {self.rejected_tasks}</div>
            <div class="kpi-label">Rejected</div></div>
        <div class="kpi"><div class="kpi-value" style="color:#d9534f">
            {self.assigned_rejected_tasks}</div>
            <div class="kpi-label">Asgn Rejected</div></div>
        <div class="kpi"><div class="kpi-value" style="color:#f0ad4e">
            {self.pending_tasks}</div>
            <div class="kpi-label">Pending</div></div>
        <div class="kpi"><div class="kpi-value" style="color:#f0ad4e">
            {self.assigned_pending_tasks}</div>
            <div class="kpi-label">Asgn Pending</div></div>
        <div class="kpi"><div class="kpi-value">{self.approval_rate:.1f}%</div>
            <div class="kpi-label">Approval Rate</div></div>
        <div class="kpi"><div class="kpi-value">{self.approved_hours:.1f}</div>
            <div class="kpi-label">Approved Hours</div></div>
        <div class="kpi"><div class="kpi-value" style="color:#d9534f">
            {self.late_entries}</div>
            <div class="kpi-label">Late Entries</div></div>
        <div class="kpi"><div class="kpi-value">{self.avg_hours_per_day:.2f}</div>
            <div class="kpi-label">Avg Hours/Day</div></div>
        <div class="kpi"><div class="kpi-value" style="color:{'#5cb85c' if self.daily_performance >= 100 else '#f0ad4e' if self.daily_performance >= 75 else '#d9534f'}">{self.daily_performance:.1f}%</div>
            <div class="kpi-label">Daily Performance</div></div>
        <div class="kpi"><div class="kpi-value" style="color:{'#5cb85c' if self.weekly_performance >= 100 else '#f0ad4e' if self.weekly_performance >= 75 else '#d9534f'}">{self.weekly_performance:.1f}%</div>
            <div class="kpi-label">Weekly Performance</div></div>
        <div class="kpi"><div class="kpi-value">{self.monthly_target:.0f}</div>
            <div class="kpi-label">Monthly Target (hrs)</div></div>
        <div class="kpi"><div class="kpi-value" style="color:{'#5cb85c' if self.monthly_performance >= 100 else '#f0ad4e' if self.monthly_performance >= 75 else '#d9534f'}">{self.monthly_performance:.1f}%</div>
            <div class="kpi-label">Monthly Performance</div></div>
    </div>

    <h2>Project Breakdown</h2>
    <table><thead><tr>
        <th>Project</th><th>Tasks</th><th>Total Hours</th>
        <th>Approved Hours</th><th>Approval Rate</th><th>Late</th>
    </tr></thead><tbody>{project_rows}</tbody></table>

    <h2>Task Details</h2>
    <table><thead><tr>
        <th>Date</th><th>Project</th><th>Description</th>
        <th>From</th><th>To</th><th>Hours</th><th>Status</th><th>Late</th>
    </tr></thead><tbody>{task_rows}</tbody></table>
    <div class="total">Total Hours: {total_hours:.2f}</div>
    <div class="footer">Generated by {company.name} - Task & Project Management System</div>
</body></html>'''

        try:
            with tempfile.NamedTemporaryFile(
                suffix='.html', mode='w', delete=False,
                encoding='utf-8',
            ) as html_file:
                html_file.write(html)
                html_path = html_file.name
            png_path = html_path.replace('.html', '.png')
            result = subprocess.run(
                ['wkhtmltoimage', '--width', '1200', html_path, png_path],
                capture_output=True, timeout=30,
            )
            if result.returncode != 0:
                raise UserError(
                    _('Failed to generate image: %s') %
                    result.stderr.decode())
            with open(png_path, 'rb') as f:
                self.report_file = base64.b64encode(f.read())
            member_name = self.member_id.name.replace(' ', '_')
            self.report_filename = (
                f'member_report_{member_name}_{d_from}_{d_to}.png')
        except FileNotFoundError:
            raise UserError(
                _('wkhtmltoimage is not installed. '
                  'Please install wkhtmltopdf package.'))
        except subprocess.TimeoutExpired:
            raise UserError(_('Image generation timed out.'))
        return {
            'type': 'ir.actions.act_url',
            'url': (
                f'/web/content?model={self._name}'
                f'&id={self.id}'
                f'&field=report_file'
                f'&filename_field=report_filename'
                f'&download=true'
            ),
            'target': 'new',
        }

    def action_export_pdf(self):
        """Export the performance report as PDF."""
        self.ensure_one()
        if not self.member_id:
            return

        d_from, d_to = self._get_date_range()
        tasks = self.env['task.management.task'].search([
            ('member_id', '=', self.member_id.id),
            ('date', '>=', d_from),
            ('date', '<=', d_to),
        ], order='date desc, id desc')

        projects = tasks.mapped('project_id')

        # Build project breakdown rows
        project_rows = ''
        for proj in projects:
            p_tasks = tasks.filtered(lambda t, p=proj: t.project_id == p)
            p_approved = p_tasks.filtered(
                lambda t: t.approval_status in ('approved', 'assigned_approved'))
            p_total = len(p_tasks)
            p_total_hrs = sum(p_tasks.mapped('duration_hours'))
            p_approved_hrs = sum(p_approved.mapped('duration_hours'))
            p_late = p_tasks.filtered(lambda t: t.is_late_entry)
            rate = round(
                (len(p_approved) / p_total * 100) if p_total else 0, 1)
            project_rows += f'''<tr>
                <td>{proj.name}</td>
                <td>{p_total}</td>
                <td>{p_total_hrs:.2f}</td>
                <td>{p_approved_hrs:.2f}</td>
                <td>{rate}%</td>
                <td>{len(p_late)}</td>
            </tr>'''

        # Build task detail rows
        task_rows = ''
        total_hours = 0
        for task in tasks:
            status_color = {
                'pending': '#f0ad4e',
                'approved': '#5cb85c',
                'rejected': '#d9534f',
                'assigned_pending': '#f0ad4e',
                'assigned_approved': '#5cb85c',
                'assigned_rejected': '#d9534f',
            }.get(task.approval_status, '#999')
            task_rows += f'''<tr>
                <td>{task.date}</td>
                <td>{task.project_id.name}</td>
                <td>{(task.description or "")[:60]}</td>
                <td>{self._float_to_time(task.time_from)}</td>
                <td>{self._float_to_time(task.time_to)}</td>
                <td>{task.duration_hours:.2f}</td>
                <td style="color:{status_color};font-weight:bold;">
                    {task.approval_status.replace('_', ' ').title()}</td>
                <td>{"Yes" if task.is_late_entry else ""}</td>
            </tr>'''
            total_hours += task.duration_hours

        # Get company logo
        company = self.env.company
        logo_html = ''
        if company.logo:
            logo_b64 = company.logo.decode() if isinstance(company.logo, bytes) else company.logo
            logo_html = f'<img src="data:image/png;base64,{logo_b64}" class="logo"/>'

        html = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"/>
<style>
    body {{ font-family: Arial, sans-serif; margin: 20px; background: #fff; }}
    .header {{ display: flex; align-items: center; gap: 15px;
               border-bottom: 3px solid #714B67; padding-bottom: 15px; margin-bottom: 20px; }}
    .logo {{ height: 60px; width: auto; }}
    .header-text h1 {{ color: #714B67; margin: 0; font-size: 24px; }}
    .header-text p {{ color: #666; margin: 3px 0 0 0; font-size: 13px; }}
    h2 {{ color: #714B67; margin-top: 20px; border-bottom: 2px solid #714B67;
          padding-bottom: 5px; font-size: 16px; }}
    .kpi-grid {{ display: flex; flex-wrap: wrap; gap: 10px; margin: 15px 0; }}
    .kpi {{ background: #f3edf2; border: 1px solid #ddd; border-radius: 8px;
            padding: 10px 15px; text-align: center; min-width: 110px; }}
    .kpi-value {{ font-size: 20px; font-weight: bold; color: #714B67; }}
    .kpi-label {{ font-size: 10px; color: #666; text-transform: uppercase; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
    th {{ background: #714B67; color: white; padding: 8px; text-align: left; font-size: 12px; }}
    td {{ padding: 6px 8px; border-bottom: 1px solid #ddd; font-size: 12px; }}
    tr:nth-child(even) {{ background: #f9f9f9; }}
    .total {{ font-weight: bold; margin-top: 10px; font-size: 14px; color: #714B67; }}
    .footer {{ margin-top: 20px; padding-top: 10px; border-top: 1px solid #ddd;
               color: #999; font-size: 10px; text-align: center; }}
</style></head><body>
    <div class="header">
        {logo_html}
        <div class="header-text">
            <h1>Member Performance Report</h1>
            <p>{company.name} | {self.member_id.name} | Period: {d_from} to {d_to}</p>
        </div>
    </div>

    <div class="kpi-grid">
        <div class="kpi"><div class="kpi-value">{self.total_tasks}</div>
            <div class="kpi-label">Total Tasks</div></div>
        <div class="kpi"><div class="kpi-value" style="color:#5cb85c">
            {self.approved_tasks}</div>
            <div class="kpi-label">Approved</div></div>
        <div class="kpi"><div class="kpi-value" style="color:#5cb85c">
            {self.assigned_approved_tasks}</div>
            <div class="kpi-label">Asgn Approved</div></div>
        <div class="kpi"><div class="kpi-value" style="color:#d9534f">
            {self.rejected_tasks}</div>
            <div class="kpi-label">Rejected</div></div>
        <div class="kpi"><div class="kpi-value" style="color:#d9534f">
            {self.assigned_rejected_tasks}</div>
            <div class="kpi-label">Asgn Rejected</div></div>
        <div class="kpi"><div class="kpi-value" style="color:#f0ad4e">
            {self.pending_tasks}</div>
            <div class="kpi-label">Pending</div></div>
        <div class="kpi"><div class="kpi-value" style="color:#f0ad4e">
            {self.assigned_pending_tasks}</div>
            <div class="kpi-label">Asgn Pending</div></div>
        <div class="kpi"><div class="kpi-value">{self.approval_rate:.1f}%</div>
            <div class="kpi-label">Approval Rate</div></div>
        <div class="kpi"><div class="kpi-value">{self.approved_hours:.1f}</div>
            <div class="kpi-label">Approved Hours</div></div>
        <div class="kpi"><div class="kpi-value" style="color:#d9534f">
            {self.late_entries}</div>
            <div class="kpi-label">Late Entries</div></div>
        <div class="kpi"><div class="kpi-value">{self.avg_hours_per_day:.2f}</div>
            <div class="kpi-label">Avg Hours/Day</div></div>
        <div class="kpi"><div class="kpi-value" style="color:{'#5cb85c' if self.daily_performance >= 100 else '#f0ad4e' if self.daily_performance >= 75 else '#d9534f'}">{self.daily_performance:.1f}%</div>
            <div class="kpi-label">Daily Performance</div></div>
        <div class="kpi"><div class="kpi-value" style="color:{'#5cb85c' if self.weekly_performance >= 100 else '#f0ad4e' if self.weekly_performance >= 75 else '#d9534f'}">{self.weekly_performance:.1f}%</div>
            <div class="kpi-label">Weekly Performance</div></div>
        <div class="kpi"><div class="kpi-value">{self.monthly_target:.0f}</div>
            <div class="kpi-label">Monthly Target (hrs)</div></div>
        <div class="kpi"><div class="kpi-value" style="color:{'#5cb85c' if self.monthly_performance >= 100 else '#f0ad4e' if self.monthly_performance >= 75 else '#d9534f'}">{self.monthly_performance:.1f}%</div>
            <div class="kpi-label">Monthly Performance</div></div>
    </div>

    <h2>Project Breakdown</h2>
    <table><thead><tr>
        <th>Project</th><th>Tasks</th><th>Total Hours</th>
        <th>Approved Hours</th><th>Approval Rate</th><th>Late</th>
    </tr></thead><tbody>{project_rows}</tbody></table>

    <h2>Task Details</h2>
    <table><thead><tr>
        <th>Date</th><th>Project</th><th>Description</th>
        <th>From</th><th>To</th><th>Hours</th><th>Status</th><th>Late</th>
    </tr></thead><tbody>{task_rows}</tbody></table>
    <div class="total">Total Hours: {total_hours:.2f}</div>
    <div class="footer">Generated by {company.name} - Task & Project Management System</div>
</body></html>'''

        try:
            with tempfile.NamedTemporaryFile(
                suffix='.html', mode='w', delete=False,
                encoding='utf-8',
            ) as html_file:
                html_file.write(html)
                html_path = html_file.name
            pdf_path = html_path.replace('.html', '.pdf')
            result = subprocess.run(
                ['wkhtmltopdf', '--page-size', 'A4',
                 '--margin-top', '10mm', '--margin-bottom', '10mm',
                 '--margin-left', '10mm', '--margin-right', '10mm',
                 html_path, pdf_path],
                capture_output=True, timeout=30,
            )
            if result.returncode != 0:
                raise UserError(
                    _('Failed to generate PDF: %s') %
                    result.stderr.decode())
            with open(pdf_path, 'rb') as f:
                self.report_file = base64.b64encode(f.read())
            member_name = self.member_id.name.replace(' ', '_')
            self.report_filename = (
                f'member_report_{member_name}_{d_from}_{d_to}.pdf')
        except FileNotFoundError:
            raise UserError(
                _('wkhtmltopdf is not installed. '
                  'Please install wkhtmltopdf package.'))
        except subprocess.TimeoutExpired:
            raise UserError(_('PDF generation timed out.'))
        return {
            'type': 'ir.actions.act_url',
            'url': (
                f'/web/content?model={self._name}'
                f'&id={self.id}'
                f'&field=report_file'
                f'&filename_field=report_filename'
                f'&download=true'
            ),
            'target': 'new',
        }

    @staticmethod
    def _float_to_time(value):
        hours = int(value)
        minutes = int((value - hours) * 60)
        return f'{hours:02d}:{minutes:02d}'


class MemberPerformanceLine(models.TransientModel):
    _name = 'task.management.member.performance.line'
    _description = 'Member Performance Report - Task Line'

    report_id = fields.Many2one(
        'task.management.member.performance.report',
        string='Report')
    date = fields.Date(string='Date')
    project_name = fields.Char(string='Project')
    description = fields.Char(string='Description')
    time_from = fields.Float(string='From')
    time_to = fields.Float(string='To')
    duration_hours = fields.Float(string='Hours')
    approval_status = fields.Selection([
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('assigned_pending', 'Assigned / Pending'),
        ('assigned_approved', 'Assigned / Approved'),
        ('assigned_rejected', 'Assigned / Rejected'),
    ], string='Status')
    is_late_entry = fields.Boolean(string='Late')


class MemberPerformanceProject(models.TransientModel):
    _name = 'task.management.member.performance.project'
    _description = 'Member Performance Report - Project Line'

    report_id = fields.Many2one(
        'task.management.member.performance.report',
        string='Report')
    project_name = fields.Char(string='Project')
    task_count = fields.Integer(string='Tasks')
    total_hours = fields.Float(string='Total Hours')
    approved_hours = fields.Float(string='Approved Hours')
    approval_rate = fields.Float(string='Approval Rate (%)')
    late_entries = fields.Integer(string='Late Entries')
