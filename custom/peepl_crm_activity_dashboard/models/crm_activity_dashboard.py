# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools
from datetime import datetime, date, timedelta
import logging

_logger = logging.getLogger(__name__)


class CrmActivityDashboard(models.Model):
    _name = 'crm.activity.dashboard'
    _description = 'CRM Activity Dashboard'
    _rec_name = 'user_id'
    _auto = False
    _order = 'date_deadline asc, priority desc, id desc'

    # Activity fields
    activity_id = fields.Integer('Activity ID', readonly=True)
    activity_type_id = fields.Many2one('mail.activity.type', string='Activity Type', readonly=True)
    activity_category = fields.Selection(related='activity_type_id.category', readonly=True)
    summary = fields.Char('Summary', readonly=True)
    note = fields.Html('Note', readonly=True)
    date_deadline = fields.Date('Due Date', readonly=True)
    date_done = fields.Date('Done Date', readonly=True)
    user_id = fields.Many2one('res.users', string='Assigned to', readonly=True)
    request_partner_id = fields.Many2one('res.partner', string='Requesting Partner', readonly=True)
    
    # Lead/Opportunity fields
    lead_id = fields.Integer('Lead ID', readonly=True)
    lead_name = fields.Char('Lead Name', readonly=True)
    lead_email = fields.Char('Email', readonly=True)
    lead_phone = fields.Char('Phone', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Customer', readonly=True)
    stage_id = fields.Many2one('crm.stage', string='Stage', readonly=True)
    team_id = fields.Many2one('crm.team', string='Sales Team', readonly=True)
    expected_revenue = fields.Monetary('Expected Revenue', currency_field='company_currency', readonly=True)
    probability = fields.Float('Probability (%)', readonly=True)
    company_currency = fields.Many2one('res.currency', string='Currency', readonly=True)
    
    # Computed fields for dashboard
    state = fields.Selection([
        ('overdue', 'Overdue'),
        ('today', 'Today'),
        ('tomorrow', 'Tomorrow'),
        ('planned', 'Planned'),
        ('done', 'Done')
    ], string='Status', readonly=True)
    
    priority = fields.Selection([
        ('0', 'Low'),
        ('1', 'Normal'),
        ('2', 'High'),
        ('3', 'Very High')
    ], string='Priority', readonly=True)
    
    days_overdue = fields.Integer('Days Overdue', readonly=True)
    activity_color = fields.Char('Color', readonly=True)
    is_active = fields.Boolean('Active', readonly=True)
    lead_type = fields.Selection([
        ('lead', 'Lead'),
        ('opportunity', 'Opportunity')
    ], string='Type', readonly=True)
    
    # Additional fields for done activities
    record_source = fields.Selection([
        ('active', 'Active'),
        ('history', 'History')
    ], string='Source', readonly=True)
    completed_by_user_id = fields.Many2one('res.users', string='Completed By', readonly=True)
    feedback = fields.Html('Feedback', readonly=True)
    # attachment_ids = fields.Many2many('ir.attachment', string='Attachments', readonly=True)

    def init(self):
        """Create the SQL view for the dashboard"""
        tools.drop_view_if_exists(self.env.cr, self._table)
        
        # Check if mail_activity_done table exists
        self.env.cr.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'mail_activity_done'
            );
        """)
        table_exists = self.env.cr.fetchone()[0]
        
        if table_exists:
            # Full query with UNION when mail_activity_done exists
            query = '''
                CREATE OR REPLACE VIEW %s AS (
                    -- Active activities from mail.activity
                    SELECT 
                        ma.id as id,
                        ma.id as activity_id,
                        ma.activity_type_id,
                        ma.summary,
                        ma.note,
                        ma.date_deadline,
                        NULL::date as date_done,
                        ma.user_id,
                        NULL::integer as completed_by_user_id,
                        ma.request_partner_id,
                        ma.res_id as lead_id,
                        cl.name as lead_name,
                        cl.email_from as lead_email,
                        cl.phone as lead_phone,
                        cl.partner_id,
                        cl.stage_id,
                        cl.team_id,
                        cl.expected_revenue,
                        cl.probability,
                        COALESCE(comp.currency_id, 1) as company_currency,
                        true as is_active,
                        cl.type as lead_type,
                        COALESCE(cl.priority, '1') as priority,
                        'active'::varchar as record_source,
                        NULL::text as feedback,
                        -- Compute state based on date_deadline
                        CASE 
                            WHEN ma.date_deadline < CURRENT_DATE THEN 'overdue'
                            WHEN ma.date_deadline = CURRENT_DATE THEN 'today'
                            WHEN ma.date_deadline = CURRENT_DATE + INTERVAL '1 day' THEN 'tomorrow'
                            ELSE 'planned'
                        END as state,
                        -- Compute days overdue
                        CASE 
                            WHEN ma.date_deadline < CURRENT_DATE THEN 
                                (CURRENT_DATE - ma.date_deadline)::integer
                            ELSE 0
                        END as days_overdue,
                        -- Compute activity color based on state and days overdue
                        CASE 
                            WHEN ma.date_deadline < CURRENT_DATE THEN 
                                CASE 
                                    WHEN (CURRENT_DATE - ma.date_deadline) > 7 THEN '#d32f2f'
                                    ELSE '#f44336'
                                END
                            WHEN ma.date_deadline = CURRENT_DATE THEN '#ff9800'
                            WHEN ma.date_deadline = CURRENT_DATE + INTERVAL '1 day' THEN '#ffeb3b'
                            ELSE '#9e9e9e'
                        END as activity_color
                    FROM mail_activity ma
                    INNER JOIN crm_lead cl ON ma.res_id = cl.id AND ma.res_model = 'crm.lead'
                    LEFT JOIN res_company comp ON comp.id = COALESCE(cl.company_id, 1)
                    WHERE ma.res_model = 'crm.lead'
                    
                    UNION ALL
                    
                    -- Done activities from mail.activity.done
                    SELECT 
                        mad.id + 100000 as id,  -- Offset to avoid ID conflicts
                        mad.original_activity_id as activity_id,
                        mad.activity_type_id,
                        mad.summary,
                        mad.note,
                        mad.date_deadline,
                        mad.date_done,
                        mad.user_id,
                        mad.completed_by_user_id,
                        mad.request_partner_id,
                        mad.lead_id,
                        mad.lead_name,
                        mad.lead_email,
                        mad.lead_phone,
                        mad.partner_id,
                        mad.stage_id,
                        mad.team_id,
                        mad.expected_revenue,
                        mad.probability,
                        mad.company_currency,
                        false as is_active,
                        mad.lead_type,
                        mad.priority,
                        'history'::varchar as record_source,
                        mad.feedback,
                        'done'::varchar as state,
                        mad.days_overdue,
                        '#4caf50'::varchar as activity_color  -- Green for done
                    FROM mail_activity_done mad
                    WHERE mad.lead_id IS NOT NULL
                )
            ''' % self._table
        else:
            # Simplified query without UNION when mail_activity_done doesn't exist yet
            query = '''
                CREATE OR REPLACE VIEW %s AS (
                    -- Active activities from mail.activity only
                    SELECT 
                        ma.id as id,
                        ma.id as activity_id,
                        ma.activity_type_id,
                        ma.summary,
                        ma.note,
                        ma.date_deadline,
                        NULL::date as date_done,
                        ma.user_id,
                        NULL::integer as completed_by_user_id,
                        ma.request_partner_id,
                        ma.res_id as lead_id,
                        cl.name as lead_name,
                        cl.email_from as lead_email,
                        cl.phone as lead_phone,
                        cl.partner_id,
                        cl.stage_id,
                        cl.team_id,
                        cl.expected_revenue,
                        cl.probability,
                        COALESCE(comp.currency_id, 1) as company_currency,
                        true as is_active,
                        cl.type as lead_type,
                        COALESCE(cl.priority, '1') as priority,
                        'active'::varchar as record_source,
                        NULL::text as feedback,
                        -- Compute state based on date_deadline
                        CASE 
                            WHEN ma.date_deadline < CURRENT_DATE THEN 'overdue'
                            WHEN ma.date_deadline = CURRENT_DATE THEN 'today'
                            WHEN ma.date_deadline = CURRENT_DATE + INTERVAL '1 day' THEN 'tomorrow'
                            ELSE 'planned'
                        END as state,
                        -- Compute days overdue
                        CASE 
                            WHEN ma.date_deadline < CURRENT_DATE THEN 
                                (CURRENT_DATE - ma.date_deadline)::integer
                            ELSE 0
                        END as days_overdue,
                        -- Compute activity color based on state and days overdue
                        CASE 
                            WHEN ma.date_deadline < CURRENT_DATE THEN 
                                CASE 
                                    WHEN (CURRENT_DATE - ma.date_deadline) > 7 THEN '#d32f2f'
                                    ELSE '#f44336'
                                END
                            WHEN ma.date_deadline = CURRENT_DATE THEN '#ff9800'
                            WHEN ma.date_deadline = CURRENT_DATE + INTERVAL '1 day' THEN '#ffeb3b'
                            ELSE '#9e9e9e'
                        END as activity_color
                    FROM mail_activity ma
                    INNER JOIN crm_lead cl ON ma.res_id = cl.id AND ma.res_model = 'crm.lead'
                    LEFT JOIN res_company comp ON comp.id = COALESCE(cl.company_id, 1)
                    WHERE ma.res_model = 'crm.lead'
                )
            ''' % self._table
            
        self.env.cr.execute(query)

    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None):
        """Override search_read to refresh the view data"""
        self.init()
        return super().search_read(domain, fields, offset, limit, order)

    @api.model
    def _refresh_dashboard_view(self):
        """Refresh the dashboard SQL view - can be called from other models"""
        try:
            self.init()
            # Clear any cached data
            self.env.registry.clear_cache()
            # Invalidate cache for this model
            self.invalidate_cache()
        except Exception as e:
            _logger.warning(f"Failed to refresh dashboard view: {e}")

    def action_open_lead(self):
        """Action to open the related lead/opportunity"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Lead/Opportunity',
            'res_model': 'crm.lead',
            'res_id': self.lead_id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_activity(self):
        """Action to open the activity form"""
        self.ensure_one()
        if self.record_source == 'active':
            return {
                'type': 'ir.actions.act_window',
                'name': 'Activity',
                'res_model': 'mail.activity',
                'res_id': self.activity_id,
                'view_mode': 'form',
                'target': 'new',
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Info',
                    'message': 'This activity has been completed and cannot be edited.',
                    'type': 'info',
                }
            }

    def action_mark_done_dashboard(self):
        """Action to mark activity as done - opens wizard for feedback and attachments"""
        self.ensure_one()
        
        # Only allow marking done for active activities
        if self.record_source != 'active':
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Warning',
                    'message': 'This activity is already completed.',
                    'type': 'warning',
                }
            }
        
        activity = self.env['mail.activity'].browse(self.activity_id)
        if not activity.exists():
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': 'Activity not found or already deleted.',
                    'type': 'danger',
                }
            }
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Mark Activity as Done',
            'res_model': 'activity.mark.done.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_id': self.id,
                'active_model': self._name,
                'form_view_ref': 'peepl_crm_activity_dashboard.view_activity_mark_done_wizard_form',
                'dashboard_refresh_needed': True,
            }
        }

    def action_schedule_next(self):
        """Action to schedule next activity"""
        self.ensure_one()
        if self.record_source == 'active':
            activity = self.env['mail.activity'].browse(self.activity_id)
            if activity.exists():
                return activity.action_feedback_schedule_next()
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Info',
                    'message': 'Cannot schedule next activity for completed activities.',
                    'type': 'info',
                }
            }
    
    def get_attachments(self):
        """Get attachments for done activities"""
        self.ensure_one()
        if self.record_source == 'history':
            # For done activities, get attachments from mail.activity.done
            done_activity_id = self.id - 100000  # Reverse the offset
            done_activity = self.env['mail.activity.done'].browse(done_activity_id)
            if done_activity.exists():
                return done_activity.attachment_ids
        return self.env['ir.attachment']

    def action_view_attachments(self):
        """Action to view attachments for completed activities"""
        self.ensure_one()
        
        if self.record_source != 'history':
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Info',
                    'message': 'Attachments are only available for completed activities.',
                    'type': 'info',
                }
            }
        
        attachments = self.get_attachments()
        
        if not attachments:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Info',
                    'message': 'No attachments found for this completed activity.',
                    'type': 'info',
                }
            }
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Activity Attachments',
            'res_model': 'ir.attachment',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', attachments.ids)],
            'context': {
                'default_res_model': 'mail.activity.done',
                'default_res_id': self.id - 100000,
            },
            'target': 'new',
        }


