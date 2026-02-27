from odoo import models, fields, api


class ResUsers(models.Model):
    _inherit = 'res.users'

    task_font_size = fields.Selection([
        ('small', 'Small'),
        ('medium', 'Medium'),
        ('large', 'Large'),
        ('xlarge', 'Extra Large'),
    ], string='Font Size', default='medium')

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ['task_font_size']

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ['task_font_size']

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        if self.env.context.get('skip_member_creation'):
            return users
        Member = self.env['task.management.member'].sudo()
        for user in users:
            if not user.login:
                continue
            existing = Member.search(
                [('email', '=', user.login), ('user_id', '=', False)],
                limit=1,
            )
            if existing:
                existing.write({'user_id': user.id})
            else:
                Member.with_context(skip_user_creation=True).create({
                    'name': user.name or user.login,
                    'email': user.login,
                    'user_id': user.id,
                })
        return users

    def write(self, vals):
        res = super().write(vals)
        if 'groups_id' in vals:
            self._sync_role_to_member()
        return res

    def _sync_role_to_member(self):
        """Sync the Task Management role from user groups to member record."""
        Member = self.env['task.management.member'].sudo()
        group_admin = self.env.ref(
            'task_project_management.group_admin_manager')
        group_pm = self.env.ref(
            'task_project_management.group_project_manager')
        group_member = self.env.ref(
            'task_project_management.group_member')
        for user in self:
            member = Member.search(
                [('user_id', '=', user.id)], limit=1)
            if not member:
                continue
            if group_admin in user.groups_id:
                new_role = 'admin_manager'
            elif group_pm in user.groups_id:
                new_role = 'project_manager'
            elif group_member in user.groups_id:
                new_role = 'member'
            else:
                continue
            if member.role != new_role:
                member.write({'role': new_role})
