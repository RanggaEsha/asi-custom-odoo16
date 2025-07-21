# -*- coding: utf-8 -*-

# from odoo import models, fields, api


# class peepl_log_note(models.Model):
#     _name = 'peepl_log_note.peepl_log_note'
#     _description = 'peepl_log_note.peepl_log_note'

#     name = fields.Char()
#     value = fields.Integer()
#     value2 = fields.Float(compute="_value_pc", store=True)
#     description = fields.Text()
#
#     @api.depends('value')
#     def _value_pc(self):
#         for record in self:
#             record.value2 = float(record.value) / 100
