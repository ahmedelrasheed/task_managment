import base64
import csv
import io

from odoo import models, fields, api, _
from datetime import timedelta


class ProjectPerformanceReport(models.TransientModel):
    _name = 'task.management.project.performance.report'
    _description = 'Project Performance Report'

    project_id = fields.Many2one(
        'task.management.project', string='Project', required=True,
    )
    period = fields.Selection([
        ('all', 'All Time'),
        ('today', 'Today'),
        ('week', 'This Week'),
        ('month', 'This Month'),
        ('custom', 'Custom Range'),
    ], string='Period', default='all', required=True)
    date_from = fields.Date(string='Date From')
    date_to = fields.Date(string='Date To')

    # Project summary
    project_status = fields.Char(
        string='Status', compute='_compute_stats')
    expected_hours = fields.Float(
        string='Expected Hours', compute='_compute_stats')
    total_tasks = fields.Integer(
        string='Total Tasks', compute='_compute_stats')
    approved_tasks = fields.Integer(
        string='Approved Tasks', compute='_compute_stats')
    rejected_tasks = fields.Integer(
        string='Rejected Tasks', compute='_compute_stats')
    pending_tasks = fields.Integer(
        string='Pending Tasks', compute='_compute_stats')
    total_hours = fields.Float(
        string='Total Hours', compute='_compute_stats')
    approved_hours = fields.Float(
        string='Approved Hours', compute='_compute_stats')
    approval_rate = fields.Float(
        string='Approval Rate (%)', compute='_compute_stats')
    progress = fields.Float(
        string='Progress (%)', compute='_compute_stats')
    late_entries = fields.Integer(
        string='Late Entries', compute='_compute_stats')
    member_count = fields.Integer(
        string='Members', compute='_compute_stats')

    # Member breakdown
    member_line_ids = fields.One2many(
        'task.management.project.performance.member', 'report_id',
        string='Member Breakdown', compute='_compute_stats')

    # Task details
    task_line_ids = fields.One2many(
        'task.management.project.performance.task', 'report_id',
        string='Task Details', compute='_compute_stats')

    # Export
    report_file = fields.Binary(string='Report File', readonly=True)
    report_filename = fields.Char(string='Filename')

    def _get_date_range(self):
        today = fields.Date.context_today(self)
        if self.period == 'all':
            return None, None
        elif self.period == 'today':
            return today, today
        elif self.period == 'week':
            week_start = today - timedelta(days=today.weekday())
            return week_start, week_start + timedelta(days=6)
        elif self.period == 'month':
            month_start = today.replace(day=1)
            if today.month == 12:
                month_end = today.replace(day=31)
            else:
                month_end = today.replace(
                    month=today.month + 1, day=1) - timedelta(days=1)
            return month_start, month_end
        else:
            return self.date_from or today, self.date_to or today

    def _get_tasks(self):
        """Get tasks for the selected project and period."""
        domain = [('project_id', '=', self.project_id.id)]
        d_from, d_to = self._get_date_range()
        if d_from:
            domain.append(('date', '>=', d_from))
        if d_to:
            domain.append(('date', '<=', d_to))
        return self.env['task.management.task'].sudo().search(
            domain, order='date desc, member_id, id desc')

    @api.depends('project_id', 'period', 'date_from', 'date_to')
    def _compute_stats(self):
        MemberLine = self.env['task.management.project.performance.member']
        TaskLine = self.env['task.management.project.performance.task']
        for report in self:
            if not report.project_id:
                report.project_status = ''
                report.expected_hours = 0
                report.total_tasks = 0
                report.approved_tasks = 0
                report.rejected_tasks = 0
                report.pending_tasks = 0
                report.total_hours = 0.0
                report.approved_hours = 0.0
                report.approval_rate = 0.0
                report.progress = 0.0
                report.late_entries = 0
                report.member_count = 0
                report.member_line_ids = MemberLine
                report.task_line_ids = TaskLine
                continue

            proj = report.project_id
            tasks = report._get_tasks()

            approved = tasks.filtered(
                lambda t: t.approval_status == 'approved')
            rejected = tasks.filtered(
                lambda t: t.approval_status == 'rejected')
            pending = tasks.filtered(
                lambda t: t.approval_status == 'pending')
            late = tasks.filtered(lambda t: t.is_late_entry)
            total = len(tasks)

            total_hrs = sum(tasks.mapped('duration_hours'))
            approved_hrs = sum(approved.mapped('duration_hours'))

            report.project_status = dict(
                proj._fields['status'].selection).get(
                proj.status, proj.status)
            report.expected_hours = proj.expected_hours
            report.total_tasks = total
            report.approved_tasks = len(approved)
            report.rejected_tasks = len(rejected)
            report.pending_tasks = len(pending)
            report.total_hours = total_hrs
            report.approved_hours = approved_hrs
            report.approval_rate = round(
                (len(approved) / total * 100) if total else 0, 1)
            report.progress = round(
                (approved_hrs / proj.expected_hours * 100)
                if proj.expected_hours else 0, 1)
            report.late_entries = len(late)

            # Members who have tasks in this period
            members = tasks.mapped('member_id')
            report.member_count = len(members)

            # Member breakdown
            member_lines = []
            for member in members:
                m_tasks = tasks.filtered(
                    lambda t, m=member: t.member_id == m)
                m_approved = m_tasks.filtered(
                    lambda t: t.approval_status == 'approved')
                m_total = len(m_tasks)
                m_late = m_tasks.filtered(lambda t: t.is_late_entry)
                m_total_hrs = sum(m_tasks.mapped('duration_hours'))
                m_approved_hrs = sum(
                    m_approved.mapped('duration_hours'))
                unique_days = len(set(m_tasks.mapped('date')))
                member_lines.append((0, 0, {
                    'member_name': member.name,
                    'role': member.role,
                    'task_count': m_total,
                    'total_hours': m_total_hrs,
                    'approved_hours': m_approved_hrs,
                    'approval_rate': round(
                        (len(m_approved) / m_total * 100)
                        if m_total else 0, 1),
                    'late_entries': len(m_late),
                    'avg_hours_per_day': round(
                        m_total_hrs / unique_days
                        if unique_days else 0, 2),
                    'pending_count': len(m_tasks.filtered(
                        lambda t: t.approval_status == 'pending')),
                    'rejected_count': len(m_tasks.filtered(
                        lambda t: t.approval_status == 'rejected')),
                }))
            report.member_line_ids = member_lines

            # Task details
            task_lines = []
            for task in tasks:
                task_lines.append((0, 0, {
                    'date': task.date,
                    'member_name': task.member_id.name,
                    'description': (task.description or '')[:80],
                    'time_from': task.time_from,
                    'time_to': task.time_to,
                    'duration_hours': task.duration_hours,
                    'approval_status': task.approval_status,
                    'is_late_entry': task.is_late_entry,
                    'manager_comment': (task.manager_comment or '')[:50],
                }))
            report.task_line_ids = task_lines

    def action_export_csv(self):
        """Export the full project report as CSV."""
        self.ensure_one()
        if not self.project_id:
            return

        tasks = self._get_tasks()
        d_from, d_to = self._get_date_range()
        members = tasks.mapped('member_id')

        output = io.StringIO()
        writer = csv.writer(output)

        # Project header
        writer.writerow(['Project Performance Report'])
        writer.writerow(['Project', self.project_id.name])
        writer.writerow(['Status', self.project_status])
        period_str = (f'{d_from} to {d_to}' if d_from
                      else 'All Time')
        writer.writerow(['Period', period_str])
        writer.writerow([])

        # Project KPIs
        writer.writerow(['--- Project Summary ---'])
        writer.writerow(['Expected Hours', f'{self.expected_hours:.2f}'])
        writer.writerow(['Total Tasks', self.total_tasks])
        writer.writerow(['Approved', self.approved_tasks])
        writer.writerow(['Rejected', self.rejected_tasks])
        writer.writerow(['Pending', self.pending_tasks])
        writer.writerow(['Total Hours', f'{self.total_hours:.2f}'])
        writer.writerow(['Approved Hours', f'{self.approved_hours:.2f}'])
        writer.writerow(['Approval Rate', f'{self.approval_rate:.1f}%'])
        writer.writerow(['Progress', f'{self.progress:.1f}%'])
        writer.writerow(['Late Entries', self.late_entries])
        writer.writerow(['Active Members', self.member_count])
        writer.writerow([])

        # Member breakdown
        writer.writerow(['--- Member Breakdown ---'])
        writer.writerow([
            'Member', 'Role', 'Tasks', 'Total Hours', 'Approved Hours',
            'Approval Rate', 'Pending', 'Rejected', 'Late Entries',
            'Avg Hours/Day',
        ])
        for member in members:
            m_tasks = tasks.filtered(
                lambda t, m=member: t.member_id == m)
            m_approved = m_tasks.filtered(
                lambda t: t.approval_status == 'approved')
            m_total = len(m_tasks)
            m_total_hrs = sum(m_tasks.mapped('duration_hours'))
            m_approved_hrs = sum(m_approved.mapped('duration_hours'))
            m_late = m_tasks.filtered(lambda t: t.is_late_entry)
            unique_days = len(set(m_tasks.mapped('date')))
            role_label = dict(
                member._fields['role'].selection).get(
                member.role, member.role)
            writer.writerow([
                member.name,
                role_label,
                m_total,
                f'{m_total_hrs:.2f}',
                f'{m_approved_hrs:.2f}',
                f'{round((len(m_approved) / m_total * 100) if m_total else 0, 1)}%',
                len(m_tasks.filtered(
                    lambda t: t.approval_status == 'pending')),
                len(m_tasks.filtered(
                    lambda t: t.approval_status == 'rejected')),
                len(m_late),
                f'{(m_total_hrs / unique_days if unique_days else 0):.2f}',
            ])
        writer.writerow([])

        # Task details
        writer.writerow(['--- All Tasks ---'])
        writer.writerow([
            'Date', 'Member', 'Description', 'From', 'To',
            'Hours', 'Status', 'Late', 'Manager Comment',
        ])
        for task in tasks:
            writer.writerow([
                str(task.date),
                task.member_id.name,
                (task.description or '')[:80],
                self._float_to_time(task.time_from),
                self._float_to_time(task.time_to),
                f'{task.duration_hours:.2f}',
                task.approval_status,
                'Yes' if task.is_late_entry else 'No',
                (task.manager_comment or '')[:50],
            ])

        csv_data = output.getvalue().encode('utf-8-sig')
        self.report_file = base64.b64encode(csv_data)
        proj_name = self.project_id.name.replace(' ', '_')
        date_suffix = f'_{d_from}_{d_to}' if d_from else '_all_time'
        self.report_filename = (
            f'project_report_{proj_name}{date_suffix}.csv')
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


