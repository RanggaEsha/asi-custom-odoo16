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
    
    # CHANGED: Store activity data as plain fields instead of references
    # This prevents issues when the activity gets deleted
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
    ], string='Priority', readonly=True)
    
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
                        'priority': getattr(activity, 'priority', '1'),
                    })
        
        return result

    def action_mark_done_wizard(self):
        """Mark the activity as done with feedback and attachments"""
        self.ensure_one()
        
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
        
        try:
            # STEP 1: Create the done activity record FIRST (before deleting the original)
            done_activity = self.env['mail.activity.done'].create_from_activity(
                activity, 
                feedback=self.feedback,
                attachment_ids=self.attachment_ids.ids if self.attachment_ids else None
            )
            
            if not done_activity:
                raise ValueError("Failed to create done activity record")
            
            _logger.info(f"Created done activity record {done_activity.id} for activity {activity.id}")
            
            # STEP 2: Prepare attachment IDs for the action_feedback call
            attachment_ids = []
            if self.attachment_ids:
                for attachment in self.attachment_ids:
                    # Create copies for the mail message
                    message_attachment = attachment.copy({
                        'res_model': 'mail.message',
                        'res_id': 0,
                    })
                    attachment_ids.append(message_attachment.id)
            
            # STEP 3: Store summary for success message (before activity is deleted)
            activity_summary = self.summary
            
            # STEP 4: Mark the original activity as done (this will DELETE the activity)
            activity.action_feedback(
                feedback=self.feedback,
                attachment_ids=attachment_ids if attachment_ids else None
            )
            
            # STEP 5: Force refresh the dashboard view
            self.env['crm.activity.dashboard']._refresh_dashboard_view()
            
            # STEP 6: Return success and close wizard
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Success',
                    'message': f'Activity "{activity_summary}" has been marked as done!',
                    'type': 'success',
                    'sticky': False,
                    'next': {
                        'type': 'ir.actions.client',
                        'tag': 'reload'  # This will refresh the dashboard view
                    }
                }
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