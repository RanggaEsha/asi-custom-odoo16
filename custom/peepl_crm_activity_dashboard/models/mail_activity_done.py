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
    
    # Lead/Opportunity related fields
    lead_id = fields.Many2one('crm.lead', string='Lead/Opportunity', required=True, ondelete='cascade')
    lead_name = fields.Char('Lead Name', related='lead_id.name', store=True)
    lead_email = fields.Char('Email', related='lead_id.email_from', store=True)
    lead_phone = fields.Char('Phone', related='lead_id.phone', store=True)
    partner_id = fields.Many2one('res.partner', string='Customer', related='lead_id.partner_id', store=True)
    stage_id = fields.Many2one('crm.stage', string='Stage', related='lead_id.stage_id', store=True)
    team_id = fields.Many2one('crm.team', string='Sales Team', related='lead_id.team_id', store=True)
    expected_revenue = fields.Monetary('Expected Revenue', related='lead_id.expected_revenue', store=True, currency_field='company_currency')
    probability = fields.Float('Probability (%)', related='lead_id.probability', store=True)
    company_currency = fields.Many2one('res.currency', related='lead_id.company_currency', store=True)
    lead_type = fields.Selection([
        ('lead', 'Lead'),
        ('opportunity', 'Opportunity')
    ], string='Type', related='lead_id.type', store=True)
    
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
                'note': activity.note,
                'date_deadline': activity.date_deadline,
                'date_done': fields.Date.context_today(self),
                'user_id': activity.user_id.id,
                'completed_by_user_id': self.env.user.id,
                'request_partner_id': activity.request_partner_id.id if activity.request_partner_id else False,
                'priority': getattr(activity, 'priority', '1'),
                'lead_id': activity.res_id,
                'feedback': feedback,
                'original_activity_id': activity.id,
            }
            
            # Create the done activity record with transaction safety
            with self.env.cr.savepoint():
                done_activity = self.create(vals)
                
                # Link attachments if provided
                if attachment_ids:
                    # Ensure attachments are valid
                    valid_attachments = self.env['ir.attachment'].browse(attachment_ids).exists()
                    if valid_attachments:
                        done_activity.attachment_ids = [(6, 0, valid_attachments.ids)]
                
                _logger.info(f"Successfully created done activity {done_activity.id} from activity {activity.id}")
                return done_activity
                
        except Exception as e:
            _logger.error(f"Failed to create done activity from {activity.id}: {e}")
            return False

    @api.model
    def create(self, vals):
        """Override create to add validation and logging"""
        # Validate required fields
        if not vals.get('lead_id'):
            raise ValueError("Lead ID is required for done activity")
        
        if not vals.get('activity_type_id'):
            raise ValueError("Activity type is required for done activity")
        
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