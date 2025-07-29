# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CrmLead(models.Model):
    """ CRM Lead Case """
    _inherit = "crm.lead"

    # Participant management
    has_participant_data = fields.Boolean(string='Has Participant Data', default=False)
    test_start_date = fields.Date(string='Test Start Date')
    test_finish_date = fields.Date(string='Test Finish Date')
    purpose = fields.Text(string='Purpose')
    
    # Assessment configuration
    type_of_assessment = fields.Many2many(
        'assessment.type',
        'lead_assessment_type_rel',
        'lead_id',
        'assessment_type_id',
        string='Type of Assessment',
        help='Select one or more types of assessment for this lead'
    )

    assessment_language = fields.Many2many(
        'assessment.language',
        'lead_assessment_language_rel',
        'lead_id',
        'assessment_language_id',
        string='Assessment Language',
        help='Select one or more languages for the assessment'
    )
    
    # Participant management
    participant_ids = fields.One2many('participant', 'lead_id', string='Participants', ondelete='cascade')
    participant_count = fields.Integer(string='Participant Count', compute='_compute_participant_count')
    
    @api.depends('participant_ids')
    def _compute_participant_count(self):
        """Count participants for this lead"""
        for record in self:
            record.participant_count = len(record.participant_ids)
    
    def action_view_participants(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Participants - {self.name}',
            'res_model': 'participant',
            'view_mode': 'tree,form',
            'domain': [('lead_id', '=', self.id)],
            'context': {
                'default_lead_id': self.id,
                'editable': True,
                'create': True,
                'edit': True,
            },
            'views': [(False, 'tree'), (False, 'form')],
            'target': 'current',
        }
    
    @api.onchange('type_of_assessment')
    def _onchange_type_of_assessment(self):
        """Update purpose field when assessment type changes"""
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