# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    """ Sale Order """
    _inherit = "sale.order"

    # Participant management
    has_participant_data = fields.Boolean(string='Has Participant Data', default=False)
    test_start_date = fields.Date(string='Test Start Date')
    test_finish_date = fields.Date(string='Test Finish Date')
    purpose = fields.Text(string='Purpose')
    
    # Assessment configuration
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
    
    @api.depends('participant_ids')
    def _compute_participant_count(self):
        """Count participants for this lead"""
        for record in self:
            record.participant_count = len(record.participant_ids)
    
    def action_view_participants(self):
        """Open participants view for this lead"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Participants - {self.name}',
            'res_model': 'participant',
            'view_mode': 'tree',
            'domain': [('sale_order_id', '=', self.id)],
            'context': {'default_sale_order_id': self.id},
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

    @api.model
    def unlink(self):
        for record in self:
            # remove sale_order_id from participants and set to default state
            record.participant_ids.write({'sale_order_id': False})
        return super().unlink()
    