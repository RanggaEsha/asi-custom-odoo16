# -*- coding: utf-8 -*-
{
    'name': "Custom Addons for TRK",
    'version': '16.0.0.0',
    'category': 'Application',
    'sequence': 4,
    'installable': True,
    'auto_install': False,
    'application': True,
    'license': 'AGPL-3', 

    # any module necessary for this one to work correctly
    'depends': ['base','account','sale','product','purchase'],

    # always loaded
    'data': [
        'views/views.xml',
        'security/ir.model.access.csv'
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}
