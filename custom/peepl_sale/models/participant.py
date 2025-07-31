# -*- coding: utf-8 -*-
# Part of Peepl Sale Module - Extends existing participant model

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class Participant(models.Model):
    _inherit = 'participant'
    """Extends existing participant model for participant-based invoicing"""

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
        """Allow only state changes if SO is confirmed; block all other edits."""
        allowed_keys = {'state', 'completion_date', 'notes','sale_line_id', 'project_id', 'lead_id', 'sale_order_id'}
        for participant in self:
            if participant.sale_order_id and participant.sale_order_id.state == 'sale':
                if set(vals.keys()) - allowed_keys:
                    raise ValidationError(_(
                        'Cannot modify participant data when the sale order is confirmed.'
                    ))

        result = super().write(vals)

        # Update sale order line delivered quantity when state changes to confirmed
        if 'state' in vals and vals['state'] == 'confirmed':
            sale_lines = self.mapped('sale_line_id').filtered(
                lambda sol: sol.qty_delivered_method == 'participants'
            )
            if sale_lines:
                sale_lines._compute_qty_delivered()

        # Post message on related sale order when state changes
        if 'state' in vals:
            for participant in self:
                if participant.sale_order_id:
                    old_state = self._get_state_display(vals.get('state'))
                    message = _('Participant %s state changed to %s.') % (participant.full_name, old_state)
                    participant.sale_order_id.message_post(body=message)
        return result


    def unlink(self):
        # Allow deletion only if not linked to confirmed sale order, or if only state is being changed
        allowed_keys = {'state', 'completion_date', 'notes','sale_line_id', 'project_id', 'lead_id', 'sale_order_id'}
        for participant in self:
            if participant.sale_order_id and participant.sale_order_id.state == 'sale':
                # If called from a state change, allow; else block
                # (Unlink is never called for state change, so always block)
                raise ValidationError(_(
                    'Cannot delete participants linked to confirmed sale orders.'
                ))
        return super().unlink()


    def _get_state_display(self, state_key):
        """Get display value for state"""
        state_dict = dict(self._fields['state'].selection)
        return state_dict.get(state_key, state_key)

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

    def action_set_confirmed(self):
        """Override to show enhanced notification for sale orders and refresh view"""
        result = super().action_set_confirmed()
        for participant in self:
            if participant.sale_line_id:
                return [
                    {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Test Completed'),
                            'message': _('Participant %s test completed! Invoice quantity updated.') % participant.full_name,
                            'type': 'success',
                        }
                    },
                    {'type': 'ir.actions.act_window_close'},
                    {'type': 'ir.actions.client', 'tag': 'reload'},
                ]
        return result
    
    def action_set_rescheduled(self):
        """Set participant state to rescheduled, show notification, and refresh view"""
        for participant in self:
            participant.state = 'rescheduled'
            participant.completion_date = False
            return [
                {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Rescheduled'),
                        'message': _('Participant %s has been rescheduled.') % participant.full_name,
                        'type': 'warning',
                    }
                },
                {'type': 'ir.actions.act_window_close'},
                {'type': 'ir.actions.client', 'tag': 'reload'},
            ]

    def action_set_cancelled(self):
        """Set participant state to cancelled, show notification, and refresh view"""
        for participant in self:
            participant.state = 'cancelled'
            participant.completion_date = False
            return [
                {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Cancelled'),
                        'message': _('Participant %s has been cancelled.') % participant.full_name,
                        'type': 'danger',
                    }
                },
                {'type': 'ir.actions.act_window_close'},
                {'type': 'ir.actions.client', 'tag': 'reload'},
            ]

    @api.model
    def _get_fields_to_export(self):
        """Fields that can be exported"""
        return [
            'first_name', 'last_name', 'full_name', 'gender', 'email_address',
            'mobile_phone', 'job_title_requiring_assessment', 'position_level',
            'state', 'completion_date', 'unit_price', 'notes'
        ]