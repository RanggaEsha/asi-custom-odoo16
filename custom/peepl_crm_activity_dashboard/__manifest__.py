# -*- coding: utf-8 -*-
{
    'name': "Peepl CRM Activity Dashboard",

    'summary': """
        Comprehensive CRM Activity Dashboard with advanced filtering and color-coded status""",

    'description': """
        CRM Activity Dashboard
        ======================
        
        This module provides a comprehensive dashboard for CRM activities with the following features:
        
        * Complete list view of all mail activities from CRM leads
        * Color-coded activity status (red for overdue, grey for planned, green for done, etc.)
        * Advanced filtering options (today, tomorrow, yesterday, past days/weeks/months/years)
        * Detailed activity information including lead details, assigned users, and notes
        * Access control through security groups
        * Enhanced search and grouping capabilities
        * Real-time activity status tracking
    """,

    'author': "Ahmad Rangga",
    'website': "https://www.yourcompany.com",
    'category': 'CRM',
    'version': '1.0.0',

    # Dependencies
    'depends': ['base', 'crm', 'mail'],

    # Data files
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/crm_activity_dashboard_views.xml',
        'views/wizard_views.xml',
        'views/menu_views.xml',
        # 'views/assets.xml',  # Temporarily disabled
    ],
    
    # Demo data
    'demo': [],
    
    'installable': True,
    'auto_install': False,
    'application': False,
}
