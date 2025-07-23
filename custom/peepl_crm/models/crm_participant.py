# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class CrmParticipant(models.Model):
    _name = 'crm.participant'
    _description = 'CRM Participant Data'
    _order = 'first_name, last_name'

    first_name = fields.Char(string='First Name', required=True)
    last_name = fields.Char(string='Last Name', required=True)
    gender = fields.Selection([('male', 'Male'), ('female', 'Female'), ('other', 'Other')], string='Gender')
    email_address = fields.Char(string='Email Address')
    mobile_phone = fields.Char(string='Mobile Phone')
    job_title_requiring_assessment = fields.Char(string='Job Title Requiring Assessment')
    position_level = fields.Char(string='Position Level')
    lead_id = fields.Many2one('crm.lead', string='Lead/Opportunity', required=True, ondelete='cascade')
    
    # Additional fields for better data management
    active = fields.Boolean(string='Active', default=True)
    sequence = fields.Integer(string='Sequence', default=10)
    notes = fields.Text(string='Notes')
    
    @api.constrains('first_name', 'last_name', 'lead_id')
    def _check_unique_participant_per_lead(self):
        """Ensure participant names are unique within the same lead"""
        for record in self:
            existing = self.search([
                ('first_name', '=', record.first_name),
                ('last_name', '=', record.last_name),
                ('lead_id', '=', record.lead_id.id),
                ('id', '!=', record.id)
            ])
            if existing:
                raise UserError(_('Participant "%s %s" already exists for this lead/opportunity.') % (record.first_name, record.last_name))

    def name_get(self):
        """Display name with job title and position level info"""
        result = []
        for record in self:
            name = f"{record.first_name} {record.last_name}".strip()
            if record.job_title_requiring_assessment:
                name += f" - {record.job_title_requiring_assessment}"
            if record.position_level:
                name += f" ({record.position_level})"
            result.append((record.id, name))
        return result

    @api.model
    def import_participants_from_data(self, lead_id, participant_data):
        """
        Import participants from external data (CSV/Excel)
        participant_data should be a list of dictionaries with keys: first_name, last_name, gender, email_address, mobile_phone, job_title_requiring_assessment, position_level
        """
        if not isinstance(participant_data, list):
            raise UserError(_('Participant data should be a list of records.'))
        
        created_participants = []
        for data in participant_data:
            if not isinstance(data, dict):
                continue
                
            # Validate required fields
            if not data.get('first_name') or not data.get('last_name'):
                _logger.warning('Skipping participant without first_name or last_name: %s', data)
                continue
            
            # Check if participant already exists
            existing = self.search([
                ('first_name', '=', data['first_name']),
                ('last_name', '=', data['last_name']),
                ('lead_id', '=', lead_id)
            ])
            
            if existing:
                # Update existing participant
                existing.write({
                    'gender': data.get('gender', existing.gender),
                    'email_address': data.get('email_address', existing.email_address),
                    'mobile_phone': data.get('mobile_phone', existing.mobile_phone),
                    'job_title_requiring_assessment': data.get('job_title_requiring_assessment', existing.job_title_requiring_assessment),
                    'position_level': data.get('position_level', existing.position_level),
                })
                created_participants.append(existing)
            else:
                # Create new participant
                participant = self.create({
                    'first_name': data['first_name'],
                    'last_name': data['last_name'],
                    'gender': data.get('gender', ''),
                    'email_address': data.get('email_address', ''),
                    'mobile_phone': data.get('mobile_phone', ''),
                    'job_title_requiring_assessment': data.get('job_title_requiring_assessment', ''),
                    'position_level': data.get('position_level', ''),
                    'lead_id': lead_id,
                })
                created_participants.append(participant)
        
        return created_participants

# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AssessmentType(models.Model):
    _name = 'crm.assessment.type'
    _description = 'Assessment Type Configuration'
    _order = 'sequence, name'
    _rec_name = 'name'

    name = fields.Char(string='Assessment Type', required=True, translate=True)
    description = fields.Text(string='Description', translate=True)
    code = fields.Char(string='Code', help='Internal code for identification')
    active = fields.Boolean(string='Active', default=True)
    sequence = fields.Integer(string='Sequence', default=10, help='Order of appearance')
    color = fields.Integer(string='Color', help='Color for display purposes')
    
    # Statistical fields
    lead_count = fields.Integer(string='Number of Leads', compute='_compute_lead_count', store=True)
    
    @api.depends('name')
    def _compute_lead_count(self):
        """Count leads using this assessment type"""
        for record in self:
            record.lead_count = self.env['crm.lead'].search_count([('type_of_assessment', '=', record.id)])
    
    @api.constrains('code')
    def _check_unique_code(self):
        """Ensure code is unique if provided"""
        for record in self:
            if record.code:
                existing = self.search([('code', '=', record.code), ('id', '!=', record.id)])
                if existing:
                    raise UserError(_('Assessment type code "%s" already exists. Please use a unique code.') % record.code)
    
    def action_view_leads(self):
        """Open leads using this assessment type"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Leads with %s') % self.name,
            'res_model': 'crm.lead',
            'view_mode': 'tree,form',
            'domain': [('type_of_assessment', '=', self.id)],
            'context': {'default_type_of_assessment': self.id},
        }


class AssessmentLanguage(models.Model):
    _name = 'crm.assessment.language'
    _description = 'Assessment Language Configuration'
    _order = 'sequence, name'
    _rec_name = 'name'

    name = fields.Char(string='Language Name', required=True, translate=True)
    code = fields.Char(string='Language Code', help='ISO language code (e.g., en, id, zh)')
    native_name = fields.Char(string='Native Name', help='Language name in its native script')
    description = fields.Text(string='Description', translate=True)
    active = fields.Boolean(string='Active', default=True)
    sequence = fields.Integer(string='Sequence', default=10, help='Order of appearance')
    color = fields.Integer(string='Color', help='Color for display purposes')
    
    # Statistical fields
    lead_count = fields.Integer(string='Number of Leads', compute='_compute_lead_count', store=True)
    
    @api.depends('name')
    def _compute_lead_count(self):
        """Count leads using this assessment language"""
        for record in self:
            record.lead_count = self.env['crm.lead'].search_count([('assessment_language', '=', record.id)])
    
    @api.constrains('code')
    def _check_unique_code(self):
        """Ensure language code is unique if provided"""
        for record in self:
            if record.code:
                existing = self.search([('code', '=', record.code), ('id', '!=', record.id)])
                if existing:
                    raise UserError(_('Language code "%s" already exists. Please use a unique code.') % record.code)
    
    def name_get(self):
        """Display name with native name if available"""
        result = []
        for record in self:
            name = record.name
            if record.native_name and record.native_name != record.name:
                name += f' ({record.native_name})'
            if record.code:
                name += f' [{record.code}]'
            result.append((record.id, name))
        return result
    
    def action_view_leads(self):
        """Open leads using this assessment language"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Leads with %s') % self.name,
            'res_model': 'crm.lead',
            'view_mode': 'tree,form',
            'domain': [('assessment_language', '=', self.id)],
            'context': {'default_assessment_language': self.id},
        }