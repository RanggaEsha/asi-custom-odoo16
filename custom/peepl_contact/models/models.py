# -*- coding: utf-8 -*-

# from odoo import models, fields, api


# class peepl_contact(models.Model):
#     _name = 'peepl_contact.peepl_contact'
#     _description = 'peepl_contact.peepl_contact'

#     name = fields.Char()
#     value = fields.Integer()
#     value2 = fields.Float(compute="_value_pc", store=True)
#     description = fields.Text()
#
#     @api.depends('value')
#     def _value_pc(self):
#         for record in self:
#             record.value2 = float(record.value) / 100
