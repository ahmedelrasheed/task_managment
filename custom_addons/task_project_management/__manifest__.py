{
    'name': 'Task & Project Management',
    'version': '17.0.1.1.0',
    'category': 'Project',
    'summary': 'Task & Project Management with approval workflow',
    'description': """
        Task & Project Management System
        =================================
        - Daily task entry with time tracking
        - Multi-level approval workflow (Pending/Approved/Rejected)
        - Three roles: Member, Project Manager, Admin Manager
        - Project progress tracking
        - Member portfolio/archive
        - Dashboards and reports with CSV/image export
        - Full audit trail
        - Bilingual Arabic/English with RTL support
    """,
    'author': 'Custom',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'base_setup',
    ],
    'data': [
        # Security first
        'security/security.xml',
        'security/ir.model.access.csv',
        # Data
        'data/default_settings_data.xml',
        'data/mail_template_data.xml',
        'data/cron_data.xml',
        # Views
        'views/member_views.xml',
        'views/project_views.xml',
        'views/task_views.xml',
        'views/task_audit_views.xml',
        'views/archive_views.xml',
        'views/res_config_settings_views.xml',
        'views/menu_views.xml',
        # Wizard
        'wizard/export_report_wizard_views.xml',
        'wizard/member_performance_report_views.xml',
        'wizard/project_performance_report_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'task_project_management/static/src/css/dashboard.css',
            'task_project_management/static/src/xml/dashboard.xml',
            'task_project_management/static/src/js/dashboard.js',
            'task_project_management/static/src/js/user_menu.js',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
