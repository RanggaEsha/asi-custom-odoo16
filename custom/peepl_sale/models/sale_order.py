# -*- coding: utf-8 -*-


from odoo import models, fields, api, _
from odoo.exceptions import UserError


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    def action_new_quotation(self):
        """Override to carry forward participant data to new quotations"""
        action = super().action_new_quotation()
        self.ensure_one()
        
        # Collect participant IDs related to this lead
        participant_ids = self.participant_ids.ids
        
        # Add assessment and participant fields to context
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

    def action_show_closed_info(self):
        """Show a notification that the sale is closed."""
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Order Closed'),
                'message': _('This sale order is closed.'),
                'type': 'warning',
                'sticky': False,
            }
        }
    _inherit = 'sale.order'

    is_product_participant = fields.Boolean(
        string='Has Participant Products',
        compute='_compute_is_product_participant'
    )

    @api.depends('order_line.product_id.service_policy')
    def _compute_is_product_participant(self):
        """Check if order has any participant-based products"""
        for order in self:
            order.is_product_participant = any(
                line.product_id.service_policy == 'delivered_participants'
                for line in order.order_line
            )

    def action_mark_all_participants_completed(self):
        """Mark all participants in this order as confirmed (test completed) and refresh view"""
        self.ensure_one()
        incomplete_participants = self.participant_ids.filtered(lambda p: p.state != 'confirmed')
        if not incomplete_participants:
            return [
                {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Info'),
                        'message': _('All participants have already completed their tests!'),
                        'type': 'info',
                    }
                },
                {'type': 'ir.actions.act_window_close'},
                {'type': 'ir.actions.client', 'tag': 'reload'},
            ]
        # Mark participants as confirmed
        incomplete_participants.write({
            'state': 'confirmed',
            'completion_date': fields.Datetime.now()
        })
        participant_sale_lines = incomplete_participants.mapped('sale_line_id').filtered(
            lambda sol: sol.qty_delivered_method == 'participants'
        )
        if participant_sale_lines:
            participant_sale_lines._compute_qty_delivered()
        participant_names = ', '.join(incomplete_participants.mapped('full_name'))
        message = _(
            '%d participants marked as test completed: %s'
        ) % (len(incomplete_participants), participant_names)
        self.message_post(body=message)
        return [
            {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('%d participants marked as test completed!') % len(incomplete_participants),
                    'type': 'success',
                }
            },
            {'type': 'ir.actions.act_window_close'},
            {'type': 'ir.actions.client', 'tag': 'reload'},
        ]

    def action_view_participants_invoicing(self):
        """Action to view participants specifically for invoicing purposes"""
        self.ensure_one()
        
        # Get participants linked to participant-based sale lines
        participant_lines = self.order_line.filtered(lambda l: l.qty_delivered_method == 'participants')
        all_participants = self.env['participant']
        
        for line in participant_lines:
            if line.auto_link_participants and not line.related_participants_ids:
                # Use all order participants if auto-link is enabled
                all_participants |= self.participant_ids
            else:
                # Use specifically linked participants
                all_participants |= line.related_participants_ids
        
        action = {
            'name': _('Test Participants - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'participant',
            'view_mode': 'kanban,tree,form',
            'domain': [('id', 'in', all_participants.ids)],
            'context': {
                'default_sale_order_id': self.id,
                'search_default_not_confirmed': 1,
            },
            'help': _("""
                <p class="o_view_nocontent_smiling_face">
                    No test participants found.
                </p><p>
                    Participants linked to sale order lines with participant-based invoicing 
                    will appear here. Mark them as test completed to trigger invoicing.
                </p>
            """),
        }
        
        return action

    def write(self, vals):
        """Override to auto-enable participant data for participant products"""
        result = super().write(vals)
        
        # Auto-enable has_participant_data when participant products are added
        for order in self:
            has_participant_products = any(
                line.product_id.service_policy == 'delivered_participants' 
                for line in order.order_line
            )
            if has_participant_products and not order.has_participant_data:
                order.has_participant_data = True
        
        return result
    
    def unlink(self):
        """Delete related participants only if they do not have a lead_id; otherwise, just clear sale_order_id. Prevent deletion if state is 'closed'."""
        for order in self:
            if order.state == 'closed':
                raise UserError(_('You cannot delete a closed sale order. Please reopen it first.'))
            for participant in order.participant_ids:
                if participant.lead_id:
                    participant.sale_order_id = False
                else:
                    participant.unlink()
        return super().unlink()

    @api.model
    def create(self, vals):
        """Override to handle participant IDs from lead conversion"""
        order = super().create(vals)
        
        # Link participants from context (from lead conversion)
        participant_ids = vals.get('participant_ids')
        if participant_ids:
            ids = []
            for command in participant_ids:
                if command[0] == 6:  # Replace command
                    ids.extend(command[2])
                elif command[0] == 4:  # Link command
                    ids.append(command[1])
            
            if ids:
                self.env['participant'].browse(ids).write({'sale_order_id': order.id})
        
        return order