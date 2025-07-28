# -*- coding: utf-8 -*-

from odoo import models, fields, api


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    def action_new_quotation(self):
        action = super().action_new_quotation()
        # Add participant and assessment fields to context
        self.ensure_one()
        # Collect participant IDs related to this lead
        participant_ids = self.env['participant'].search([('lead_id', '=', self.id)]).ids
        # Add assessment fields (adjust field names if needed)
        context = dict(action.get('context', {}))
        context.update({
            'default_has_participant_data': self.has_participant_data,
            'default_participant_ids': [(6, 0, participant_ids)],
            'default_test_start_date': self.test_start_date,
            'default_test_finish_date': self.test_finish_date,
            'default_type_of_assessment': [(6, 0, self.type_of_assessment.ids)],
            'default_assessment_language': [(6, 0, self.assessment_language.ids)],
            'default_purpose': self.purpose,
            'default_lead_id': self.id,
        })
        action['context'] = context
        return action

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    is_product_participant = fields.Boolean(
        string='Has Participant Products',
        compute='_compute_is_product_participant'
    )

    @api.depends('order_line.product_id.service_policy')
    def _compute_is_product_participant(self):
        for order in self:
            order.is_product_participant = any(
                line.product_id.service_policy == 'delivered_participants'
                for line in order.order_line
            )

    def action_mark_all_participants_completed(self):
        """Mark all participants in this order as test completed"""
        self.ensure_one()
        
        incomplete_participants = self.participant_ids.filtered(lambda p: not p.test_completed)
        if not incomplete_participants:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Info'),
                    'message': _('All participants have already completed their tests!'),
                    'type': 'info',
                }
            }
        
        incomplete_participants.write({
            'test_completed': True,
            'completion_date': fields.Datetime.now()
        })
        
        # Update related sale order lines
        participant_sale_lines = incomplete_participants.mapped('sale_line_id').filtered(
            lambda sol: sol.qty_delivered_method == 'participants'
        )
        if participant_sale_lines:
            participant_sale_lines._compute_qty_delivered()
        
        # Post message on sale order
        message = _(
            '%d participants marked as completed. Tests finished for: %s'
        ) % (
            len(incomplete_participants),
            ', '.join(incomplete_participants.mapped('full_name'))
        )
        self.message_post(body=message)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('%d participants marked as completed!') % len(incomplete_participants),
                'type': 'success',
            }
        }

    def action_view_participants_invoicing(self):
        """Action to view participants specifically for invoicing purposes"""
        self.ensure_one()
        
        # Get participants linked to participant-based sale lines
        participant_lines = self.order_line.filtered(lambda l: l.qty_delivered_method == 'participants')
        all_participants = self.env['participant']
        
        for line in participant_lines:
            if line.auto_link_participants and not line.related_participants_ids:
                all_participants |= self.participant_ids
            else:
                all_participants |= line.related_participants_ids
        
        action = {
            'name': _('Participants for Invoicing - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'participant',
            'view_mode': 'kanban,tree,form',
            'view_ids': [
                (5, 0, 0),
                (0, 0, {'view_mode': 'kanban', 'view_id': self.env.ref('peepl_sale.participant_view_kanban_invoicing').id}),
                (0, 0, {'view_mode': 'tree', 'view_id': self.env.ref('peepl_sale.participant_view_tree_invoicing').id}),
                (0, 0, {'view_mode': 'form', 'view_id': self.env.ref('peepl_sale.participant_view_form_invoicing').id}),
            ],
            'domain': [('id', 'in', all_participants.ids)],
            'context': {
                'default_sale_order_id': self.id,
                'search_default_test_pending': 1,
            },
            'help': _("""
                <p class="o_view_nocontent_smiling_face">
                    No participants found for invoicing.
                </p><p>
                    Participants linked to sale order lines with participant-based invoicing 
                    will appear here. Mark them as completed when they finish their tests.
                </p>
            """),
        }
        
        if len(all_participants) == 1:
            action.update({
                'view_mode': 'form',
                'view_ids': [(5, 0, 0), (0, 0, {'view_mode': 'form', 'view_id': self.env.ref('peepl_sale.participant_view_form_invoicing').id})],
                'res_id': all_participants.id,
            })
        
        return action

    def write(self, vals):
        """Override to handle participant-based product changes"""
        result = super().write(vals)
        
        # Update has_participant_data based on order lines
        for order in self:
            has_participant_products = any(
                line.product_id.service_policy == 'delivered_participants' 
                for line in order.order_line
            )
            if has_participant_products and not order.has_participant_data:
                order.has_participant_data = True
        
        return result

    @api.model
    def create(self, vals):
        order = super().create(vals)
        participant_ids = vals.get('participant_ids')
        ids = []
        if participant_ids:
            for command in participant_ids:
                if command[0] == 6:
                    ids.extend(command[2])
                elif command[0] == 4:
                    ids.append(command[1])
        if ids:
            self.env['participant'].browse(ids).write({'sale_order_id': order.id})
        return order
