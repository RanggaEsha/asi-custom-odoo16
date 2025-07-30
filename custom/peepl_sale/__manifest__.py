# -*- coding: utf-8 -*-
{
    'name': 'Peepl Sale - Participant-Based Invoicing',
    'version': '17.0.1.0.0',
    'category': 'Sales/Projects',
    'summary': 'Participant-based invoicing policy for assessment services',
    'description': """
Participant-Based Invoicing System
==================================

This module extends Odoo's sale and project management to support participant-based invoicing,
building on the existing participant management system.

Key Features:
* New invoicing policy: "Based on Participants" 
* Extends existing participant model with test completion tracking
* Automatic quantity delivered calculation based on participant completion
* Integration with existing sale order and CRM participant workflows
* Assessment type and language management
* Configurable participant-based products

Perfect for:
* Assessment and testing services
* Training and certification programs
* Educational courses  
* HR recruitment services
* Any service billed per participant completion

Installation & Setup:
1. Install this module (depends on existing participant system)
2. Go to Project Settings and enable "Participant-Based Invoicing"
3. Create products with service policy "Based on Participants"
4. Use in sale orders with existing participant data
5. Mark participants as test completed to trigger invoicing

Integration with Existing System:
* Builds on existing 'participant' model
* Works with current CRM lead and sale order participant management
* Adds completion tracking and invoicing capabilities
* Maintains all existing participant fields and functionality
* Compatible with assessment types and languages

Technical Details:
* Extends existing participant model (no new models created)
* Follows Odoo's milestone invoicing pattern
* Computed qty_delivered based on completed participants  
* Full integration with existing invoice workflows
* Backward compatible with existing participant data
    """,
    'author': 'Peepl',
    'website': 'https://peepl.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'sale',
        'project',
        'sale_project', 
        'sale_management',
        'base_import',
        # 'peepl_participant',  # Assuming this is the existing participant module
        # 'peepl_crm',  # Assuming this is the existing CRM module
        'crm',
    ],
    'data': [
        # Security
        'security/groups.xml',
        'security/ir.model.access.csv',
        
        # Data
        # 'data/sequences.xml',
        # 'data/demo_data.xml',
        
        # Views
        # 'views/participant_views.xml',
        'views/sale_order_views.xml',
        'views/res_config_settings_views.xml',
        'views/project_views.xml',
        'views/project_task_participant_views.xml',
        'views/sale_order_closure.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'peepl_sale/static/src/css/custom_ribbon.css',
        ],
    },
    'demo': [],
    'installable': True,
    'auto_install': False,
    'application': False,
    'post_init_hook': None,
    'uninstall_hook': None,
    'external_dependencies': {
        'python': [],
    },
}