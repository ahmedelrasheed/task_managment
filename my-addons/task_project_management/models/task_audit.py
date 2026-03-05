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
        default=lambda self: self.env.uid,
        ondelete='set null',
    )
    changed_at = fields.Datetime(
        string='Changed At',
        required=True, default=fields.Datetime.now,
    )
    previous_comment = fields.Text(string='Previous Comment')
    comment = fields.Text(string='Comment')

    # --- Task Snapshot Fields ---
    snap_date = fields.Date(string='Task Date')
    snap_description = fields.Text(string='Task Description')
    snap_project_name = fields.Char(string='Project Name')
    snap_phase_name = fields.Char(string='Phase Name')
    snap_time_from = fields.Float(string='Time From')
    snap_time_to = fields.Float(string='Time To')
    snap_duration_hours = fields.Float(string='Duration (Hours)')
    snap_manager_comment = fields.Text(string='Manager Comment')
    snap_approval_status = fields.Selection([
        ('assigned', 'Assigned'),
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='Status at Snapshot')
    snap_task_type = fields.Selection([
        ('initiated', 'Initiated'),
        ('assigned', 'Assigned'),
    ], string='Task Type')
    snap_assignment_name = fields.Char(string='Task Name')
    snap_assignment_description = fields.Text(string='Assignment Instructions')
    snap_due_date = fields.Date(string='Due Date')
    snap_attachment_names = fields.Text(string='Attachments')
    snap_assignment_attachment_names = fields.Text(string='Reference Files')
    snap_attachment_ids = fields.Many2many(
        'ir.attachment', 'audit_snap_attachment_rel',
        'audit_id', 'attachment_id',
        string='Attached Files',
    )
    snap_assignment_attachment_ids = fields.Many2many(
        'ir.attachment', 'audit_snap_assign_attachment_rel',
        'audit_id', 'attachment_id',
        string='Reference Attached Files',
    )
