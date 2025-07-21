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
    
    Features:
    - Create tasks in existing projects directly from CRM leads
    - Sales to Solution Delivery team handover process
    - Maintain client relationships post-sales through Solution Delivery team
    - Separate revenue tracking for both teams
    - Complete audit trail of handover process
    - Dedicated views and workflows for handover management
    - Task tracking and management linked to opportunities
    - Secure handover workflow with proper permissions
    - Participant data management with import capabilities
    - Import participants from Excel/CSV files
    - Track participant test results and levels
    
    Task on Lead, Add Task from Lead, Task Lead, Create Task from Lead, Sales Handover, Solution Delivery Pipeline, CRM Team Management, Handover Lead Management, Participant Data Management, Import Participants.
""",
    'author': 'Ahmad Rangga',
    'website': 'https://www.browseinfo.com/demo-request?app=bi_crm_task&version=16&edition=Community',
    'depends': ['base', 'crm', 'sale', 'project', 'base_import'],
    'data': [
            'security/security.xml',
            'security/ir.model.access.csv',
            'views/crm_lead_view.xml',
            'views/crm_participant.xml'
            ],
    'installable': True,
    'auto_install': False,
    'application': True,
    'live_test_url':'https://www.browseinfo.com/demo-request?app=bi_crm_task&version=16&edition=Community',
    "images":['static/description/Banner.gif'],
}