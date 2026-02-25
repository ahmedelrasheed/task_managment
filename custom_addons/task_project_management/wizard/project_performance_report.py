import base64
import csv
import io
import subprocess
import tempfile

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import timedelta


class ProjectPerformanceReport(models.TransientModel):
    _name = 'task.management.project.performance.report'
    _description = 'Project Performance Report'

    @api.depends()
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = _("Project Report")

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
    phase_count = fields.Integer(
        string='Phases', compute='_compute_stats')
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

    # Phase breakdown
    phase_line_ids = fields.One2many(
        'task.management.project.performance.phase', 'report_id',
        string='Phase Breakdown', compute='_compute_stats')

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
        return self.env['task.management.task'].search(
            domain, order='date desc, member_id, id desc')

    @api.depends('project_id', 'period', 'date_from', 'date_to')
    def _compute_stats(self):
        MemberLine = self.env['task.management.project.performance.member']
        TaskLine = self.env['task.management.project.performance.task']
        PhaseLine = self.env['task.management.project.performance.phase']
        for report in self:
            if not report.project_id:
                report.project_status = ''
                report.phase_count = 0
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
                report.phase_line_ids = PhaseLine
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
            report.phase_count = len(proj.phase_ids)
            report.total_tasks = total
            report.approved_tasks = len(approved)
            report.rejected_tasks = len(rejected)
            report.pending_tasks = len(pending)
            report.total_hours = total_hrs
            report.approved_hours = approved_hrs
            report.approval_rate = round(
                (len(approved) / total * 100) if total else 0, 1)
            report.progress = round(proj.progress_percentage, 1)
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
            report.member_line_ids = member_lines or MemberLine

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
                    'task_type': task.task_type,
                    'approval_status': task.approval_status,
                    'is_late_entry': task.is_late_entry,
                    'manager_comment': (task.manager_comment or '')[:50],
                }))
            report.task_line_ids = task_lines or TaskLine

            # Phase breakdown
            phase_lines = []
            for phase in proj.phase_ids:
                phase_lines.append((0, 0, {
                    'phase_name': phase.name,
                    'percentage': phase.percentage,
                    'completion_rate': phase.completion_rate,
                    'effective_progress': phase.effective_progress,
                }))
            report.phase_line_ids = phase_lines or PhaseLine

    def _get_selection_labels(self):
        """Get translated selection labels for task_type and approval_status."""
        Task = self.env['task.management.task']
        fget = Task.fields_get(['task_type', 'approval_status'])
        return (
            dict(fget['task_type']['selection']),
            dict(fget['approval_status']['selection']),
        )

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
        company = self.env.company.name
        period_str = (f'{d_from}  {_("to")}  {d_to}' if d_from else _('All Time'))

        # -- Report Header --
        writer.writerow([_('PROJECT PERFORMANCE REPORT')])
        writer.writerow([])
        writer.writerow([_('Company:'), company])
        writer.writerow([_('Project:'), self.project_id.name])
        writer.writerow([_('Status:'), self.project_status.replace(
            '_', ' ').title()])
        writer.writerow([_('Period:'), period_str])
        writer.writerow([])

        # -- Project Summary --
        writer.writerow([_('PROJECT SUMMARY')])
        writer.writerow([])
        writer.writerow(['', _('Metric'), _('Value')])
        writer.writerow(['', _('Phases'), self.phase_count])
        writer.writerow(['', _('Total Tasks'), self.total_tasks])
        writer.writerow(['', _('Approved'), self.approved_tasks])
        writer.writerow(['', _('Rejected'), self.rejected_tasks])
        writer.writerow(['', _('Pending'), self.pending_tasks])
        writer.writerow(['', _('Total Hours'), f'{self.total_hours:.2f}'])
        writer.writerow(['', _('Approved Hours'),
                          f'{self.approved_hours:.2f}'])
        writer.writerow(['', _('Approval Rate'),
                          f'{self.approval_rate:.1f}%'])
        writer.writerow(['', _('Progress'), f'{self.progress:.1f}%'])
        writer.writerow(['', _('Late Entries'), self.late_entries])
        writer.writerow(['', _('Active Members'), self.member_count])
        writer.writerow([])

        # -- Member Breakdown --
        writer.writerow([_('MEMBER BREAKDOWN')])
        writer.writerow([])
        writer.writerow([
            '', _('No.'), _('Member'), _('Role'), _('Tasks'), _('Total Hours'),
            _('Approved Hours'), _('Approval Rate'), _('Pending'), _('Rejected'),
            _('Late Entries'), _('Avg Hours/Day'),
        ])
        g_tasks = 0
        g_hrs = 0.0
        g_app_hrs = 0.0
        g_late = 0
        for mi, member in enumerate(members, 1):
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
                '', mi, member.name, role_label, m_total,
                f'{m_total_hrs:.2f}', f'{m_approved_hrs:.2f}',
                f'{round((len(m_approved) / m_total * 100) if m_total else 0, 1)}%',
                len(m_tasks.filtered(
                    lambda t: t.approval_status == 'pending')),
                len(m_tasks.filtered(
                    lambda t: t.approval_status == 'rejected')),
                len(m_late),
                f'{(m_total_hrs / unique_days if unique_days else 0):.2f}',
            ])
            g_tasks += m_total
            g_hrs += m_total_hrs
            g_app_hrs += m_approved_hrs
            g_late += len(m_late)
        writer.writerow(['', '', _('TOTAL'), '', g_tasks,
                          f'{g_hrs:.2f}', f'{g_app_hrs:.2f}',
                          '', '', '', g_late, ''])
        writer.writerow([])

        # -- Phase Breakdown --
        if self.phase_line_ids:
            writer.writerow([_('PHASE BREAKDOWN')])
            writer.writerow([])
            writer.writerow(['', _('No.'), _('Phase'), _('Weight'),
                              _('Completion'), _('Contribution')])
            for pi, phase in enumerate(self.phase_line_ids, 1):
                writer.writerow([
                    '', pi, phase.phase_name,
                    f'{phase.percentage:.1f}%',
                    f'{phase.completion_rate:.1f}%',
                    f'{phase.effective_progress:.1f}%',
                ])
            writer.writerow([])

        # -- Task Details --
        writer.writerow([_('ALL TASKS')])
        writer.writerow([])
        writer.writerow([
            '', _('No.'), _('Date'), _('Member'), _('Description'), _('From'), _('To'),
            _('Hours'), _('Task Type'), _('Status'), _('Late'), _('Manager Comment'),
        ])
        type_map, status_map = self._get_selection_labels()
        total_hrs = 0.0
        for i, task in enumerate(tasks, 1):
            writer.writerow([
                '', i, str(task.date), task.member_id.name,
                (task.description or '')[:80],
                self._float_to_time(task.time_from),
                self._float_to_time(task.time_to),
                f'{task.duration_hours:.2f}',
                type_map.get(task.task_type, task.task_type),
                status_map.get(task.approval_status, task.approval_status),
                _('Yes') if task.is_late_entry else '',
                (task.manager_comment or '')[:50],
            ])
            total_hrs += task.duration_hours
        writer.writerow(['', '', '', '', _('TOTAL'), '', '',
                          f'{total_hrs:.2f}', '', '', '', ''])
        writer.writerow([])
        writer.writerow([_('END OF REPORT')])

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

    def action_export_png(self):
        """Export the full project report as PNG image."""
        self.ensure_one()
        if not self.project_id:
            return

        tasks = self._get_tasks()
        d_from, d_to = self._get_date_range()
        members = tasks.mapped('member_id')
        period_str = f'{d_from} {_("to")} {d_to}' if d_from else _('All Time')

        # Build member breakdown rows
        member_rows = ''
        for member in members:
            m_tasks = tasks.filtered(lambda t, m=member: t.member_id == m)
            m_approved = m_tasks.filtered(
                lambda t: t.approval_status == 'approved')
            m_total = len(m_tasks)
            m_total_hrs = sum(m_tasks.mapped('duration_hours'))
            m_approved_hrs = sum(m_approved.mapped('duration_hours'))
            m_late = m_tasks.filtered(lambda t: t.is_late_entry)
            rate = round(
                (len(m_approved) / m_total * 100) if m_total else 0, 1)
            member_rows += f'''<tr>
                <td>{member.name}</td>
                <td>{m_total}</td>
                <td>{m_total_hrs:.2f}</td>
                <td>{m_approved_hrs:.2f}</td>
                <td>{rate}%</td>
                <td>{len(m_late)}</td>
            </tr>'''

        # Build task detail rows
        type_map, status_map = self._get_selection_labels()
        task_rows = ''
        total_hours = 0
        for task in tasks:
            type_color = '#17a2b8' if task.task_type == 'assigned' else '#6c757d'
            status_color = {
                'pending': '#f0ad4e',
                'approved': '#5cb85c',
                'rejected': '#d9534f',
            }.get(task.approval_status, '#999')
            task_rows += f'''<tr>
                <td>{task.date}</td>
                <td>{task.member_id.name}</td>
                <td>{(task.description or "")[:60]}</td>
                <td>{self._float_to_time(task.time_from)}</td>
                <td>{self._float_to_time(task.time_to)}</td>
                <td>{task.duration_hours:.2f}</td>
                <td style="color:{type_color};font-weight:bold;">{type_map.get(task.task_type, task.task_type)}</td>
                <td style="color:{status_color};font-weight:bold;">
                    {status_map.get(task.approval_status, task.approval_status)}</td>
                <td>{_("Yes") if task.is_late_entry else ""}</td>
            </tr>'''
            total_hours += task.duration_hours

        # Build phase breakdown rows
        phase_rows = ''
        for phase in self.phase_line_ids:
            phase_rows += f'''<tr>
                <td>{phase.phase_name}</td>
                <td>{phase.percentage:.1f}%</td>
                <td>{phase.completion_rate:.1f}%</td>
                <td>{phase.effective_progress:.1f}%</td>
            </tr>'''

        # Get company logo
        company = self.env.company
        logo_html = ''
        if company.logo:
            logo_b64 = company.logo.decode() if isinstance(company.logo, bytes) else company.logo
            logo_html = f'<img src="data:image/png;base64,{logo_b64}" class="logo"/>'

        is_rtl = self.env.lang and self.env.lang.startswith('ar')
        dir_attr = ' dir="rtl"' if is_rtl else ''
        th_align = 'right' if is_rtl else 'left'

        html = f'''<!DOCTYPE html>
<html{dir_attr}><head><meta charset="utf-8"/>
<style>
    body {{ font-family: Arial, sans-serif; margin: 20px; background: #fff; }}
    .header {{ display: flex; align-items: center; gap: 15px;
               border-bottom: 3px solid #0B3D91; padding-bottom: 15px; margin-bottom: 20px; }}
    .logo {{ height: 60px; width: auto; }}
    .header-text h1 {{ color: #0B3D91; margin: 0; font-size: 24px; }}
    .header-text p {{ color: #666; margin: 3px 0 0 0; font-size: 13px; }}
    h2 {{ color: #0B3D91; margin-top: 20px; border-bottom: 2px solid #0B3D91;
          padding-bottom: 5px; font-size: 16px; }}
    .meta {{ color: #666; margin-bottom: 15px; font-size: 13px; }}
    .kpi-grid {{ display: flex; flex-wrap: wrap; gap: 10px; margin: 15px 0; }}
    .kpi {{ background: #E8EEF7; border: 1px solid #ddd; border-radius: 8px;
            padding: 10px 15px; text-align: center; min-width: 110px; }}
    .kpi-value {{ font-size: 20px; font-weight: bold; color: #0B3D91; }}
    .kpi-label {{ font-size: 10px; color: #666; text-transform: uppercase; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
    th {{ background: #0B3D91; color: white; padding: 8px; text-align: {th_align}; font-size: 12px; }}
    td {{ padding: 6px 8px; border-bottom: 1px solid #ddd; font-size: 12px; }}
    tr:nth-child(even) {{ background: #f9f9f9; }}
    .total {{ font-weight: bold; margin-top: 10px; font-size: 14px; color: #0B3D91; }}
    .footer {{ margin-top: 20px; padding-top: 10px; border-top: 1px solid #ddd;
               color: #999; font-size: 10px; text-align: center; }}
</style></head><body>
    <div class="header">
        {logo_html}
        <div class="header-text">
            <h1>{_("Project Performance Report")}</h1>
            <p>{company.name} | {self.project_id.name} | {period_str} | {_("Status:")} {self.project_status}</p>
        </div>
    </div>

    <div class="kpi-grid">
        <div class="kpi"><div class="kpi-value">{self.total_tasks}</div>
            <div class="kpi-label">{_("Total Tasks")}</div></div>
        <div class="kpi"><div class="kpi-value" style="color:#5cb85c">
            {self.approved_tasks}</div>
            <div class="kpi-label">{_("Approved")}</div></div>
        <div class="kpi"><div class="kpi-value" style="color:#d9534f">
            {self.rejected_tasks}</div>
            <div class="kpi-label">{_("Rejected")}</div></div>
        <div class="kpi"><div class="kpi-value" style="color:#f0ad4e">
            {self.pending_tasks}</div>
            <div class="kpi-label">{_("Pending")}</div></div>
        <div class="kpi"><div class="kpi-value">{self.phase_count}</div>
            <div class="kpi-label">{_("Phases")}</div></div>
        <div class="kpi"><div class="kpi-value">{self.progress:.1f}%</div>
            <div class="kpi-label">{_("Progress")}</div></div>
        <div class="kpi"><div class="kpi-value">{self.approval_rate:.1f}%</div>
            <div class="kpi-label">{_("Approval Rate")}</div></div>
        <div class="kpi"><div class="kpi-value">{self.approved_hours:.1f}</div>
            <div class="kpi-label">{_("Approved Hours")}</div></div>
        <div class="kpi"><div class="kpi-value" style="color:#d9534f">
            {self.late_entries}</div>
            <div class="kpi-label">{_("Late Entries")}</div></div>
    </div>

    <h2>{_("Member Breakdown")}</h2>
    <table><thead><tr>
        <th>{_("Member")}</th><th>{_("Tasks")}</th><th>{_("Total Hours")}</th>
        <th>{_("Approved Hours")}</th><th>{_("Approval Rate")}</th><th>{_("Late")}</th>
    </tr></thead><tbody>{member_rows}</tbody></table>

    <h2>{_("Phase Breakdown")}</h2>
    <table><thead><tr>
        <th>{_("Phase")}</th><th>{_("Weight (%)")}</th><th>{_("Completion (%)")}</th>
        <th>{_("Contribution (%)")}</th>
    </tr></thead><tbody>{phase_rows}</tbody></table>

    <h2>{_("Task Details")}</h2>
    <table><thead><tr>
        <th>{_("Date")}</th><th>{_("Member")}</th><th>{_("Description")}</th>
        <th>{_("From")}</th><th>{_("To")}</th><th>{_("Hours")}</th><th>{_("Type")}</th><th>{_("Status")}</th><th>{_("Late")}</th>
    </tr></thead><tbody>{task_rows}</tbody></table>
    <div class="total">{_("Total Hours:")} {total_hours:.2f}</div>
    <div class="footer">{_("Generated by")} {company.name} | {_("Project Performance Report")} | {fields.Date.context_today(self)}</div>
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
            proj_name = self.project_id.name.replace(' ', '_')
            d_from, d_to = self._get_date_range()
            date_suffix = f'_{d_from}_{d_to}' if d_from else '_all_time'
            self.report_filename = (
                f'project_report_{proj_name}{date_suffix}.png')
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
        """Export the full project report as PDF."""
        self.ensure_one()
        if not self.project_id:
            return

        tasks = self._get_tasks()
        d_from, d_to = self._get_date_range()
        members = tasks.mapped('member_id')
        period_str = f'{d_from} {_("to")} {d_to}' if d_from else _('All Time')

        # Build member breakdown rows
        member_rows = ''
        for member in members:
            m_tasks = tasks.filtered(lambda t, m=member: t.member_id == m)
            m_approved = m_tasks.filtered(
                lambda t: t.approval_status == 'approved')
            m_total = len(m_tasks)
            m_total_hrs = sum(m_tasks.mapped('duration_hours'))
            m_approved_hrs = sum(m_approved.mapped('duration_hours'))
            m_late = m_tasks.filtered(lambda t: t.is_late_entry)
            rate = round(
                (len(m_approved) / m_total * 100) if m_total else 0, 1)
            member_rows += f'''<tr>
                <td>{member.name}</td>
                <td>{m_total}</td>
                <td>{m_total_hrs:.2f}</td>
                <td>{m_approved_hrs:.2f}</td>
                <td>{rate}%</td>
                <td>{len(m_late)}</td>
            </tr>'''

        # Build task detail rows
        type_map, status_map = self._get_selection_labels()
        task_rows = ''
        total_hours = 0
        for task in tasks:
            type_color = '#17a2b8' if task.task_type == 'assigned' else '#6c757d'
            status_color = {
                'pending': '#f0ad4e',
                'approved': '#5cb85c',
                'rejected': '#d9534f',
            }.get(task.approval_status, '#999')
            task_rows += f'''<tr>
                <td>{task.date}</td>
                <td>{task.member_id.name}</td>
                <td>{(task.description or "")[:60]}</td>
                <td>{self._float_to_time(task.time_from)}</td>
                <td>{self._float_to_time(task.time_to)}</td>
                <td>{task.duration_hours:.2f}</td>
                <td style="color:{type_color};font-weight:bold;">{type_map.get(task.task_type, task.task_type)}</td>
                <td style="color:{status_color};font-weight:bold;">
                    {status_map.get(task.approval_status, task.approval_status)}</td>
                <td>{_("Yes") if task.is_late_entry else ""}</td>
            </tr>'''
            total_hours += task.duration_hours

        # Build phase breakdown rows
        phase_rows = ''
        for phase in self.phase_line_ids:
            phase_rows += f'''<tr>
                <td>{phase.phase_name}</td>
                <td>{phase.percentage:.1f}%</td>
                <td>{phase.completion_rate:.1f}%</td>
                <td>{phase.effective_progress:.1f}%</td>
            </tr>'''

        # Get company logo
        company = self.env.company
        logo_html = ''
        if company.logo:
            logo_b64 = company.logo.decode() if isinstance(company.logo, bytes) else company.logo
            logo_html = f'<img src="data:image/png;base64,{logo_b64}" class="logo"/>'

        is_rtl = self.env.lang and self.env.lang.startswith('ar')
        dir_attr = ' dir="rtl"' if is_rtl else ''
        th_align = 'right' if is_rtl else 'left'

        html = f'''<!DOCTYPE html>
