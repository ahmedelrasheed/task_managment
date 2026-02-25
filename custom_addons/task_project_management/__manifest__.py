{
    'name': 'Task & Project Management',
    'version': '17.0.3.1.0',
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
        'views/complaint_views.xml',
        'views/res_config_settings_views.xml',
        'views/res_users_views.xml',
        'views/menu_views.xml',
        'views/login_templates.xml',
        # Wizard
        'wizard/complaint_wizard_views.xml',
        'wizard/export_report_wizard_views.xml',
        'wizard/member_performance_report_views.xml',
        'wizard/project_performance_report_views.xml',
        'wizard/change_password_wizard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'task_project_management/static/src/css/dashboard.css',
            'task_project_management/static/src/xml/dashboard.xml',
            'task_project_management/static/src/xml/navbar_logo.xml',
            'task_project_management/static/src/xml/messaging_menu_override.xml',
            'task_project_management/static/src/xml/form_save_override.xml',
            'task_project_management/static/src/js/dashboard.js',
            'task_project_management/static/src/js/user_menu.js',
            'task_project_management/static/src/js/systray_cleanup.js',
            'task_project_management/static/src/js/float_time_spinner.js',
            'task_project_management/static/src/js/font_size.js',
            'task_project_management/static/src/js/breadcrumb_enhancer.js',
            'task_project_management/static/src/js/login_alert.js',
            'task_project_management/static/src/js/mobile_menu.js',
            'task_project_management/static/src/xml/login_alert.xml',
            'task_project_management/static/src/xml/navbar_apps_hide.xml',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
