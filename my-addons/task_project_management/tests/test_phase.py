from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestProjectPhase(TransactionCase):
    """Tests for task.management.project.phase model."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Project = cls.env['task.management.project']
        cls.Phase = cls.env['task.management.project.phase']
        cls.Member = cls.env['task.management.member']

        cls.user_pm = cls.env['res.users'].create({
            'name': 'PM Phase Test',
            'login': 'pm_phase_test',
            'email': 'pm_phase@test.com',
            'groups_id': [(6, 0, [
                cls.env.ref(
                    'task_project_management.group_project_manager').id,
            ])],
        })
        cls.user_member = cls.env['res.users'].create({
            'name': 'Member Phase Test',
            'login': 'member_phase_test',
            'email': 'member_phase@test.com',
            'groups_id': [(6, 0, [
                cls.env.ref('task_project_management.group_member').id,
            ])],
        })
        cls.pm_member = cls.Member.create({
            'name': 'PM Phase',
            'email': 'pm_phase_m@test.com',
            'user_id': cls.user_pm.id,
        })
        cls.regular_member = cls.Member.create({
            'name': 'Member Phase',
            'email': 'member_phase_m@test.com',
            'user_id': cls.user_member.id,
        })

    def _create_project(self, name='Test Phase Project'):
        return self.Project.create({
            'name': name,
            'project_manager_ids': [(4, self.pm_member.id)],
            'member_ids': [(4, self.regular_member.id)],
        })

    def test_phase_crud(self):
        """Test basic phase creation, read, update, delete."""
        project = self._create_project()
        phase = self.Phase.create({
            'name': 'Design',
            'project_id': project.id,
            'percentage': 100,
            'completion_rate': 0,
        })
        self.assertTrue(phase.id)
        self.assertEqual(phase.name, 'Design')
        self.assertEqual(phase.percentage, 100)
        self.assertEqual(phase.completion_rate, 0)
        self.assertAlmostEqual(phase.effective_progress, 0.0)

        # Update completion
        phase.write({'completion_rate': 50})
        self.assertAlmostEqual(phase.effective_progress, 50.0)

        # Delete
        phase.unlink()
        self.assertFalse(phase.exists())

    def test_completion_rate_bounds(self):
        """Completion rate must be between 0 and 100."""
        project = self._create_project()
        with self.assertRaises(ValidationError):
            self.Phase.create({
                'name': 'Bad Phase',
                'project_id': project.id,
                'percentage': 100,
                'completion_rate': 150,
            })
        with self.assertRaises(ValidationError):
            self.Phase.create({
                'name': 'Bad Phase',
                'project_id': project.id,
                'percentage': 100,
                'completion_rate': -10,
            })

    def test_percentage_must_be_positive(self):
        """Phase weight must be greater than 0."""
        project = self._create_project()
        with self.assertRaises(ValidationError):
            self.Phase.create({
                'name': 'Zero Phase',
                'project_id': project.id,
                'percentage': 0,
            })

    def test_phase_percentage_sum_constraint(self):
        """Phase weights must sum to 100% when saving project."""
        project = self._create_project()
        self.Phase.create({
            'name': 'Phase A',
            'project_id': project.id,
            'percentage': 60,
        })
        self.Phase.create({
            'name': 'Phase B',
            'project_id': project.id,
            'percentage': 30,
        })
        # Sum is 90%, not 100% - should fail on project constraint
        with self.assertRaises(ValidationError):
            project.write({'phase_ids': [(0, 0, {
                'name': 'Trigger',
                'percentage': 1,
            })]})

    def test_progress_from_phases(self):
        """Project progress is computed from phases."""
        project = self._create_project()
        self.Phase.create({
            'name': 'Design',
            'project_id': project.id,
            'percentage': 30,
            'completion_rate': 100,
        })
        self.Phase.create({
            'name': 'Development',
            'project_id': project.id,
            'percentage': 50,
            'completion_rate': 50,
        })
        self.Phase.create({
            'name': 'Testing',
            'project_id': project.id,
            'percentage': 20,
            'completion_rate': 0,
        })
        project.invalidate_recordset()
        # 30*100/100 + 50*50/100 + 20*0/100 = 30 + 25 + 0 = 55
        self.assertAlmostEqual(project.progress_percentage, 55.0, places=1)

    def test_no_phases_zero_progress(self):
        """Project with no phases has 0% progress."""
        project = self._create_project()
        self.assertAlmostEqual(project.progress_percentage, 0.0)

    def test_effective_progress_computed(self):
        """Effective progress = percentage * completion_rate / 100."""
        project = self._create_project()
        phase = self.Phase.create({
            'name': 'Only Phase',
            'project_id': project.id,
            'percentage': 100,
            'completion_rate': 75,
        })
        self.assertAlmostEqual(phase.effective_progress, 75.0)
