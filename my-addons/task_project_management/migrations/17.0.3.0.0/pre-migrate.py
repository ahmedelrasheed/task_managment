import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Migrate compound statuses to simple statuses + task_type field."""
    _logger.info("Pre-migration: Adding task_type column and migrating statuses")

    # Add task_type column if it doesn't exist
    cr.execute("""
        ALTER TABLE task_management_task
        ADD COLUMN IF NOT EXISTS task_type VARCHAR DEFAULT 'initiated'
    """)

    # Add is_seen_by_member and is_seen_by_pm columns for Phase 5
    cr.execute("""
        ALTER TABLE task_management_task
        ADD COLUMN IF NOT EXISTS is_seen_by_member BOOLEAN DEFAULT FALSE
    """)
    cr.execute("""
        ALTER TABLE task_management_task
        ADD COLUMN IF NOT EXISTS is_seen_by_pm BOOLEAN DEFAULT FALSE
    """)

    # Migrate task data: compound statuses → simple + task_type
    # assigned_pending → pending + task_type='assigned'
    cr.execute("""
        UPDATE task_management_task
        SET approval_status = 'pending', task_type = 'assigned'
        WHERE approval_status = 'assigned_pending'
    """)
    _logger.info("Migrated assigned_pending → pending + task_type=assigned: %d rows", cr.rowcount)

    # assigned_approved → approved + task_type='assigned'
    cr.execute("""
        UPDATE task_management_task
        SET approval_status = 'approved', task_type = 'assigned'
        WHERE approval_status = 'assigned_approved'
    """)
    _logger.info("Migrated assigned_approved → approved + task_type=assigned: %d rows", cr.rowcount)

    # assigned_rejected → rejected + task_type='assigned'
    cr.execute("""
        UPDATE task_management_task
        SET approval_status = 'rejected', task_type = 'assigned'
        WHERE approval_status = 'assigned_rejected'
    """)
    _logger.info("Migrated assigned_rejected → rejected + task_type=assigned: %d rows", cr.rowcount)

    # assigned → keep assigned + task_type='assigned'
    cr.execute("""
        UPDATE task_management_task
        SET task_type = 'assigned'
        WHERE approval_status = 'assigned'
    """)
    _logger.info("Set task_type=assigned for status=assigned: %d rows", cr.rowcount)

    # remaining (pending/approved/rejected without assigned_by) → task_type='initiated'
    cr.execute("""
        UPDATE task_management_task
        SET task_type = 'initiated'
        WHERE task_type IS NULL OR task_type = ''
    """)

    # Migrate audit trail
    cr.execute("""
        UPDATE task_management_task_audit
        SET old_status = 'pending'
        WHERE old_status = 'assigned_pending'
    """)
    cr.execute("""
        UPDATE task_management_task_audit
        SET old_status = 'approved'
        WHERE old_status = 'assigned_approved'
    """)
    cr.execute("""
        UPDATE task_management_task_audit
        SET old_status = 'rejected'
        WHERE old_status = 'assigned_rejected'
    """)
    cr.execute("""
        UPDATE task_management_task_audit
        SET new_status = 'pending'
        WHERE new_status = 'assigned_pending'
    """)
    cr.execute("""
        UPDATE task_management_task_audit
        SET new_status = 'approved'
        WHERE new_status = 'assigned_approved'
    """)
    cr.execute("""
        UPDATE task_management_task_audit
        SET new_status = 'rejected'
        WHERE new_status = 'assigned_rejected'
    """)
    _logger.info("Migrated audit trail compound statuses")

    # Migrate archive fields: project_name → document_name, end_date → creation_date
    cr.execute("""
        ALTER TABLE task_management_archive
        ADD COLUMN IF NOT EXISTS document_name VARCHAR
    """)
    cr.execute("""
        ALTER TABLE task_management_archive
        ADD COLUMN IF NOT EXISTS creation_date DATE
    """)
    cr.execute("""
        UPDATE task_management_archive
        SET document_name = COALESCE(project_name, 'Untitled'),
            creation_date = end_date
        WHERE document_name IS NULL
    """)
    _logger.info("Migrated archive fields: project_name → document_name, end_date → creation_date")
