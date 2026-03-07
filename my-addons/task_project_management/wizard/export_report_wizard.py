import base64
import csv
import io
import subprocess
import tempfile

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ExportReportWizard(models.TransientModel):
    _name = 'task.management.export.report.wizard'
    _description = 'Export Report Wizard'

    project_id = fields.Many2one(
        'task.management.project', string='Project')
    member_id = fields.Many2one(
        'task.management.member', string='Member',
        domain=[('role', '!=', 'manager')])
    date_from = fields.Date(string='Date From', required=True)
    date_to = fields.Date(string='Date To', required=True)
    export_type = fields.Selection([
        ('csv', 'CSV'),
        ('image', 'Image (PNG)'),
        ('pdf', 'PDF'),
    ], string='Export Type', required=True, default='csv')
    report_file = fields.Binary(string='Report File', readonly=True)
    report_filename = fields.Char(string='Filename')

    def action_export(self):
        self.ensure_one()
        domain = [
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ]
        if self.project_id:
            domain.append(('project_id', '=', self.project_id.id))
        if self.member_id:
            domain.append(('member_id', '=', self.member_id.id))

        tasks = self.env['task.management.task'].search(domain)

        if self.export_type == 'csv':
            return self._export_csv(tasks)
        elif self.export_type == 'pdf':
            return self._export_pdf(tasks)
        else:
            return self._export_image(tasks)

    def _export_csv(self, tasks):
        output = io.StringIO()
        writer = csv.writer(output)
        company = self.env.company.name

        # ── Report Header ──
        writer.writerow([_('TASK REPORT')])
        writer.writerow([])
        writer.writerow([_('Company:'), company])
        writer.writerow([_('Period:'), f'{self.date_from}  {_("to")}  {self.date_to}'])
        if self.project_id:
            writer.writerow([_('Project:'), self.project_id.name])
        if self.member_id:
            writer.writerow([_('Member:'), self.member_id.name])
        writer.writerow([_('Total Tasks:'), len(tasks)])
        total_hours = sum(tasks.mapped('duration_hours'))
        writer.writerow([_('Total Hours:'), f'{total_hours:.2f}'])
        writer.writerow([])

        # ── Summary by Status ──
        approved = tasks.filtered(lambda t: t.approval_status == 'approved')
        pending = tasks.filtered(lambda t: t.approval_status == 'pending')
        rejected = tasks.filtered(lambda t: t.approval_status == 'rejected')
        assigned = tasks.filtered(lambda t: t.approval_status == 'assigned')
        late = tasks.filtered(lambda t: t.is_late_entry)
        writer.writerow([_('STATUS SUMMARY')])
        writer.writerow([])
        writer.writerow(['', _('Status'), _('Count'), _('Hours')])
        writer.writerow(['', _('Approved'), len(approved),
                          f'{sum(approved.mapped("duration_hours")):.2f}'])
        writer.writerow(['', _('Pending'), len(pending),
                          f'{sum(pending.mapped("duration_hours")):.2f}'])
        writer.writerow(['', _('Revision Requests'), len(rejected),
                          f'{sum(rejected.mapped("duration_hours")):.2f}'])
        if assigned:
            writer.writerow(['', _('Assigned'), len(assigned),
                              f'{sum(assigned.mapped("duration_hours")):.2f}'])
        writer.writerow(['', _('Late Entries'), len(late), ''])
        writer.writerow([])

        # ── Task Details ──
        writer.writerow([_('TASK DETAILS')])
        writer.writerow([])
        writer.writerow([
            _('No.'), _('Date'), _('Project'), _('Member'), _('Description'),
            _('From'), _('To'), _('Hours'), _('Status'), _('Late'), _('Manager Comment'),
        ])
        Task = self.env['task.management.task']
        fget = Task.fields_get(['approval_status'])
        status_map = dict(fget['approval_status']['selection'])
        for i, task in enumerate(tasks, 1):
            writer.writerow([
                i,
                str(task.date),
                task.project_id.name,
                task.member_id.name,
                task.description or '',
                self._float_to_time(task.time_from),
                self._float_to_time(task.time_to),
                f'{task.duration_hours:.2f}',
                status_map.get(task.approval_status, task.approval_status),
                _('Yes') if task.is_late_entry else '',
                task.manager_comment or '',
            ])
        writer.writerow([])
        writer.writerow(
            ['', '', '', '', _('TOTAL'), '', '', f'{total_hours:.2f}',
             '', '', ''])
        writer.writerow([])
        writer.writerow([_('END OF REPORT')])

        csv_data = output.getvalue().encode('utf-8-sig')
        self.report_file = base64.b64encode(csv_data)
        self.report_filename = f'task_report_{self.date_from}_{self.date_to}.csv'
        return self._return_download_action()

    def _export_image(self, tasks):
        """Export report as PNG image using wkhtmltoimage."""
        html = self._build_html_report(tasks)
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
            self.report_filename = (
                f'task_report_{self.date_from}_{self.date_to}.png')
        except FileNotFoundError:
            raise UserError(
                _('wkhtmltoimage is not installed. '
                  'Please install wkhtmltopdf package.'))
        except subprocess.TimeoutExpired:
            raise UserError(_('Image generation timed out.'))
        return self._return_download_action()

    def _export_pdf(self, tasks):
        """Export report as PDF using wkhtmltopdf."""
        html = self._build_html_report(tasks)
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
            self.report_filename = (
                f'task_report_{self.date_from}_{self.date_to}.pdf')
        except FileNotFoundError:
            raise UserError(
                _('wkhtmltopdf is not installed. '
                  'Please install wkhtmltopdf package.'))
        except subprocess.TimeoutExpired:
            raise UserError(_('PDF generation timed out.'))
        return self._return_download_action()

    def _build_html_report(self, tasks):
        """Build an HTML table for the report."""
        Task = self.env['task.management.task']
        fget = Task.fields_get(['approval_status'])
        status_map = dict(fget['approval_status']['selection'])
        rows = ''
        total_hours = 0
        for task in tasks:
            status_color = {
                'pending': '#f0ad4e',
                'approved': '#5cb85c',
                'rejected': '#d9534f',
            }.get(task.approval_status, '#999')
            rows += f'''
            <tr>
                <td>{task.date}</td>
                <td>{task.project_id.name}</td>
                <td>{task.member_id.name}</td>
                <td>{task.description or ''}</td>
                <td>{self._float_to_time(task.time_from)}</td>
                <td>{self._float_to_time(task.time_to)}</td>
                <td>{task.duration_hours:.2f}</td>
                <td style="color: {status_color}; font-weight: bold;">
                    {status_map.get(task.approval_status, task.approval_status)}
                </td>
                <td>{'⚠' if task.is_late_entry else ''}</td>
            </tr>'''
            total_hours += task.duration_hours

        title = _('Task Report')
        if self.project_id:
            title += f' — {self.project_id.name}'
        if self.member_id:
            title += f' — {self.member_id.name}'

        is_rtl = self.env.lang and self.env.lang.startswith('ar')
        dir_attr = ' dir="rtl"' if is_rtl else ''
        th_align = 'right' if is_rtl else 'left'

        return f'''<!DOCTYPE html>
<html{dir_attr}>
<head>
<meta charset="utf-8"/>
<style>
    body {{ font-family: Arial, sans-serif; margin: 20px; }}
    h1 {{ color: #333; }}
    .meta {{ color: #666; margin-bottom: 20px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
    th {{ background-color: #0B3D91; color: white; padding: 10px; text-align: {th_align}; }}
    td {{ padding: 8px; border-bottom: 1px solid #ddd; }}
    tr:nth-child(even) {{ background-color: #f9f9f9; }}
    .total {{ font-weight: bold; margin-top: 15px; font-size: 16px; }}
</style>
</head>
<body>
    <h1>{title}</h1>
    <div class="meta">
        {_("Period:")} {self.date_from} {_("to")} {self.date_to} |
        {_("Total Tasks:")} {len(tasks)}
    </div>
    <table>
        <thead>
            <tr>
                <th>{_("Date")}</th><th>{_("Project")}</th><th>{_("Member")}</th>
                <th>{_("Description")}</th><th>{_("From")}</th><th>{_("To")}</th>
                <th>{_("Hours")}</th><th>{_("Status")}</th><th>{_("Late")}</th>
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    <div class="total">{_("Total Hours:")} {total_hours:.2f}</div>
</body>
</html>'''

    @staticmethod
    def _float_to_time(value):
        hours = int(value)
        minutes = int((value - hours) * 60)
        return f'{hours:02d}:{minutes:02d}'

    def _return_download_action(self):
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
