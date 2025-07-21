# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo.tools.translate import _
from datetime import datetime, timedelta, date
from dateutil.relativedelta import relativedelta
from odoo import tools, api
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT
from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging
from odoo.osv import  osv
from odoo import SUPERUSER_ID



class crm_lead(models.Model):
    """ CRM Lead Case """
    _inherit = "crm.lead"

    def task_count(self):
        task_obj = self.env['project.task']
        self.task_number = task_obj.search_count([('lead_id', 'in', [a.id for a in self])])

    def handover_count(self):
        """Count solution delivery leads created from this sales lead"""
        self.handover_number = self.env['crm.lead'].search_count([('parent_lead_id', '=', self.id)])

    def _compute_is_won_stage(self):
        """Compute if current stage is won"""
        for record in self:
            record.is_won_stage = record.stage_id.is_won if record.stage_id else False

    def _compute_participant_count(self):
        """Compute participant count"""
        for record in self:
            record.participant_count = self.env['crm.participant'].search_count([('lead_id', '=', record.id)])

    task_number = fields.Integer(compute='task_count', string='Tasks')
    
    # Handover fields
    parent_lead_id = fields.Many2one('crm.lead', string='Parent Sales Lead', 
                                   help='Original sales lead that was handed over to solution delivery')
    handover_number = fields.Integer(compute='handover_count', string='Handovers')
    is_handover_lead = fields.Boolean(string='Is Handover Lead', default=False,
                                    help='True if this lead was created from a sales handover')
    handover_date = fields.Datetime(string='Handover Date', 
                                  help='Date when this lead was handed over or created from handover')
    is_won_stage = fields.Boolean(string='Is Won Stage', compute='_compute_is_won_stage',
                                help='True if current stage is marked as won')
    
    # Participant data fields
    has_participant_data = fields.Boolean(string='Has Participant Data', default=False,
                                        help='Enable to manage participant data for this lead/opportunity')
    participant_ids = fields.One2many('crm.participant', 'lead_id', string='Participants')
    participant_count = fields.Integer(string='Participant Count', compute='_compute_participant_count')
    
    # Assessment fields (visible when has_participant_data is True)
    purpose = fields.Text(string='Purpose', help='Purpose of the assessment')
    test_start_date = fields.Date(string='Test Start Date')
    test_finish_date = fields.Date(string='Test Finish Date')
    type_of_assessment = fields.Selection([
        ('written', 'Written'),
        ('practical', 'Practical'),
        ('oral', 'Oral'),
        ('mixed', 'Mixed'),
        ('online', 'Online')
    ], string='Type of Assessment')
    assessment_language = fields.Selection([
        ('english', 'English'),
        ('indonesian', 'Indonesian'),
        ('mandarin', 'Mandarin'),
        ('japanese', 'Japanese'),
        ('korean', 'Korean'),
        ('other', 'Other')
    ], string='Assessment Language')
    
    def action_handover_to_solution_delivery(self):
        """Open handover wizard for team selection"""
        # Check if current lead is won
        if not self.is_won_stage:
            raise UserError(_('Only won leads can be handed over to Solution Delivery team.'))
        
        # Check user permission
        if not self.env.user.has_group('peepl_crm.group_handover_manager'):
            raise UserError(_('You do not have permission to perform handover operations. Please contact your administrator.'))
        
        # Return wizard action
        return {
            'type': 'ir.actions.act_window',
            'name': 'Handover to Team',
            'res_model': 'crm.handover.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_source_lead_id': self.id,
                'active_id': self.id,
            }
        }

    def action_view_participants(self):
        """Action to view participants in a dedicated window"""
        return {
            'name': _('Participants'),
            'type': 'ir.actions.act_window',
            'res_model': 'crm.participant',
            'view_mode': 'tree,form',
            'domain': [('lead_id', '=', self.id)],
            'context': {
                'default_lead_id': self.id,
                'search_default_lead_id': self.id,
            },
            'target': 'current',
        }
    
class crm_task_wizard(models.TransientModel):
    _name = 'crm.task.wizard'
    _description = "CRM Task Wizard"
    
    def get_name(self):
        ctx = dict(self._context or {})
        active_id = ctx.get('active_id')
        crm_brw = self.env['crm.lead'].browse(active_id)
        name = crm_brw.name
        return name
    
    project_id = fields.Many2one('project.project', 'Project', required=True)
    dead_line = fields.Date('Deadline')
    name = fields.Char('Task Name', default=get_name, required=True)
    user_ids = fields.Many2many('res.users', relation='project_task_assignee_rel', column1='task_id', column2='user_id',
        string='Assignees', default=lambda self: self.env.user)

    def create_task(self):
        """Create task in selected project"""
        ctx = dict(self._context or {})
        active_id = ctx.get('active_id')
        crm_brw = self.env['crm.lead'].browse(active_id)
        
        if not self.project_id:
            raise UserError(_('Please select a project for the task.'))
        
        # Create task
        user = []
        for users in self.user_ids:
            user.append(users.id)
            
        vals = {
            'name': self.name,
            'project_id': self.project_id.id,
            'user_ids': user or False,
            'date_deadline': self.dead_line or False,
            'partner_id': crm_brw.partner_id.id or False,
            'lead_id': crm_brw.id or False
        }
        created_task = self.env['project.task'].create(vals)
        
        # Return action to show created task
        return {
            'type': 'ir.actions.act_window',
            'name': 'Created Task',
            'res_model': 'project.task',
            'res_id': created_task.id,
            'view_mode': 'form',
            'target': 'current',
        }
        
