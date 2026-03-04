from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from markupsafe import Markup
from datetime import datetime, timedelta


class TaskManagementMeeting(models.Model):
    _name = 'task.management.meeting'
    _description = 'Project Meeting'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, time_from asc, id desc'

    name = fields.Char(
        string='Meeting Title',
        required=True,
        tracking=True,
    )
    date = fields.Date(
        string='Date',
        required=True,
        tracking=True,
        default=fields.Date.context_today,
    )
    time_from = fields.Float(
        string='From',
        required=True,
        tracking=True,
    )
    time_to = fields.Float(
        string='To',
        required=True,
        tracking=True,
    )
    duration = fields.Float(
        string='Duration (Hours)',
        compute='_compute_duration',
        store=True,
    )
    meeting_mode = fields.Selection([
        ('in_person', 'In Person'),
        ('online', 'Online'),
        ('hybrid', 'Hybrid'),
    ], string='Mode', default='online', required=True, tracking=True)
    location = fields.Char(string='Location')
    meeting_link = fields.Char(
        string='Meeting Link',
        tracking=True,
        help='Google Meet or other online meeting URL',
    )
    meeting_type = fields.Selection([
        ('project_review', 'Project Review'),
        ('task_review', 'Task Review'),
        ('team_meeting', 'Team Meeting'),
        ('other', 'Other'),
    ], string='Meeting Type', default='team_meeting', required=True, tracking=True)
    status = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', required=True, tracking=True)
    project_id = fields.Many2one(
        'task.management.project',
        string='Project',
        required=True,
        tracking=True,
        ondelete='restrict',
        domain="[('status', 'in', ['waiting', 'active'])]",
    )
    task_id = fields.Many2one(
        'task.management.task',
        string='Related Task',
        tracking=True,
        ondelete='set null',
    )
    organizer_id = fields.Many2one(
        'task.management.member',
        string='Organizer',
        required=True,
        tracking=True,
        ondelete='restrict',
    )
    attendee_ids = fields.Many2many(
        'task.management.member',
        'meeting_attendee_rel',
        'meeting_id', 'member_id',
        string='Attendees',
    )
    agenda = fields.Html(string='Agenda')
    minutes = fields.Html(string='Minutes')

    # Computed datetime fields for calendar view
    datetime_start = fields.Datetime(
        string='Start',
        compute='_compute_datetimes',
        store=True,
    )
    datetime_end = fields.Datetime(
        string='End',
        compute='_compute_datetimes',
        store=True,
    )

    # Role flags
    is_current_user_pm = fields.Boolean(
        compute='_compute_role_flags',
    )
    is_current_user_admin = fields.Boolean(
        compute='_compute_role_flags',
    )
    is_current_user_organizer = fields.Boolean(
        compute='_compute_role_flags',
    )

    # -------------------------------------------------------------------------
    # Computed methods
    # -------------------------------------------------------------------------

    @api.depends('time_from', 'time_to')
    def _compute_duration(self):
        for rec in self:
            if rec.time_to > rec.time_from:
                rec.duration = rec.time_to - rec.time_from
            else:
                rec.duration = 0.0

    @api.depends('date', 'time_from', 'time_to')
    def _compute_datetimes(self):
        for rec in self:
            if rec.date and rec.time_from is not False and rec.time_to is not False:
                # Convert float time to hours and minutes
                from_hours = int(rec.time_from)
                from_minutes = int(round((rec.time_from - from_hours) * 60))
                to_hours = int(rec.time_to)
                to_minutes = int(round((rec.time_to - to_hours) * 60))
                base_date = datetime.combine(rec.date, datetime.min.time())
                rec.datetime_start = base_date + timedelta(
                    hours=from_hours, minutes=from_minutes)
                rec.datetime_end = base_date + timedelta(
                    hours=to_hours, minutes=to_minutes)
            else:
                rec.datetime_start = False
                rec.datetime_end = False

    @api.depends_context('uid')
    def _compute_role_flags(self):
        user = self.env.user
        is_pm = user.has_group(
            'task_project_management.group_project_manager') or \
            user.has_group(
            'task_project_management.group_manager')
        is_admin = user.has_group(
            'task_project_management.group_admin_manager')
        member = self.env['task.management.member'].sudo().search(
            [('user_id', '=', user.id)], limit=1)
        for rec in self:
            rec.is_current_user_pm = is_pm
            rec.is_current_user_admin = is_admin
            rec.is_current_user_organizer = (
                member and rec.organizer_id.id == member.id)

    # -------------------------------------------------------------------------
    # Constraints
    # -------------------------------------------------------------------------

    @api.constrains('time_from', 'time_to')
    def _check_time_validity(self):
        for rec in self:
            if rec.time_from < 0 or rec.time_from > 24:
                raise ValidationError(
                    _('Start time must be between 0:00 and 24:00.'))
            if rec.time_to < 0 or rec.time_to > 24:
                raise ValidationError(
                    _('End time must be between 0:00 and 24:00.'))
            if rec.time_to <= rec.time_from:
                raise ValidationError(
                    _('End time must be after start time.'))

    @api.constrains('date')
    def _check_date_not_past(self):
        today = fields.Date.context_today(self)
        is_admin = self.env.user.has_group(
            'task_project_management.group_admin_manager')
        if is_admin:
            return
        for rec in self:
            if rec.date and rec.date < today:
                raise ValidationError(
                    _('Meeting date cannot be in the past.'))

    # -------------------------------------------------------------------------
    # CRUD
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        user = self.env.user
        is_pm = user.has_group(
            'task_project_management.group_project_manager') or \
            user.has_group(
            'task_project_management.group_manager')
        is_admin = user.has_group(
            'task_project_management.group_admin_manager')
        if not is_pm and not is_admin:
            raise UserError(
                _('Only Project Managers and Admins can create meetings.'))
        # Auto-set organizer_id from current user's member record
        member = self.env['task.management.member'].sudo().search(
            [('user_id', '=', user.id)], limit=1)
        for vals in vals_list:
            if not vals.get('organizer_id') and member:
                vals['organizer_id'] = member.id
        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        # If minutes updated by non-organizer, notify organizer
        if 'minutes' in vals:
            user = self.env.user
            member = self.env['task.management.member'].sudo().search(
                [('user_id', '=', user.id)], limit=1)
            for rec in self:
                if member and rec.organizer_id != member:
                    rec._notify_organizer_minutes_added()
        return res

    # -------------------------------------------------------------------------
    # Status actions
    # -------------------------------------------------------------------------

    def action_confirm(self):
        for rec in self:
            if rec.status != 'draft':
                raise UserError(
                    _('Only draft meetings can be confirmed.'))
            rec.status = 'confirmed'
            rec._notify_attendees_confirmed()

    def action_start(self):
        for rec in self:
            if rec.status != 'confirmed':
                raise UserError(
                    _('Only confirmed meetings can be started.'))
            rec.status = 'in_progress'

    def action_complete(self):
        for rec in self:
            if rec.status != 'in_progress':
                raise UserError(
                    _('Only in-progress meetings can be completed.'))
            rec.status = 'completed'

    def action_cancel(self):
        for rec in self:
            if rec.status in ('completed',):
                raise UserError(
                    _('Completed meetings cannot be cancelled.'))
            rec.status = 'cancelled'
            rec._notify_attendees_cancelled()

    def action_reset_draft(self):
        for rec in self:
            if rec.status != 'cancelled':
                raise UserError(
                    _('Only cancelled meetings can be reset to draft.'))
            rec.status = 'draft'

    # -------------------------------------------------------------------------
    # Notifications
    # -------------------------------------------------------------------------

    def _notify_attendees_confirmed(self):
        """Notify attendees that the meeting has been confirmed."""
        self.ensure_one()
        attendee_partners = self.attendee_ids.mapped('user_id.partner_id')
        if not attendee_partners:
            return
        # Build details based on meeting mode
        details = ''
        if self.meeting_mode in ('online', 'hybrid') and self.meeting_link:
            details += '<br/>Meeting Link: <a href="%s">%s</a>' % (
                self.meeting_link, self.meeting_link)
        if self.meeting_mode in ('in_person', 'hybrid') and self.location:
            details += '<br/>Location: %s' % self.location
        body = Markup(
            '<p>Meeting <strong>%s</strong> has been confirmed.'
            '<br/>Date: %s'
            '<br/>Time: %s - %s'
            '%s</p>'
        ) % (
            self.name,
            self.date,
            self._float_to_time_str(self.time_from),
            self._float_to_time_str(self.time_to),
            Markup(details),
        )
        try:
            self.sudo().message_post(
                body=body,
                partner_ids=attendee_partners.ids,
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )
        except Exception:
            pass

    def _notify_attendees_cancelled(self):
        """Notify attendees that the meeting has been cancelled."""
        self.ensure_one()
        attendee_partners = self.attendee_ids.mapped('user_id.partner_id')
        if not attendee_partners:
            return
        body = Markup(
            '<p>Meeting <strong>%s</strong> scheduled for %s '
            'has been <strong>cancelled</strong>.</p>'
        ) % (self.name, self.date)
        try:
            self.sudo().message_post(
                body=body,
                partner_ids=attendee_partners.ids,
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )
        except Exception:
            pass

    def _notify_organizer_minutes_added(self):
        """Notify the organizer when someone else updates the minutes."""
        self.ensure_one()
        organizer_partner = self.organizer_id.user_id.partner_id
        if not organizer_partner:
            return
        body = Markup(
            '<p>Meeting minutes for <strong>%s</strong> '
            'have been updated by <strong>%s</strong>.</p>'
        ) % (self.name, self.env.user.name)
        try:
            self.sudo().message_post(
                body=body,
                partner_ids=[organizer_partner.id],
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _float_to_time_str(value):
        """Convert a float time value (e.g. 14.5) to a string (e.g. '14:30')."""
        hours = int(value)
        minutes = int(round((value - hours) * 60))
        return '%02d:%02d' % (hours, minutes)

    # -------------------------------------------------------------------------
    # Dashboard RPC methods
    # -------------------------------------------------------------------------

    @api.model
    def get_member_meeting_data(self):
        """Return upcoming meetings for the current member
        (as organizer or attendee). Includes meeting_mode and meeting_link."""
        today = fields.Date.context_today(self)
        member = self.env['task.management.member'].sudo().search(
            [('user_id', '=', self.env.uid)], limit=1)
        if not member:
            return []
        meetings = self.search([
            ('date', '>=', today),
            ('status', 'in', ['draft', 'confirmed', 'in_progress']),
            '|',
            ('organizer_id', '=', member.id),
            ('attendee_ids', 'in', [member.id]),
        ], order='date asc, time_from asc', limit=20)
        fget = self.fields_get(['meeting_type', 'meeting_mode'])
        type_map = dict(fget['meeting_type']['selection'])
        mode_map = dict(fget['meeting_mode']['selection'])
        result = []
        for m in meetings:
            result.append({
                'id': m.id,
                'name': m.name,
                'date': str(m.date),
                'time_from': m._float_to_time_str(m.time_from),
                'time_to': m._float_to_time_str(m.time_to),
                'time_display': '%s - %s' % (
                    m._float_to_time_str(m.time_from),
                    m._float_to_time_str(m.time_to)),
                'status': m.status,
                'project': m.project_id.name,
                'organizer': m.organizer_id.name,
                'meeting_type': m.meeting_type,
                'meeting_type_display': type_map.get(
                    m.meeting_type, m.meeting_type),
                'meeting_mode': m.meeting_mode,
                'meeting_mode_display': mode_map.get(
                    m.meeting_mode, m.meeting_mode),
                'meeting_link': m.meeting_link or '',
                'location': m.location or '',
            })
        return result

    @api.model
    def get_pm_meeting_data(self):
        """Return upcoming meetings grouped by project for the PM."""
        today = fields.Date.context_today(self)
        member = self.env['task.management.member'].sudo().search(
            [('user_id', '=', self.env.uid)], limit=1)
        if not member:
            return {}
        meetings = self.search([
            ('date', '>=', today),
            ('status', 'in', ['draft', 'confirmed', 'in_progress']),
            '|',
            ('organizer_id', '=', member.id),
            ('project_id.project_manager_ids', 'in', [member.id]),
        ], order='date asc, time_from asc')
        grouped = {}
        for m in meetings:
            project_name = m.project_id.name
            if project_name not in grouped:
                grouped[project_name] = []
            grouped[project_name].append({
                'id': m.id,
                'name': m.name,
                'date': str(m.date),
                'time_from': m._float_to_time_str(m.time_from),
                'time_to': m._float_to_time_str(m.time_to),
                'status': m.status,
                'organizer': m.organizer_id.name,
                'attendee_count': len(m.attendee_ids),
                'meeting_mode': m.meeting_mode,
                'meeting_link': m.meeting_link or '',
                'location': m.location or '',
            })
        return grouped
