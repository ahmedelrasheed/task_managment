import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Remove complaint system tables and related data before module upgrade."""
    if not version:
        return

    _logger.info("Removing complaint system (pre-migration 17.0.3.2.0)")

    # Clean up mail references to complaint model
    cr.execute("DELETE FROM mail_followers WHERE res_model = 'task.management.complaint'")
    cr.execute("DELETE FROM mail_message WHERE model = 'task.management.complaint'")
    cr.execute("DELETE FROM mail_activity WHERE res_model = 'task.management.complaint'")
    cr.execute("DELETE FROM ir_attachment WHERE res_model IN ('task.management.complaint', 'task.management.complaint.wizard')")
    _logger.info("Cleaned up mail references to complaint model")

    # Remove ir.model.data entries for complaint-related XML IDs
    cr.execute("""
        DELETE FROM ir_model_data
        WHERE module = 'task_project_management'
          AND name IN (
              'rule_complaint_member',
              'rule_complaint_admin',
              'rule_complaint_manager',
              'action_complaints',
              'action_member_complaints',
              'view_complaint_form',
              'view_complaint_tree',
              'view_complaint_search',
              'menu_complaints_parent',
              'menu_complaints',
              'menu_my_complaints',
              'view_complaint_wizard_form'
          )
    """)
    _logger.info("Removed complaint ir.model.data entries")

    # Remove complaint record rules
    cr.execute("""
        DELETE FROM ir_rule
        WHERE name ILIKE '%complaint%'
    """)
    _logger.info("Removed complaint record rules")

    # Remove complaint ACL entries
    cr.execute("""
        DELETE FROM ir_model_access
        WHERE name ILIKE '%complaint%'
    """)
    _logger.info("Removed complaint ACL entries")

    # Remove complaint menu items (children first, then parents)
    cr.execute("""
        DELETE FROM ir_ui_menu
        WHERE parent_id IN (
            SELECT id FROM ir_ui_menu WHERE name::text ILIKE '%complaint%'
        )
    """)
    cr.execute("""
        DELETE FROM ir_ui_menu
        WHERE name::text ILIKE '%complaint%'
    """)

    # Remove complaint act_window actions
    cr.execute("""
        DELETE FROM ir_act_window
        WHERE res_model = 'task.management.complaint'
    """)
    cr.execute("""
        DELETE FROM ir_act_window
        WHERE res_model = 'task.management.complaint.wizard'
    """)

    # Remove complaint views
    cr.execute("""
        DELETE FROM ir_ui_view
        WHERE model IN ('task.management.complaint', 'task.management.complaint.wizard')
    """)

    # Drop the complaint wizard table
    cr.execute("DROP TABLE IF EXISTS task_management_complaint_wizard CASCADE")
    _logger.info("Dropped task_management_complaint_wizard table")

    # Drop the complaint table
    cr.execute("DROP TABLE IF EXISTS task_management_complaint CASCADE")
    _logger.info("Dropped task_management_complaint table")

    # Clean up ir_model entries for complaint models
    cr.execute("""
        DELETE FROM ir_model_fields
        WHERE model_id IN (
            SELECT id FROM ir_model
            WHERE model IN ('task.management.complaint', 'task.management.complaint.wizard')
        )
    """)
    cr.execute("""
        DELETE FROM ir_model
        WHERE model IN ('task.management.complaint', 'task.management.complaint.wizard')
    """)
    _logger.info("Cleaned up ir_model entries for complaint models")

    # Remove complaint_ids, has_complaint, can_file_complaint fields from task model
    cr.execute("""
        DELETE FROM ir_model_fields
        WHERE model = 'task.management.task'
          AND name IN ('complaint_ids', 'has_complaint', 'can_file_complaint')
    """)
    _logger.info("Removed complaint fields from task model registry")
