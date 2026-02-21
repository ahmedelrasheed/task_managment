from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from markupsafe import Markup


class TaskManagementProject(models.Model):
    _name = 'task.management.project'
    _description = 'Project'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(string='Project Name', required=True, tracking=True)
    description = fields.Text(string='Description')
    date_begin = fields.Date(string='Begin Date', tracking=True)
    expected_end_date = fields.Date(
        string='Expected End Date', tracking=True)
    status = fields.Selection([
        ('active', 'Active'),
        ('on_hold', 'On Hold'),
        ('completed', 'Completed'),
        ('archived', 'Archived'),
    ], string='Status', default='active', required=True, tracking=True)

    # Relations
    project_manager_ids = fields.Many2many(
        'task.management.member',
        'project_manager_rel',
        'project_id', 'member_id',
        string='Project Managers',
    )
    member_ids = fields.Many2many(
        'task.management.member',
        'project_member_rel',
        'project_id', 'member_id',
        string='Members',
    )
    removed_member_ids = fields.Many2many(
        'task.management.member',
        'project_removed_member_rel',
        'project_id', 'member_id',
        string='Removed Members',
    )
    task_ids = fields.One2many(
        'task.management.task', 'project_id',
        string='Tasks',
    )
    phase_ids = fields.One2many(
        'task.management.project.phase', 'project_id',
        string='Phases',
    )

    # Computed fields
    total_logged_hours = fields.Float(
        string='Total Logged Hours',
        compute='_compute_total_logged_hours',
        store=True,
    )
    progress_percentage = fields.Float(
        string='Progress (%)',
        compute='_compute_progress_percentage',
    )
    task_count = fields.Integer(
        string='Task Count',
        compute='_compute_task_stats',
    )
    pending_task_count = fields.Integer(
        string='Pending Tasks',
        compute='_compute_task_stats',
    )

    @api.depends('task_ids.duration_hours', 'task_ids.approval_status')
    def _compute_total_logged_hours(self):
        for project in self:
            approved_tasks = project.task_ids.filtered(
                lambda t: t.approval_status == 'approved')
            project.total_logged_hours = sum(
                approved_tasks.mapped('duration_hours'))

    @api.depends('phase_ids.percentage', 'phase_ids.completion_rate')
    def _compute_progress_percentage(self):
        for project in self:
            if project.phase_ids:
                project.progress_percentage = sum(
                    phase.percentage * phase.completion_rate / 100.0
                    for phase in project.phase_ids
                )
            else:
                project.progress_percentage = 0.0

    @api.depends('task_ids', 'task_ids.approval_status')
    def _compute_task_stats(self):
        for project in self:
            project.task_count = len(project.task_ids)
            project.pending_task_count = len(
                project.task_ids.filtered(
                    lambda t: t.approval_status == 'pending'))

    @api.constrains('project_manager_ids', 'member_ids')
    def _check_pm_not_member(self):
        for project in self:
            overlap = project.project_manager_ids & project.member_ids
            if overlap:
                names = ', '.join(overlap.mapped('name'))
                raise ValidationError(
                    _('A Project Manager cannot also be a member of the '
                      'same project: %s') % names)

    @api.constrains('phase_ids')
    def _check_phase_percentage_sum(self):
        for project in self:
            if project.phase_ids:
                total = sum(project.phase_ids.mapped('percentage'))
                if abs(total - 100.0) > 0.01:
                    raise ValidationError(
                        _('Phase weights must sum to 100%%. '
                          'Current total: %.2f%%') % total)

    @api.constrains('project_manager_ids')
    def _check_at_least_one_pm(self):
        for project in self:
            if not project.project_manager_ids:
                raise ValidationError(
                    _('A project must have at least one Project Manager.'))

    def write(self, vals):
        # Track removed members
        if 'member_ids' in vals:
            for project in self:
                old_members = project.member_ids
                result = super(TaskManagementProject, project).write(vals)
                new_members = project.member_ids
                removed = old_members - new_members
                if removed:
                    # Add to removed_member_ids without triggering recursion
                    existing_removed = project.removed_member_ids
                    all_removed = existing_removed | removed
                    super(TaskManagementProject, project).write({
                        'removed_member_ids': [(6, 0, all_removed.ids)],
                    })
            return True
        return super().write(vals)

    @api.model
    def _name_search(self, name='', domain=None, operator='ilike',
                     limit=100, order=None):
        """Restrict project dropdown in task form: PMs and members only
        see projects where they are a regular member."""
        domain = domain or []
        if self.env.context.get('restrict_to_member_projects'):
            is_admin = self.env.user.has_group(
                'task_project_management.group_admin_manager')
            if not is_admin:
                domain = domain + [
                    ('member_ids.user_id', '=', self.env.uid)]
        return super()._name_search(
            name, domain, operator, limit, order)

    @api.model
    def web_search_read(self, domain, specification, offset=0, limit=None,
                        order=None, count_limit=None):
        """Also restrict the dropdown list/search dialog."""
        if self.env.context.get('restrict_to_member_projects'):
            is_admin = self.env.user.has_group(
                'task_project_management.group_admin_manager')
            if not is_admin:
                domain = domain + [
                    ('member_ids.user_id', '=', self.env.uid)]
        return super().web_search_read(
            domain, specification, offset=offset, limit=limit,
            order=order, count_limit=count_limit)

    @api.model
    def _cron_check_project_deadlines(self):
        """Check for projects that have reached their expected end date
        with pending tasks. Notify PM and Admin."""
        today = fields.Date.context_today(self)
        projects = self.search([
            ('status', '=', 'active'),
            ('expected_end_date', '<=', today),
        ])
        for project in projects:
            pending_count = project.pending_task_count
            if pending_count > 0:
                # Notify PMs
                pm_partners = project.project_manager_ids.mapped(
                    'user_id.partner_id')
                # Notify admins
                admin_group = self.env.ref(
                    'task_project_management.group_admin_manager')
                admin_partners = admin_group.users.mapped('partner_id')
                all_partners = pm_partners | admin_partners
                if all_partners:
                    try:
                        body = Markup(
                            '<p>Project <strong>"%s"</strong> has reached '
                            'its expected end date (%s) with %s pending '
                            'task(s).</p>'
                        ) % (
                            project.name or '',
                            project.expected_end_date or '',
                            pending_count,
                        )
                        project.sudo().message_post(
                            body=body,
                            partner_ids=all_partners.ids,
                            message_type='notification',
                            subtype_xmlid='mail.mt_note',
                        )
                    except Exception:
                        pass