<html{dir_attr}><head><meta charset="utf-8"/>
<style>
    body {{ font-family: Arial, sans-serif; margin: 20px; background: #fff; }}
    .header {{ display: flex; align-items: center; gap: 15px;
               border-bottom: 3px solid #0B3D91; padding-bottom: 15px; margin-bottom: 20px; }}
    .logo {{ height: 60px; width: auto; }}
    .header-text h1 {{ color: #0B3D91; margin: 0; font-size: 24px; }}
    .header-text p {{ color: #666; margin: 3px 0 0 0; font-size: 13px; }}
    h2 {{ color: #0B3D91; margin-top: 20px; border-bottom: 2px solid #0B3D91;
          padding-bottom: 5px; font-size: 16px; }}
    .kpi-grid {{ display: flex; flex-wrap: wrap; gap: 10px; margin: 15px 0; }}
    .kpi {{ background: #E8EEF7; border: 1px solid #ddd; border-radius: 8px;
            padding: 10px 15px; text-align: center; min-width: 110px; }}
    .kpi-value {{ font-size: 20px; font-weight: bold; color: #0B3D91; }}
    .kpi-label {{ font-size: 10px; color: #666; text-transform: uppercase; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
    th {{ background: #0B3D91; color: white; padding: 8px; text-align: {th_align}; font-size: 12px; }}
    td {{ padding: 6px 8px; border-bottom: 1px solid #ddd; font-size: 12px; }}
    tr:nth-child(even) {{ background: #f9f9f9; }}
    .total {{ font-weight: bold; margin-top: 10px; font-size: 14px; color: #0B3D91; }}
    .footer {{ margin-top: 20px; padding-top: 10px; border-top: 1px solid #ddd;
               color: #999; font-size: 10px; text-align: center; }}
</style></head><body>
    <div class="header">
        {logo_html}
        <div class="header-text">
            <h1>{_("Project Performance Report")}</h1>
            <p>{company.name} | {self.project_id.name} | {period_str} | {_("Status:")} {self.project_status}</p>
        </div>
    </div>

    <div class="kpi-grid">
        <div class="kpi"><div class="kpi-value">{self.total_tasks}</div>
            <div class="kpi-label">{_("Total Tasks")}</div></div>
        <div class="kpi"><div class="kpi-value" style="color:#5cb85c">
            {self.approved_tasks}</div>
            <div class="kpi-label">{_("Approved")}</div></div>
        <div class="kpi"><div class="kpi-value" style="color:#d9534f">
            {self.rejected_tasks}</div>
            <div class="kpi-label">{_("Rejected")}</div></div>
        <div class="kpi"><div class="kpi-value" style="color:#f0ad4e">
            {self.pending_tasks}</div>
            <div class="kpi-label">{_("Pending")}</div></div>
        <div class="kpi"><div class="kpi-value">{self.phase_count}</div>
            <div class="kpi-label">{_("Phases")}</div></div>
        <div class="kpi"><div class="kpi-value">{self.progress:.1f}%</div>
            <div class="kpi-label">{_("Progress")}</div></div>
        <div class="kpi"><div class="kpi-value">{self.approval_rate:.1f}%</div>
            <div class="kpi-label">{_("Approval Rate")}</div></div>
        <div class="kpi"><div class="kpi-value">{self.approved_hours:.1f}</div>
            <div class="kpi-label">{_("Approved Hours")}</div></div>
        <div class="kpi"><div class="kpi-value" style="color:#d9534f">
            {self.late_entries}</div>
            <div class="kpi-label">{_("Late Entries")}</div></div>
    </div>

    <h2>{_("Member Breakdown")}</h2>
    <table><thead><tr>
        <th>{_("Member")}</th><th>{_("Tasks")}</th><th>{_("Total Hours")}</th>
        <th>{_("Approved Hours")}</th><th>{_("Approval Rate")}</th><th>{_("Late")}</th>
    </tr></thead><tbody>{member_rows}</tbody></table>

    <h2>{_("Phase Breakdown")}</h2>
    <table><thead><tr>
        <th>{_("Phase")}</th><th>{_("Weight (%)")}</th><th>{_("Completion (%)")}</th>
        <th>{_("Contribution (%)")}</th>
    </tr></thead><tbody>{phase_rows}</tbody></table>

    <h2>{_("Task Details")}</h2>
    <table><thead><tr>
        <th>{_("Date")}</th><th>{_("Member")}</th><th>{_("Description")}</th>
        <th>{_("From")}</th><th>{_("To")}</th><th>{_("Hours")}</th><th>{_("Type")}</th><th>{_("Status")}</th><th>{_("Late")}</th>
    </tr></thead><tbody>{task_rows}</tbody></table>
    <div class="total">{_("Total Hours:")} {total_hours:.2f}</div>
    <div class="footer">{_("Generated by")} {company.name} | {_("Project Performance Report")} | {fields.Date.context_today(self)}</div>
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
            proj_name = self.project_id.name.replace(' ', '_')
            d_from, d_to = self._get_date_range()
            date_suffix = f'_{d_from}_{d_to}' if d_from else '_all_time'
            self.report_filename = (
                f'project_report_{proj_name}{date_suffix}.pdf')
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
    task_type = fields.Selection([
        ('initiated', 'Initiated'),
        ('assigned', 'Assigned'),
    ], string='Task Type')
    approval_status = fields.Selection([
        ('assigned', 'Assigned'),
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='Status')
    is_late_entry = fields.Boolean(string='Late')
    manager_comment = fields.Char(string='Comment')


class ProjectPerformancePhase(models.TransientModel):
    _name = 'task.management.project.performance.phase'
    _description = 'Project Performance Report - Phase Line'

    report_id = fields.Many2one(
        'task.management.project.performance.report', string='Report')
    phase_name = fields.Char(string='Phase')
    percentage = fields.Float(string='Weight (%)')
    completion_rate = fields.Float(string='Completion (%)')
    effective_progress = fields.Float(string='Contribution (%)')
