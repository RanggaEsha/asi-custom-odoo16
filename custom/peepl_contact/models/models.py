# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Documents section fields
    sla = fields.Binary(string='SLA Document', help='Service Level Agreement document')
    sla_filename = fields.Char(string='SLA Filename')
    
    ncif = fields.Binary(string='NCIF Document', help='NCIF document')
    ncif_filename = fields.Char(string='NCIF Filename')
    
    kontrak_kerja = fields.Binary(string='Kontrak Kerja Document', help='Work Contract document')
    kontrak_kerja_filename = fields.Char(string='Kontrak Kerja Filename')