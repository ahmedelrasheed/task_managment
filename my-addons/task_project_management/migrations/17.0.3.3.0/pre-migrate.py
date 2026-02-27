import logging

_logger = logging.getLogger(__name__)

SNAPSHOT_COLUMNS = [
    ('snap_date', 'date'),
    ('snap_description', 'text'),
    ('snap_project_name', 'varchar'),
    ('snap_phase_name', 'varchar'),
    ('snap_time_from', 'double precision'),
    ('snap_time_to', 'double precision'),
    ('snap_duration_hours', 'double precision'),
    ('snap_manager_comment', 'text'),
    ('snap_approval_status', 'varchar'),
    ('snap_task_type', 'varchar'),
    ('snap_assignment_name', 'varchar'),
    ('snap_assignment_description', 'text'),
    ('snap_due_date', 'date'),
    ('snap_attachment_names', 'text'),
    ('snap_assignment_attachment_names', 'text'),
]


def migrate(cr, version):
    """Add snapshot columns to audit table and backfill from current task data."""
    if not version:
        return

    _logger.info("Adding snapshot columns to task audit table (pre-migration 17.0.3.3.0)")

    for col_name, col_type in SNAPSHOT_COLUMNS:
        cr.execute(
            "ALTER TABLE task_management_task_audit ADD COLUMN IF NOT EXISTS %s %s"
            % (col_name, col_type)
        )

    _logger.info("Added %d snapshot columns", len(SNAPSHOT_COLUMNS))

    # Backfill existing audit records with current task data (approximate)
    cr.execute("""
        UPDATE task_management_task_audit a
        SET
            snap_date = t.date,
            snap_description = t.description,
            snap_project_name = p.name::text,
            snap_phase_name = ph.name::text,
            snap_time_from = t.time_from,
            snap_time_to = t.time_to,
            snap_duration_hours = t.duration_hours,
            snap_manager_comment = t.manager_comment,
            snap_approval_status = a.new_status,
            snap_task_type = t.task_type,
            snap_assignment_name = t.assignment_name,
            snap_assignment_description = t.assignment_description,
            snap_due_date = t.due_date
        FROM task_management_task t
        LEFT JOIN task_management_project p ON p.id = t.project_id
        LEFT JOIN task_management_project_phase ph ON ph.id = t.phase_id
        WHERE a.task_id = t.id
          AND a.snap_date IS NULL
    """)

    _logger.info("Backfilled existing audit records with task snapshot data")
