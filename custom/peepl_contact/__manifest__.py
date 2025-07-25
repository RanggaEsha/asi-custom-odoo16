# -*- coding: utf-8 -*-
{
    'name': "Peepl Contact",

    'summary': """
        Extends partner contact form with document management and automated reminder system""",

    'description': """
        This module extends the res.partner model to include a Documents section
        with fields for SLA, NCIF, and Kontrak Kerja documents, plus an advanced
        reminder system for contract agreements.
        
        Document Management Features:
        * Adds Documents tab to partner form
        * File upload for SLA documents
        * File upload for NCIF documents  
        * File upload for Kontrak Kerja documents
        * Document description field
        * Automatic logging of document changes (create, update, delete)
        * User tracking for document modifications
        * Clean UI integration with existing partner form
        
        Reminder System Features:
        * Agreement date tracking
        * Flexible reminder date calculation (exact date or calculated)
        * Automatic reminder calculation (days/months/years before agreement)
        * Customizable email templates with variables
        * Push notifications to web interface
        * Internal activity notifications
        * Automated daily reminder checking via cron job
        * Reminder status tracking and reset functionality
        * Email delivery with error handling
        
        Logging Features:
        * Automatically logs when documents are uploaded
        * Tracks document updates and replacements
        * Records document deletions
        * Shows user name who made the changes
        * Displays changes in partner's message/communication history
        * Logs reminder activities and status changes
        
        Notification Features:
        * Email reminders with customizable templates
        * Push notifications to logged-in users
        * Internal Odoo activities for task management
        * Automatic daily checking for due reminders
        * Manual reminder sending capability
    """,

    'author': "Ahmad Rangga",
    'website': "https://www.yourcompany.com",

    'category': 'Contacts',
    'version': '16.0.3.0.0',

    # Dependencies
    'depends': ['base', 'contacts', 'mail', 'crm'],

    # Data files
    'data': [
        'security/ir.model.access.csv',
        'views/views.xml',
        'views/res_partner.xml',
        'data/ir_cron.xml',
    ],
    
    # Installation
    'installable': True,
    'auto_install': False,
    'application': False,
}