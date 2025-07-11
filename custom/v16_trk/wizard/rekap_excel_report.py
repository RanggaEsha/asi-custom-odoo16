# -*- coding: utf-8 -*-

from datetime import datetime
from odoo import models, fields, api


class RekapReport(models.TransientModel):
    _name = "wizard.rekap.report"
    _description = "Laporan Rekap"
    
    partner_id = fields.Many2one('res.partner', string='Customer')
    start_date = fields.Date('Start Date')
    end_date = fields.Date('End Date')
    
    def export_xls(self):
        context = self._context
        datas = {'ids': context.get('active_ids', [])}
        datas['model'] = 'wizard.rekap.report'
        datas['form'] = self.read()[0]
        for field in datas['form'].keys():
            if isinstance(datas['form'][field], tuple):
                datas['form'][field] = datas['form'][field][0]
        if context.get('xls_export'):
            return self.env.ref('v14_print.rekap_xlsx').report_action(self, data=datas)
