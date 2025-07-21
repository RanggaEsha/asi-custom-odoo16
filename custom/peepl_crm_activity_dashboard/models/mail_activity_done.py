# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)


class MailActivityDone(models.Model):
    _name = 'mail.activity.done'
    _description = 'Completed Mail Activities for CRM Dashboard'
    _order = 'date_done desc, id desc'
    _rec_name = 'summary'

    # Original activity fields
    activity_type_id = fields.Many2one('mail.activity.type', string='Activity Type', required=True)
    summary = fields.Char('Summary', required=True)
    note = fields.Html('Note')
    date_deadline = fields.Date('Due Date', required=True)
    date_done = fields.Date('Completed Date', required=True, default=fields.Date.context_today)
    user_id = fields.Many2one('res.users', string='Assigned to', required=True)
    completed_by_user_id = fields.Many2one('res.users', string='Completed by', required=True)
    request_partner_id = fields.Many2one('res.partner', string='Requesting Partner')
    priority = fields.Selection([
        ('0', 'Low'),
        ('1', 'Normal'),
        ('2', 'High'),
        ('3', 'Very High')
    ], string='Priority', default='1')
    
    # Lead/Opportunity related fields - Store data directly instead of using related fields
    lead_id = fields.Many2one('crm.lead', string='Lead/Opportunity', required=True, ondelete='cascade')
    lead_name = fields.Char('Lead Name', store=True)
    lead_email = fields.Char('Email', store=True)
    lead_phone = fields.Char('Phone', store=True)
    partner_id = fields.Many2one('res.partner', string='Customer', store=True)
    stage_id = fields.Many2one('crm.stage', string='Stage', store=True)
    team_id = fields.Many2one('crm.team', string='Sales Team', store=True)
    expected_revenue = fields.Monetary('Expected Revenue', store=True, currency_field='company_currency')
    probability = fields.Float('Probability (%)', store=True)
    company_currency = fields.Many2one('res.currency', string='Currency', store=True)
    lead_type = fields.Selection([
        ('lead', 'Lead'),
        ('opportunity', 'Opportunity')
    ], string='Type', store=True)
    
    # Completion specific fields
    feedback = fields.Html('Feedback', help='Feedback provided when marking activity as done')
    attachment_ids = fields.Many2many(
        'ir.attachment', 
        'mail_activity_done_attachment_rel',
        'activity_done_id', 
        'attachment_id',
        string='Attachments',
        help='Attachments provided when marking activity as done'
    )
    
    # Original activity ID for reference (will be null after activity is deleted)
    original_activity_id = fields.Integer('Original Activity ID', help='ID of the original mail.activity record')
    
    # Computed fields
    days_overdue = fields.Integer('Days Overdue', compute='_compute_days_overdue', store=True)
    state = fields.Selection([
        ('done', 'Done')
    ], string='Status', default='done', readonly=True)
    activity_color = fields.Char('Color', default='#4caf50', readonly=True)  # Green for done
    is_active = fields.Boolean('Active', default=False, readonly=True)
    record_source = fields.Selection([
        ('history', 'History')
    ], string='Source', default='history', readonly=True)

    @api.depends('date_deadline', 'date_done')
    def _compute_days_overdue(self):
        """Compute how many days the activity was overdue when completed"""
        for record in self:
            if record.date_deadline and record.date_done:
                if record.date_done > record.date_deadline:
                    delta = record.date_done - record.date_deadline
                    record.days_overdue = delta.days
                else:
                    record.days_overdue = 0
            else:
                record.days_overdue = 0

    @api.model
    def create_from_activity(self, activity, feedback=None, attachment_ids=None):
        """Create a done activity record from a mail.activity before it's deleted"""
        if not activity or activity.res_model != 'crm.lead':
            _logger.warning(f"Invalid activity for done record: {activity}")
            return False
        
        # Ensure we have a valid lead
        lead = self.env['crm.lead'].browse(activity.res_id)
        if not lead.exists():
            _logger.warning(f"Lead {activity.res_id} not found for activity {activity.id}")
            return False
            
        try:
            # Prepare values for the done activity record
            vals = {
                'activity_type_id': activity.activity_type_id.id,
                'summary': activity.summary or activity.activity_type_id.name,
                'note': activity.note or False,
                'date_deadline': activity.date_deadline,
                'date_done': fields.Date.context_today(self),
                'user_id': activity.user_id.id,
                'completed_by_user_id': self.env.user.id,
                'request_partner_id': activity.request_partner_id.id if activity.request_partner_id else False,
                'priority': '1',  # Default priority since mail.activity might not have this field
                'lead_id': lead.id,  # Pass the lead record ID, not activity.res_id
                'feedback': feedback or False,
                'original_activity_id': activity.id,
                
                # Store lead data directly to avoid related field issues
                'lead_name': lead.name,
                'lead_email': lead.email_from,
                'lead_phone': lead.phone,
                'partner_id': lead.partner_id.id if lead.partner_id else False,
                'stage_id': lead.stage_id.id if lead.stage_id else False,
                'team_id': lead.team_id.id if lead.team_id else False,
                'expected_revenue': lead.expected_revenue,
                'probability': lead.probability,
                'company_currency': lead.company_currency.id if lead.company_currency else False,
                'lead_type': lead.type,
            }
            
            # Create the done activity record
            done_activity = self.create(vals)
            
            # Link attachments if provided
            if attachment_ids:
                # Ensure attachments are valid and exist
                valid_attachments = self.env['ir.attachment'].browse(attachment_ids).exists()
                if valid_attachments:
                    # Create copies of attachments for the done activity
                    done_attachments = []
                    for attachment in valid_attachments:
                        try:
                            done_attachment = attachment.copy({
                                'res_model': 'mail.activity.done',
                                'res_id': done_activity.id,
                                'name': f"[DONE] {attachment.name}",
                            })
                            done_attachments.append(done_attachment.id)
                        except Exception as e:
                            _logger.warning(f"Failed to copy attachment {attachment.id}: {e}")
                    
                    if done_attachments:
                        done_activity.attachment_ids = [(6, 0, done_attachments)]
            
            _logger.info(f"Successfully created done activity {done_activity.id} from activity {activity.id}")
            return done_activity
                
        except Exception as e:
            _logger.error(f"Failed to create done activity from {activity.id}: {e}")
            # Log the full traceback for debugging
            import traceback
            _logger.error(f"Full traceback: {traceback.format_exc()}")
            return False

    @api.model
    def create(self, vals):
        """Override create to add validation and logging"""
        # Validate required fields
        if not vals.get('lead_id'):
            raise ValueError("Lead ID is required for done activity")
        
        if not vals.get('activity_type_id'):
            raise ValueError("Activity type is required for done activity")
        
        # Ensure lead exists
        lead = self.env['crm.lead'].browse(vals['lead_id'])
        if not lead.exists():
            raise ValueError(f"Lead with ID {vals['lead_id']} does not exist")
        
        result = super().create(vals)
        _logger.info(f"Created done activity record {result.id} for lead {vals.get('lead_id')}")
        return result

    def action_open_lead(self):
        """Action to open the related lead/opportunity"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Lead/Opportunity',
            'res_model': 'crm.lead',
            'res_id': self.lead_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_feedback(self):
        """Action to view completion feedback in a popup"""
        self.ensure_one()
        
        if not self.feedback:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Info',
                    'message': 'No feedback was provided for this completed activity.',
                    'type': 'info',
                }
            }
        
        return {
            'type': 'ir.actions.act_window',
            'name': f'Feedback: {self.summary}',
            'res_model': 'mail.activity.done',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {'form_view_initial_mode': 'readonly'},
        }

    def unlink(self):
        """Override unlink to log deletions"""
        for record in self:
            _logger.info(f"Deleting done activity {record.id} - {record.summary}")
        return super().unlink()