from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError
from psycopg2 import IntegrityError


class TestMember(TransactionCase):
    """Tests for task.management.member model.
    Covers: MEM-1 through MEM-7"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Member = cls.env['task.management.member']
        cls.Project = cls.env['task.management.project']
        cls.Task = cls.env['task.management.task']

        # Create users
        cls.user_admin = cls.env.ref('base.user_admin')
        cls.user_member = cls.env['res.users'].create({
            'name': 'Test Member User',
            'login': 'test_member_user',
            'email': 'member_user@test.com',
            'groups_id': [(6, 0, [
                cls.env.ref('task_project_management.group_member').id,
            ])],
        })
        cls.user_pm = cls.env['res.users'].create({
            'name': 'Test PM User',
            'login': 'test_pm_user',
            'email': 'pm_user@test.com',
            'groups_id': [(6, 0, [
                cls.env.ref('task_project_management.group_project_manager').id,
            ])],
        })

    # --- MEM-1: Add member with all fields ---
    def test_create_member_all_fields(self):
        """MEM-1: Create member with all fields (name, email, phone,
        job title)."""
        member = self.Member.create({
            'name': 'Ahmed Hassan',
            'email': 'ahmed@company.com',
            'phone': '0501234567',
            'job_title': 'Senior Developer',
            'user_id': self.user_member.id,
        })
        self.assertTrue(member.id)
        self.assertEqual(member.name, 'Ahmed Hassan')
        self.assertEqual(member.email, 'ahmed@company.com')
        self.assertEqual(member.phone, '0501234567')
        self.assertEqual(member.job_title, 'Senior Developer')
        self.assertEqual(member.user_id, self.user_member)

    # --- MEM-2: Duplicate email ---
    def test_duplicate_email_blocked(self):
        """MEM-2: Adding a member with a duplicate email raises error."""
        self.Member.create({
            'name': 'First Member',
            'email': 'duplicate@company.com',
        })
        with self.assertRaises(IntegrityError):
            self.Member.create({
                'name': 'Second Member',
                'email': 'duplicate@company.com',
            })

    # --- MEM-3: Missing required fields ---
    def test_missing_name_raises(self):
        """MEM-3: Creating member with False name raises error."""
        with self.assertRaises(IntegrityError):
            self.Member.create({
                'name': False,
                'email': 'noname@company.com',
            })

    def test_missing_email_raises(self):
        """MEM-3: Creating member with False email raises error."""
        with self.assertRaises(IntegrityError):
            self.Member.create({
                'name': 'No Email',
                'email': False,
            })

    # --- MEM-4: Edit member info ---
    def test_edit_member(self):
        """MEM-4: Editing member info updates successfully."""
        member = self.Member.create({
            'name': 'Original Name',
            'email': 'original@company.com',
            'job_title': 'Developer',
        })
        member.write({
            'name': 'Updated Name',
            'job_title': 'Senior Developer',
        })
        self.assertEqual(member.name, 'Updated Name')
        self.assertEqual(member.job_title, 'Senior Developer')

    # --- MEM-5: Remove member from project (tasks kept) ---
    def test_remove_member_from_project_tasks_kept(self):
        """MEM-5: Removing a member from a project marks them as removed
        but keeps their existing tasks."""
        pm_member = self.Member.create({
            'name': 'PM',
            'email': 'pm_mem5@company.com',
            'user_id': self.user_pm.id,
        })
        member = self.Member.create({
            'name': 'Worker',
            'email': 'worker_mem5@company.com',
            'user_id': self.user_member.id,
        })
        project = self.Project.create({
            'name': 'Test Project MEM5',
            'project_manager_ids': [(4, pm_member.id)],
            'member_ids': [(4, member.id)],
        })
        # Create a task for the member
        task = self.Task.with_user(self.user_member).create({
            'date': '2026-02-19',
            'description': 'Test task',
            'project_id': project.id,
            'member_id': member.id,
            'time_from': 9.0,
            'time_to': 12.0,
        })
        # Remove member from project
        project.write({
            'member_ids': [(3, member.id)],
        })
        # Member is in removed_member_ids
        self.assertIn(member, project.removed_member_ids)
        # Task still exists
        self.assertTrue(task.exists())
        self.assertEqual(task.member_id, member)

    # --- MEM-6: Removed member cannot submit new tasks ---
    def test_removed_member_cannot_submit_task(self):
        """MEM-6: A removed member cannot submit new tasks to the project."""
        pm_member = self.Member.create({
            'name': 'PM',
            'email': 'pm_mem6@company.com',
            'user_id': self.user_pm.id,
        })
        member = self.Member.create({
            'name': 'Worker',
            'email': 'worker_mem6@company.com',
            'user_id': self.user_member.id,
        })
        project = self.Project.create({
            'name': 'Test Project MEM6',
            'project_manager_ids': [(4, pm_member.id)],
            'member_ids': [(4, member.id)],
        })
        # Remove member
        project.write({
            'member_ids': [(3, member.id)],
        })
        # Try to create task — should fail (member not in project)
        with self.assertRaises(ValidationError):
            self.Task.with_user(self.user_member).create({
                'date': '2026-02-19',
                'description': 'Should fail',
                'project_id': project.id,
                'member_id': member.id,
                'time_from': 9.0,
                'time_to': 12.0,
            })

    # --- MEM-7: Removed member's tasks still in reports ---
    def test_removed_member_tasks_in_reports(self):
        """MEM-7: Tasks of removed members are still visible
        in project reports."""
        pm_member = self.Member.create({
            'name': 'PM',
            'email': 'pm_mem7@company.com',
            'user_id': self.user_pm.id,
        })
        member = self.Member.create({
            'name': 'Worker',
            'email': 'worker_mem7@company.com',
            'user_id': self.user_member.id,
        })
        project = self.Project.create({
            'name': 'Test Project MEM7',
            'project_manager_ids': [(4, pm_member.id)],
            'member_ids': [(4, member.id)],
        })
        # Create task
        task = self.Task.with_user(self.user_member).create({
            'date': '2026-02-19',
            'description': 'Historical task',
            'project_id': project.id,
            'member_id': member.id,
            'time_from': 9.0,
            'time_to': 12.0,
        })
        # Remove member
        project.write({
            'member_ids': [(3, member.id)],
        })
        # Task still appears in project's tasks
        self.assertIn(task, project.task_ids)
        self.assertEqual(project.task_count, 1)

    # --- Helper: _get_member_for_user ---
    def test_get_member_for_user(self):
        """Test _get_member_for_user returns correct member record."""
        member = self.Member.create({
            'name': 'Linked Member',
            'email': 'linked@company.com',
            'user_id': self.user_member.id,
        })
        found = self.Member._get_member_for_user(self.user_member)
        self.assertEqual(found, member)

    def test_get_member_for_user_not_found(self):
        """Test _get_member_for_user returns empty recordset
        when no member linked."""
        user = self.env['res.users'].create({
            'name': 'Orphan User',
            'login': 'orphan_user',
            'email': 'orphan@test.com',
        })
        found = self.Member._get_member_for_user(user)
        self.assertFalse(found)

    # --- Unique user_id constraint ---
    def test_duplicate_user_id_blocked(self):
        """A user cannot be linked to two member records."""
        self.Member.create({
            'name': 'Member A',
            'email': 'member_a@company.com',
            'user_id': self.user_member.id,
        })
        with self.assertRaises(IntegrityError):
            self.Member.create({
                'name': 'Member B',
                'email': 'member_b@company.com',
                'user_id': self.user_member.id,
            })
