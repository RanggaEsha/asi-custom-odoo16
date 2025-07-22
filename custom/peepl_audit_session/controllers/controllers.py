# -*- coding: utf-8 -*-
# from odoo import http


# class PeeplAuditSession(http.Controller):
#     @http.route('/peepl_audit_session/peepl_audit_session', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/peepl_audit_session/peepl_audit_session/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('peepl_audit_session.listing', {
#             'root': '/peepl_audit_session/peepl_audit_session',
#             'objects': http.request.env['peepl_audit_session.peepl_audit_session'].search([]),
#         })

#     @http.route('/peepl_audit_session/peepl_audit_session/objects/<model("peepl_audit_session.peepl_audit_session"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('peepl_audit_session.object', {
#             'object': obj
#         })
