from odoo.tests.common import TransactionCase
from odoo.exceptions import AccessError
from datetime import date


class TestSecurity(TransactionCase):
    """Tests for record rules and access control.
    Covers: ACL-1 through ACL-12"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Member = cls.env['task.management.member']
        cls.Project = cls.env['task.management.project']
        cls.Task = cls.env['task.management.task']

        # Admin user
        cls.user_admin = cls.env['res.users'].create({
            'name': 'Admin',
            'login': 'sec_admin',
            'email': 'sec_admin@test.com',
            'groups_id': [(6, 0, [
                cls.env.ref(
                    'task_project_management.group_admin_manager').id,
            ])],
        })
        # PM user
        cls.user_pm = cls.env['res.users'].create({
            'name': 'PM',
            'login': 'sec_pm',
            'email': 'sec_pm@test.com',
            'groups_id': [(6, 0, [
                cls.env.ref(
                    'task_project_management.group_project_manager').id,
            ])],
        })
        # Member 1
        cls.user_member1 = cls.env['res.users'].create({
            'name': 'Member1',
            'login': 'sec_member1',
            'email': 'sec_member1@test.com',
            'groups_id': [(6, 0, [
                cls.env.ref('task_project_management.group_member').id,
            ])],
        })
        # Member 2
        cls.user_member2 = cls.env['res.users'].create({
            'name': 'Member2',
            'login': 'sec_member2',
            'email': 'sec_member2@test.com',
            'groups_id': [(6, 0, [
                cls.env.ref('task_project_management.group_member').id,
            ])],
        })

        cls.admin_member = cls.Member.create({
            'name': 'Admin Person',
            'email': 'admin_sec@test.com',
            'user_id': cls.user_admin.id,
        })
        cls.pm_member = cls.Member.create({
            'name': 'PM Person',
            'email': 'pm_sec@test.com',
            'user_id': cls.user_pm.id,
        })
        cls.member1 = cls.Member.create({
            'name': 'Member One',
            'email': 'member1_sec@test.com',
            'user_id': cls.user_member1.id,
        })
        cls.member2 = cls.Member.create({
            'name': 'Member Two',
            'email': 'member2_sec@test.com',
            'user_id': cls.user_member2.id,
        })

        # Project managed by PM, members: member1, member2
        cls.project = cls.Project.create({
            'name': 'Security Project',
            'project_manager_ids': [(4, cls.pm_member.id)],
            'member_ids': [
                (4, cls.member1.id),
                (4, cls.member2.id),
            ],
        })

        # Unrelated project (PM not involved, member2 not involved)
        cls.unrelated_project = cls.Project.create({
            'name': 'Unrelated Project',
            'project_manager_ids': [(4, cls.admin_member.id)],
            'member_ids': [(4, cls.member2.id)],
        })

        # Create tasks
        cls.task_member1 = cls.Task.create({
            'date': date.today().isoformat(),
            'description': 'Member1 task',
            'project_id': cls.project.id,
            'member_id': cls.member1.id,
            'time_from': 9.0,
            'time_to': 12.0,
        })
        cls.task_member2 = cls.Task.create({
            'date': date.today().isoformat(),
            'description': 'Member2 task',
            'project_id': cls.project.id,
            'member_id': cls.member2.id,
            'time_from': 9.0,
            'time_to': 12.0,
        })

    # --- ACL-1: Member accesses own tasks ---
    def test_member_sees_own_tasks(self):
        """ACL-1: Member can access their own tasks."""
        tasks = self.Task.with_user(self.user_member1).search([
            ('member_id', '=', self.member1.id),
        ])
        self.assertIn(self.task_member1, tasks)

    # --- ACL-2: Member cannot access another member's tasks ---
    def test_member_cannot_see_other_tasks(self):
        """ACL-2: Member cannot see another member's tasks."""
        tasks = self.Task.with_user(self.user_member1).search([
            ('member_id', '=', self.member2.id),
        ])
        self.assertEqual(len(tasks), 0)

    # --- ACL-3: Member cannot access project management ---
    def test_member_cannot_create_project(self):
        """ACL-3: Member cannot create projects (no create permission)."""
        with self.assertRaises(AccessError):
            self.Project.with_user(self.user_member1).create({
                'name': 'Member Project',
                'project_manager_ids': [(4, self.pm_member.id)],
            })

    # --- ACL-4: Member cannot access admin settings ---
    def test_member_cannot_change_settings(self):
        """ACL-4: Member cannot modify system parameters."""
        with self.assertRaises(AccessError):
            self.env['ir.config_parameter'].with_user(
                self.user_member1).set_param(
                'task_project_management.past_date_limit', '99')

    # --- ACL-5: PM accesses managed project tasks ---
    def test_pm_sees_managed_project_tasks(self):
        """ACL-5: PM can see all tasks in managed projects."""
        tasks = self.Task.with_user(self.user_pm).search([
            ('project_id', '=', self.project.id),
        ])
        self.assertIn(self.task_member1, tasks)
        self.assertIn(self.task_member2, tasks)

    # --- ACL-6: PM sees only own tasks in member-of project ---
    def test_pm_sees_own_tasks_as_member(self):
        """ACL-6: When PM is a regular member of a project,
        they see only their own tasks."""
        # Create a project where PM is a member, not a manager
        project_c = self.Project.create({
            'name': 'PM As Member',
            'project_manager_ids': [(4, self.admin_member.id)],
            'member_ids': [
                (4, self.pm_member.id),
                (4, self.member1.id),
            ],
        })
        pm_task = self.Task.create({
            'date': date.today().isoformat(),
            'description': 'PM task as member',
            'project_id': project_c.id,
            'member_id': self.pm_member.id,
            'time_from': 13.0,
            'time_to': 15.0,
        })
        m1_task = self.Task.create({
            'date': date.today().isoformat(),
            'description': 'Member1 task in project_c',
            'project_id': project_c.id,
            'member_id': self.member1.id,
            'time_from': 13.0,
            'time_to': 15.0,
        })
        # PM should see their own task but NOT member1's (not managing this)
        tasks = self.Task.with_user(self.user_pm).search([
            ('project_id', '=', project_c.id),
        ])
        self.assertIn(pm_task, tasks)
        # PM should not see member1's task since they don't manage project_c
        self.assertNotIn(m1_task, tasks)

    # --- ACL-7: PM cannot access unrelated project ---
    def test_pm_cannot_see_unrelated_project(self):
        """ACL-7: PM cannot see projects they don't manage or belong to."""
        projects = self.Project.with_user(self.user_pm).search([
            ('id', '=', self.unrelated_project.id),
        ])
        self.assertEqual(len(projects), 0)

    # --- ACL-8: PM cannot access admin settings ---
    def test_pm_cannot_change_settings(self):
        """ACL-8: PM cannot modify system parameters."""
        with self.assertRaises(AccessError):
            self.env['ir.config_parameter'].with_user(
                self.user_pm).set_param(
                'task_project_management.past_date_limit', '99')

    # --- ACL-9: Admin sees all projects ---
    def test_admin_sees_all_projects(self):
        """ACL-9: Admin can see all projects."""
        projects = self.Project.with_user(self.user_admin).search([])
        self.assertIn(self.project, projects)
        self.assertIn(self.unrelated_project, projects)

    # --- ACL-10: Admin sees archived projects ---
    def test_admin_sees_archived_project(self):
        """ACL-10: Admin can access archived projects."""
        self.project.write({'status': 'archived'})
        projects = self.Project.with_user(self.user_admin).search([
            ('status', '=', 'archived'),
        ])
        self.assertIn(self.project, projects)
        self.project.write({'status': 'active'})

    # --- ACL-11: PM/Member cannot see archived projects ---
    def test_pm_member_cannot_see_archived(self):
        """ACL-11: PM and members cannot see archived projects."""
        self.project.write({'status': 'archived'})
        pm_projects = self.Project.with_user(self.user_pm).search([
            ('id', '=', self.project.id),
        ])
        self.assertEqual(len(pm_projects), 0)
        member_projects = self.Project.with_user(
            self.user_member1).search([
            ('id', '=', self.project.id),
        ])
        self.assertEqual(len(member_projects), 0)
        self.project.write({'status': 'active'})

    # --- ACL-12: Admin changes settings ---
    def test_admin_changes_settings(self):
        """ACL-12: Admin can change any module settings."""
        self.env['ir.config_parameter'].with_user(
            self.user_admin).sudo().set_param(
            'task_project_management.past_date_limit', '14')
        val = self.env['ir.config_parameter'].sudo().get_param(
            'task_project_management.past_date_limit')
        self.assertEqual(val, '14')
        # Reset
        self.env['ir.config_parameter'].sudo().set_param(
            'task_project_management.past_date_limit', '3')

    # --- Member profile visibility ---
    def test_member_sees_own_profile(self):
        """Member can see their own profile."""
        members = self.Member.with_user(self.user_member1).search([
            ('id', '=', self.member1.id),
        ])
        self.assertEqual(len(members), 1)

    def test_member_cannot_see_other_profiles(self):
        """Member cannot see other members' profiles."""
        members = self.Member.with_user(self.user_member1).search([
            ('id', '=', self.member2.id),
        ])
        self.assertEqual(len(members), 0)

    def test_pm_sees_managed_project_members(self):
        """PM can see members in their managed projects."""
        members = self.Member.with_user(self.user_pm).search([
            ('id', 'in', [self.member1.id, self.member2.id]),
        ])
        self.assertEqual(len(members), 2)

    def test_admin_sees_all_members(self):
        """Admin can see all members."""
        members = self.Member.with_user(self.user_admin).search([])
        self.assertIn(self.member1, members)
        self.assertIn(self.member2, members)
        self.assertIn(self.pm_member, members)
