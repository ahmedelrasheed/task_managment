import base64
import csv
import io
import subprocess
import tempfile

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
        string='Date',
        default=fields.Date.context_today, tracking=True,
    )
    description = fields.Text(string='Task Description')
    project_id = fields.Many2one(
        'task.management.project', string='Project',
        required=True, ondelete='restrict',
        domain="[('status', 'in', ['waiting', 'active'])]",
        tracking=True,
    )
    phase_id = fields.Many2one(
        'task.management.project.phase', string='Phase',
        ondelete='set null',
        domain="[('project_id', '=', project_id), ('is_active', '=', True), ('completion_rate', '<', 100)]",
    )
    member_id = fields.Many2one(
        'task.management.member', string='Member',
        required=True, ondelete='restrict',
        default=lambda self: self.env['task.management.member'].sudo()._get_member_for_user(),
        tracking=True,
    )
    time_from = fields.Float(string='Time From')
    time_to = fields.Float(string='Time To')
    duration_hours = fields.Float(
        string='Duration (Hours)',
        compute='_compute_duration_hours',
        store=True,
    )
    approval_status = fields.Selection([
        ('assigned', 'Assigned'),
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='Approval Status', default='pending', required=True, tracking=True)
    task_type = fields.Selection([
        ('initiated', 'Initiated'),
        ('assigned', 'Assigned'),
    ], string='Task Type', default='initiated', required=True, readonly=True)
    is_seen_by_member = fields.Boolean(default=False)
    is_seen_by_pm = fields.Boolean(default=False)
    manager_comment = fields.Text(string='Manager Comment', tracking=True)
    attachment_ids = fields.Many2many(
        'ir.attachment', 'task_attachment_rel',
        'task_id', 'attachment_id',
        string='Attachments',
    )

    # --- Assignment Fields ---
    assignment_name = fields.Char(string='Task Name', tracking=True)
    due_date = fields.Date(string='Due Date', tracking=True)
    assigned_by_id = fields.Many2one(
        'task.management.member', string='Assigned By',
        readonly=True, ondelete='set null',
    )
    assignment_description = fields.Text(string='Assignment Instructions')
    assignment_attachment_ids = fields.Many2many(
        'ir.attachment', 'task_assignment_attachment_rel',
        'task_id', 'attachment_id',
        string='Reference Files',
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
    is_current_user_project_pm = fields.Boolean(
        compute='_compute_is_current_user_project_pm',
    )
    can_assign = fields.Boolean(
        compute='_compute_can_assign',
    )
    is_current_user_member = fields.Boolean(
        compute='_compute_is_current_user_member',
    )
    project_member_ids = fields.Many2many(
        'task.management.member',
        compute='_compute_project_member_ids',
    )

    @api.depends_context('uid')
    def _compute_is_current_user_pm(self):
        is_pm = self.env.user.has_group(
            'task_project_management.group_project_manager') or \
            self.env.user.has_group(
            'task_project_management.group_admin_manager')
        for task in self:
            task.is_current_user_pm = is_pm

    @api.depends('project_id')
    @api.depends_context('uid')
    def _compute_is_current_user_project_pm(self):
        """Check if current user is PM of the task's project (or is admin)."""
        is_admin = self.env.user.has_group(
            'task_project_management.group_admin_manager')
        for task in self:
            if is_admin:
                task.is_current_user_project_pm = True
            elif task.project_id:
                task.is_current_user_project_pm = self.env.uid in \
                    task.project_id.project_manager_ids.mapped('user_id.id')
            else:
                task.is_current_user_project_pm = False

    @api.depends_context('uid')
    def _compute_can_assign(self):
        """PMs and Admins can assign tasks."""
        is_pm = self.env.user.has_group(
            'task_project_management.group_project_manager')
        is_admin = self.env.user.has_group(
            'task_project_management.group_admin_manager')
        for task in self:
            task.can_assign = is_pm or is_admin

    @api.depends('member_id')
    @api.depends_context('uid')
    def _compute_is_current_user_member(self):
        for task in self:
            task.is_current_user_member = (
                task.member_id and task.member_id.user_id.id == self.env.uid
            )

    @api.depends('project_id')
    def _compute_project_member_ids(self):
        for task in self:
            if task.project_id:
                task.project_member_ids = task.project_id.member_ids
            else:
                task.project_member_ids = self.env['task.management.member']

    @api.onchange('project_id')
    def _onchange_project_id_phase(self):
        self.phase_id = False

    @api.onchange('member_id')
    def _onchange_member_id_project_domain(self):
        """Restrict project dropdown: admins see all active projects,
        PMs see projects they manage or are a member of,
        members see only projects they are a member of."""
        is_admin = self.env.user.has_group(
            'task_project_management.group_admin_manager')
        if is_admin:
            return {'domain': {'project_id': [('status', 'in', ['waiting', 'active'])]}}
        is_pm = self.env.user.has_group(
            'task_project_management.group_project_manager')
        if is_pm:
            if self.member_id:
                return {'domain': {'project_id': [
                    ('status', 'in', ['waiting', 'active']),
                    '|',
                    ('member_ids', '=', self.member_id.id),
                    ('project_manager_ids', '=', self.member_id.id),
                ]}}
            return {'domain': {'project_id': [
                ('status', 'in', ['waiting', 'active']),
                '|',
                ('member_ids.user_id', '=', self.env.uid),
                ('project_manager_ids.user_id', '=', self.env.uid),
            ]}}
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

    @api.constrains('approval_status', 'date', 'time_from', 'time_to', 'description')
    def _check_required_for_submission(self):
        """Ensure date, time, description are filled for non-assigned tasks."""
        for task in self:
            if task.approval_status != 'assigned':
                if not task.date:
                    raise ValidationError(
                        _('Date is required.'))
                if not task.time_from and not task.time_to:
                    raise ValidationError(
                        _('Time From and Time To are required.'))
                if not task.description:
                    raise ValidationError(
                        _('Task Description is required.'))

    @api.constrains('time_from', 'time_to')
    def _check_time_validity(self):
        allow_after_midnight = self.env[
            'ir.config_parameter'].sudo().get_param(
            'task_project_management.allow_after_midnight', 'False')
        for task in self:
            # Skip validation for assigned tasks (member hasn't filled time yet)
            if task.approval_status == 'assigned':
                continue
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
            if task.approval_status == 'assigned':
                continue
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
            if task.approval_status == 'assigned':
                continue
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
        PMs can add tasks for themselves in projects they manage or
        are a member of. PMs can add tasks on behalf of members in
        their managed projects.
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
                    # PM can add tasks in projects they manage or
                    # are a regular member of
                    if is_manager_of_project:
                        continue
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

    @api.model
    def default_get(self, fields_list):
        """Include context-dependent computed booleans in defaults so the
        web client has the correct values when opening a new form.  These
        fields only depend on ``uid`` (via @api.depends_context), which
        means the standard onchange mechanism never triggers their
        recomputation for new records."""
        defaults = super().default_get(fields_list)
        is_pm = (
            self.env.user.has_group(
                'task_project_management.group_project_manager') or
            self.env.user.has_group(
                'task_project_management.group_admin_manager'))
        if 'is_current_user_pm' in fields_list:
            defaults['is_current_user_pm'] = is_pm
        if 'can_assign' in fields_list:
            defaults['can_assign'] = is_pm
        if 'is_current_user_member' in fields_list:
            # Check if the task will belong to the current user
            default_member = self.env.context.get('default_member_id')
            if default_member:
                member = self.env['task.management.member'].browse(default_member)
                defaults['is_current_user_member'] = (
                    member.exists() and member.user_id.id == self.env.uid
                )
            else:
                # No explicit member -> task creation auto-assigns current user
                member = self.env['task.management.member'].search(
                    [('user_id', '=', self.env.uid)], limit=1)
                defaults['is_current_user_member'] = bool(member)
        return defaults

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['entry_timestamp'] = fields.Datetime.now()

            if vals.get('approval_status') == 'assigned':
                # Only PMs and Admins can assign tasks to members
                is_pm = self.env.user.has_group(
                    'task_project_management.group_project_manager')
                is_admin = self.env.user.has_group(
                    'task_project_management.group_admin_manager')
                if not is_pm and not is_admin:
                    raise UserError(
                        _('Only Project Managers or Admins can assign tasks to members.'))
                # Prevent self-assignment
                pm_member = self.env[
                    'task.management.member'].sudo()._get_member_for_user()
                if pm_member and vals.get('member_id') == pm_member.id:
                    raise UserError(
                        _('You cannot assign a task to yourself.'))
                # Auto-set assigned_by from current PM
                if not vals.get('assigned_by_id') and pm_member:
                    vals['assigned_by_id'] = pm_member.id
                # Clear date default to avoid constraint issues
                if not vals.get('date'):
                    vals['date'] = False
                # Set task_type to assigned
                vals['task_type'] = 'assigned'
            else:
                # Auto-set member from current user for regular tasks
                if not vals.get('member_id'):
                    member = self.env[
                        'task.management.member']._get_member_for_user()
                    if member:
                        vals['member_id'] = member.id
        records = super().create(vals_list)
        for record in records:
            is_assignment = record.approval_status == 'assigned'
            # Auto-activate project on first task submission
            if not is_assignment and record.project_id.status == 'waiting':
                record.project_id.sudo().write({'status': 'active'})
            # Create initial audit entry
            initial_status = 'assigned' if is_assignment else 'pending'
            comment = _('Task assigned') if is_assignment else _('Task created')
            record._create_audit_entry(False, initial_status, comment)
            # Validate attachments and fix access control
            record._validate_attachment_size()
            record._ensure_attachment_access()
            if is_assignment:
                # Notify the member about the assignment
                record._notify_member_on_assign()
            else:
                # Notify PM about submission
                record._notify_pm_on_submit()
        return records

    def write(self, vals):
        # Enforce field-level write restrictions based on role vs task ownership
        is_admin = self.env.user.has_group(
            'task_project_management.group_admin_manager')
        if not is_admin:
            current_member = self.env[
                'task.management.member'].sudo()._get_member_for_user()
            for task in self:
                is_task_member = (task.member_id == current_member)
                is_project_pm = (
                    task.project_id and
                    self.env.uid in
                    task.project_id.project_manager_ids.mapped('user_id.id'))
                if is_project_pm and not is_task_member:
                    # PM reviewing someone else's task -- only PM fields allowed
                    pm_allowed = {
                        'approval_status', 'manager_comment',
                        'message_follower_ids', 'message_ids',
                    }
                    for f in list(set(vals.keys()) - pm_allowed):
                        vals.pop(f, None)
                    if not vals:
                        return True
                elif is_task_member:
                    # Task member (even if PM) -- cannot write manager_comment
                    vals.pop('manager_comment', None)
                    if not vals:
                        return True

        # Capture old statuses, comments, and snapshots BEFORE any write happens
        old_statuses = {task.id: task.approval_status for task in self}
        old_comments = {task.id: task.manager_comment or '' for task in self}
        old_snapshots = {task.id: task._build_snapshot() for task in self}

        for task in self:
            # Block editing of approved tasks (except status/comment changes)
            if task.approval_status in ('approved',):
                allowed_fields = {
                    'approval_status', 'manager_comment',
                    'message_follower_ids', 'message_ids',
                }
                if not set(vals.keys()).issubset(allowed_fields):
                    raise UserError(
                        _('Cannot edit an approved task.'))

            # If editing a rejected task (non-status fields), reset to pending
            if task.approval_status in ('rejected',):
                if 'approval_status' not in vals:
                    non_status_fields = set(vals.keys()) - {
                        'approval_status', 'manager_comment',
                        'message_follower_ids', 'message_ids',
                    }
                    if non_status_fields:
                        vals = dict(vals, approval_status='pending')

            # If the assigned member edits an assigned task, submit it
            # The assigning PM/Admin editing should NOT trigger submission
            if task.approval_status == 'assigned':
                if 'approval_status' not in vals:
                    is_assigned_member = (
                        task.member_id
                        and task.member_id.user_id.id == self.env.uid
                    )
                    if is_assigned_member:
                        submit_fields = {'date', 'time_from', 'time_to',
                                         'description', 'attachment_ids'}
                        if set(vals.keys()) & submit_fields:
                            vals = dict(vals,
                                        approval_status='pending')

        result = super().write(vals)

        # Handle approval status changes
        if 'approval_status' in vals:
            new_status = vals['approval_status']
            for task in self:
                old_status = old_statuses.get(task.id, 'pending')
                previous_comment = old_comments.get(task.id, '')
                comment = vals.get('manager_comment', '')
                task._create_audit_entry(
                    old_status, new_status, comment, previous_comment,
                    snapshot=old_snapshots.get(task.id))
                if new_status in ('approved', 'rejected'):
                    task._notify_member_status_change(new_status)
                elif (new_status in ('pending',)
                      and old_status in ('rejected',)):
                    # Resubmission after rejection: notify PM
                    task._notify_pm_on_submit()
                elif (new_status == 'pending'
                      and old_status == 'assigned'):
                    # Member submitted assigned task: notify PM
                    task._notify_pm_on_submit()

            # Reset seen flags based on new status
            if new_status == 'pending':
                self.sudo().write({'is_seen_by_pm': False})
            elif new_status == 'assigned':
                self.sudo().write({'is_seen_by_member': False})

        # Validate attachment sizes and fix access if attachments changed
        if 'attachment_ids' in vals or 'assignment_attachment_ids' in vals:
            for task in self:
                task._validate_attachment_size()
                task._ensure_attachment_access()

        return result

    def unlink(self):
        raise UserError(_('Tasks cannot be deleted. You can only edit them.'))

    # --- Actions ---

    def action_approve(self):
        self._check_can_approve()
        for task in self:
            task.write({'approval_status': 'approved'})

    def action_reject(self):
        self._check_can_approve()
        for task in self:
            task.write({'approval_status': 'rejected'})

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

    def _build_snapshot(self):
        """Build a snapshot dict of the current task state."""
        self.ensure_one()
        return {
            'snap_date': self.date,
            'snap_description': self.description or '',
            'snap_project_name': self.project_id.name or '',
            'snap_phase_name': self.phase_id.name or '',
            'snap_time_from': self.time_from,
            'snap_time_to': self.time_to,
            'snap_duration_hours': self.duration_hours,
            'snap_manager_comment': self.manager_comment or '',
            'snap_approval_status': self.approval_status,
            'snap_task_type': self.task_type,
            'snap_assignment_name': self.assignment_name or '',
            'snap_assignment_description': self.assignment_description or '',
            'snap_due_date': self.due_date,
            'snap_attachment_names': ', '.join(
                self.attachment_ids.mapped('name')) if self.attachment_ids else '',
            'snap_assignment_attachment_names': ', '.join(
                self.assignment_attachment_ids.mapped('name')) if self.assignment_attachment_ids else '',
            'snap_attachment_ids': [(6, 0, self.attachment_ids.ids)],
            'snap_assignment_attachment_ids': [(6, 0, self.assignment_attachment_ids.ids)],
        }

    def _create_audit_entry(self, old_status, new_status, comment='', previous_comment='', snapshot=None):
        vals = {
            'task_id': self.id,
            'old_status': old_status or False,
            'new_status': new_status,
            'changed_by': self.env.uid,
            'previous_comment': previous_comment or False,
            'comment': comment,
        }
        # Use provided snapshot (pre-write) or build from current state (create)
        snap = snapshot if snapshot is not None else self._build_snapshot()
        vals.update(snap)
        self.env['task.management.task.audit'].sudo().create(vals)

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

    def _ensure_attachment_access(self):
        """Set res_model/res_id on task attachments so Odoo's built-in
        ir.attachment access check grants read to anyone who can read
        the task (PM, Admin, Manager)."""
        self.ensure_one()
        all_attachments = (
            self.sudo().attachment_ids | self.sudo().assignment_attachment_ids
        )
        to_fix = all_attachments.filtered(
            lambda a: a.res_model != self._name or a.res_id != self.id
        )
        if to_fix:
            to_fix.write({
                'res_model': self._name,
                'res_id': self.id,
            })

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

    def _notify_member_on_assign(self):
        """Notify member when a task is assigned to them by a PM."""
        try:
            member_partner = self.sudo().member_id.user_id.partner_id
            if member_partner:
                body = Markup(
                    '<p>You have been assigned a new task: '
                    '<strong>%s</strong> in project '
                    '<strong>%s</strong>.</p>'
                ) % (
                    self.assignment_name or '',
                    self.project_id.name or '',
                )
                if self.due_date:
                    body += Markup(
                        '<p>Due date: <strong>%s</strong></p>'
                    ) % self.due_date
                self.sudo().message_post(
                    body=body,
                    partner_ids=[member_partner.id],
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
                'totalTasks': 0, 'assignedTasks': 0,
                'pendingTasks': 0,
                'approvedTasks': 0,
                'rejectedTasks': 0,
                'hoursToday': '0.00', 'hoursWeek': '0.00',
                'hoursMonth': '0.00',
                'dailyTarget': '8.00', 'weeklyTarget': '40.00',
                'monthlyTarget': '0.00',
                'dailyPerformance': 0, 'weeklyPerformance': 0,
                'monthlyPerformance': 0,
                'recentTasks': [],
            }
        tasks = self.sudo().search([('member_id', '=', member.id)])
        non_rejected = tasks.filtered(lambda t: t.approval_status != 'rejected')
        today = fields.Date.context_today(self)
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)

        hours_today = sum(non_rejected.filtered(
            lambda t: t.date == today).mapped('duration_hours'))
        hours_week = sum(non_rejected.filtered(
            lambda t: t.date and t.date >= week_start).mapped('duration_hours'))
        hours_month = sum(non_rejected.filtered(
            lambda t: t.date and t.date >= month_start).mapped('duration_hours'))

        recent = tasks[:10]
        fget = self.fields_get(['approval_status', 'task_type'])
        status_map = dict(fget['approval_status']['selection'])
        type_map = dict(fget['task_type']['selection'])
        recent_data = [{
            'id': t.id,
            'date': str(t.date),
            'project': t.project_id.name,
            'description': (t.description or '')[:60],
            'hours': f'{t.duration_hours:.2f}',
            'task_type': t.task_type,
            'task_type_display': type_map.get(t.task_type, t.task_type),
            'status': t.approval_status,
            'status_display': status_map.get(t.approval_status,
                                             t.approval_status),
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

        # Monthly target = daily_target * (30 - off days)
        off_days = int(self.env['ir.config_parameter'].sudo().get_param(
            'task_project_management.monthly_off_days', '0'))
        monthly_target = daily_target * max(30 - off_days, 0)
        monthly_perf = round(
            (hours_month / monthly_target * 100) if monthly_target else 0, 1)

        return {
            'totalTasks': len(tasks),
            'assignedTasks': len(tasks.filtered(
                lambda t: t.approval_status == 'assigned')),
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
            'monthlyTarget': f'{monthly_target:.2f}',
            'dailyPerformance': daily_perf,
            'weeklyPerformance': weekly_perf,
            'monthlyPerformance': monthly_perf,
            'recentTasks': recent_data,
        }

    @api.model
    def get_pm_dashboard_data(self):
        """Return dashboard data for PM's managed projects."""
        Project = self.env['task.management.project'].sudo()
        member = self.env['task.management.member'].sudo().search(
            [('user_id', '=', self.env.uid)], limit=1)

        if member:
            projects = Project.search([
                ('project_manager_ids', 'in', [member.id]),
                ('status', '!=', 'archived'),
            ])
        else:
            return {'projects': []}

        Project = self.env['task.management.project']
        status_map = dict(
            Project.fields_get(['status'])['status']['selection'])

        result = []
        for proj in projects:
            members_data = []
            for m in proj.member_ids:
                m_tasks = proj.task_ids.filtered(
                    lambda t, member=m: t.member_id == member)
                m_tasks_non_rejected = m_tasks.filtered(
                    lambda t: t.approval_status != 'rejected')
                approved = len(m_tasks.filtered(
                    lambda t: t.approval_status == 'approved'))
                total = len(m_tasks)
                rate = round((approved / total * 100) if total else 0, 1)
                late = len(m_tasks.filtered(lambda t: t.is_late_entry))
                members_data.append({
                    'id': m.id,
                    'name': m.name,
                    'task_count': total,
                    'hours': f'{sum(m_tasks_non_rejected.mapped("duration_hours")):.2f}',
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

            assigned_count = len(proj.task_ids.filtered(
                lambda t: t.approval_status == 'assigned'))
            result.append({
                'id': proj.id,
                'name': proj.name,
                'status': proj.status,
                'status_display': status_map.get(proj.status, proj.status),
                'logged_hours': f'{proj.total_logged_hours:.2f}',
                'progress': round(proj.progress_percentage, 1),
                'pending_tasks': proj.pending_task_count,
                'approved_tasks': proj.approved_task_count,
                'rejected_tasks': proj.rejected_task_count,
                'assigned_tasks': assigned_count,
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
        status_map = dict(
            Project.fields_get(['status'])['status']['selection'])

        projects_data = []
        total_late = 0
        for proj in projects:
            late = len(proj.task_ids.filtered(lambda t: t.is_late_entry))
            total_late += late
            projects_data.append({
                'id': proj.id,
                'name': proj.name,
                'status': proj.status,
                'status_display': status_map.get(proj.status, proj.status),
                'progress': round(proj.progress_percentage, 1),
                'task_count': proj.task_count,
                'pending_tasks': proj.pending_task_count,
                'approved_tasks': proj.approved_task_count,
                'rejected_tasks': proj.rejected_task_count,
                'member_count': len(proj.member_ids),
                'late_entries': late,
            })

        return {
            'totalProjects': len(projects),
            'totalMembers': Member.search_count([]),
            'totalHours': f'{sum(all_tasks.filtered(lambda t: t.approval_status != "rejected").mapped("duration_hours")):.2f}',
            'totalLateEntries': total_late,
            'projects': projects_data,
        }

    # ----------------------------------------------------------------
    # Direct Dashboard Exports (CSV / PNG)
    # ----------------------------------------------------------------

    @api.model
    def export_pm_dashboard_csv(self):
        """Export PM dashboard data as CSV (all projects)."""
        data = self.get_pm_dashboard_data()
        company = self.env.company.name
        today = fields.Date.context_today(self)
        SEP = [''] * 7  # blank separator row

        output = io.StringIO()
        writer = csv.writer(output)

        # -- Report Header --
        writer.writerow([_('PROJECT MANAGER DASHBOARD REPORT')])
        writer.writerow([])
        writer.writerow([_('Company:'), company])
        writer.writerow([_('Report Date:'), str(today)])
        writer.writerow([_('Total Projects:'), len(data.get('projects', []))])
        writer.writerow(SEP)

        projects = data.get('projects', [])
        for idx, proj in enumerate(projects, 1):
            # -- Project Header --
            writer.writerow([_('PROJECT %(num)s: %(name)s') % {'num': idx, 'name': proj["name"].upper()}])
            writer.writerow([])
            writer.writerow(
                ['', _('Status'), _('Progress'), _('Logged Hours'),
                 _('Pending'),
                 _('Approved'),
                 _('Rejected'),
                 _('Assigned Tasks')])
            writer.writerow(
                ['', proj['status'].replace('_', ' ').title(),
                 f'{proj["progress"]}%', proj['logged_hours'],
                 proj['pending_tasks'],
                 proj.get('approved_tasks', 0),
                 proj.get('rejected_tasks', 0),
                 proj.get('assigned_tasks', 0)])
            writer.writerow([])

            # -- Team Members --
            if proj.get('members'):
                writer.writerow(['', _('TEAM MEMBERS')])
                writer.writerow(
                    ['', _('No.'), _('Member'), _('Tasks'), _('Hours'),
                     _('Approval Rate'), _('Late Entries')])
                for mi, m in enumerate(proj['members'], 1):
                    writer.writerow(
                        ['', mi, m['name'], m['task_count'], m['hours'],
                         f'{m["approval_rate"]}%', m['late_entries']])
                total_tasks = sum(m['task_count'] for m in proj['members'])
                total_hours = sum(
                    float(m['hours']) for m in proj['members'])
                total_late = sum(m['late_entries'] for m in proj['members'])
                writer.writerow(
                    ['', '', _('TOTAL'), total_tasks, f'{total_hours:.2f}',
                     '', total_late])
                writer.writerow([])

            # -- Phases --
            if proj.get('phases'):
                writer.writerow(['', _('PROJECT PHASES')])
                writer.writerow(
                    ['', _('No.'), _('Phase'), _('Weight'),
                     _('Completion'), _('Contribution')])
                for pi, p in enumerate(proj['phases'], 1):
                    writer.writerow(
                        ['', pi, p['name'], f'{p["percentage"]:.1f}%',
                         f'{p["completion_rate"]:.1f}%',
                         f'{p["effective_progress"]:.1f}%'])
                writer.writerow([])

            if idx < len(projects):
                writer.writerow(['_' * 60])
                writer.writerow([])

        # -- Footer --
        writer.writerow(SEP)
        writer.writerow([_('END OF REPORT')])

        csv_data = output.getvalue().encode('utf-8-sig')
        return {
            'file_content': base64.b64encode(csv_data).decode(),
            'filename': f'pm_dashboard_{today}.csv',
        }

    @api.model
    def _build_pm_dashboard_html(self, data, company, today):
        """Build HTML for PM dashboard export (shared by PNG and PDF)."""

        logo_html = ''
        if company.logo:
            logo_b64 = (company.logo.decode()
                        if isinstance(company.logo, bytes)
                        else company.logo)
            logo_html = (
                f'<img src="data:image/png;base64,{logo_b64}"'
                f' style="height:50px;width:auto;"/>')

        # Build project cards
        project_cards = ''
        for proj in data.get('projects', []):
            status_color = {
                'active': '#5cb85c', 'completed': '#5cb85c',
                'waiting': '#f0ad4e', 'on_hold': '#f0ad4e',
                'archived': '#999',
            }.get(proj['status'], '#0B3D91')

            # Member rows
            member_rows = ''
            for m in proj.get('members', []):
                member_rows += (
                    f'<tr><td>{m["name"]}</td>'
                    f'<td>{m["task_count"]}</td>'
                    f'<td>{m["hours"]}</td>'
                    f'<td>{m["approval_rate"]}%</td>'
                    f'<td>{m["late_entries"]}</td></tr>')

            # Phase rows
            phase_rows = ''
            for p in proj.get('phases', []):
                phase_rows += (
                    f'<tr><td>{p["name"]}</td>'
                    f'<td>{p["percentage"]:.1f}%</td>'
                    f'<td>{p["completion_rate"]:.1f}%</td>'
                    f'<td>{p["effective_progress"]:.1f}%</td></tr>')

            phase_section = ''
            if phase_rows:
                phase_section = f'''
                <h3>{_("Phases")}</h3>
                <table class="data"><thead><tr>
                    <th>{_("Phase")}</th><th>{_("Weight")}</th>
                    <th>{_("Completion")}</th><th>{_("Contribution")}</th>
                </tr></thead><tbody>{phase_rows}</tbody></table>'''

            member_section = ''
            if member_rows:
                member_section = f'''
                <h3>{_("Team Members")}</h3>
                <table class="data"><thead><tr>
                    <th>{_("Member")}</th><th>{_("Tasks")}</th><th>{_("Hours")}</th>
                    <th>{_("Approval Rate")}</th><th>{_("Late")}</th>
                </tr></thead><tbody>{member_rows}</tbody></table>'''

            project_cards += f'''
            <div class="project-card">
                <div class="project-header">
                    <span class="project-name">{proj["name"]}</span>
                    <span class="status-badge"
                          style="background:{status_color}">
                        {proj["status_display"]}</span>
                </div>
                <table class="kpi-grid"><tr>
                    <td>
                        <div class="kpi-value">{proj["progress"]}%</div>
                        <div class="kpi-label">{_("Progress")}</div></td>
                    <td>
                        <div class="kpi-value">{proj["logged_hours"]}</div>
                        <div class="kpi-label">{_("Hours")}</div></td>
                    <td>
                        <div class="kpi-value" style="color:#f0ad4e">{proj["pending_tasks"]}</div>
                        <div class="kpi-label">{_("Pending")}</div></td>
                    <td>
                        <div class="kpi-value" style="color:#5cb85c">{proj.get("approved_tasks", 0)}</div>
                        <div class="kpi-label">{_("Approved")}</div></td>
                    <td>
                        <div class="kpi-value" style="color:#d9534f">{proj.get("rejected_tasks", 0)}</div>
                        <div class="kpi-label">{_("Rejected")}</div></td>
                    <td>
                        <div class="kpi-value" style="color:#17a2b8">{proj.get("assigned_tasks", 0)}</div>
                        <div class="kpi-label">{_("Assigned")}</div></td>
                </tr></table>
                {member_section}
                {phase_section}
            </div>'''

        is_rtl = self.env.lang and self.env.lang.startswith('ar')
        dir_attr = ' dir="rtl"' if is_rtl else ''
        th_align = 'right' if is_rtl else 'left'

        html = f'''<!DOCTYPE html>
<html{dir_attr}><head><meta charset="utf-8"/>
<style>
    body {{ font-family: Arial, sans-serif; margin: 20px; background: #fff; }}
    .header {{ border-bottom: 3px solid #0B3D91; padding-bottom: 15px;
               margin-bottom: 20px; overflow: hidden; }}
    .header-logo {{ float: {"right" if is_rtl else "left"}; margin-{"left" if is_rtl else "right"}: 15px; }}
    .header h1 {{ color: #0B3D91; margin: 0; font-size: 22px; }}
    .header p {{ color: #666; margin: 3px 0 0 0; font-size: 12px; }}
    .project-card {{ border: 1px solid #ddd; border-radius: 10px;
                     margin-bottom: 20px; padding: 15px;
                     background: #fafafa; }}
    .project-header {{ overflow: hidden; margin-bottom: 10px; }}
    .project-name {{ font-size: 18px; font-weight: bold; color: #0B3D91;
                     float: {"right" if is_rtl else "left"}; }}
    .status-badge {{ color: #fff; padding: 3px 10px; border-radius: 12px;
                     font-size: 11px; font-weight: bold;
                     float: {"left" if is_rtl else "right"}; }}
    h3 {{ color: #0B3D91; font-size: 14px; margin: 12px 0 6px 0;
          border-bottom: 1px solid #0B3D91; padding-bottom: 4px; clear: both; }}
    .kpi-grid {{ width: 100%; border-collapse: separate; border-spacing: 8px 0;
                 margin: 10px 0; }}
    .kpi-grid td {{ background: #E8EEF7; border-radius: 8px;
                    padding: 8px 14px; text-align: center; }}
    .kpi-value {{ font-size: 18px; font-weight: bold; color: #0B3D91; }}
    .kpi-label {{ font-size: 9px; color: #666; text-transform: uppercase; }}
    table.data {{ width: 100%; border-collapse: collapse; margin-top: 6px; }}
    table.data th {{ background: #0B3D91; color: #fff; padding: 6px 8px;
          text-align: {th_align}; font-size: 11px; }}
    table.data td {{ padding: 5px 8px; border-bottom: 1px solid #ddd; font-size: 11px; }}
    table.data tr:nth-child(even) {{ background: #E8EEF7; }}
    .footer {{ clear: both; margin-top: 30px; padding-top: 8px; border-top: 1px solid #ddd;
               color: #999; font-size: 10px; text-align: center; }}
</style></head><body>
    <div class="header">
        <div class="header-logo">{logo_html}</div>
        <div>
            <h1>{_("PM Dashboard Report")}</h1>
            <p>{company.name} | {_("Generated:")} {today}</p>
        </div>
    </div>
    {project_cards}
    <div class="footer">{_("Generated by")} {company.name} | {_("PM Dashboard")} | {today}</div>
</body></html>'''

        return html

    @api.model
    def export_pm_dashboard_png(self):
        """Export PM dashboard as PNG image."""
        data = self.get_pm_dashboard_data()
        company = self.env.company
        today = fields.Date.context_today(self)
        html = self._build_pm_dashboard_html(data, company, today)
        return self._html_to_png(html, f'pm_dashboard_{today}.png')

    @api.model
    def export_pm_dashboard_pdf(self):
        """Export PM dashboard as PDF."""
        data = self.get_pm_dashboard_data()
        company = self.env.company
        today = fields.Date.context_today(self)
        html = self._build_pm_dashboard_html(data, company, today)
        return self._html_to_pdf(html, f'pm_dashboard_{today}.pdf')

    @api.model
    def export_admin_dashboard_csv(self):
        """Export Admin dashboard data as CSV (all projects)."""
        data = self.get_admin_dashboard_data()
        company = self.env.company.name
        today = fields.Date.context_today(self)

        output = io.StringIO()
        writer = csv.writer(output)

        # -- Report Header --
        writer.writerow([_('MANAGER DASHBOARD REPORT')])
        writer.writerow([])
        writer.writerow([_('Company:'), company])
        writer.writerow([_('Report Date:'), str(today)])
        writer.writerow([])

        # -- Organization Summary --
        writer.writerow([_('ORGANIZATION SUMMARY')])
        writer.writerow([])
        writer.writerow(['', _('Metric'), _('Value')])
        writer.writerow(['', _('Total Projects'), data['totalProjects']])
        writer.writerow(['', _('Total Members'), data['totalMembers']])
        writer.writerow(['', _('Total Logged Hours'), data['totalHours']])
        writer.writerow(['', _('Total Late Entries'), data['totalLateEntries']])
        writer.writerow([])

        # -- All Projects --
        writer.writerow([_('ALL PROJECTS')])
        writer.writerow([])
        writer.writerow(
            [_('No.'), _('Project'), _('Status'), _('Progress'),
             _('Tasks'), _('Pending'),
             _('Approved'),
             _('Rejected'),
             _('Members'), _('Late Entries')])
        total_tasks = 0
        total_pending = 0
        total_late = 0
        for i, proj in enumerate(data.get('projects', []), 1):
            writer.writerow([
                i,
                proj['name'],
                proj['status'].replace('_', ' ').title(),
                f'{proj["progress"]}%',
                proj['task_count'],
                proj['pending_tasks'],
                proj.get('approved_tasks', 0),
                proj.get('rejected_tasks', 0),
                proj['member_count'],
                proj['late_entries'],
            ])
            total_tasks += proj['task_count']
            total_pending += proj['pending_tasks']
            total_late += proj['late_entries']
        writer.writerow([])
        writer.writerow(
            ['', _('TOTAL'), '', '',
             total_tasks, total_pending, '', total_late])
        writer.writerow([])

        # -- Footer --
        writer.writerow([_('END OF REPORT')])

        csv_data = output.getvalue().encode('utf-8-sig')
        return {
            'file_content': base64.b64encode(csv_data).decode(),
            'filename': f'admin_dashboard_{today}.csv',
        }

    @api.model
    def _build_admin_dashboard_html(self, data, company, today):
        """Build HTML for Admin dashboard export (shared by PNG and PDF)."""

        logo_html = ''
        if company.logo:
            logo_b64 = (company.logo.decode()
                        if isinstance(company.logo, bytes)
                        else company.logo)
            logo_html = (
                f'<img src="data:image/png;base64,{logo_b64}"'
                f' style="height:50px;width:auto;"/>')

        # Project rows
        project_rows = ''
        for proj in data.get('projects', []):
            status_color = {
                'active': '#5cb85c', 'completed': '#5cb85c',
                'waiting': '#f0ad4e', 'on_hold': '#f0ad4e',
                'archived': '#999',
            }.get(proj['status'], '#0B3D91')
            project_rows += (
                f'<tr><td>{proj["name"]}</td>'
                f'<td style="color:{status_color};font-weight:bold;">'
                f'{proj["status_display"]}</td>'
                f'<td>{proj["progress"]}%</td>'
                f'<td>{proj["task_count"]}</td>'
                f'<td>{proj["pending_tasks"]}</td>'
                f'<td>{proj.get("approved_tasks", 0)}</td>'
                f'<td>{proj.get("rejected_tasks", 0)}</td>'
                f'<td>{proj["member_count"]}</td>'
                f'<td>{proj["late_entries"]}</td></tr>')

        is_rtl = self.env.lang and self.env.lang.startswith('ar')
        dir_attr = ' dir="rtl"' if is_rtl else ''
        th_align = 'right' if is_rtl else 'left'

        html = f'''<!DOCTYPE html>
<html{dir_attr}><head><meta charset="utf-8"/>
<style>
    body {{ font-family: Arial, sans-serif; margin: 20px; background: #fff; }}
    .header {{ border-bottom: 3px solid #0B3D91; padding-bottom: 15px;
               margin-bottom: 20px; overflow: hidden; }}
    .header-logo {{ float: {"right" if is_rtl else "left"}; margin-{"left" if is_rtl else "right"}: 15px; }}
    .header h1 {{ color: #0B3D91; margin: 0; font-size: 22px; }}
    .header p {{ color: #666; margin: 3px 0 0 0; font-size: 12px; }}
    .kpi-grid {{ width: 100%; border-collapse: separate; border-spacing: 12px 0;
                 margin: 15px 0 20px 0; }}
    .kpi-grid td {{ background: #E8EEF7; border: 1px solid #ddd; border-radius: 8px;
                    padding: 12px 18px; text-align: center; width: 25%; }}
    .kpi-value {{ font-size: 24px; font-weight: bold; color: #0B3D91; }}
    .kpi-label {{ font-size: 10px; color: #666; text-transform: uppercase; }}
    h2 {{ color: #0B3D91; font-size: 16px; margin-top: 20px;
          border-bottom: 2px solid #0B3D91; padding-bottom: 5px; }}
    table.data {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
    table.data th {{ background: #0B3D91; color: #fff; padding: 8px;
          text-align: {th_align}; font-size: 12px; }}
    table.data td {{ padding: 6px 8px; border-bottom: 1px solid #ddd; font-size: 12px; }}
    table.data tr:nth-child(even) {{ background: #E8EEF7; }}
    .footer {{ clear: both; margin-top: 30px; padding-top: 8px; border-top: 1px solid #ddd;
               color: #999; font-size: 10px; text-align: center; }}
</style></head><body>
    <div class="header">
        <div class="header-logo">{logo_html}</div>
        <div>
            <h1>{_("Manager Dashboard Report")}</h1>
            <p>{company.name} | {_("Generated:")} {today}</p>
        </div>
    </div>

    <table class="kpi-grid"><tr>
        <td>
            <div class="kpi-value">{data["totalProjects"]}</div>
            <div class="kpi-label">{_("Total Projects")}</div></td>
        <td>
            <div class="kpi-value" style="color:#5cb85c">{data["totalMembers"]}</div>
            <div class="kpi-label">{_("Total Members")}</div></td>
        <td>
            <div class="kpi-value">{data["totalHours"]}</div>
            <div class="kpi-label">{_("Total Hours")}</div></td>
        <td>
            <div class="kpi-value" style="color:#d9534f">{data["totalLateEntries"]}</div>
            <div class="kpi-label">{_("Late Entries")}</div></td>
    </tr></table>

    <h2>{_("All Projects")}</h2>
    <table class="data"><thead><tr>
        <th>{_("Project")}</th><th>{_("Status")}</th><th>{_("Progress")}</th>
        <th>{_("Tasks")}</th><th>{_("Pending")}</th>
        <th>{_("Approved")}</th>
        <th>{_("Rejected")}</th>
        <th>{_("Members")}</th><th>{_("Late")}</th>
    </tr></thead><tbody>{project_rows}</tbody></table>

    <div class="footer">{_("Generated by")} {company.name} | {_("Manager Dashboard")} | {today}</div>
</body></html>'''

        return html

    @api.model
    def export_admin_dashboard_png(self):
        """Export Admin dashboard as PNG image."""
        data = self.get_admin_dashboard_data()
        company = self.env.company
        today = fields.Date.context_today(self)
        html = self._build_admin_dashboard_html(data, company, today)
        return self._html_to_png(html, f'admin_dashboard_{today}.png')

    @api.model
    def export_admin_dashboard_pdf(self):
        """Export Admin dashboard as PDF."""
        data = self.get_admin_dashboard_data()
        company = self.env.company
        today = fields.Date.context_today(self)
        html = self._build_admin_dashboard_html(data, company, today)
        return self._html_to_pdf(html, f'admin_dashboard_{today}.pdf')

    @api.model
    def _html_to_png(self, html_content, filename):
        """Convert HTML to PNG using wkhtmltoimage and return base64."""
        try:
            with tempfile.NamedTemporaryFile(
                suffix='.html', mode='w', delete=False,
                encoding='utf-8',
            ) as html_file:
                html_file.write(html_content)
                html_path = html_file.name
            png_path = html_path.replace('.html', '.png')
            result = subprocess.run(
                ['wkhtmltoimage', '--width', '1200',
                 html_path, png_path],
                capture_output=True, timeout=30,
            )
            if result.returncode != 0:
                raise UserError(
                    _('Failed to generate image: %s') %
                    result.stderr.decode())
            with open(png_path, 'rb') as f:
                png_data = base64.b64encode(f.read()).decode()
            import os
            os.unlink(html_path)
            os.unlink(png_path)
            return {
                'file_content': png_data,
                'filename': filename,
            }
        except FileNotFoundError:
            raise UserError(
                _('wkhtmltoimage is not installed. '
                  'Please install wkhtmltopdf package.'))
        except subprocess.TimeoutExpired:
            raise UserError(_('Image generation timed out.'))

    @api.model
    def _html_to_pdf(self, html_content, filename):
        """Convert HTML to PDF using wkhtmltopdf and return base64."""
        try:
            with tempfile.NamedTemporaryFile(
                suffix='.html', mode='w', delete=False,
                encoding='utf-8',
            ) as html_file:
                html_file.write(html_content)
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
                pdf_data = base64.b64encode(f.read()).decode()
            import os
            os.unlink(html_path)
            os.unlink(pdf_path)
            return {
                'file_content': pdf_data,
                'filename': filename,
            }
        except FileNotFoundError:
            raise UserError(
                _('wkhtmltopdf is not installed. '
                  'Please install wkhtmltopdf package.'))
        except subprocess.TimeoutExpired:
            raise UserError(_('PDF generation timed out.'))

    # ----------------------------------------------------------------
    # Phase 5: Login Alert RPC Methods
    # ----------------------------------------------------------------

    @api.model
    def get_login_alerts(self):
        """Return unseen alerts for the current user."""
        member = self.env['task.management.member'].sudo().search(
            [('user_id', '=', self.env.uid)], limit=1)
        if not member:
            return {'member_alerts': [], 'pm_alerts': []}

        # Member alerts: assigned tasks not yet seen
        member_alerts = self.sudo().search([
            ('member_id', '=', member.id),
            ('task_type', '=', 'assigned'),
            ('approval_status', '=', 'assigned'),
            ('is_seen_by_member', '=', False),
        ])
        # PM alerts: pending tasks in projects I manage, not yet seen
        pm_alerts = self.env['task.management.task']
        is_pm = self.env.user.has_group(
            'task_project_management.group_project_manager') or \
            self.env.user.has_group(
            'task_project_management.group_admin_manager')
        if is_pm:
            managed_projects = self.env['task.management.project'].sudo().search([
                ('project_manager_ids', 'in', [member.id]),
            ])
            if managed_projects:
                pm_alerts = self.sudo().search([
                    ('project_id', 'in', managed_projects.ids),
                    ('approval_status', '=', 'pending'),
                    ('is_seen_by_pm', '=', False),
                    ('member_id', '!=', member.id),
                ])

        return {
            'member_alerts': [{
                'id': t.id,
                'assignment_name': t.assignment_name or '',
                'project_name': t.project_id.name or '',
            } for t in member_alerts],
            'pm_alerts': [{
                'id': t.id,
                'member_name': t.member_id.name or '',
                'project_name': t.project_id.name or '',
                'description': (t.description or '')[:50],
            } for t in pm_alerts],
        }

    @api.model
    def acknowledge_member_alerts(self):
        """Mark all unseen assigned tasks as seen by the member."""
        member = self.env['task.management.member'].sudo().search(
            [('user_id', '=', self.env.uid)], limit=1)
        if member:
            tasks = self.sudo().search([
                ('member_id', '=', member.id),
                ('task_type', '=', 'assigned'),
                ('approval_status', '=', 'assigned'),
                ('is_seen_by_member', '=', False),
            ])
            tasks.sudo().write({'is_seen_by_member': True})
        return True

    @api.model
    def acknowledge_pm_alerts(self):
        """Mark all unseen pending tasks as seen by the PM."""
        member = self.env['task.management.member'].sudo().search(
            [('user_id', '=', self.env.uid)], limit=1)
        if member:
            managed_projects = self.env['task.management.project'].sudo().search([
                ('project_manager_ids', 'in', [member.id]),
            ])
            if managed_projects:
                tasks = self.sudo().search([
                    ('project_id', 'in', managed_projects.ids),
                    ('approval_status', '=', 'pending'),
                    ('is_seen_by_pm', '=', False),
                    ('member_id', '!=', member.id),
                ])
                tasks.sudo().write({'is_seen_by_pm': True})
        return True
