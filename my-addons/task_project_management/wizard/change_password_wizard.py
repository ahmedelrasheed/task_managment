from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ChangePasswordWizard(models.TransientModel):
    _name = 'task.management.change.password.wizard'
    _description = 'Change Member Password'

    member_id = fields.Many2one(
        'task.management.member', string='Member',
        required=True, readonly=True,
    )
    new_password = fields.Char(string='New Password', required=True)

    def action_confirm(self):
        self.ensure_one()
        if not self.env.user.has_group(
                'task_project_management.group_admin_manager'):
            raise UserError(_('Only Admin Managers can change passwords.'))
        if not self.member_id.user_id:
            raise UserError(_('This member has no linked user account.'))
        self.member_id.user_id.sudo().password = self.new_password
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {
                    'title': _('Password Changed'),
                    'message': _('Password for %s has been updated.',
                                 self.member_id.name),
                    'type': 'success',
                    'sticky': False,
                }}
