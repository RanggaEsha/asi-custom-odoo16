# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.


{
    'name': 'CRM Peepl',
    'version': '16.0.0.2',
    'category': 'CRM',
    'license': 'OPL-1',
    'summary': 'Complete CRM workflow with Sales to Solution Delivery handover process, task and project management from leads.',
    'description': """
    CRM Sales to Solution Delivery Handover Module
    ==============================================
    
    Features:
    - Create tasks and projects directly from CRM leads
    - Sales to Solution Delivery team handover process
    - Maintain client relationships post-sales through Solution Delivery team
    - Separate revenue tracking for both teams
    - Complete audit trail of handover process
    - Dedicated views and workflows for handover management
    
    Task on Lead, Add Task from lead, Task Lead, Create Project Task from Lead, Create Project from Lead, Sales Handover, Solution Delivery Pipeline, CRM Team Management.
""",
    'author': 'BROWSEINFO',
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


# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
