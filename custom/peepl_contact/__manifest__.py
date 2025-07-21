# -*- coding: utf-8 -*-
{
    'name': "Partner Contact Documents",

    'summary': """
        Extends partner contact form with document management section""",

    'description': """
        This module extends the res.partner model to include a Documents section
        with fields for SLA, NCIF, and Kontrak Kerja documents.
        
        Features:
        * Adds Documents tab to partner form
        * File upload for SLA documents
        * File upload for NCIF documents  
        * File upload for Kontrak Kerja documents
        * Clean UI integration with existing partner form
    """,

    'author': "Ahmad Rangga",
    'website': "https://www.yourcompany.com",

    'category': 'Contacts',
    'version': '16.0.1.0.0',

    # Dependencies
    'depends': ['base', 'contacts'],

    # Data files
    'data': [
        'security/ir.model.access.csv',
        'views/views.xml',
    ],
    
    # Installation
    'installable': True,
    'auto_install': False,
    'application': False,
}