class MailActivity(models.Model):
    _inherit = 'mail.activity'

    @api.model
    def create(self, vals):
        """Override create to refresh dashboard view and notify users"""
        result = super().create(vals)
        
        # Refresh dashboard for CRM activities
        if vals.get('res_model') == 'crm.lead':
            self._refresh_dashboard_view()
        
        return result

    def write(self, vals):
        """Override write to refresh dashboard view and notify users"""
        crm_activities = self.filtered(lambda x: x.res_model == 'crm.lead')
        result = super().write(vals)
        
        if crm_activities:
            self._refresh_dashboard_view()
        
        return result

    def unlink(self):
        """Override unlink to refresh dashboard view and notify users"""
        crm_activities = self.filtered(lambda x: x.res_model == 'crm.lead')
        
        result = super().unlink()
        
        if crm_activities:
            self._refresh_dashboard_view()
        
        return result

    def action_done(self):
        """Override action_done to refresh dashboard immediately"""
        crm_activities = self.filtered(lambda x: x.res_model == 'crm.lead')
        result = super().action_done()
        
        if crm_activities:
            self._refresh_dashboard_view()
        
        return result

    def action_feedback_schedule_next(self):
        """Override action_feedback_schedule_next to refresh dashboard"""
        crm_activities = self.filtered(lambda x: x.res_model == 'crm.lead')
        result = super().action_feedback_schedule_next()
        
        if crm_activities:
            self._refresh_dashboard_view()
        
        return result

    def _refresh_dashboard_view(self):
        """Refresh the dashboard SQL view"""
        try:
            self.env['crm.activity.dashboard']._refresh_dashboard_view()
        except Exception as e:
            # Log error but don't break the activity operation
            _logger.warning(f"Failed to refresh dashboard view: {e}")


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    @api.model
    def create(self, vals):
        """Override create to refresh dashboard when lead is created"""
        result = super().create(vals)
        
        # If lead has activities, refresh dashboard
        if result.activity_ids:
            self.env['crm.activity.dashboard']._refresh_dashboard_view()
        
        return result

    def write(self, vals):
        """Override write to refresh dashboard when lead is updated"""
        result = super().write(vals)
        
        # If lead information that affects dashboard is updated, refresh
        dashboard_fields = ['name', 'email_from', 'phone', 'partner_id', 
                          'stage_id', 'team_id', 'expected_revenue', 'probability', 'type']
        
        if any(field in vals for field in dashboard_fields) and self.activity_ids:
            self.env['crm.activity.dashboard']._refresh_dashboard_view()
        
        return result