class project_Task(models.Model):
    _inherit='project.task'
    
    lead_id =  fields.Many2one('crm.lead', 'Opportunity')

class crm_handover_wizard(models.TransientModel):
    _name = 'crm.handover.wizard'
    _description = "CRM Handover Wizard"
    
    source_lead_id = fields.Many2one('crm.lead', string='Source Lead', required=True)
    target_team_id = fields.Many2one('crm.team', string='Target Team', required=True,
                                   domain="[('id', '!=', source_team_id)]")
    source_team_id = fields.Many2one('crm.team', string='Source Team', related='source_lead_id.team_id', readonly=True)
    assigned_user_id = fields.Many2one('res.users', string='Assign to User',
                                     help='Leave empty to assign to team leader')
    handover_note = fields.Text(string='Handover Notes', 
                               help='Additional notes for the handover process')
    expected_revenue = fields.Float(string='Expected Revenue', default=0.0,
                                  help='Expected revenue for the target team (leave 0 for them to set)')
    
    @api.onchange('target_team_id')
    def _onchange_target_team_id(self):
        """Update user domain when team changes"""
        if self.target_team_id:
            # Set default user to team leader
            self.assigned_user_id = self.target_team_id.user_id
            # Update domain for user selection
            return {
                'domain': {
                    'assigned_user_id': [
                        '|', 
                        ('id', 'in', self.target_team_id.member_ids.ids),
                        ('id', '=', self.target_team_id.user_id.id)
                    ]
                }
            }
        else:
            self.assigned_user_id = False
            return {'domain': {'assigned_user_id': []}}
    
    def action_create_handover_lead(self):
        """Create handover lead with selected team"""
        # Validation
        if not self.target_team_id:
            raise UserError(_('Please select a target team for handover.'))
        
        if self.target_team_id == self.source_team_id:
            raise UserError(_('Target team cannot be the same as source team.'))
        
        # Prepare handover lead data
        source_lead = self.source_lead_id
        
        # Get the first stage for the target team
        target_stage = False
        if self.target_team_id:
            # Get stages available for the target team
            stages = self.env['crm.stage'].search([
                '|', 
                ('team_id', '=', self.target_team_id.id),
                ('team_id', '=', False)  # Global stages
            ], order='sequence', limit=1)
            if stages:
                target_stage = stages[0].id
        
        handover_vals = {
            'name': f"[HANDOVER] {source_lead.name}",
            'partner_id': source_lead.partner_id.id,
            'partner_name': source_lead.partner_name,
            'email_from': source_lead.email_from,
            'phone': source_lead.phone,
            'mobile': source_lead.mobile,
            'website': source_lead.website,
            'street': source_lead.street,
            'street2': source_lead.street2,
            'city': source_lead.city,
            'state_id': source_lead.state_id.id if source_lead.state_id else False,
            'zip': source_lead.zip,
            'country_id': source_lead.country_id.id if source_lead.country_id else False,
            'description': source_lead.description,
            'team_id': self.target_team_id.id,
            'user_id': self.assigned_user_id.id if self.assigned_user_id else self.target_team_id.user_id.id,
            'parent_lead_id': source_lead.id,
            'is_handover_lead': True,
            'handover_date': fields.Datetime.now(),
            'type': 'opportunity',  # Start as opportunity in target team
            'stage_id': target_stage,
        }
        
        # Create handover lead
        handover_lead = self.env['crm.lead'].create(handover_vals)
        
        # Prepare handover message
        handover_message = f"Lead handed over to {self.target_team_id.name} team."
        if self.assigned_user_id:
            handover_message += f" Assigned to: {self.assigned_user_id.name}"
        if self.handover_note:
            handover_message += f"\n\nHandover Notes: {self.handover_note}"
        handover_message += f"\n\nNew lead created: {handover_lead.name}"
        
        # Log activity in source lead
        source_lead.message_post(
            body=handover_message,
            subject=f"Handover to {self.target_team_id.name}"
        )
        
        # Log activity in handover lead
        creation_message = f"Lead created from {self.source_team_id.name} team handover."
        creation_message += f"\nOriginal lead: {source_lead.name}"
        if self.handover_note:
            creation_message += f"\n\nHandover Notes: {self.handover_note}"
        
        handover_lead.message_post(
            body=creation_message,
            subject=f"Created from {self.source_team_id.name} Handover"
        )
        
        # Create activity for assigned user
        if self.assigned_user_id:
            handover_lead.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=self.assigned_user_id.id,
                summary=f'New handover lead from {self.source_team_id.name}',
                note=f'Please review this lead handed over from {self.source_team_id.name} team.'
            )
        
        # Return action to show the created handover lead
        return {
            'type': 'ir.actions.act_window',
            'name': f'Handover Lead - {self.target_team_id.name}',
            'res_model': 'crm.lead',
            'res_id': handover_lead.id,
            'view_mode': 'form',
            'target': 'current',
        }
        