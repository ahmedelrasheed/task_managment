from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class TaskManagementMember(models.Model):
    _name = 'task.management.member'
    _description = 'Company Staff'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'

    name = fields.Char(string='Name', required=True, tracking=True)
    email = fields.Char(string='Email', required=True, tracking=True)
    phone = fields.Char(string='Phone')
    job_title = fields.Char(string='Job Title')
    role = fields.Selection([
        ('member', 'Member'),
        ('project_manager', 'Project Manager'),
        ('admin_manager', 'Admin Manager'),
        ('manager', 'Manager'),
    ], string='Role', default='member', required=True, tracking=True)
    user_id = fields.Many2one(
        'res.users', string='Related User',
        ondelete='set null', tracking=True,
    )
    is_current_user_admin = fields.Boolean(
        compute='_compute_is_current_user_admin',
    )

    @api.depends_context('uid')
    def _compute_is_current_user_admin(self):
        is_admin = self.env.user.has_group(
            'task_project_management.group_admin_manager')
        for rec in self:
            rec.is_current_user_admin = is_admin

    # Manager oversight fields
    supervise_all_projects = fields.Boolean(
        string='Supervise All Projects',
        default=False,
    )
    supervised_project_ids = fields.Many2many(
        'task.management.project',
        'project_oversight_manager_rel',
        'member_id', 'project_id',
        string='Supervised Projects',
    )

    # Relational fields
    managed_project_ids = fields.Many2many(
        'task.management.project',
        'project_manager_rel',
        'member_id', 'project_id',
        string='Managed Projects',
    )
    member_project_ids = fields.Many2many(
        'task.management.project',
        'project_member_rel',
        'member_id', 'project_id',
        string='Member Projects',
    )
    task_ids = fields.One2many(
        'task.management.task', 'member_id',
        string='Tasks',
    )
    archive_ids = fields.One2many(
        'task.management.archive', 'member_id',
        string='Library Entries',
    )

    @api.model
    def fields_get(self, allfields=None, attributes=None):
        res = super().fields_get(allfields, attributes)
        if 'role' in res and res['role'].get('selection'):
            res['role']['selection'] = [
                s for s in res['role']['selection']
                if s[0] != 'admin_manager'
            ]
        return res

    _sql_constraints = [
        ('email_unique', 'UNIQUE(email)',
         'A member with this email already exists.'),
        ('user_id_unique', 'UNIQUE(user_id)',
         'This user is already linked to another member.'),
    ]

    @api.constrains('role')
    def _check_admin_role_limit(self):
        """Only one admin_manager is allowed in the system."""
        for rec in self:
            if rec.role == 'admin_manager':
                existing_admin = self.sudo().search([
                    ('role', '=', 'admin_manager'),
                    ('id', '!=', rec.id),
                ], limit=1)
                if existing_admin:
                    raise ValidationError(
                        _('Only one Admin Manager is allowed. '
                          '"%s" already holds this role.') % existing_admin.name)

    _role_group_map = {
        'member': 'task_project_management.group_member',
        'project_manager': 'task_project_management.group_project_manager',
        'admin_manager': 'task_project_management.group_admin_manager',
        'manager': 'task_project_management.group_manager',
    }

    def _get_role_group(self, role):
        return self.env.ref(self._role_group_map[role])

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('user_id') and vals.get('email') \
                    and not self.env.context.get('skip_user_creation'):
                role = vals.get('role', 'member')
                role_group = self._get_role_group(role)
                existing_user = self.env['res.users'].sudo().search(
                    [('login', '=', vals['email'])], limit=1)
                if existing_user:
                    linked = self.sudo().search(
                        [('user_id', '=', existing_user.id)], limit=1)
                    if not linked:
                        vals['user_id'] = existing_user.id
                        existing_user.sudo().write({
                            'groups_id': [(4, role_group.id)],
                        })
                else:
                    new_user = self.env['res.users'].sudo().with_context(
                        skip_member_creation=True,
                    ).create({
                        'name': vals.get('name', vals['email']),
                        'login': vals['email'],
                        'email': vals['email'],
                        'password': '123456',
                        'groups_id': [(4, role_group.id)],
                    })
                    vals['user_id'] = new_user.id
        records = super().create(vals_list)
        # Auto-add global managers to all existing projects
        for rec in records:
            if rec.role == 'manager' and rec.supervise_all_projects:
                all_projects = self.env['task.management.project'].sudo().search([])
                all_projects.sudo().write({
                    'manager_ids': [(4, rec.id)],
                })
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'role' in vals:
            role_group = self._get_role_group(vals['role'])
            all_groups = [
                self.env.ref(xml_id)
                for xml_id in self._role_group_map.values()
            ]
            for rec in self:
                if rec.user_id:
                    # Remove all TM groups, then add the correct one
                    rec.user_id.sudo().write({
                        'groups_id': (
                            [(3, g.id) for g in all_groups]
                            + [(4, role_group.id)]
                        ),
                    })
        # Handle manager oversight assignment changes
        if 'supervise_all_projects' in vals or 'supervised_project_ids' in vals:
            for rec in self.filtered(lambda m: m.role == 'manager'):
                all_projects = self.env['task.management.project'].sudo().search([])
                if rec.supervise_all_projects:
                    # Add to ALL projects
                    all_projects.sudo().write({
                        'manager_ids': [(4, rec.id)],
                    })
                else:
                    # Remove from projects not in supervised_project_ids
                    projects_to_remove = all_projects - rec.supervised_project_ids
                    projects_to_remove.sudo().write({
                        'manager_ids': [(3, rec.id)],
                    })
        return res

    def unlink(self):
        users_to_archive = self.mapped('user_id')
        # Clear the FK before deleting member records
        self.write({'user_id': False})
        res = super().unlink()
        if users_to_archive:
            users_to_archive.sudo().write({'active': False})
        return res

    def action_assign_task(self):
        """Open assign-task form pre-filled with this member."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Assign Task'),
            'res_model': 'task.management.task',
            'view_mode': 'form',
            'context': {
                'default_approval_status': 'assigned',
                'default_member_id': self.id,
                'form_view_initial_mode': 'edit',
            },
            'target': 'current',
        }

    def action_assign_task_from_project(self):
        """Open assign-task form pre-filled with this member and the parent project."""
        self.ensure_one()
        project_id = self.env.context.get('default_project_id') or \
            self.env.context.get('active_id')
        ctx = {
            'default_approval_status': 'assigned',
            'default_member_id': self.id,
            'form_view_initial_mode': 'edit',
        }
        if project_id:
            ctx['default_project_id'] = project_id
        return {
            'type': 'ir.actions.act_window',
            'name': _('Assign Task'),
            'res_model': 'task.management.task',
            'view_mode': 'form',
            'context': ctx,
            'target': 'current',
        }

    def action_change_password(self):
        """Open the change-password wizard for this member."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Change Password'),
            'res_model': 'task.management.change.password.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_member_id': self.id},
        }

    def action_open_member_report(self):
        """Open member performance report wizard pre-filled with this member."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Performance Report'),
            'res_model': 'task.management.member.performance.report',
            'view_mode': 'form',
            'target': 'current',
            'context': {'default_member_id': self.id},
        }

    @api.model
    def _get_member_for_user(self, user=None):
        """Get the member record for a given user (or current user)."""
        if user is None:
            user = self.env.user
        return self.search([('user_id', '=', user.id)], limit=1)
