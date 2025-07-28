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

    @api.depends('participant_ids')
    def _compute_participant_count(self):
        for project in self:
            project.participant_count = len(project.participant_ids)
            project.completed_participants_count = len(
                project.participant_ids.filtered('done')
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
            'name': _('Participants - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'participant',
            'view_mode': 'tree,form',
            'domain': [('project_id', '=', self.id)],
            'context': {
                'default_project_id': self.id,
                'default_sale_line_id': self.sale_line_id.id if self.sale_line_id else False,
            },
            'help': _("""
                <p class="o_view_nocontent_smiling_face">
                    No participants found. Let's create some!
                </p><p>
                    Add participants who will take the test. 
                    Mark them as completed when they finish.
                </p>
            """),
        }
        
        return action

    def action_mark_all_participants_done(self):
        """Action to mark all participants as done"""
        self.ensure_one()
        
        incomplete_participants = self.participant_ids.filtered(lambda p: not p.done)
        if not incomplete_participants:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Info'),
                    'message': _('All participants are already completed!'),
                    'type': 'info',
                }
            }
        
        incomplete_participants.write({
            'done': True,
            'done_date': fields.Datetime.now()
        })
        
        # Update related sale order lines
        sale_lines = incomplete_participants.mapped('sale_line_id')
        if sale_lines:
            sale_lines._compute_qty_delivered()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('%d participants marked as completed!') % len(incomplete_participants),
                'type': 'success',
            }
        }

    def _get_stat_buttons(self):
        """Override to add participant statistics"""
        buttons = super()._get_stat_buttons()
        
        if self.is_participant_based and self.participant_count > 0:
            buttons.append({
                'icon': 'users',
                'text': _('Participants'),
                'number': f"{self.completed_participants_count}/{self.participant_count}",
                'action_type': 'object',
                'action': 'action_view_sale_participants',
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
            'completed': len(participants.filtered('done')),
            'data': participants.read([
                'name', 'participant_code', 'done', 
                'done_date', 'email', 'phone'
            ])[:10],  # Limit to first 10 for performance
        }