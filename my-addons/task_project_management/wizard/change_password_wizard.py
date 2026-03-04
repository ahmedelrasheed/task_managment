from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ChangePasswordWizard(models.TransientModel):
    _name = 'task.management.change.password.wizard'
    _description = 'Change Member Password'

    member_id = fields.Many2one(
        'task.management.member', string='Member',
        required=True, readonly=True,
    )
    current_password = fields.Char(string='Current Password')
    new_password = fields.Char(string='New Password', required=True)
    confirm_password = fields.Char(string='Confirm Password', required=True)
    is_self = fields.Boolean(compute='_compute_is_self')

    @api.depends('member_id')
    def _compute_is_self(self):
        for rec in self:
            rec.is_self = (
                rec.member_id and
                rec.member_id.user_id.id == self.env.uid
            )

    def action_confirm(self):
        self.ensure_one()
        is_admin = self.env.user.has_group(
            'task_project_management.group_admin_manager')
        is_self = self.member_id.user_id.id == self.env.uid

        if not is_admin and not is_self:
            raise UserError(
                _('Only Admin Managers or the member themselves '
                  'can change this password.'))

        if not self.member_id.user_id:
            raise UserError(_('This member has no linked user account.'))

        # Validate new password matches confirm
        if self.new_password != self.confirm_password:
            raise UserError(_('New password and confirm password do not match.'))

        # If user is changing their own password, verify current password
        if is_self:
            if not self.current_password:
                raise UserError(_('Please enter your current password.'))
            try:
                self.env['res.users'].sudo()._check_credentials(
                    self.current_password, {'interactive': True})
            except Exception:
                raise UserError(_('Current password is incorrect.'))

        self.member_id.user_id.sudo().password = self.new_password
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {
                    'title': _('Password Changed'),
                    'message': _('Password for %s has been updated.',
                                 self.member_id.name),
                    'type': 'success',
                    'sticky': False,
                }}
