# -*- coding: utf-8 -*-
# Part of Peepl Sale Module - Extends existing participant model

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class Participant(models.Model):
    _inherit = 'participant'

    # Add invoicing-related fields to existing participant model
    sale_line_id = fields.Many2one(
        'sale.order.line', 
        string='Sales Order Item', 
        help='Sales Order Item that will be updated when the participant completes the test.',
        domain="[('order_partner_id', '=?', order_partner_id), ('qty_delivered_method', '=', 'participants')]",
        ondelete='set null'
    )
    
    # Project linking (if needed for project-based services)
    project_id = fields.Many2one(
        'project.project', 
        string='Project',
        compute='_compute_project_id',
        store=True,
        help='Project associated with the sale order line'
    )
    
    # Completion tracking for invoicing
    test_completed = fields.Boolean(
        string='Test Completed', 
        default=False,
        help='Mark as true when the participant has completed their test'
    )
    completion_date = fields.Datetime(
        string='Completion Date', 
        readonly=True,
        help='Date and time when the test was completed'
    )
    
    # Related fields for domain filtering and pricing
    order_partner_id = fields.Many2one(
        related='sale_order_id.partner_id', 
        string='Sale Order Partner',
        store=True
    )
    currency_id = fields.Many2one(
        related='sale_line_id.currency_id',
        string='Currency'
    )
    unit_price = fields.Monetary(
        string='Unit Price per Participant', 
        compute='_compute_unit_price',
        currency_field='currency_id',
        help='Price allocated to this participant based on sale order line'
    )
    
    # Enhanced name display
    full_name = fields.Char(
        string='Full Name',
        compute='_compute_full_name',
        store=True
    )


    @api.depends('first_name', 'last_name')
    def _compute_full_name(self):
        for participant in self:
            participant.full_name = f"{participant.first_name or ''} {participant.last_name or ''}".strip()

    @api.depends('sale_line_id', 'sale_order_id')
    def _compute_project_id(self):
        for participant in self:
            project = False
            if participant.sale_line_id and hasattr(participant.sale_line_id, 'project_id'):
                project = participant.sale_line_id.project_id
            elif participant.sale_order_id and hasattr(participant.sale_order_id, 'project_id'):
                project = participant.sale_order_id.project_id
            participant.project_id = project

    @api.depends('sale_line_id', 'sale_line_id.price_unit')
    def _compute_unit_price(self):
        for participant in self:
            if participant.sale_line_id:
                # Calculate price per participant
                total_participants = self.search_count([
                    ('sale_line_id', '=', participant.sale_line_id.id)
                ])
                if total_participants > 0:
                    participant.unit_price = participant.sale_line_id.price_unit / total_participants
                else:
                    participant.unit_price = 0.0
            else:
                participant.unit_price = 0.0

    def write(self, vals):
        # Track completion date
        if 'test_completed' in vals:
            if vals['test_completed']:
                vals['completion_date'] = fields.Datetime.now()
            else:
                vals['completion_date'] = False
        
        result = super().write(vals)
        
        # Update sale order line delivered quantity when completion status changes
        if 'test_completed' in vals:
            sale_lines = self.mapped('sale_line_id').filtered(
                lambda sol: sol.qty_delivered_method == 'participants'
            )
            if sale_lines:
                sale_lines._compute_qty_delivered()
        
        return result

    def action_mark_completed(self):
        """Action to mark participant test as completed"""
        self.ensure_one()
        if self.test_completed:
            raise ValidationError(
                _('Participant %s has already completed the test.') % self.full_name
            )
        
        self.write({
            'test_completed': True,
            'completion_date': fields.Datetime.now()
        })
        
        # Post message on related sale order
        if self.sale_order_id:
            message = _(
                'Test completed by participant: %s (%s - %s)'
            ) % (
                self.full_name,
                self.job_title_requiring_assessment or 'N/A',
                self.position_level or 'N/A'
            )
            self.sale_order_id.message_post(body=message)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Test completed for %s!') % self.full_name,
                'type': 'success',
            }
        }

    def action_mark_incomplete(self):
        """Action to mark participant test as incomplete"""
        self.ensure_one()
        if not self.test_completed:
            raise ValidationError(
                _('Participant %s has not completed the test yet.') % self.full_name
            )
        
        self.write({
            'test_completed': False,
            'completion_date': False
        })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Test marked as incomplete for %s!') % self.full_name,
                'type': 'info',
            }
        }

    @api.constrains('sale_line_id')
    def _check_sale_line_participants_method(self):
        """Ensure sale line uses participants delivery method when linked"""
        for participant in self:
            if (participant.sale_line_id and 
                participant.sale_line_id.qty_delivered_method != 'participants'):
                raise ValidationError(_(
                    'The selected Sales Order Item must use "Participants" as delivery method '
                    'to enable invoicing based on participant completion.'
                ))

    def name_get(self):
        """Enhanced display name with completion status"""
        result = []
        for participant in self:
            # Use existing name_get logic but add completion indicator
            name = f"{participant.first_name} {participant.last_name}".strip()
            if participant.job_title_requiring_assessment:
                name += f" - {participant.job_title_requiring_assessment}"
            if participant.position_level:
                name += f" ({participant.position_level})"
            
            # Add completion indicator
            if participant.test_completed:
                name += " ✓"
            
            result.append((participant.id, name))
        return result

    @api.model
    def _get_fields_to_export(self):
        """Fields that can be exported"""
        return [
            'first_name', 'last_name', 'full_name', 'gender', 'email_address', 
            'mobile_phone', 'job_title_requiring_assessment', 'position_level',
            'test_completed', 'completion_date', 'unit_price', 'notes'
        ]