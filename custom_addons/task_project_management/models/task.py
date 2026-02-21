from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from markupsafe import Markup
from datetime import timedelta, date


class TaskManagementTask(models.Model):
    _name = 'task.management.task'
    _description = 'Daily Task Entry'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    date = fields.Date(
        string='Date', required=True,
        default=fields.Date.context_today, tracking=True,
    )
    description = fields.Text(string='Task Description', required=True)
    project_id = fields.Many2one(
        'task.management.project', string='Project',
        required=True, ondelete='restrict',
        domain="[('status', 'in', ['waiting', 'active'])]",
        tracking=True,
    )
    member_id = fields.Many2one(
        'task.management.member', string='Member',
        required=True, ondelete='restrict',
        default=lambda self: self.env['task.management.member'].sudo()._get_member_for_user(),
        tracking=True,
    )
    time_from = fields.Float(string='Time From', required=True)
    time_to = fields.Float(string='Time To', required=True)
    duration_hours = fields.Float(
        string='Duration (Hours)',
        compute='_compute_duration_hours',
        store=True,
    )
    approval_status = fields.Selection([
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='Approval Status', default='pending',
        required=True, tracking=True,
    )
    manager_comment = fields.Text(string='Manager Comment', tracking=True)
    attachment_ids = fields.Many2many(
        'ir.attachment', 'task_attachment_rel',
        'task_id', 'attachment_id',
        string='Attachments',
    )
    entry_timestamp = fields.Datetime(
        string='Entry Timestamp',
        default=fields.Datetime.now, readonly=True,
    )
    is_late_entry = fields.Boolean(
        string='Late Entry',
        compute='_compute_is_late_entry',
        store=True,
    )
    late_days = fields.Integer(
        string='Days Late',
        compute='_compute_is_late_entry',
        store=True,
    )
    audit_ids = fields.One2many(
        'task.management.task.audit', 'task_id',
        string='Audit Trail',
    )
    is_current_user_pm = fields.Boolean(
        compute='_compute_is_current_user_pm',
    )

    @api.depends_context('uid')
    def _compute_is_current_user_pm(self):
        is_pm = self.env.user.has_group(
            'task_project_management.group_project_manager') or \
            self.env.user.has_group(
            'task_project_management.group_admin_manager')
        for task in self:
            task.is_current_user_pm = is_pm

    @api.onchange('member_id')
    def _onchange_member_id_project_domain(self):
        """Restrict project dropdown: admins see all active projects,
        PMs and members see only projects they are a member of."""
        is_admin = self.env.user.has_group(
            'task_project_management.group_admin_manager')
        if is_admin:
            return {'domain': {'project_id': [('status', 'in', ['waiting', 'active'])]}}
        if self.member_id:
            return {'domain': {'project_id': [
                ('status', 'in', ['waiting', 'active']),
                ('member_ids', '=', self.member_id.id),
            ]}}
        return {'domain': {'project_id': [
            ('status', 'in', ['waiting', 'active']),
            ('member_ids.user_id', '=', self.env.uid),
        ]}}

    @api.depends('time_from', 'time_to')
    def _compute_duration_hours(self):
        for task in self:
            allow_after_midnight = self.env[
                'ir.config_parameter'].sudo().get_param(
                'task_project_management.allow_after_midnight', 'False')
            if allow_after_midnight == 'True' and task.time_to < task.time_from:
                # Cross-midnight: e.g., 23:00 to 01:00 = 2 hours
                task.duration_hours = (24.0 - task.time_from) + task.time_to
            else:
                task.duration_hours = task.time_to - task.time_from

    @api.depends('date', 'entry_timestamp')
    def _compute_is_late_entry(self):
        for task in self:
            if task.date and task.entry_timestamp:
                entry_date = fields.Date.to_date(
                    task.entry_timestamp.date() if task.entry_timestamp
                    else fields.Date.context_today(self))
                task_date = task.date
                diff = (entry_date - task_date).days
                task.is_late_entry = diff > 0
                task.late_days = max(diff, 0)
            else:
                task.is_late_entry = False
                task.late_days = 0

    # --- Constraints ---

    @api.constrains('time_from', 'time_to')
    def _check_time_validity(self):
        allow_after_midnight = self.env[
            'ir.config_parameter'].sudo().get_param(
            'task_project_management.allow_after_midnight', 'False')
        for task in self:
            if task.time_from < 0 or task.time_to < 0:
                raise ValidationError(
                    _('Time values cannot be negative.'))
            if task.time_from >= 24 or task.time_to >= 24:
                raise ValidationError(
                    _('Time values must be less than 24:00.'))
            if allow_after_midnight != 'True':
                if task.time_to <= task.time_from:
                    raise ValidationError(
                        _('Time To must be after Time From. '
                          'After-midnight tasks are disabled.'))
            else:
                # Even with after-midnight enabled, 0 duration is invalid
                if task.time_to == task.time_from:
                    raise ValidationError(
                        _('Time From and Time To cannot be the same.'))

    @api.constrains('date', 'member_id', 'time_from', 'time_to')
    def _check_time_overlap(self):
        """Check for overlapping time entries per member per day
        across all projects."""
        allow_after_midnight = self.env[
            'ir.config_parameter'].sudo().get_param(
            'task_project_management.allow_after_midnight', 'False')
        for task in self:
            domain = [
                ('member_id', '=', task.member_id.id),
                ('date', '=', task.date),
                ('id', '!=', task.id),
            ]
            existing_tasks = self.search(domain)
            for existing in existing_tasks:
                if self._times_overlap(
                    task.time_from, task.time_to,
                    existing.time_from, existing.time_to,
                    allow_after_midnight == 'True',
                ):
                    raise ValidationError(
                        _('Time overlap detected! You already have a task '
                          'from %(from)s to %(to)s on %(date)s.',
                          **{
                              'from': self._float_to_time_str(
                                  existing.time_from),
                              'to': self._float_to_time_str(
                                  existing.time_to),
                              'date': task.date,
                          }))

    @staticmethod
    def _times_overlap(from1, to1, from2, to2, allow_midnight):
        """Check if two time ranges overlap. Handles cross-midnight."""
        def get_segments(t_from, t_to, midnight):
            if midnight and t_to < t_from:
                # Cross-midnight: split into two segments
                return [(t_from, 24.0), (0.0, t_to)]
            return [(t_from, t_to)]

        segs1 = get_segments(from1, to1, allow_midnight)
        segs2 = get_segments(from2, to2, allow_midnight)

        for s1_from, s1_to in segs1:
            for s2_from, s2_to in segs2:
                if s1_from < s2_to and s2_from < s1_to:
                    return True
        return False

    @staticmethod
    def _float_to_time_str(value):
        """Convert float time to HH:MM string."""
        hours = int(value)
        minutes = int((value - hours) * 60)
        return f'{hours:02d}:{minutes:02d}'

    @api.constrains('date')
    def _check_past_date_limit(self):
        """Members can only enter tasks within the configured past date
        limit. PMs and Admins can enter for any past date."""
        is_pm_or_admin = self.env.user.has_group(
            'task_project_management.group_project_manager') or \
            self.env.user.has_group(
            'task_project_management.group_admin_manager')
        if is_pm_or_admin:
            return
        limit_days = int(self.env['ir.config_parameter'].sudo().get_param(
            'task_project_management.past_date_limit', '7'))
        today = fields.Date.context_today(self)
        min_date = today - timedelta(days=limit_days)
        for task in self:
            if task.date < min_date:
                raise ValidationError(
                    _('You can only enter tasks up to %(days)s days '
                      'in the past. Contact your PM or Admin.',
                      days=limit_days))
            if task.date > today:
                raise ValidationError(
                    _('You cannot enter tasks for future dates.'))

    @api.constrains('member_id', 'project_id')
    def _check_member_in_project(self):
        """Ensure the member is assigned to the project.
        PMs can only add tasks for themselves in projects where they
        are a regular member (not PM). PMs can add tasks on behalf of
        members in their managed projects.
        Admins can enter tasks for any member in any project."""
        for task in self:
            project = task.sudo().project_id
            # Admin can always bypass
            is_admin = self.env.user.has_group(
                'task_project_management.group_admin_manager')
            if is_admin:
                continue
            is_pm = self.env.user.has_group(
                'task_project_management.group_project_manager')
            if is_pm:
                current_member = self.env[
                    'task.management.member'].sudo()._get_member_for_user()
                is_manager_of_project = (
                    current_member in project.project_manager_ids)
                # PM adding task for themselves
                if task.member_id == current_member:
                    if is_manager_of_project:
                        raise ValidationError(
                            _('As a Project Manager of "%(project)s", '
                              'you cannot add tasks for yourself here. '
                              'Add tasks in projects where you are a '
                              'regular member.',
                              project=project.name))
                    # PM is a regular member of this project
                    if task.member_id in project.member_ids:
                        continue
                    raise ValidationError(
                        _('You are not assigned as a member of '
                          'project "%(project)s".',
                          project=project.name))
                # PM adding task on behalf of another member
                if is_manager_of_project:
                    if task.member_id in project.member_ids:
                        continue
                    raise ValidationError(
                        _('Member "%(member)s" is not assigned to '
                          'project "%(project)s".',
                          member=task.member_id.name,
                          project=project.name))
                # PM is not manager of this project
                raise ValidationError(
                    _('You can only add tasks on behalf of members '
                      'in projects you manage.'))
            # Regular member: must be in project
            if task.member_id in project.member_ids:
                continue
            raise ValidationError(
                _('Member "%(member)s" is not assigned to '
                  'project "%(project)s".',
                  member=task.member_id.name,
                  project=project.name))

    @api.constrains('project_id')
    def _check_project_status(self):
        """Ensure the project allows task submission."""
        for task in self:
            status = task.project_id.status
            if status == 'on_hold':
                raise ValidationError(
                    _('This project is currently on hold. '
                      'You cannot submit new tasks.'))
            if status == 'completed':
                # Only admin can submit to completed projects
                is_admin = self.env.user.has_group(
                    'task_project_management.group_admin_manager')
                if not is_admin:
                    raise ValidationError(
                        _('This project is completed. '
                          'Only Admin can submit tasks.'))
            if status == 'archived':
                raise ValidationError(
                    _('This project is archived. No tasks can be submitted.'))

    # --- CRUD Overrides ---

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Auto-set member from current user if not provided
            if not vals.get('member_id'):
                member = self.env['task.management.member']._get_member_for_user()
                if member:
                    vals['member_id'] = member.id
            # Set entry timestamp
            vals['entry_timestamp'] = fields.Datetime.now()
        records = super().create(vals_list)
        for record in records:
            # Auto-activate project on first task submission
            if record.project_id.status == 'waiting':
                record.project_id.sudo().write({'status': 'active'})
            # Create initial audit entry
            record._create_audit_entry(False, 'pending', _('Task created'))
            # Validate attachments
            record._validate_attachment_size()
            # Notify PM
            record._notify_pm_on_submit()
        return records

    def write(self, vals):
        # Capture old statuses BEFORE any write happens
        old_statuses = {task.id: task.approval_status for task in self}

        for task in self:
            # Block editing of approved tasks (except status/comment changes)
            if task.approval_status == 'approved':
                allowed_fields = {
                    'approval_status', 'manager_comment',
                    'message_follower_ids', 'message_ids',
                }
                if not set(vals.keys()).issubset(allowed_fields):
                    raise UserError(
                        _('Cannot edit an approved task.'))

            # If editing a rejected task (non-status fields), reset to pending
            if task.approval_status == 'rejected':
                if 'approval_status' not in vals:
                    non_status_fields = set(vals.keys()) - {
                        'approval_status', 'manager_comment',
                        'message_follower_ids', 'message_ids',
                    }
                    if non_status_fields:
                        vals = dict(vals, approval_status='pending')

        result = super().write(vals)

        # Handle approval status changes
        if 'approval_status' in vals:
            new_status = vals['approval_status']
            for task in self:
                old_status = old_statuses.get(task.id, 'pending')
                comment = vals.get('manager_comment', '')
                task._create_audit_entry(old_status, new_status, comment)
                if new_status in ('approved', 'rejected'):
                    task._notify_member_status_change(new_status)
                elif new_status == 'pending' and old_status == 'rejected':
                    # Resubmission after rejection: notify PM
                    task._notify_pm_on_submit()

        # Validate attachment sizes if attachments changed
        if 'attachment_ids' in vals:
            for task in self:
                task._validate_attachment_size()

        return result

    def unlink(self):
        raise UserError(_('Tasks cannot be deleted. You can only edit them.'))

    # --- Actions ---

    def action_approve(self):
        self._check_can_approve()
        self.write({
            'approval_status': 'approved',
        })

    def action_reject(self):
        self._check_can_approve()
        self.write({
            'approval_status': 'rejected',
        })

    def _check_can_approve(self):
        """Check that the current user can approve/reject tasks."""
        is_admin = self.env.user.has_group(
            'task_project_management.group_admin_manager')
        if is_admin:
            return
        current_user = self.env.user
        member = self.env['task.management.member'].sudo(
            )._get_member_for_user(current_user)
        for task in self:
            if member and member == task.member_id:
                raise UserError(
                    _('You cannot approve or reject your own tasks.'))
            # Use sudo to bypass record rules when checking PM membership
            if member not in task.sudo().project_id.project_manager_ids:
                raise UserError(
                    _('Only Project Managers of this project '
                      'or Admins can approve tasks.'))

    def _create_audit_entry(self, old_status, new_status, comment=''):
        self.env['task.management.task.audit'].sudo().create({
            'task_id': self.id,
            'old_status': old_status or False,
            'new_status': new_status,
            'changed_by': self.env.uid,
            'comment': comment,
        })

    def _validate_attachment_size(self):
        """Validate that no attachment exceeds the configured max size."""
        max_mb = int(self.env['ir.config_parameter'].sudo().get_param(
            'task_project_management.max_attachment_size', '100'))
        max_bytes = max_mb * 1024 * 1024
        for attachment in self.attachment_ids:
            if attachment.file_size and attachment.file_size > max_bytes:
                raise ValidationError(
                    _('File "%(name)s" exceeds maximum size of %(size)s MB.',
                      name=attachment.name, size=max_mb))

    def _notify_pm_on_submit(self):
        """Notify project managers when a member submits a task."""
        try:
            pm_partners = self.sudo().project_id.project_manager_ids.mapped(
                'user_id.partner_id')
            if pm_partners:
                body = Markup(
                    '<p>New task submitted by <strong>%s</strong> '
                    'for project <strong>%s</strong> on %s.</p>'
                ) % (
                    self.member_id.name or '',
                    self.project_id.name or '',
                    self.date or '',
                )
                self.sudo().message_post(
                    body=body,
                    partner_ids=pm_partners.ids,
                    message_type='notification',
                    subtype_xmlid='mail.mt_note',
                )
        except Exception:
            pass

    def _notify_member_status_change(self, new_status):
        """Notify the member when their task status changes."""
        try:
            member_partner = self.sudo().member_id.user_id.partner_id
            if member_partner:
                status_labels = {
                    'approved': 'Approved',
                    'rejected': 'Rejected',
                    'pending': 'Pending',
                }
                status_text = status_labels.get(new_status, new_status)
                desc = (self.description or '')[:50]
                body = Markup(
                    '<p>Your task <strong>"%s"</strong> has been '
                    '<strong>%s</strong>.</p>'
                ) % (desc, status_text)
                if self.manager_comment:
                    body += Markup(
                        '<p>Comment: %s</p>'
                    ) % self.manager_comment
                self.sudo().message_post(
                    body=body,
                    partner_ids=[member_partner.id],
                    message_type='notification',
                    subtype_xmlid='mail.mt_note',
                )
        except Exception:
            pass

    # --- Dashboard Data Methods ---

    @api.model
    def get_member_dashboard_data(self):
        """Return dashboard data for the current member."""
        member = self.env['task.management.member'].sudo().search(
            [('user_id', '=', self.env.uid)], limit=1)
        if not member:
            return {
                'totalTasks': 0, 'pendingTasks': 0,
                'approvedTasks': 0, 'rejectedTasks': 0,
                'hoursToday': '0.00', 'hoursWeek': '0.00',
                'hoursMonth': '0.00',
                'dailyTarget': '8.00', 'weeklyTarget': '40.00',
                'dailyPerformance': 0, 'weeklyPerformance': 0,
                'recentTasks': [],
            }
        tasks = self.sudo().search([('member_id', '=', member.id)])
        today = fields.Date.context_today(self)
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)

        hours_today = sum(tasks.filtered(
            lambda t: t.date == today).mapped('duration_hours'))
        hours_week = sum(tasks.filtered(
            lambda t: t.date and t.date >= week_start).mapped('duration_hours'))
        hours_month = sum(tasks.filtered(
            lambda t: t.date and t.date >= month_start).mapped('duration_hours'))

        recent = tasks[:10]
        recent_data = [{
            'id': t.id,
            'date': str(t.date),
            'project': t.project_id.name,
            'description': (t.description or '')[:60],
            'hours': f'{t.duration_hours:.2f}',
            'status': t.approval_status,
        } for t in recent]

        # Performance vs targets
        daily_target = float(
            self.env['ir.config_parameter'].sudo().get_param(
                'task_project_management.daily_hours_average', '8.0'))
        weekly_target = float(
            self.env['ir.config_parameter'].sudo().get_param(
                'task_project_management.weekly_hours_average', '40.0'))
        daily_perf = round(
            (hours_today / daily_target * 100) if daily_target else 0, 1)
        weekly_perf = round(
            (hours_week / weekly_target * 100) if weekly_target else 0, 1)

        return {
            'totalTasks': len(tasks),
            'pendingTasks': len(tasks.filtered(
                lambda t: t.approval_status == 'pending')),
            'approvedTasks': len(tasks.filtered(
                lambda t: t.approval_status == 'approved')),
            'rejectedTasks': len(tasks.filtered(
                lambda t: t.approval_status == 'rejected')),
            'hoursToday': f'{hours_today:.2f}',
            'hoursWeek': f'{hours_week:.2f}',
            'hoursMonth': f'{hours_month:.2f}',
            'dailyTarget': f'{daily_target:.2f}',
            'weeklyTarget': f'{weekly_target:.2f}',
            'dailyPerformance': daily_perf,
            'weeklyPerformance': weekly_perf,
            'recentTasks': recent_data,
        }

    @api.model
    def get_pm_dashboard_data(self):
        """Return dashboard data for PM's managed projects."""
        Project = self.env['task.management.project'].sudo()
        member = self.env['task.management.member'].sudo().search(
            [('user_id', '=', self.env.uid)], limit=1)

        # Admin sees all non-archived projects even if not a PM
        is_admin = self.env.user.has_group(
            'task_project_management.group_admin_manager')

        if is_admin:
            projects = Project.search([
                ('status', '!=', 'archived'),
            ])
        elif member:
            projects = Project.search([
                ('project_manager_ids', 'in', [member.id]),
                ('status', '!=', 'archived'),
            ])
        else:
            return {'projects': []}

        result = []
        for proj in projects:
            members_data = []
            for m in proj.member_ids:
                m_tasks = proj.task_ids.filtered(
                    lambda t, member=m: t.member_id == member)
                approved = len(m_tasks.filtered(
                    lambda t: t.approval_status == 'approved'))
                total = len(m_tasks)
                rate = round((approved / total * 100) if total else 0, 1)
                late = len(m_tasks.filtered(lambda t: t.is_late_entry))
                members_data.append({
                    'id': m.id,
                    'name': m.name,
                    'task_count': total,
                    'hours': f'{sum(m_tasks.mapped("duration_hours")):.2f}',
                    'approval_rate': rate,
                    'late_entries': late,
                })
            phases_data = [{
                'id': phase.id,
                'name': phase.name,
                'percentage': phase.percentage,
                'completion_rate': phase.completion_rate,
                'effective_progress': round(phase.effective_progress, 1),
            } for phase in proj.phase_ids]

            result.append({
                'id': proj.id,
                'name': proj.name,
                'status': proj.status,
                'logged_hours': f'{proj.total_logged_hours:.2f}',
                'progress': round(proj.progress_percentage, 1),
                'pending_tasks': proj.pending_task_count,
                'members': members_data,
                'phases': phases_data,
            })
        return {'projects': result}

    @api.model
    def get_admin_dashboard_data(self):
        """Return organization-wide dashboard data for Admin."""
        Project = self.env['task.management.project'].sudo()
        Member = self.env['task.management.member'].sudo()

        projects = Project.search([])
        all_tasks = self.sudo().search([])

        projects_data = []
        total_late = 0
        for proj in projects:
            late = len(proj.task_ids.filtered(lambda t: t.is_late_entry))
            total_late += late
            projects_data.append({
                'id': proj.id,
                'name': proj.name,
                'status': proj.status,
                'progress': round(proj.progress_percentage, 1),
                'task_count': proj.task_count,
                'pending_tasks': proj.pending_task_count,
                'member_count': len(proj.member_ids),
                'late_entries': late,
            })

        return {
            'totalProjects': len(projects),
            'totalMembers': Member.search_count([]),
            'totalHours': f'{sum(all_tasks.mapped("duration_hours")):.2f}',
            'totalLateEntries': total_late,
            'projects': projects_data,
        }
