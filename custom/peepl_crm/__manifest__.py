# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.


{
    'name': 'Peepl CRM',
    'version': '16.0.0.2',
    'category': 'CRM',
    'license': 'OPL-1',
    'summary': 'Complete CRM workflow with Sales to Solution Delivery handover process and task management from leads.',
    'description': """
    CRM Sales to Solution Delivery Handover Module
    ==============================================
    
    Features:
    - Create tasks in existing projects directly from CRM leads
    - Sales to Solution Delivery team handover process
    - Maintain client relationships post-sales through Solution Delivery team
    - Separate revenue tracking for both teams
    - Complete audit trail of handover process
    - Dedicated views and workflows for handover management
    - Task tracking and management linked to opportunities
    - Secure handover workflow with proper permissions
    
    Task on Lead, Add Task from Lead, Task Lead, Create Task from Lead, Sales Handover, Solution Delivery Pipeline, CRM Team Management, Handover Lead Management.
""",
    'author': 'Ahmad Rangga',
    'website': 'https://www.browseinfo.com/demo-request?app=bi_crm_task&version=16&edition=Community',
    'depends': ['base', 'crm', 'sale', 'project'],
    'data': [
            'security/security.xml',
            'security/ir.model.access.csv',
            'data/demo_data.xml',
            'views/crm_lead_view.xml'
            ],
    'installable': True,
    'auto_install': False,
    'application': True,
    'live_test_url':'https://www.browseinfo.com/demo-request?app=bi_crm_task&version=16&edition=Community',
    "images":['static/description/Banner.gif'],
}
