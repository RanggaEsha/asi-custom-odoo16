# -*- coding: utf-8 -*-

# from odoo import models, fields, api


# class peepl_audit_session(models.Model):
#     _name = 'peepl_audit_session.peepl_audit_session'
#     _description = 'peepl_audit_session.peepl_audit_session'

#     name = fields.Char()
#     value = fields.Integer()
#     value2 = fields.Float(compute="_value_pc", store=True)
#     description = fields.Text()
#
#     @api.depends('value')
#     def _value_pc(self):
#         for record in self:
#             record.value2 = float(record.value) / 100
