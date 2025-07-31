# -*- coding: utf-8 -*-
# Part of Peepl Sale Module

from odoo import api, fields, models, _


class Project(models.Model):
    _inherit = 'project.project'

    participant_ids = fields.One2many(
        'participant', 
        'project_id', 
        string='Participants'
    )
    
    participant_count = fields.Integer(
        string='Total Participants',
        compute='_compute_participant_count'
    )

    completed_participants_count = fields.Integer(
        string='Completed Participants',
        compute='_compute_participant_count'
    )
    
    is_participant_based = fields.Boolean(
        string='Has Participant-Based Products',
        compute='_compute_is_participant_based'
    )

    @api.depends('participant_ids', 'participant_ids.state')
    def _compute_participant_count(self):
        for project in self:
            project.participant_count = len(project.participant_ids)
            project.completed_participants_count = len(
                project.participant_ids.filtered(lambda p: p.state == 'confirmed')
            )

    @api.depends('sale_line_id.product_id.service_policy')
    def _compute_is_participant_based(self):
        for project in self:
            project.is_participant_based = (
                project.sale_line_id and 
                project.sale_line_id.product_id.service_policy == 'delivered_participants'
            )

    def action_view_participants(self):
        """Action to view all participants in this project"""
        self.ensure_one()
        
        action = {
            'name': _('Test Participants - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'participant',
            'view_mode': 'tree,form',
            'domain': [('project_id', '=', self.id)],
            'context': {
                'default_project_id': self.id,
                'default_sale_line_id': self.sale_line_id.id if self.sale_line_id else False,
                'search_default_not_confirmed': 1,
            },
            'help': _("""
                <p class="o_view_nocontent_smiling_face">
                    No test participants found. Let's create some!
                </p><p>
                    Add participants who will take the test. 
                    Mark them as test completed when they finish.
                </p>
            """),
        }
        
        return action

    def action_mark_all_participants_completed(self):
        """Action to mark all participants as test completed and refresh view"""
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
        incomplete_participants.write({
            'state': 'confirmed',
            'completion_date': fields.Datetime.now()
        })
        sale_lines = incomplete_participants.mapped('sale_line_id').filtered(
            lambda sol: sol.qty_delivered_method == 'participants'
        )
        if sale_lines:
            sale_lines._compute_qty_delivered()
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

    def _get_stat_buttons(self):
        """Override to add participant statistics"""
        buttons = super()._get_stat_buttons()
        
        if self.is_participant_based and self.participant_count > 0:
            buttons.append({
                'icon': 'users',
                'text': _('Test Participants'),
                'number': f"{self.completed_participants_count}/{self.participant_count}",
                'action_type': 'object',
                'action': 'action_view_participants',
                'show': True,
                'sequence': 5,
            })
        
        return buttons

    def get_panel_data(self):
        """Override to include participant data in project panel"""
        panel_data = super().get_panel_data()
        
        if self.is_participant_based:
            panel_data.update({
                'participants': self._get_participants_data(),
            })
        
        return panel_data

    def _get_participants_data(self):
        """Get participant data for project panel"""
        if not self.user_has_groups('project.group_project_user'):
            return {}
        
        participants = self.participant_ids.sudo()
        
        return {
            'total': len(participants),
            'completed': len(participants.filtered(lambda p: p.state == 'confirmed')),
            'pending': len(participants.filtered(lambda p: p.state == 'not_yet_confirmed')),
            'rescheduled': len(participants.filtered(lambda p: p.state == 'rescheduled')),
            'cancelled': len(participants.filtered(lambda p: p.state == 'cancelled')),
            'data': participants.read([
                'first_name', 'last_name', 'state',
                'completion_date', 'email_address', 'mobile_phone'
            ])[:10],  # Limit to first 10 for performance
        }
    
    @api.model
    def get_project_overview_data(self, project_id):
        """Override to remove sales and profitability data from project overview"""
        result = super().get_project_overview_data(project_id)
        
        # Remove sales-related data from the result
        if isinstance(result, dict):
            # Remove sales sections
            result.pop('sales', None)
            result.pop('profitability', None)
            result.pop('sale_orders', None)
            result.pop('sales_orders', None)
            
            # Remove any nested sales data
            if 'sections' in result:
                result['sections'] = [
                    section for section in result['sections'] 
                    if section.get('name', '').lower() not in ['sales', 'profitability', 'sale_orders']
                ]
        
        return result

    def get_last_update_or_default(self, project_id):
        """Override to remove sales data from project updates"""
        result = super().get_last_update_or_default(project_id)
        
        if isinstance(result, dict):
            # Remove sales-related fields from project update data
            result.pop('sales_data', None)
            result.pop('profitability_data', None)
            
        return result

    @api.model
    def get_project_dashboard_data(self, project_ids):
        """Override dashboard data to exclude sales information"""
        result = super().get_project_dashboard_data(project_ids)
        
        if isinstance(result, dict):
            for project_id, project_data in result.items():
                if isinstance(project_data, dict):
                    # Remove sales-related dashboard data
                    project_data.pop('sales', None)
                    project_data.pop('profitability', None)
                    project_data.pop('sale_orders', None)
                    
        return result

    def _get_stat_buttons(self):
        """Override to remove sales-related stat buttons"""
        result = super()._get_stat_buttons()
        
        # Filter out sales-related stat buttons
        if isinstance(result, list):
            result = [
                button for button in result 
                if not any(keyword in button.get('name', '').lower() 
                          for keyword in ['sale', 'profit', 'invoice'])
            ]
        
        return result