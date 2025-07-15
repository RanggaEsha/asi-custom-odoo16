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
    
    def project_count(self):
        project_obj = self.env['project.project']
        self.project_number = project_obj.search_count([('lead_id', 'in', [a.id for a in self])])

    def handover_count(self):
        """Count solution delivery leads created from this sales lead"""
        self.handover_number = self.env['crm.lead'].search_count([('parent_lead_id', '=', self.id)])

    def _compute_is_won_stage(self):
        """Compute if current stage is won"""
        for record in self:
            record.is_won_stage = record.stage_id.is_won if record.stage_id else False

    task_number = fields.Integer(compute='task_count', string='Tasks')
    project_number = fields.Integer(compute='project_count', string='Projects')
    
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
    
    def action_handover_to_solution_delivery(self):
        """Open handover wizard for team selection"""
        # Check if current lead is won
        if not self.is_won_stage:
            raise UserError(_('Only won leads can be handed over to Solution Delivery team.'))
        
        # Check user permission
        if not self.env.user.has_group('bi_crm_task.group_handover_manager'):
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
    
class crm_task_wizard(models.TransientModel):
    _name = 'crm.task.wizard'
    _description = "CRM Task Wizard"
    
    
    def get_name(self):
        ctx = dict(self._context or {})
        active_id = ctx.get('active_id')
        crm_brw = self.env['crm.lead'].browse(active_id)
        name = crm_brw.name
        return name
    
    
    create_project = fields.Boolean('Create New Project', default=False)
    project_id = fields.Many2one('project.project','Existing Project')
    project_name = fields.Char('Project Name')
    project_description = fields.Text('Project Description')
    create_task = fields.Boolean('Create Initial Task', default=True)
    dead_line = fields.Date('Deadline')
    name = fields.Char('Task Name',default = get_name)
    user_ids = fields.Many2many('res.users', relation='project_task_assignee_rel', column1='task_id', column2='user_id',
        string='Assignees', default=lambda self: self.env.user)

    @api.onchange('create_project')
    def _onchange_create_project(self):
        """Clear project_id when creating new project"""
        if self.create_project:
            self.project_id = False
            if not self.project_name:
                self.project_name = self.name
            # When creating new project, task creation becomes optional
            self.create_task = False
        else:
            # When using existing project, task creation is mandatory
            self.create_task = True
    
    @api.onchange('project_id')  
    def _onchange_project_id(self):
        """Clear create_project when selecting existing project"""
        if self.project_id:
            self.create_project = False
            self.create_task = True

    def create_project_task(self):
        ctx = dict(self._context or {})
        active_id = ctx.get('active_id')
        crm_brw = self.env['crm.lead'].browse(active_id)
        
        # Determine project_id
        project_id = False
        created_project = None
        
        if self.create_project:
            # Create new project
            project_vals = {
                'name': self.project_name or self.name,
                'description': self.project_description or False,
                'partner_id': crm_brw.partner_id.id or False,
                'lead_id': crm_brw.id or False,
            }
            created_project = self.env['project.project'].create(project_vals)
            project_id = created_project.id
        else:
            # Use existing project
            project_id = self.project_id.id if self.project_id else False
        
        # Create task only if requested
        created_task = None
        if self.create_task:
            user = []
            for users in self.user_ids:
                user.append(users.id)
            vals = {'name': self.name,
                    'project_id': project_id,
                    'user_ids': user or False,
                    'date_deadline':  self.dead_line or False,
                    'partner_id': crm_brw.partner_id.id or False,
                    'lead_id': crm_brw.id or False
                    }
            created_task = self.env['project.task'].create(vals)
        
        # Return action to show created project or task
        if self.create_project and created_project:
            return {
                'type': 'ir.actions.act_window',
                'name': 'Created Project',
                'res_model': 'project.project',
                'res_id': created_project.id,
                'view_mode': 'form',
                'target': 'current',
            }
        elif created_task:
            return {
                'type': 'ir.actions.act_window',
                'name': 'Created Task',
                'res_model': 'project.task',
                'res_id': created_task.id,
                'view_mode': 'form',
                'target': 'current',
            }
        else:
            # If only project was created without task, show success message
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Success',
                    'message': f'Project "{self.project_name or self.name}" has been created successfully.',
                    'type': 'success',
                    'sticky': False,
                }
            }
        
class project_Task(models.Model):
    _inherit='project.task'
    
    lead_id =  fields.Many2one('crm.lead', 'Opportunity')

class project_Project(models.Model):
    _inherit='project.project'
    
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
            'expected_revenue': self.expected_revenue,
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
        
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
