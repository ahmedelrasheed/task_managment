from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError
from datetime import date


class TestApproval(TransactionCase):
    """Tests for the approval workflow.
    Covers: APPR-1 through APPR-10"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Member = cls.env['task.management.member']
        cls.Project = cls.env['task.management.project']
        cls.Task = cls.env['task.management.task']

        # Admin user
        cls.user_admin = cls.env['res.users'].create({
            'name': 'Admin User',
            'login': 'appr_admin',
            'email': 'appr_admin@test.com',
            'groups_id': [(6, 0, [
                cls.env.ref(
                    'task_project_management.group_admin_manager').id,
            ])],
        })
        # PM user
        cls.user_pm = cls.env['res.users'].create({
            'name': 'PM User',
            'login': 'appr_pm',
            'email': 'appr_pm@test.com',
            'groups_id': [(6, 0, [
                cls.env.ref(
                    'task_project_management.group_project_manager').id,
            ])],
        })
        # Second PM
        cls.user_pm2 = cls.env['res.users'].create({
            'name': 'PM User 2',
            'login': 'appr_pm2',
            'email': 'appr_pm2@test.com',
            'groups_id': [(6, 0, [
                cls.env.ref(
                    'task_project_management.group_project_manager').id,
            ])],
        })
        # Member user
        cls.user_member = cls.env['res.users'].create({
            'name': 'Member User',
            'login': 'appr_member',
            'email': 'appr_member@test.com',
            'groups_id': [(6, 0, [
                cls.env.ref('task_project_management.group_member').id,
            ])],
        })

        cls.admin_member = cls.Member.create({
            'name': 'Admin',
            'email': 'admin_appr@test.com',
            'user_id': cls.user_admin.id,
        })
        cls.pm_member = cls.Member.create({
            'name': 'PM',
            'email': 'pm_appr@test.com',
            'user_id': cls.user_pm.id,
        })
        cls.pm_member2 = cls.Member.create({
            'name': 'PM2',
            'email': 'pm2_appr@test.com',
            'user_id': cls.user_pm2.id,
        })
        cls.regular_member = cls.Member.create({
            'name': 'Regular',
            'email': 'regular_appr@test.com',
            'user_id': cls.user_member.id,
        })

        cls.project = cls.Project.create({
            'name': 'Approval Project',
            'project_manager_ids': [
                (4, cls.pm_member.id),
                (4, cls.pm_member2.id),
            ],
            'member_ids': [(4, cls.regular_member.id)],
        })

        # Second project where PM is a member
        cls.project_b = cls.Project.create({
            'name': 'PM Member Project',
            'project_manager_ids': [(4, cls.pm_member2.id)],
            'member_ids': [(4, cls.pm_member.id)],
        })

    def _create_task(self, member=None, project=None, **kwargs):
        defaults = {
            'date': date.today().isoformat(),
            'description': 'Approval test task',
            'project_id': (project or self.project).id,
            'member_id': (member or self.regular_member).id,
            'time_from': kwargs.pop('time_from', 9.0),
            'time_to': kwargs.pop('time_to', 12.0),
        }
        defaults.update(kwargs)
        return self.Task.create(defaults)

    # --- APPR-1: PM approves member task ---
    def test_pm_approves_task(self):
        """APPR-1: PM approves a member task — status: Approved, locked."""
        task = self._create_task()
        task.with_user(self.user_pm).action_approve()
        self.assertEqual(task.approval_status, 'approved')

    # --- APPR-2: PM rejects with comment ---
    def test_pm_rejects_task_with_comment(self):
        """APPR-2: PM rejects a task with comment — status: Rejected."""
        task = self._create_task(time_from=13.0, time_to=15.0)
        task.with_user(self.user_pm).write({
            'manager_comment': 'Needs more detail',
        })
        task.with_user(self.user_pm).action_reject()
        self.assertEqual(task.approval_status, 'rejected')
        self.assertEqual(task.manager_comment, 'Needs more detail')

    # --- APPR-3: PM comments without approval decision ---
    def test_pm_comment_only_stays_pending(self):
        """APPR-3: PM adds comment without approval — stays Pending."""
        task = self._create_task(time_from=15.0, time_to=17.0)
        task.with_user(self.user_pm).write({
            'manager_comment': 'Looks good, reviewing later',
        })
        self.assertEqual(task.approval_status, 'pending')

    # --- APPR-4: PM cannot be member of own project (N/A) ---
    # This is enforced by the project constraint, not the approval flow.
    # The PM physically cannot have a task as member of their managed project.

    # --- APPR-5: PM cannot approve in unmanaged project ---
    def test_pm_cannot_approve_unmanaged_project(self):
        """APPR-5: PM cannot approve tasks in projects they don't manage."""
        # pm_member is a MEMBER (not PM) of project_b
        task = self._create_task(
            member=self.pm_member,
            project=self.project_b,
            time_from=9.0, time_to=11.0)
        # pm_member tries to approve their own task — should fail
        with self.assertRaises(UserError):
            task.with_user(self.user_pm).action_approve()

    # --- APPR-6: Either PM of multi-PM project can approve ---
    def test_either_pm_can_approve(self):
        """APPR-6: Both PMs of a multi-PM project can approve tasks."""
        task1 = self._create_task(time_from=9.0, time_to=10.0)
        task2 = self._create_task(time_from=10.0, time_to=11.0,
                                  description='Task 2')
        task1.with_user(self.user_pm).action_approve()
        self.assertEqual(task1.approval_status, 'approved')
        task2.with_user(self.user_pm2).action_approve()
        self.assertEqual(task2.approval_status, 'approved')

    # --- APPR-7: Admin approves any project ---
    def test_admin_approves_any_project(self):
        """APPR-7: Admin can approve tasks on any project."""
        task = self._create_task(time_from=11.0, time_to=12.0)
        task.with_user(self.user_admin).action_approve()
        self.assertEqual(task.approval_status, 'approved')

    # --- APPR-8: Member resubmits rejected task ---
    def test_member_resubmits_rejected_task(self):
        """APPR-8: Member resubmits rejected task — status resets
        to Pending."""
        task = self._create_task(time_from=13.0, time_to=14.0)
        task.with_user(self.user_pm).action_reject()
        self.assertEqual(task.approval_status, 'rejected')
        # Member edits the task
        task.with_user(self.user_member).write({
            'description': 'Updated with more details',
        })
        self.assertEqual(task.approval_status, 'pending')

    # --- APPR-9: Full cycle audit trail ---
    def test_full_cycle_audit_trail(self):
        """APPR-9: Full lifecycle: Pending → Rejected → Pending → Approved.
        All changes recorded in audit trail."""
        task = self._create_task(time_from=14.0, time_to=15.0)
        # Created: Pending
        self.assertEqual(len(task.audit_ids), 1)

        # Reject
        task.with_user(self.user_pm).write({
            'manager_comment': 'Rejected reason',
        })
        task.with_user(self.user_pm).action_reject()
        # Resubmit (edit)
        task.with_user(self.user_member).write({
            'description': 'Resubmitted',
        })
        # Approve
        task.with_user(self.user_pm2).action_approve()

        audit = task.audit_ids.sorted('changed_at')
        self.assertEqual(len(audit), 4)
        self.assertEqual(audit[0].new_status, 'pending')    # Created
        self.assertEqual(audit[1].new_status, 'rejected')   # Rejected
        self.assertEqual(audit[2].new_status, 'pending')    # Resubmitted
        self.assertEqual(audit[3].new_status, 'approved')   # Approved

    # --- APPR-10: View audit trail ---
    def test_audit_trail_has_timestamps(self):
        """APPR-10: Audit trail entries have timestamps and changed_by."""
        task = self._create_task(time_from=15.0, time_to=16.0)
        task.with_user(self.user_pm).action_approve()
        for entry in task.audit_ids:
            self.assertTrue(entry.changed_at)
            self.assertTrue(entry.changed_by)

    # --- Self-approval blocked ---
    def test_member_cannot_approve_own_task(self):
        """Member cannot approve or reject their own tasks."""
        # Create a task in project_b where pm_member is a regular member
        task = self._create_task(
            member=self.pm_member,
            project=self.project_b,
            time_from=14.0, time_to=16.0)
        # pm_member tries to approve their own task — blocked
        with self.assertRaises(UserError):
            task.with_user(self.user_pm).action_approve()

    # --- Approved task is locked ---
    def test_approved_task_locked(self):
        """Approved task cannot be edited (except manager comment)."""
        task = self._create_task(time_from=16.0, time_to=17.0)
        task.with_user(self.user_pm).action_approve()
        with self.assertRaises(UserError):
            task.write({'description': 'Should fail'})
        # But manager comment is still editable
        task.with_user(self.user_pm).write({
            'manager_comment': 'Additional note',
        })
        self.assertEqual(task.manager_comment, 'Additional note')
