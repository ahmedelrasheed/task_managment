from odoo.tests.common import TransactionCase
from odoo.exceptions import AccessError


class TestArchive(TransactionCase):
    """Tests for task.management.archive (Member Portfolio)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Member = cls.env['task.management.member']
        cls.Archive = cls.env['task.management.archive']

        cls.user_admin = cls.env['res.users'].create({
            'name': 'Admin',
            'login': 'arch_admin',
            'email': 'arch_admin@test.com',
            'groups_id': [(6, 0, [
                cls.env.ref(
                    'task_project_management.group_admin_manager').id,
            ])],
        })
        cls.user_member1 = cls.env['res.users'].create({
            'name': 'Member1',
            'login': 'arch_member1',
            'email': 'arch_member1@test.com',
            'groups_id': [(6, 0, [
                cls.env.ref('task_project_management.group_member').id,
            ])],
        })
        cls.user_member2 = cls.env['res.users'].create({
            'name': 'Member2',
            'login': 'arch_member2',
            'email': 'arch_member2@test.com',
            'groups_id': [(6, 0, [
                cls.env.ref('task_project_management.group_member').id,
            ])],
        })

        cls.admin_member = cls.Member.create({
            'name': 'Admin Person',
            'email': 'admin_arch@test.com',
            'user_id': cls.user_admin.id,
        })
        cls.member1 = cls.Member.create({
            'name': 'Member One',
            'email': 'one_arch@test.com',
            'user_id': cls.user_member1.id,
        })
        cls.member2 = cls.Member.create({
            'name': 'Member Two',
            'email': 'two_arch@test.com',
            'user_id': cls.user_member2.id,
        })

    # --- Create archive entry ---
    def test_create_archive_entry(self):
        """Member can create their own archive entry."""
        entry = self.Archive.with_user(self.user_member1).create({
            'member_id': self.member1.id,
            'project_name': 'Website Redesign',
            'description': 'Built the frontend',
            'start_date': '2025-01-01',
            'end_date': '2025-12-31',
            'role_played': 'Frontend Developer',
            'visibility': 'public',
        })
        self.assertTrue(entry.id)
        self.assertEqual(entry.project_name, 'Website Redesign')
        self.assertEqual(entry.visibility, 'public')

    # --- Default visibility is private ---
    def test_default_visibility_private(self):
        """Default visibility is private."""
        entry = self.Archive.create({
            'member_id': self.member1.id,
            'project_name': 'Private Project',
        })
        self.assertEqual(entry.visibility, 'private')

    # --- Edit own archive ---
    def test_edit_own_archive(self):
        """Member can edit their own archive entries."""
        entry = self.Archive.create({
            'member_id': self.member1.id,
            'project_name': 'Old Name',
        })
        entry.with_user(self.user_member1).write({
            'project_name': 'New Name',
            'description': 'Updated description',
        })
        self.assertEqual(entry.project_name, 'New Name')

    # --- Cannot edit other's archive ---
    def test_cannot_edit_others_archive(self):
        """Member cannot edit another member's archive entries."""
        entry = self.Archive.create({
            'member_id': self.member2.id,
            'project_name': 'Their Project',
        })
        with self.assertRaises(AccessError):
            entry.with_user(self.user_member1).write({
                'project_name': 'Hacked!',
            })

    # --- Delete own archive ---
    def test_delete_own_archive(self):
        """Member can delete their own archive entries."""
        entry = self.Archive.create({
            'member_id': self.member1.id,
            'project_name': 'Delete Me',
        })
        entry.with_user(self.user_member1).unlink()
        self.assertFalse(entry.exists())

    # --- Cannot delete other's archive ---
    def test_cannot_delete_others_archive(self):
        """Member cannot delete another member's archive entries."""
        entry = self.Archive.create({
            'member_id': self.member2.id,
            'project_name': 'Theirs',
        })
        with self.assertRaises(AccessError):
            entry.with_user(self.user_member1).unlink()

    # --- Admin can edit any archive ---
    def test_admin_can_edit_any_archive(self):
        """Admin can edit any member's archive entry."""
        entry = self.Archive.create({
            'member_id': self.member1.id,
            'project_name': 'Original',
        })
        entry.with_user(self.user_admin).write({
            'project_name': 'Admin Edit',
        })
        self.assertEqual(entry.project_name, 'Admin Edit')

    # --- Admin can delete any archive ---
    def test_admin_can_delete_any_archive(self):
        """Admin can delete any member's archive entry."""
        entry = self.Archive.create({
            'member_id': self.member1.id,
            'project_name': 'Admin Delete',
        })
        entry.with_user(self.user_admin).unlink()
        self.assertFalse(entry.exists())

    # --- Public archives visible to all ---
    def test_public_archive_visible_to_others(self):
        """Public archive entries are visible to other members."""
        entry = self.Archive.create({
            'member_id': self.member2.id,
            'project_name': 'Public Entry',
            'visibility': 'public',
        })
        archives = self.Archive.with_user(self.user_member1).search([
            ('id', '=', entry.id),
        ])
        self.assertEqual(len(archives), 1)

    # --- Private archives hidden from others ---
    def test_private_archive_hidden_from_others(self):
        """Private archive entries are not visible to other members."""
        entry = self.Archive.create({
            'member_id': self.member2.id,
            'project_name': 'Private Entry',
            'visibility': 'private',
        })
        archives = self.Archive.with_user(self.user_member1).search([
            ('id', '=', entry.id),
        ])
        self.assertEqual(len(archives), 0)

    # --- Own private archives visible to self ---
    def test_own_private_archive_visible(self):
        """Members can see their own private archive entries."""
        entry = self.Archive.create({
            'member_id': self.member1.id,
            'project_name': 'My Private',
            'visibility': 'private',
        })
        archives = self.Archive.with_user(self.user_member1).search([
            ('id', '=', entry.id),
        ])
        self.assertEqual(len(archives), 1)

    # --- Admin sees all archives ---
    def test_admin_sees_all_archives(self):
        """Admin can see all archive entries regardless of visibility."""
        entry_public = self.Archive.create({
            'member_id': self.member1.id,
            'project_name': 'Public',
            'visibility': 'public',
        })
        entry_private = self.Archive.create({
            'member_id': self.member2.id,
            'project_name': 'Private',
            'visibility': 'private',
        })
        archives = self.Archive.with_user(self.user_admin).search([
            ('id', 'in', [entry_public.id, entry_private.id]),
        ])
        self.assertEqual(len(archives), 2)
