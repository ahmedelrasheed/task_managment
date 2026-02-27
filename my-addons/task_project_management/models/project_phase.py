from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class TaskManagementProjectPhase(models.Model):
    _name = 'task.management.project.phase'
    _description = 'Project Phase'
    _order = 'sequence, id'

    name = fields.Char(string='Phase Name', required=True)
    project_id = fields.Many2one(
        'task.management.project', string='Project',
        required=True, ondelete='cascade',
    )
    sequence = fields.Integer(string='Sequence', default=10)
    is_active = fields.Boolean(string='Active', default=True)
    percentage = fields.Float(
        string='Weight (%)', required=True,
        help='Weight of this phase as a percentage of total project. '
             'All phases must sum to 100%.',
    )
    completion_rate = fields.Float(
        string='Completion (%)', default=0.0,
        help='How complete this phase is (0-100%).',
    )
    effective_progress = fields.Float(
        string='Effective Progress',
        compute='_compute_effective_progress',
        store=True,
    )

    @api.depends('percentage', 'completion_rate')
    def _compute_effective_progress(self):
        for phase in self:
            phase.effective_progress = (
                phase.percentage * phase.completion_rate / 100.0)

    @api.onchange('completion_rate')
    def _onchange_completion_rate(self):
        if self.completion_rate >= 100:
            self.is_active = False

    @api.constrains('completion_rate')
    def _check_completion_rate(self):
        for phase in self:
            if phase.completion_rate < 0 or phase.completion_rate > 100:
                raise ValidationError(
                    _('Completion rate must be between 0 and 100%.'))

    def write(self, vals):
        res = super().write(vals)
        if 'completion_rate' in vals:
            for phase in self:
                if phase.completion_rate >= 100 and phase.is_active:
                    super(TaskManagementProjectPhase, phase).write({'is_active': False})
        return res

    @api.constrains('percentage')
    def _check_percentage_positive(self):
        for phase in self:
            if phase.percentage <= 0:
                raise ValidationError(
                    _('Phase weight must be greater than 0%.'))

    def action_delete_phase(self):
        """Delete phase via button with confirmation dialog."""
        self.ensure_one()
        project_id = self.project_id.id
        self.unlink()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'task.management.project',
            'res_id': project_id,
            'view_mode': 'form',
            'target': 'current',
        }
