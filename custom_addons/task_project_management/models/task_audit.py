from odoo import models, fields


class TaskManagementTaskAudit(models.Model):
    _name = 'task.management.task.audit'
    _description = 'Task Approval Audit Trail'
    _order = 'changed_at desc'

    task_id = fields.Many2one(
        'task.management.task', string='Task',
        required=True, ondelete='cascade', index=True,
    )
    old_status = fields.Selection([
        ('assigned', 'Assigned'),
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='Previous Status')
    new_status = fields.Selection([
        ('assigned', 'Assigned'),
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='New Status', required=True)
    changed_by = fields.Many2one(
        'res.users', string='Changed By',
        required=True, default=lambda self: self.env.uid,
    )
    changed_at = fields.Datetime(
        string='Changed At',
        required=True, default=fields.Datetime.now,
    )
    previous_comment = fields.Text(string='Previous Comment')
    comment = fields.Text(string='Comment')
