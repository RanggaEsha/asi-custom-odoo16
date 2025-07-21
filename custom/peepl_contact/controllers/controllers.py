# -*- coding: utf-8 -*-
# from odoo import http


# class PeeplContact(http.Controller):
#     @http.route('/peepl_contact/peepl_contact', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/peepl_contact/peepl_contact/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('peepl_contact.listing', {
#             'root': '/peepl_contact/peepl_contact',
#             'objects': http.request.env['peepl_contact.peepl_contact'].search([]),
#         })

#     @http.route('/peepl_contact/peepl_contact/objects/<model("peepl_contact.peepl_contact"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('peepl_contact.object', {
#             'object': obj
#         })
