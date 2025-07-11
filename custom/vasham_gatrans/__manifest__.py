# -*- coding: utf-8 -*-
{
    'name': "Custom Addons for Gatrans",
    'version': '16',
    'category': 'Custom',
    'sequence': 1,
    'installable': True,
    'auto_install': False,
    'application': True,
    'license': 'AGPL-3', 
    'depends': ['base','account','sale','product','purchase','stock'],
    'data': [
        'views/views.xml',
        'security/ir.model.access.csv',
    ],
}
