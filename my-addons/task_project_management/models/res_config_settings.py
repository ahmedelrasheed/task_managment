from odoo import api, models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    task_past_date_limit = fields.Integer(
        string='Past Date Entry Limit (Days)',
        default=7,
        config_parameter='task_project_management.past_date_limit',
        help='Number of days in the past a member can enter tasks. '
             'Set to 0 to allow only today. '
             'Beyond this limit, only PM or Admin can enter tasks.',
    )

    def set_values(self):
        super().set_values()
        # Force-write integer params that can be 0 (Odoo deletes falsy values)
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('task_project_management.past_date_limit',
                       str(self.task_past_date_limit))
        ICP.set_param('task_project_management.monthly_off_days',
                       str(self.task_monthly_off_days))
    task_allow_after_midnight = fields.Boolean(
        string='Allow After-Midnight Tasks',
        default=False,
        config_parameter='task_project_management.allow_after_midnight',
        help='If enabled, members can log tasks that span past midnight '
             '(e.g., 23:00 to 01:00).',
    )
    task_max_attachment_size = fields.Integer(
        string='Max Attachment Size (MB)',
        default=100,
        config_parameter='task_project_management.max_attachment_size',
        help='Maximum allowed file size for task attachments in megabytes.',
    )
    task_daily_hours_average = fields.Float(
        string='Daily Hours Target',
        default=8.0,
        config_parameter='task_project_management.daily_hours_average',
        help='Target average daily working hours for member performance.',
    )
    task_weekly_hours_average = fields.Float(
        string='Weekly Hours Target',
        default=40.0,
        config_parameter='task_project_management.weekly_hours_average',
        help='Target average weekly working hours for member performance.',
    )
    task_monthly_off_days = fields.Integer(
        string='Monthly Off Days',
        default=0,
        config_parameter='task_project_management.monthly_off_days',
        help='Number of off days (holidays) per month to subtract from working days when calculating monthly target.',
    )
