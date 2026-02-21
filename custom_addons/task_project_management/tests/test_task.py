from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, UserError
from datetime import date, timedelta


class TestTask(TransactionCase):
    """Tests for task.management.task model.
    Covers: TASK-1 through TASK-20, EDIT-1 through EDIT-6"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Member = cls.env['task.management.member']
        cls.Project = cls.env['task.management.project']
        cls.Task = cls.env['task.management.task']
        cls.ICP = cls.env['ir.config_parameter'].sudo()

        # Set default config
        cls.ICP.set_param(
            'task_project_management.past_date_limit', '3')
        cls.ICP.set_param(
            'task_project_management.allow_after_midnight', 'False')
        cls.ICP.set_param(
            'task_project_management.max_attachment_size', '100')

        cls.user_admin = cls.env.ref('base.user_admin')
        cls.user_pm = cls.env['res.users'].create({
            'name': 'PM',
            'login': 'task_pm',
            'email': 'task_pm@test.com',
            'groups_id': [(6, 0, [
                cls.env.ref(
                    'task_project_management.group_project_manager').id,
            ])],
        })
        cls.user_member = cls.env['res.users'].create({
            'name': 'Member',
            'login': 'task_member',
            'email': 'task_member@test.com',
            'groups_id': [(6, 0, [
                cls.env.ref('task_project_management.group_member').id,
            ])],
        })
        cls.user_member2 = cls.env['res.users'].create({
            'name': 'Member2',
            'login': 'task_member2',
            'email': 'task_member2@test.com',
            'groups_id': [(6, 0, [
                cls.env.ref('task_project_management.group_member').id,
            ])],
        })

        cls.pm_member = cls.Member.create({
            'name': 'PM Person',
            'email': 'pm_task@test.com',
            'user_id': cls.user_pm.id,
        })
        cls.member = cls.Member.create({
            'name': 'Regular Person',
            'email': 'member_task@test.com',
            'user_id': cls.user_member.id,
        })
        cls.member2 = cls.Member.create({
            'name': 'Regular Person 2',
            'email': 'member2_task@test.com',
            'user_id': cls.user_member2.id,
        })

        cls.project = cls.Project.create({
            'name': 'Active Project',
            'project_manager_ids': [(4, cls.pm_member.id)],
            'member_ids': [
                (4, cls.member.id),
                (4, cls.member2.id),
            ],
        })

    def _create_task(self, **kwargs):
        """Helper to create a task with sensible defaults."""
        defaults = {
            'date': date.today().isoformat(),
            'description': 'Test task',
            'project_id': self.project.id,
            'member_id': self.member.id,
            'time_from': 9.0,
            'time_to': 12.0,
        }
        defaults.update(kwargs)
        user = kwargs.pop('user', self.user_member)
        return self.Task.with_user(user).create(defaults)

    # ================================================================
    # TASK CREATION TESTS
    # ================================================================

    # --- TASK-1: Create task with all fields ---
    def test_create_task_all_fields(self):
        """TASK-1: Create task with all required fields — status: Pending."""
        task = self._create_task()
        self.assertTrue(task.id)
        self.assertEqual(task.approval_status, 'pending')
        self.assertEqual(task.member_id, self.member)
        self.assertTrue(task.entry_timestamp)

    # --- TASK-2: Missing date ---
    def test_create_task_no_date(self):
        """TASK-2: Task with False date raises error."""
        with self.assertRaises(Exception):
            self.Task.create({
                'date': False,
                'description': 'No date',
                'project_id': self.project.id,
                'member_id': self.member.id,
                'time_from': 9.0,
                'time_to': 12.0,
            })

    # --- TASK-5: Missing time ---
    def test_create_task_no_time(self):
        """TASK-5: Task without time_from/time_to gets 0.0 defaults
        and may fail validation (time_to <= time_from)."""
        with self.assertRaises(ValidationError):
            self.Task.create({
                'date': date.today().isoformat(),
                'description': 'No time',
                'project_id': self.project.id,
                'member_id': self.member.id,
                'time_from': 0.0,
                'time_to': 0.0,
            })

    # --- TASK-6: time_from > time_to (after-midnight disabled) ---
    def test_time_from_after_time_to(self):
        """TASK-6: time_from > time_to raises error when
        after-midnight is disabled."""
        with self.assertRaises(ValidationError):
            self._create_task(time_from=14.0, time_to=10.0)

    # --- TASK-7: Overlapping time (same day, same member) ---
    def test_overlapping_time_blocked(self):
        """TASK-7: Overlapping time entries on the same day are blocked."""
        self._create_task(time_from=9.0, time_to=12.0)
        with self.assertRaises(ValidationError):
            self._create_task(
                time_from=11.0, time_to=14.0,
                description='Overlap task')

    # --- TASK-8: Adjacent time allowed ---
    def test_adjacent_time_allowed(self):
        """TASK-8: Adjacent time (12:00 ends, 13:00 starts) is allowed."""
        self._create_task(time_from=9.0, time_to=12.0)
        task2 = self._create_task(
            time_from=13.0, time_to=15.0,
            description='Adjacent task')
        self.assertTrue(task2.id)

    # --- TASK-9: Today's date allowed ---
    def test_today_date_allowed(self):
        """TASK-9: Tasks for today's date are allowed."""
        task = self._create_task(date=date.today().isoformat())
        self.assertEqual(task.date, date.today())

    # --- TASK-10: Past date within limit (late entry flagged) ---
    def test_past_date_within_limit(self):
        """TASK-10: Past date within limit is allowed, flagged as late."""
        past = date.today() - timedelta(days=2)
        task = self._create_task(date=past.isoformat())
        task.invalidate_recordset()
        self.assertTrue(task.is_late_entry)
        self.assertEqual(task.late_days, 2)

    # --- TASK-11: Past date beyond limit blocked for member ---
    def test_past_date_beyond_limit_blocked_for_member(self):
        """TASK-11: Members cannot enter tasks beyond the past date limit."""
        past = date.today() - timedelta(days=5)
        with self.assertRaises(ValidationError):
            self._create_task(date=past.isoformat())

    def test_past_date_beyond_limit_allowed_for_pm(self):
        """TASK-11: PM can enter tasks beyond the past date limit."""
        past = date.today() - timedelta(days=5)
        project_b = self.Project.create({
            'name': 'PM Entry Project',
            'project_manager_ids': [(4, self.pm_member.id)],
            'member_ids': [(4, self.member.id)],
        })
        task = self.Task.with_user(self.user_pm).create({
            'date': past.isoformat(),
            'description': 'PM past date task',
            'project_id': project_b.id,
            'member_id': self.member.id,
            'time_from': 9.0,
            'time_to': 12.0,
        })
        self.assertTrue(task.id)

    # --- TASK-15: Dropdown shows only active projects user is member of ---
    def test_member_in_project_constraint(self):
        """TASK-15: Task member must be assigned to the project."""
        other_project = self.Project.create({
            'name': 'Other Project',
            'project_manager_ids': [(4, self.pm_member.id)],
            'member_ids': [(4, self.member2.id)],
        })
        with self.assertRaises(ValidationError):
            self._create_task(
                project_id=other_project.id,
                time_from=14.0, time_to=16.0)

    # --- TASK-16: Task for On Hold project ---
    def test_on_hold_project_blocks_task(self):
        """TASK-16: Cannot create tasks for On Hold projects."""
        self.project.write({'status': 'on_hold'})
        with self.assertRaises(ValidationError):
            self._create_task(time_from=14.0, time_to=16.0)
        self.project.write({'status': 'active'})

    # --- TASK-17: Task for Completed project ---
    def test_completed_project_blocks_member_task(self):
        """TASK-17: Members cannot create tasks for completed projects."""
        self.project.write({'status': 'completed'})
        with self.assertRaises(ValidationError):
            self._create_task(time_from=14.0, time_to=16.0)
        self.project.write({'status': 'active'})

    # --- TASK-18: Overlapping across different projects blocked ---
    def test_overlap_across_projects_blocked(self):
        """TASK-18: Time overlap is per member per day, not per project."""
        project_b = self.Project.create({
            'name': 'Second Project',
            'project_manager_ids': [(4, self.pm_member.id)],
            'member_ids': [(4, self.member.id)],
        })
        self._create_task(time_from=9.0, time_to=12.0)
        with self.assertRaises(ValidationError):
            self._create_task(
                project_id=project_b.id,
                time_from=11.0, time_to=14.0,
                description='Cross-project overlap')

    # --- TASK-19: After-midnight disabled ---
    def test_after_midnight_disabled(self):
        """TASK-19: Cross-midnight tasks blocked when setting disabled."""
        with self.assertRaises(ValidationError):
            self._create_task(time_from=23.0, time_to=1.0)

    # --- TASK-20: After-midnight enabled ---
    def test_after_midnight_enabled(self):
        """TASK-20: Cross-midnight tasks allowed when setting enabled."""
        self.ICP.set_param(
            'task_project_management.allow_after_midnight', 'True')
        task = self._create_task(
            time_from=23.0, time_to=1.0,
            description='After midnight task')
        self.assertTrue(task.id)
        self.assertAlmostEqual(task.duration_hours, 2.0, places=1)
        # Reset
        self.ICP.set_param(
            'task_project_management.allow_after_midnight', 'False')

    # --- Duration calculation ---
    def test_duration_hours_computed(self):
        """Duration = time_to - time_from."""
        task = self._create_task(time_from=9.0, time_to=12.5)
        self.assertAlmostEqual(task.duration_hours, 3.5, places=1)

    # --- Future date blocked ---
    def test_future_date_blocked_for_member(self):
        """Members cannot enter tasks for future dates."""
        future = date.today() + timedelta(days=1)
        with self.assertRaises(ValidationError):
            self._create_task(date=future.isoformat())

    # --- Auto member assignment ---
    def test_auto_member_from_user(self):
        """Member is auto-assigned from current user if not provided."""
        task = self.Task.with_user(self.user_member).create({
            'date': date.today().isoformat(),
            'description': 'Auto member',
            'project_id': self.project.id,
            'time_from': 14.0,
            'time_to': 16.0,
        })
        self.assertEqual(task.member_id, self.member)

    # --- Audit entry on create ---
    def test_audit_entry_on_create(self):
        """An audit entry is created when a task is created."""
        task = self._create_task(time_from=14.0, time_to=16.0)
        self.assertEqual(len(task.audit_ids), 1)
        self.assertEqual(task.audit_ids[0].new_status, 'pending')

    # ================================================================
    # TASK EDITING TESTS
    # ================================================================

    # --- EDIT-1: Edit pending task ---
    def test_edit_pending_task(self):
        """EDIT-1: Editing a pending task is allowed."""
        task = self._create_task(time_from=14.0, time_to=16.0)
        task.write({'description': 'Updated description'})
        self.assertEqual(task.description, 'Updated description')
        self.assertEqual(task.approval_status, 'pending')

    # --- EDIT-2: Edit rejected task resets to pending ---
    def test_edit_rejected_task_resets_to_pending(self):
        """EDIT-2: Editing a rejected task resets status to Pending."""
        task = self._create_task(time_from=14.0, time_to=16.0)
        task.write({'approval_status': 'rejected',
                    'manager_comment': 'Needs more detail'})
        self.assertEqual(task.approval_status, 'rejected')
        # Member edits the task
        task.with_user(self.user_member).write({
            'description': 'More detailed description',
        })
        self.assertEqual(task.approval_status, 'pending')

    # --- EDIT-3: Cannot edit approved task ---
    def test_cannot_edit_approved_task(self):
        """EDIT-3: Editing an approved task is blocked."""
        task = self._create_task(time_from=14.0, time_to=16.0)
        task.write({'approval_status': 'approved'})
        with self.assertRaises(UserError):
            task.write({'description': 'Should fail'})

    # --- EDIT-4: Cannot delete task ---
    def test_cannot_delete_task(self):
        """EDIT-4: Tasks cannot be deleted."""
        task = self._create_task(time_from=14.0, time_to=16.0)
        with self.assertRaises(UserError):
            task.unlink()

    # --- EDIT-5: Edit time to overlap blocked ---
    def test_edit_time_to_overlap_blocked(self):
        """EDIT-5: Editing task time to overlap another is blocked."""
        task1 = self._create_task(
            time_from=9.0, time_to=12.0)
        task2 = self._create_task(
            time_from=13.0, time_to=15.0,
            description='Second task')
        with self.assertRaises(ValidationError):
            task2.write({'time_from': 11.0})

    # --- EDIT-6: Rejected edit audit trail ---
    def test_rejected_edit_creates_audit_trail(self):
        """EDIT-6: Editing rejected task creates audit entry:
        Pending → Rejected → Pending."""
        task = self._create_task(time_from=14.0, time_to=16.0)
        # Task created: audit[0] = (None → pending)
        task.write({'approval_status': 'rejected',
                    'manager_comment': 'Rejected'})
        # Rejection: audit[0] = (pending → rejected)
        task.with_user(self.user_member).write({
            'description': 'Resubmitted',
        })
        # Resubmission: audit[0] = (rejected → pending)
        audit = task.audit_ids.sorted('changed_at')
        self.assertEqual(len(audit), 3)
        self.assertEqual(audit[0].new_status, 'pending')
        self.assertEqual(audit[1].new_status, 'rejected')
        self.assertEqual(audit[2].new_status, 'pending')

    # --- Negative time blocked ---
    def test_negative_time_blocked(self):
        """Time values cannot be negative."""
        with self.assertRaises(ValidationError):
            self._create_task(time_from=-1.0, time_to=5.0)

    # --- Time >= 24 blocked ---
    def test_time_over_24_blocked(self):
        """Time values must be less than 24:00."""
        with self.assertRaises(ValidationError):
            self._create_task(time_from=9.0, time_to=24.0)

    # --- Same time (0 duration) blocked ---
    def test_same_time_blocked(self):
        """Time from and time to cannot be the same."""
        with self.assertRaises(ValidationError):
            self._create_task(time_from=9.0, time_to=9.0)
