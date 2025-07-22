# -*- coding: utf-8 -*-
{
    'name': "Advanced User Audit Log Tracking",

    'summary': """
        Comprehensive User Activity and Session Audit Tracking for Odoo 16 Enterprise
    """,

    'description': """
        Advanced User Audit Log Tracking for Odoo provides comprehensive tracking of user activities, 
        offering insights into behavior, access patterns, and actions like read, write, create, and delete. 
        It ensures transparency and monitoring through detailed audit logs, supporting compliance and system audit.
        
        Key Features:
        * User Activity Tracking (CRUD operations)
        * Session Monitoring with IP, Device, and Location tracking
        * Automatic Activity Recording linked to sessions
        * Configurable audit settings for users and models
        * Access-based session control
        * Detailed audit logs with filtering capabilities
        * Support for all models including third-party modules
    """,

    'author': "Peepl Solutions",
    'website': "https://www.peepl.com",
    'category': 'Administration',
    'version': '16.0.1.0.0',
    'license': 'LGPL-3',

    # Dependencies
    'depends': [
        'base',
        'web',
        'mail',
    ],

    # Data files
    'data': [
        'security/audit_security.xml',
        'security/ir.model.access.csv',
        'wizard/audit_clear_wizard_views.xml',
        'views/audit_config_views.xml',
        'views/audit_session_views.xml',
        'views/audit_log_views.xml',
        'views/audit_menus.xml',
        'data/audit_data.xml',
    ],

    # Demo data
    'demo': [
        'demo/audit_demo.xml',
    ],

    'installable': True,
    'application': True,
    'auto_install': False,
}