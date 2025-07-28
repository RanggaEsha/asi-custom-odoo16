# -*- coding: utf-8 -*-
# Part of Peepl Sale Module

from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    group_project_participant = fields.Boolean(
        string='Participant-Based Invoicing',
        implied_group='peepl_sale.group_project_participant',
        help='Allow invoicing based on participant completion in projects'
    )

    def set_values(self):
        super().set_values()
        
        if self.group_project_participant:
            # Enable participant functionality
            # Search for existing participant-based SOLs and update delivery method
            participant_sol_read_group = self.env['sale.order.line'].read_group(
                [('product_id.service_type', '=', 'participants')],
                ['ids:array_agg(id)'],
                [],
            )
            if participant_sol_read_group:
                participant_sol_ids = participant_sol_read_group[0]['ids']
                participant_sols = self.env['sale.order.line'].sudo().browse(participant_sol_ids)
                
                # Update service policy on products
                products = participant_sols.mapped('product_id')
                products.write({'service_policy': 'delivered_participants'})
                
                # Update delivery method on SOLs
                participant_sols.write({'qty_delivered_method': 'participants'})
        else:
            # Disable participant functionality
            # Convert participant-based products back to manual
            product_domain = [
                ('type', '=', 'service'), 
                ('service_type', '=', 'participants')
            ]
            products = self.env['product.product'].search(product_domain)
            products.write({'service_policy': 'delivered_manual'})
            
            # Update related SOLs
            sol_domain = [('product_id', 'in', products.ids)]
            sols = self.env['sale.order.line'].sudo().search(sol_domain)
            sols.write({'qty_delivered_method': 'manual'})

    @api.model
    def get_values(self):
        res = super().get_values()
        
        # Check if participant group is enabled
        participant_group = self.env.ref('peepl_sale.group_project_participant', False)
        if participant_group:
            res['group_project_participant'] = bool(
                self.env.user.has_group('peepl_sale.group_project_participant')
            )
        
        return res