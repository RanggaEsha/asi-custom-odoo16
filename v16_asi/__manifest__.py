# -*- coding: utf-8 -*-
{
    'name': "Custom Addons for PT. Aneka Search Indonesia",
    'version': '14.0.0.0',
    'category': 'Application',
    'sequence': 4,
    'installable': True,
    'auto_install': False,
    'application': True,
    'license': 'AGPL-3', 

    # any module necessary for this one to work correctly
    'depends': ['base','account','sale','product','purchase','stock','l10n_id_efaktur','account_followup','web'],

    # always loaded
    'data': [
        'views/views.xml',
        'views/report_purchase_order.xml',
        'views/report_invoice.xml',
        'views/report_payment.xml',
        'views/report_journal_entries_asi.xml',
        'views/report_petty_cash_asi.xml',
        'security/ir.model.access.csv',
        'security/ir_rule.xml',
        'wizard/cancel_purchase_request_view.xml'
    ],
    
    'assets': {
        'web.assets_backend': [
            'v16_asi/static/css/invoice_residual.css',
        ]
    },

    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}
