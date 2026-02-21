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

    @api.constrains('completion_rate')
    def _check_completion_rate(self):
        for phase in self:
            if phase.completion_rate < 0 or phase.completion_rate > 100:
                raise ValidationError(
                    _('Completion rate must be between 0 and 100%.'))

    @api.constrains('percentage')
    def _check_percentage_positive(self):
        for phase in self:
            if phase.percentage <= 0:
                raise ValidationError(
                    _('Phase weight must be greater than 0%.'))
