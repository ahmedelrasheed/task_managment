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
        ('waiting', 'Waiting'),
        ('active', 'Active'),
        ('on_hold', 'On Hold'),
        ('completed', 'Completed'),
        ('archived', 'Archived'),
    ], string='Status', default='waiting', required=True, tracking=True)

    # Relations
    project_manager_ids = fields.Many2many(
        'task.management.member',
        'project_manager_rel',
        'project_id', 'member_id',
        string='Project Managers',
        domain=lambda self: [
            ('user_id.groups_id', 'in',
             [self.env.ref('task_project_management.group_project_manager').id])
        ],
    )
    member_ids = fields.Many2many(
        'task.management.member',
        'project_member_rel',
        'project_id', 'member_id',
        string='Members',
        domain=[('role', '!=', 'manager')],
    )
    task_ids = fields.One2many(
        'task.management.task', 'project_id',
        string='Tasks',
    )
    phase_ids = fields.One2many(
        'task.management.project.phase', 'project_id',
        string='Phases',
    )
    manager_ids = fields.Many2many(
        'task.management.member',
        'project_oversight_manager_rel',
        'project_id', 'member_id',
        string='Oversight Managers',
        domain=[('role', '=', 'manager')],
    )

    # Role flag for view readonly control
    is_admin_user = fields.Boolean(
        compute='_compute_is_admin_user',
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
    assigned_pending_task_count = fields.Integer(
        string='Assigned Pending',
        compute='_compute_task_stats',
    )
    approved_task_count = fields.Integer(
        string='Approved Tasks',
        compute='_compute_task_stats',
    )
    assigned_approved_task_count = fields.Integer(
        string='Assigned Approved',
        compute='_compute_task_stats',
    )
    rejected_task_count = fields.Integer(
        string='Rejected Tasks',
        compute='_compute_task_stats',
    )
    assigned_rejected_task_count = fields.Integer(
        string='Assigned Rejected',
        compute='_compute_task_stats',
    )

    def _compute_is_admin_user(self):
        is_admin = self.env.user.has_group(
            'task_project_management.group_admin_manager')
        for rec in self:
            rec.is_admin_user = is_admin

    @api.depends('task_ids.duration_hours', 'task_ids.approval_status')
    def _compute_total_logged_hours(self):
        for project in self:
            approved_tasks = project.task_ids.filtered(
                lambda t: t.approval_status in (
                    'approved', 'assigned_approved'))
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
            tasks = project.task_ids
            project.task_count = len(tasks)
            project.pending_task_count = len(
                tasks.filtered(lambda t: t.approval_status == 'pending'))
            project.assigned_pending_task_count = len(
                tasks.filtered(lambda t: t.approval_status == 'assigned_pending'))
            project.approved_task_count = len(
                tasks.filtered(lambda t: t.approval_status == 'approved'))
            project.assigned_approved_task_count = len(
                tasks.filtered(lambda t: t.approval_status == 'assigned_approved'))
            project.rejected_task_count = len(
                tasks.filtered(lambda t: t.approval_status == 'rejected'))
            project.assigned_rejected_task_count = len(
                tasks.filtered(lambda t: t.approval_status == 'assigned_rejected'))

    @api.model_create_multi
    def create(self, vals_list):
        projects = super().create(vals_list)
        # Auto-add managers with supervise_all_projects=True
        global_managers = self.env['task.management.member'].sudo().search([
            ('role', '=', 'manager'),
            ('supervise_all_projects', '=', True),
        ])
        if global_managers:
            for project in projects:
                project.sudo().write({
                    'manager_ids': [(4, m.id) for m in global_managers],
                })
        return projects

    @api.constrains('project_manager_ids', 'member_ids')
    def _check_pm_not_member(self):
        for project in self:
            overlap = project.project_manager_ids & project.member_ids
            if overlap:
                names = ', '.join(overlap.mapped('name'))
                raise ValidationError(
                    _('A Project Manager cannot also be a member of the '
                      'same project: %s') % names)

    @api.constrains('member_ids')
    def _check_no_manager_as_member(self):
        for project in self:
            managers = project.member_ids.filtered(
                lambda m: m.role == 'manager')
            if managers:
                names = ', '.join(managers.mapped('name'))
                raise ValidationError(
                    _('A Manager (oversight role) cannot be added as a '
                      'project member: %s') % names)

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
    def _check_exactly_one_pm(self):
        for project in self:
            if not project.project_manager_ids:
                raise ValidationError(
                    _('A project must have a Project Manager.'))
            if len(project.project_manager_ids) > 1:
                raise ValidationError(
                    _('A project can only have one Project Manager.'))

    @api.constrains('date_begin', 'expected_end_date')
    def _check_dates(self):
        for project in self:
            if project.date_begin and project.expected_end_date:
                if project.date_begin > project.expected_end_date:
                    raise ValidationError(
                        _('Begin Date cannot be after Expected End Date.'))

    @api.onchange('member_ids')
    def _onchange_member_ids_warn(self):
        if not self._origin.id:
            return
        old_ids = set(self._origin.member_ids.ids)
        new_ids = set(self.member_ids.ids)
        removed_ids = old_ids - new_ids
        if removed_ids:
            removed = self.env['task.management.member'].browse(removed_ids)
            names = ', '.join(removed.mapped('name'))
            return {'warning': {
                'title': _('Member Removed'),
                'message': _('You are about to remove member(s): %s '
                             'from project "%s". '
                             'Please save to confirm.') % (names, self.name),
            }}

    @api.onchange('phase_ids')
    def _onchange_phase_ids_warn(self):
        if not self._origin.id:
            return
        old_ids = set(self._origin.phase_ids.ids)
        new_ids = set(rec.id for rec in self.phase_ids if rec.id)
        removed_ids = old_ids - new_ids
        if removed_ids:
            removed = self.env['task.management.project.phase'].browse(removed_ids)
            names = ', '.join(removed.mapped('name'))
            return {'warning': {
                'title': _('Phase Removed'),
                'message': _('You are about to remove phase(s): %s '
                             'from project "%s". '
                             'Please save to confirm.') % (names, self.name),
            }}

    @api.onchange('project_manager_ids')
    def _onchange_pm_ids_warn(self):
        if not self._origin.id:
            return
        old_ids = set(self._origin.project_manager_ids.ids)
        new_ids = set(self.project_manager_ids.ids)
        removed_ids = old_ids - new_ids
        if removed_ids:
            removed = self.env['task.management.member'].browse(removed_ids)
            names = ', '.join(removed.mapped('name'))
            return {'warning': {
                'title': _('Project Manager Removed'),
                'message': _('You are about to remove Project Manager(s): %s '
                             'from project "%s". '
                             'Please save to confirm.') % (names, self.name),
            }}

    def write(self, vals):
        for project in self:
            # Track removed members
            if 'member_ids' in vals:
                old_members = project.member_ids
                result = super(TaskManagementProject, project).write(vals)
                removed_members = old_members - project.member_ids
                if removed_members:
                    self._notify_member_removed(project, removed_members)
                return result

            # Track deleted phases
            if 'phase_ids' in vals:
                old_phases = project.phase_ids
                old_phase_names = {p.id: p.name for p in old_phases}

        result = super().write(vals)

        if 'phase_ids' in vals:
            for project in self:
                current_phase_ids = set(project.phase_ids.ids)
                removed_phase_names = [
                    name for pid, name in old_phase_names.items()
                    if pid not in current_phase_ids
                ]
                if removed_phase_names:
                    self._notify_phase_removed(project, removed_phase_names)

        return result

    def _notify_member_removed(self, project, removed_members):
        """Notify PMs and the removed member when a member is removed."""
        try:
            pm_partners = project.sudo().project_manager_ids.mapped(
                'user_id.partner_id')
            removed_partners = removed_members.mapped('user_id.partner_id')
            all_partners = pm_partners | removed_partners
            if all_partners:
                names = ', '.join(removed_members.mapped('name'))
                body = Markup(
                    '<p>Member(s) <strong>%s</strong> removed from '
                    'project <strong>%s</strong>.</p>'
                ) % (names, project.name)
                project.sudo().message_post(
                    body=body,
                    partner_ids=all_partners.ids,
                    message_type='notification',
                    subtype_xmlid='mail.mt_note',
                )
        except Exception:
            pass

    def _notify_phase_removed(self, project, phase_names):
        """Notify PMs when a phase is removed from a project."""
        try:
            pm_partners = project.sudo().project_manager_ids.mapped(
                'user_id.partner_id')
            if pm_partners:
                names = ', '.join(phase_names)
                body = Markup(
                    '<p>Phase(s) <strong>%s</strong> removed from '
                    'project <strong>%s</strong>.</p>'
                ) % (names, project.name)
                project.sudo().message_post(
                    body=body,
                    partner_ids=pm_partners.ids,
                    message_type='notification',
                    subtype_xmlid='mail.mt_note',
                )
        except Exception:
            pass

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
            pending_count = (project.pending_task_count +
                            project.assigned_pending_task_count)
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