class ProjectPerformanceMember(models.TransientModel):
    _name = 'task.management.project.performance.member'
    _description = 'Project Performance Report - Member Line'

    report_id = fields.Many2one(
        'task.management.project.performance.report',
        string='Report')
    member_name = fields.Char(string='Member')
    role = fields.Selection([
        ('member', 'Member'),
        ('project_manager', 'Project Manager'),
        ('admin_manager', 'Admin Manager'),
    ], string='Role')
    task_count = fields.Integer(string='Tasks')
    total_hours = fields.Float(string='Total Hours')
    approved_hours = fields.Float(string='Approved Hours')
    approval_rate = fields.Float(string='Approval Rate (%)')
    pending_count = fields.Integer(string='Pending')
    rejected_count = fields.Integer(string='Rejected')
    late_entries = fields.Integer(string='Late Entries')
    avg_hours_per_day = fields.Float(string='Avg Hours/Day')


class ProjectPerformanceTask(models.TransientModel):
    _name = 'task.management.project.performance.task'
    _description = 'Project Performance Report - Task Line'

    report_id = fields.Many2one(
        'task.management.project.performance.report',
        string='Report')
    date = fields.Date(string='Date')
    member_name = fields.Char(string='Member')
    description = fields.Char(string='Description')
    time_from = fields.Float(string='From')
    time_to = fields.Float(string='To')
    duration_hours = fields.Float(string='Hours')
    approval_status = fields.Selection([
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='Status')
    is_late_entry = fields.Boolean(string='Late')
    manager_comment = fields.Char(string='Comment')
