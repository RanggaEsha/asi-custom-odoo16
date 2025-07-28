# -*- coding: utf-8 -*-
# from odoo import http


# class PeeplSale(http.Controller):
#     @http.route('/peepl_sale/peepl_sale', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/peepl_sale/peepl_sale/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('peepl_sale.listing', {
#             'root': '/peepl_sale/peepl_sale',
#             'objects': http.request.env['peepl_sale.peepl_sale'].search([]),
#         })

#     @http.route('/peepl_sale/peepl_sale/objects/<model("peepl_sale.peepl_sale"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('peepl_sale.object', {
#             'object': obj
#         })
