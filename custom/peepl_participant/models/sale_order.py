
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


class SaleOrder(models.Model):
    """ Sale Order Case """
    _inherit = "sale.order"

    # Participant management
    has_participant_data = fields.Boolean(string='Has Participant Data', default=False)
    test_start_date = fields.Date(string='Test Start Date')
    test_finish_date = fields.Date(string='Test Finish Date')
    purpose = fields.Text(string='Purpose')
    
    # REFACTORED: Changed from Selection to Many2one
    type_of_assessment = fields.Many2many(
        'assessment.type',
        'sale_order_assessment_type_rel',
        'sale_order_id',
        'assessment_type_id',
        string='Type of Assessment',
        help='Select one or more types of assessment for this sale order'
    )

    assessment_language = fields.Many2many(
        'assessment.language',
        'sale_order_assessment_language_rel',
        'sale_order_id',
        'assessment_language_id',
        string='Assessment Language',
        help='Select one or more languages for the assessment'
    )
    
    # Participant management
    participant_ids = fields.One2many('participant', 'sale_order_id', string='Participants')
    participant_count = fields.Integer(string='Participant Count', compute='_compute_participant_count')
    
    def _compute_participant_count(self):
        """Compute participant count"""
        for record in self:
            record.participant_count = self.env['participant'].search_count([('sale_order_id', '=', record.id)])

    @api.depends('participant_ids')
    def _compute_participant_count(self):
        """Count participants for this sale order"""
        for record in self:
            record.participant_count = len(record.participant_ids)
    
    def action_view_participants(self):
        """Open participants view for this sale order"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Participants - {self.name}',
            'res_model': 'participant',
            'view_mode': 'tree,form',
            'domain': [('sale_order_id', '=', self.id)],
            'context': {'default_sale_order_id': self.id},
        }
    
    @api.onchange('type_of_assessment')
    def _onchange_type_of_assessment(self):
        """Update purpose field when assessment type changes (Many2many)"""
        if self.type_of_assessment:
            descriptions = [desc for desc in self.type_of_assessment.mapped('description') if isinstance(desc, str) and desc]
            if descriptions and not self.purpose:
                self.purpose = ', '.join(descriptions)
    
    @api.onchange('has_participant_data')
    def _onchange_has_participant_data(self):
        """Clear assessment fields when participant data is disabled"""
        if not self.has_participant_data:
            self.type_of_assessment = False
            self.assessment_language = False
            self.test_start_date = False
            self.test_finish_date = False
            self.purpose = False

    @api.model_create_multi
    def create(self, vals_list):
        """Update assessment type/language counts when creating leads"""
        records = super().create(vals_list)
        self._update_assessment_counts(records)
        return records
    
    def write(self, vals):
        """Update assessment type/language counts when updating leads"""
        old_assessment_types = self.mapped('type_of_assessment')
        old_assessment_languages = self.mapped('assessment_language')
        
        result = super().write(vals)
        
        if 'type_of_assessment' in vals or 'assessment_language' in vals:
            new_assessment_types = self.mapped('type_of_assessment')
            new_assessment_languages = self.mapped('assessment_language')
            
            # Update counts for old and new assessment types/languages
            all_types = (old_assessment_types | new_assessment_types).filtered(lambda x: x)
            all_languages = (old_assessment_languages | new_assessment_languages).filtered(lambda x: x)
            
            self._update_specific_counts(all_types, all_languages)
        
        return result
    
    def unlink(self):
        """Update assessment type/language counts when deleting leads"""
        assessment_types = self.mapped('type_of_assessment').filtered(lambda x: x)
        assessment_languages = self.mapped('assessment_language').filtered(lambda x: x)
        
        result = super().unlink()
        
        self._update_specific_counts(assessment_types, assessment_languages)
        return result
    
    def _update_assessment_counts(self, records):
        """Helper method to update assessment counts"""
        assessment_types = records.mapped('type_of_assessment').filtered(lambda x: x)
        assessment_languages = records.mapped('assessment_language').filtered(lambda x: x)
        self._update_specific_counts(assessment_types, assessment_languages)
    
    def _update_specific_counts(self, assessment_types, assessment_languages):
        """Update lead counts for specific assessment types and languages"""
        if assessment_types:
            assessment_types._compute_lead_count()
        if assessment_languages:
            assessment_languages._compute_lead_count()