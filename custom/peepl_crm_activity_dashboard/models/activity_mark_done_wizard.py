# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class ActivityMarkDoneWizard(models.TransientModel):
    _name = 'activity.mark.done.wizard'
    _description = 'Mark Activity as Done with Feedback'

    activity_dashboard_id = fields.Many2one(
        'crm.activity.dashboard', 
        string='Activity Dashboard Record',
        required=True
    )
    activity_id = fields.Many2one(
        'mail.activity',
        string='Activity',
        required=True
    )
    activity_type_id = fields.Many2one(
        'mail.activity.type',
        string='Activity Type',
        readonly=True
    )
    summary = fields.Char('Summary', readonly=True)
    lead_name = fields.Char('Lead/Opportunity', readonly=True)
    user_id = fields.Many2one('res.users', string='Assigned To', readonly=True)
    date_deadline = fields.Date('Due Date', readonly=True)
    
    # Input fields
    feedback = fields.Html('Feedback', help='Provide feedback for this completed activity')
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'activity_done_wizard_attachment_rel',
        'wizard_id',
        'attachment_id',
        string='Attachments',
        help='Attach files to this completed activity'
    )

    @api.model
    def default_get(self, fields_list):
        """Set default values from context"""
        result = super().default_get(fields_list)
        
        # Get the activity dashboard record from context
        dashboard_id = self.env.context.get('active_id')
        if dashboard_id:
            dashboard = self.env['crm.activity.dashboard'].browse(dashboard_id)
            if dashboard.exists():
                activity = self.env['mail.activity'].browse(dashboard.activity_id)
                if activity.exists():
                    result.update({
                        'activity_dashboard_id': dashboard.id,
                        'activity_id': activity.id,
                        'activity_type_id': activity.activity_type_id.id,
                        'summary': activity.summary or activity.activity_type_id.name,
                        'lead_name': dashboard.lead_name,
                        'user_id': activity.user_id.id,
                        'date_deadline': activity.date_deadline,
                    })
        
        return result

    def action_mark_done_wizard(self):
        """Mark the activity as done with feedback and attachments"""
        self.ensure_one()
        
        activity = self.activity_id
        if not activity.exists():
            return {'type': 'ir.actions.act_window_close'}
        
        try:
            # Prepare attachment IDs for processing
            attachment_ids = []
            if self.attachment_ids:
                # Create copies of attachments that will be linked to both the done activity and the message
                for attachment in self.attachment_ids:
                    # Create a copy for the mail message
                    message_attachment = attachment.copy({
                        'res_model': 'mail.message',  # Will be updated after message creation
                        'res_id': 0,  # Will be updated after message creation
                    })
                    attachment_ids.append(message_attachment.id)
            
            # First, create the done activity record to preserve the data
            done_activity = self.env['mail.activity.done'].create_from_activity(
                activity, 
                feedback=self.feedback,
                attachment_ids=self.attachment_ids.ids if self.attachment_ids else None
            )
            
            if done_activity:
                _logger.info(f"Created done activity record {done_activity.id} for activity {activity.id}")
            
            # Now mark the original activity as done with feedback
            activity.action_feedback(
                feedback=self.feedback,
                attachment_ids=attachment_ids if attachment_ids else None
            )
            
            # Refresh the dashboard view
            activity.write({
                'state': 'done',
                'date_done': fields.Date.context_today(self),
            })
            
            # Return action to close wizard
            return {
                'type': 'ir.actions.act_window',
                'name': f'Feedback: {self.summary}',
                'res_model': 'mail.activity.done',
                'res_id': done_activity.id,
                'view_mode': 'form',
                'target': 'new',
                'context': {'form_view_initial_mode': 'readonly'},
            }
            
        except Exception as e:
            _logger.error(f"Error marking activity as done: {e}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': f'Failed to mark activity as done: {str(e)}',
                    'type': 'danger',
                }
            }

    def action_cancel(self):
        """Cancel the wizard"""
        return {'type': 'ir.actions.act_window_close'}
