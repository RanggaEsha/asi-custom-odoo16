# -*- coding: utf-8 -*-
# from odoo import http


# class DkpFsd2203002(http.Controller):
#     @http.route('/dkp_fsd_2203002/dkp_fsd_2203002/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/dkp_fsd_2203002/dkp_fsd_2203002/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('dkp_fsd_2203002.listing', {
#             'root': '/dkp_fsd_2203002/dkp_fsd_2203002',
#             'objects': http.request.env['dkp_fsd_2203002.dkp_fsd_2203002'].search([]),
#         })

#     @http.route('/dkp_fsd_2203002/dkp_fsd_2203002/objects/<model("dkp_fsd_2203002.dkp_fsd_2203002"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('dkp_fsd_2203002.object', {
#             'object': obj
#         })
