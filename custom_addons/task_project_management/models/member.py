from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class TaskManagementMember(models.Model):
    _name = 'task.management.member'
    _description = 'Organization Member'
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
    ], string='Role', default='member', required=True, tracking=True)
    user_id = fields.Many2one(
        'res.users', string='Related User',
        ondelete='restrict', tracking=True,
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
        string='Archive Entries',
    )

    _sql_constraints = [
        ('email_unique', 'UNIQUE(email)',
         'A member with this email already exists.'),
        ('user_id_unique', 'UNIQUE(user_id)',
         'This user is already linked to another member.'),
    ]

    _role_group_map = {
        'member': 'task_project_management.group_member',
        'project_manager': 'task_project_management.group_project_manager',
        'admin_manager': 'task_project_management.group_admin_manager',
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
        return super().create(vals_list)

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
        return res

    def unlink(self):
        users_to_archive = self.mapped('user_id')
        # Clear the FK before deleting member records
        self.write({'user_id': False})
        res = super().unlink()
        if users_to_archive:
            users_to_archive.sudo().write({'active': False})
        return res

    @api.model
    def _get_member_for_user(self, user=None):
        """Get the member record for a given user (or current user)."""
        if user is None:
            user = self.env.user
        return self.search([('user_id', '=', user.id)], limit=1)
