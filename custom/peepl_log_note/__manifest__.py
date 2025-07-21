# -*- coding: utf-8 -*-
{
    'name': "Partner Log Note Dashboard",

    'summary': """
        Searchable dashboard for managing partner log notes with real-time updates and advanced filtering""",

    'description': """
This module provides a comprehensive dashboard for managing log notes on partners.

Key Features:
- Smart button on partner form for quick access
- Tree view with search and filter capabilities  
- Real-time updates without page refresh
- Add, edit, delete log notes directly from dashboard
- Batch operations for multiple log notes
- Attachment support with download/view options
- Respects Odoo access rights and security
- Full-text search in log note content
- Filter by author, date, and content
    """,

    'author': "Your Company",
    'website': "https://www.yourcompany.com",

    'category': 'Sales/CRM',
    'version': '1.0.0',

    'depends': ['base', 'mail', 'contacts'],

    'data': [
        'security/ir.model.access.csv',
        'views/mail_message_views.xml', 
        'views/res_partner.xml',
        'data/server_actions.xml',
    ],
    
    'demo': [],
    
    'installable': True,
    'application': False,
    'auto_install': False,
}