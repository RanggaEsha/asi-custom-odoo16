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
    
    # Store activity data as plain fields instead of references
    activity_id_original = fields.Integer('Original Activity ID', required=True)
    activity_type_id = fields.Many2one('mail.activity.type', string='Activity Type', readonly=True)
    summary = fields.Char('Summary', readonly=True)
    lead_name = fields.Char('Lead/Opportunity', readonly=True)
    lead_id = fields.Integer('Lead ID', readonly=True)
    user_id = fields.Many2one('res.users', string='Assigned To', readonly=True)
    date_deadline = fields.Date('Due Date', readonly=True)
    note = fields.Html('Activity Notes', readonly=True)
    request_partner_id = fields.Many2one('res.partner', string='Requesting Partner', readonly=True)
    priority = fields.Selection([
        ('0', 'Low'),
        ('1', 'Normal'),
        ('2', 'High'),
        ('3', 'Very High')
    ], string='Priority', readonly=True, default='1')
    
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
        
        try:
            # Get the activity dashboard record from context
            dashboard_id = self.env.context.get('active_id')
            if dashboard_id:
                dashboard = self.env['crm.activity.dashboard'].browse(dashboard_id)
                if dashboard.exists():
                    # Get the actual activity record
                    activity = self.env['mail.activity'].browse(dashboard.activity_id)
                    if activity.exists():
                        # Store all activity data as plain fields (no references)
                        result.update({
                            'activity_dashboard_id': dashboard.id,
                            'activity_id_original': activity.id,
                            'activity_type_id': activity.activity_type_id.id,
                            'summary': activity.summary or activity.activity_type_id.name,
                            'lead_name': dashboard.lead_name,
                            'lead_id': dashboard.lead_id,
                            'user_id': activity.user_id.id,
                            'date_deadline': activity.date_deadline,
                            'note': activity.note,
                            'request_partner_id': activity.request_partner_id.id if activity.request_partner_id else False,
                            'priority': '1',  # Default priority
                        })
        except Exception as e:
            _logger.error(f"Error in wizard default_get: {e}")
        
        return result

    def action_mark_done_wizard(self):
        """Mark the activity as done with feedback and attachments"""
        self.ensure_one()
        
        try:
            # Get the activity record using the stored ID
            activity = self.env['mail.activity'].browse(self.activity_id_original)
            if not activity.exists():
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Error',
                        'message': 'Activity not found or already completed.',
                        'type': 'warning',
                    }
                }
            
            _logger.info(f"Starting to mark activity {activity.id} as done")
            
            # STEP 1: Create the done activity record FIRST (before deleting the original)
            done_activity = self.env['mail.activity.done'].create_from_activity(
                activity, 
                feedback=self.feedback,
                attachment_ids=self.attachment_ids.ids if self.attachment_ids else None
            )
            
            if not done_activity:
                _logger.error(f"Failed to create done activity record for activity {activity.id}")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Error',
                        'message': 'Failed to create completed activity record. Please check the logs.',
                        'type': 'danger',
                    }
                }
            
            _logger.info(f"Successfully created done activity record {done_activity.id}")
            
            # STEP 2: Prepare attachment IDs for the action_feedback call
            attachment_ids = []
            if self.attachment_ids:
                for attachment in self.attachment_ids:
                    # Create copies for the mail message
                    try:
                        message_attachment = attachment.copy({
                            'res_model': 'mail.message',
                            'res_id': 0,
                        })
                        attachment_ids.append(message_attachment.id)
                    except Exception as e:
                        _logger.warning(f"Failed to copy attachment {attachment.id}: {e}")
            
            # STEP 3: Store summary for success message (before activity is deleted)
            activity_summary = self.summary
            
            # STEP 4: Mark the original activity as done (this will DELETE the activity)
            _logger.info(f"Calling action_feedback on activity {activity.id}")
            message_id = activity.action_feedback(
                feedback=self.feedback,
                attachment_ids=attachment_ids if attachment_ids else None
            )

            _logger.info(f"Activity feedback completed, message_id: {message_id}")

            _logger.info(f"Activity feedback completed, message_id: {message_id}")

            # Send success notification via bus
            self.env['bus.bus']._sendone(
                self.env.user.partner_id,
                'simple_notification',
                {
                    'title': 'Activity Completed',
                    'message': f'Activity "{activity_summary}" has been marked as done successfully.',
                    'type': 'success',
                    'sticky': False,
                }
            )

            # Get lead information for navigation
            lead_id = self.lead_id
            if not lead_id and hasattr(activity, 'res_id') and activity.res_model == 'crm.lead':
                lead_id = activity.res_id

            # Navigate directly to the lead with the log note focused
            return {
                'type': 'ir.actions.act_window',
                'name': 'Lead/Opportunity',
                'res_model': 'crm.lead',
                'res_id': lead_id,
                'view_mode': 'form',
                'target': 'current',
                'context': {
                    'default_type': 'lead',
                    'focus_message_id': message_id,
                    'open_chatter': True,
                    'scroll_to_message': message_id,
                    'highlight_message': message_id,
                }
            }
        except Exception as e:
            _logger.error(f"Error marking activity as done: {e}")
            import traceback
            _logger.error(f"Full traceback: {traceback.format_exc()}")
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