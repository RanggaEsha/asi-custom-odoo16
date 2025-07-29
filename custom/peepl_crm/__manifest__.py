# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.


{
    'name': 'Peepl CRM',
    'version': '16.0.0.3',
    'category': 'CRM',
    'license': 'OPL-1',
    'summary': 'Complete CRM workflow with Sales to Solution Delivery handover process, task management from leads, and participant data management.',
    'description': """
    CRM Sales to Solution Delivery Handover Module with Participant Management
    ========================================================================
    
This module extends Odoo CRM with advanced assessment management capabilities:
        
        Assessment Management:
        * Configurable assessment types (Technical, Language, Personality, etc.)
        * Flexible assessment language configuration
        * Assessment period tracking with start and end dates
        * Customizable purpose field for assessment details
        
        Participant Management:
        * Detailed participant tracking per lead/opportunity
        * Participant data import capabilities
        * Individual participant profiles with job titles and levels
        * Bulk participant management
        
        Configuration Features:
        * Assessment Type Configuration - Add/edit assessment types
        * Assessment Language Configuration - Manage available languages
        * Color-coded categorization for visual organization
        * Statistical tracking of usage per type/language
        
        Integration Features:
        * Seamless CRM integration
        * Assessment workflow management
        * Participant relationship tracking
        * Enhanced lead/opportunity forms
        
        Data Management:
        * Bulk import/export capabilities
        * Data validation and constraints
        * Archive functionality for historical data
        * Comprehensive search and filtering
""",
    'author': 'Ahmad Rangga',
    'website': 'https://www.browseinfo.com/demo-request?app=bi_crm_task&version=16&edition=Community',
    'depends': ['base', 'crm', 'sale', 'project', 'base_import'],
    'data': [
            'security/security.xml',
            'security/ir.model.access.csv',
            'views/crm_lead_view.xml',

            
    ],
    'demo': [
        'demo/demo_data.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
    'live_test_url':'https://www.browseinfo.com/demo-request?app=bi_crm_task&version=16&edition=Community',
    "images":['static/description/Banner.gif'],
}