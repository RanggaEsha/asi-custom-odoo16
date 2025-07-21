# -*- coding: utf-8 -*-
# from odoo import http


# class PeeplLogNote(http.Controller):
#     @http.route('/peepl_log_note/peepl_log_note', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/peepl_log_note/peepl_log_note/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('peepl_log_note.listing', {
#             'root': '/peepl_log_note/peepl_log_note',
#             'objects': http.request.env['peepl_log_note.peepl_log_note'].search([]),
#         })

#     @http.route('/peepl_log_note/peepl_log_note/objects/<model("peepl_log_note.peepl_log_note"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('peepl_log_note.object', {
#             'object': obj
#         })
