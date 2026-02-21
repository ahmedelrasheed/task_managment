from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError
from datetime import date, timedelta


class TestProject(TransactionCase):
    """Tests for task.management.project model.
    Covers: PROJ-1 through PROJ-14"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Member = cls.env['task.management.member']
        cls.Project = cls.env['task.management.project']
        cls.Task = cls.env['task.management.task']

        cls.user_admin = cls.env.ref('base.user_admin')
        cls.user_pm = cls.env['res.users'].create({
            'name': 'PM User',
            'login': 'proj_pm',
            'email': 'proj_pm@test.com',
            'groups_id': [(6, 0, [
                cls.env.ref(
                    'task_project_management.group_project_manager').id,
            ])],
        })
        cls.user_pm2 = cls.env['res.users'].create({
            'name': 'PM User 2',
            'login': 'proj_pm2',
            'email': 'proj_pm2@test.com',
            'groups_id': [(6, 0, [
                cls.env.ref(
                    'task_project_management.group_project_manager').id,
            ])],
        })
        cls.user_member = cls.env['res.users'].create({
            'name': 'Member User',
            'login': 'proj_member',
            'email': 'proj_member@test.com',
            'groups_id': [(6, 0, [
                cls.env.ref('task_project_management.group_member').id,
            ])],
        })

        cls.pm_member = cls.Member.create({
            'name': 'PM',
            'email': 'pm@proj.com',
            'user_id': cls.user_pm.id,
        })
        cls.pm_member2 = cls.Member.create({
            'name': 'PM2',
            'email': 'pm2@proj.com',
            'user_id': cls.user_pm2.id,
        })
        cls.regular_member = cls.Member.create({
            'name': 'Regular',
            'email': 'regular@proj.com',
            'user_id': cls.user_member.id,
        })

    # --- PROJ-1: Create project with all fields ---
    def test_create_project_all_fields(self):
        """PROJ-1: Create project with all fields — defaults to Active."""
        project = self.Project.create({
            'name': 'Website Redesign',
            'description': 'Redesign the company website',
            'expected_end_date': '2026-06-01',
            'project_manager_ids': [(4, self.pm_member.id)],
            'member_ids': [(4, self.regular_member.id)],
        })
        self.assertTrue(project.id)
        self.assertEqual(project.status, 'active')
        self.assertIn(self.pm_member, project.project_manager_ids)
        self.assertIn(self.regular_member, project.member_ids)

    # --- PROJ-2: Create project without PM ---
    def test_create_project_no_pm_raises(self):
        """PROJ-2: Project must have at least one PM."""
        with self.assertRaises(ValidationError):
            self.Project.create({
                'name': 'No PM Project',
                'project_manager_ids': [(6, 0, [])],
            })

    # --- PROJ-4: Multiple PMs ---
    def test_create_project_multiple_pms(self):
        """PROJ-4: Create project with multiple PMs."""
        project = self.Project.create({
            'name': 'Multi PM Project',
            'project_manager_ids': [
                (4, self.pm_member.id),
                (4, self.pm_member2.id),
            ],
            'member_ids': [(4, self.regular_member.id)],
        })
        self.assertEqual(len(project.project_manager_ids), 2)
        self.assertIn(self.pm_member, project.project_manager_ids)
        self.assertIn(self.pm_member2, project.project_manager_ids)

    # --- PROJ-5: PM cannot also be member ---
    def test_pm_cannot_be_member_same_project(self):
        """PROJ-5: Assigning a PM as member of the same project is blocked."""
        with self.assertRaises(ValidationError):
            self.Project.create({
                'name': 'PM As Member',
                'project_manager_ids': [(4, self.pm_member.id)],
                'member_ids': [(4, self.pm_member.id)],
            })

    # --- PROJ-6: PM of project A, member of project B ---
    def test_pm_of_one_member_of_another(self):
        """PROJ-6: A person can be PM of one project and member of another."""
        project_a = self.Project.create({
            'name': 'Project A',
            'project_manager_ids': [(4, self.pm_member.id)],
            'member_ids': [(4, self.regular_member.id)],
        })
        project_b = self.Project.create({
            'name': 'Project B',
            'project_manager_ids': [(4, self.pm_member2.id)],
            'member_ids': [(4, self.pm_member.id)],
        })
        self.assertIn(self.pm_member, project_a.project_manager_ids)
        self.assertIn(self.pm_member, project_b.member_ids)

    # --- PROJ-7: On Hold — members can't submit ---
    def test_on_hold_blocks_task_submission(self):
        """PROJ-7: Members cannot submit tasks to an On Hold project."""
        project = self.Project.create({
            'name': 'On Hold Project',
            'project_manager_ids': [(4, self.pm_member.id)],
            'member_ids': [(4, self.regular_member.id)],
        })
        project.write({'status': 'on_hold'})
        with self.assertRaises(ValidationError):
            self.Task.with_user(self.user_member).create({
                'date': '2026-02-19',
                'description': 'Should be blocked',
                'project_id': project.id,
                'member_id': self.regular_member.id,
                'time_from': 9.0,
                'time_to': 12.0,
            })

    # --- PROJ-8: Completed — locked for non-admin ---
    def test_completed_blocks_non_admin(self):
        """PROJ-8: Only admin can submit tasks to completed project."""
        project = self.Project.create({
            'name': 'Completed Project',
            'project_manager_ids': [(4, self.pm_member.id)],
            'member_ids': [(4, self.regular_member.id)],
        })
        project.write({'status': 'completed'})
        with self.assertRaises(ValidationError):
            self.Task.with_user(self.user_member).create({
                'date': '2026-02-19',
                'description': 'Member task on completed',
                'project_id': project.id,
                'member_id': self.regular_member.id,
                'time_from': 9.0,
                'time_to': 12.0,
            })

    # --- PROJ-9: Archived — no tasks ---
    def test_archived_blocks_all_tasks(self):
        """PROJ-9: No tasks can be submitted to archived projects."""
        project = self.Project.create({
            'name': 'Archived Project',
            'project_manager_ids': [(4, self.pm_member.id)],
            'member_ids': [(4, self.regular_member.id)],
        })
        project.write({'status': 'archived'})
        with self.assertRaises(ValidationError):
            self.Task.create({
                'date': '2026-02-19',
                'description': 'Task on archived',
                'project_id': project.id,
                'member_id': self.regular_member.id,
                'time_from': 9.0,
                'time_to': 12.0,
            })

    # --- PROJ-10: Restore archived project ---
    def test_restore_archived_project(self):
        """PROJ-10: Restoring an archived project makes it visible again."""
        project = self.Project.create({
            'name': 'Restore Project',
            'project_manager_ids': [(4, self.pm_member.id)],
            'member_ids': [(4, self.regular_member.id)],
        })
        project.write({'status': 'archived'})
        self.assertEqual(project.status, 'archived')
        project.write({'status': 'active'})
        self.assertEqual(project.status, 'active')

    # --- PROJ-11: Deadline with pending tasks triggers cron ---
    def test_deadline_cron_notification(self):
        """PROJ-11: Project reaching end date with pending tasks
        triggers notification."""
        project = self.Project.create({
            'name': 'Deadline Project',
            'expected_end_date': date.today(),
            'project_manager_ids': [(4, self.pm_member.id)],
            'member_ids': [(4, self.regular_member.id)],
        })
        # Create a pending task
        self.Task.create({
            'date': date.today().isoformat(),
            'description': 'Pending task',
            'project_id': project.id,
            'member_id': self.regular_member.id,
            'time_from': 9.0,
            'time_to': 12.0,
        })
        messages_before = len(project.message_ids)
        self.Project._cron_check_project_deadlines()
        project.invalidate_recordset()
        messages_after = len(project.message_ids)
        self.assertGreater(messages_after, messages_before)

    # --- PROJ-12: Phase-based progress ---
    def test_phase_based_progress(self):
        """Progress is computed from phases."""
        project = self.Project.create({
            'name': 'Phase Project',
            'project_manager_ids': [(4, self.pm_member.id)],
            'member_ids': [(4, self.regular_member.id)],
        })
        Phase = self.env['task.management.project.phase']
        Phase.create({
            'name': 'Design', 'project_id': project.id,
            'percentage': 30, 'completion_rate': 100,
        })
        Phase.create({
            'name': 'Development', 'project_id': project.id,
            'percentage': 50, 'completion_rate': 50,
        })
        Phase.create({
            'name': 'Testing', 'project_id': project.id,
            'percentage': 20, 'completion_rate': 0,
        })
        project.invalidate_recordset()
        # 30*100/100 + 50*50/100 + 20*0/100 = 30 + 25 + 0 = 55%
        self.assertAlmostEqual(project.progress_percentage, 55.0, places=1)

    # --- PROJ-13: Edit expected end date ---
    def test_edit_expected_end_date(self):
        """PROJ-13: Editing expected end date updates it."""
        project = self.Project.create({
            'name': 'Date Project',
            'expected_end_date': '2026-06-01',
            'project_manager_ids': [(4, self.pm_member.id)],
        })
        project.write({'expected_end_date': '2026-09-01'})
        self.assertEqual(str(project.expected_end_date), '2026-09-01')

    # --- PROJ-14: Member in multiple projects ---
    def test_member_in_multiple_projects(self):
        """PROJ-14: A member can be assigned to multiple projects."""
        project_a = self.Project.create({
            'name': 'Project Alpha',
            'project_manager_ids': [(4, self.pm_member.id)],
            'member_ids': [(4, self.regular_member.id)],
        })
        project_b = self.Project.create({
            'name': 'Project Beta',
            'project_manager_ids': [(4, self.pm_member2.id)],
            'member_ids': [(4, self.regular_member.id)],
        })
        self.assertIn(self.regular_member, project_a.member_ids)
        self.assertIn(self.regular_member, project_b.member_ids)
        self.assertEqual(len(self.regular_member.member_project_ids), 2)

    # --- Computed fields ---
    def test_total_logged_hours_only_approved(self):
        """Total logged hours only counts approved tasks."""
        project = self.Project.create({
            'name': 'Hours Project',
            'project_manager_ids': [(4, self.pm_member.id)],
            'member_ids': [(4, self.regular_member.id)],
        })
        task1 = self.Task.create({
            'date': date.today().isoformat(),
            'description': 'Approved task',
            'project_id': project.id,
            'member_id': self.regular_member.id,
            'time_from': 9.0,
            'time_to': 12.0,
        })
        task1.write({'approval_status': 'approved'})
        task2 = self.Task.create({
            'date': date.today().isoformat(),
            'description': 'Pending task',
            'project_id': project.id,
            'member_id': self.regular_member.id,
            'time_from': 13.0,
            'time_to': 15.0,
        })
        project.invalidate_recordset()
        # Only 3 hours from approved task, not 5 total
        self.assertAlmostEqual(project.total_logged_hours, 3.0, places=1)

    def test_progress_percentage_full(self):
        """All phases at 100% completion equals 100% progress."""
        project = self.Project.create({
            'name': 'Full Progress',
            'project_manager_ids': [(4, self.pm_member.id)],
            'member_ids': [(4, self.regular_member.id)],
        })
        Phase = self.env['task.management.project.phase']
        Phase.create({
            'name': 'Phase 1', 'project_id': project.id,
            'percentage': 60, 'completion_rate': 100,
        })
        Phase.create({
            'name': 'Phase 2', 'project_id': project.id,
            'percentage': 40, 'completion_rate': 100,
        })
        project.invalidate_recordset()
        self.assertAlmostEqual(project.progress_percentage, 100.0, places=1)
