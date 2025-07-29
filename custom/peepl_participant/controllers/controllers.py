# -*- coding: utf-8 -*-
# from odoo import http


# class PeeplParticipant(http.Controller):
#     @http.route('/peepl_participant/peepl_participant', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/peepl_participant/peepl_participant/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('peepl_participant.listing', {
#             'root': '/peepl_participant/peepl_participant',
#             'objects': http.request.env['peepl_participant.peepl_participant'].search([]),
#         })

#     @http.route('/peepl_participant/peepl_participant/objects/<model("peepl_participant.peepl_participant"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('peepl_participant.object', {
#             'object': obj
#         })
