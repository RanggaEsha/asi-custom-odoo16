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

    @api.depends('sale_line_id', 'sale_line_id.project_id', 'sale_order_id', 'sale_order_id.project_ids')
    def _compute_project_id(self):
        for participant in self:
            project = False
            
            # First try to get project from sale order line
            if participant.sale_line_id:
                if hasattr(participant.sale_line_id, 'project_id') and participant.sale_line_id.project_id:
                    project = participant.sale_line_id.project_id
                elif hasattr(participant.sale_line_id, 'task_id') and participant.sale_line_id.task_id and participant.sale_line_id.task_id.project_id:
                    project = participant.sale_line_id.task_id.project_id
            
            # Fallback to sale order project
            if not project and participant.sale_order_id:
                if hasattr(participant.sale_order_id, 'project_ids') and participant.sale_order_id.project_ids:
                    # Get the most recent project
                    project = participant.sale_order_id.project_ids.sorted('create_date', reverse=True)[0]
                elif hasattr(participant.sale_order_id, 'project_id') and participant.sale_order_id.project_id:
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

    # Replace your existing write method in the Participant model with this enhanced version

    def write(self, vals):
        """Allow only state changes if SO is confirmed; block all other edits."""
        allowed_keys = {'state', 'completion_date', 'notes','sale_line_id', 'project_id', 'lead_id', 'sale_order_id'}
        
        # Store sale lines that will need quantity updates
        affected_sale_lines = set()
        
        for participant in self:
            if participant.sale_order_id and participant.sale_order_id.state == 'sale':
                if set(vals.keys()) - allowed_keys:
                    raise ValidationError(_(
                        'Cannot modify participant data when the sale order is confirmed.'
                    ))
            
            # Collect sale lines that will be affected by state changes
            if 'state' in vals and participant.sale_line_id and participant.sale_line_id.qty_delivered_method == 'participants':
                affected_sale_lines.add(participant.sale_line_id.id)

        result = super().write(vals)

        # **FIX: Recompute project_id when sale_line_id changes**
        if 'sale_line_id' in vals:
            self._compute_project_id()

        # Post message on related sale order when state changes
        if 'state' in vals:
            for participant in self:
                if participant.sale_order_id:
                    old_state = self._get_state_display(vals.get('state'))
                    message = _('Participant %s state changed to %s.') % (participant.full_name, old_state)
                    if participant.sale_line_id.qty_delivered_method == 'participants':
                        # If the sale line uses participants delivery method, we need to update qty_delivered
                        participant.sale_line_id._compute_qty_delivered()
                        message += _(' Quantity delivered updated.')
                    # update sale order line qyty_delivered
                   
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
        
    def action_set_not_yet_confirmed(self):
        """Set participant state to not yet confirmed, show notification, and refresh view"""
        for participant in self:
            participant.state = 'not_yet_confirmed'
            participant.completion_date = False
            return [
                {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Not Yet Confirmed'),
                        'message': _('Participant %s is now marked as not yet confirmed.') % participant.full_name,
                        'type': 'info',
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
    

    # If the above methods still don't work, replace with this ultra-robust approach

    @api.model
    def rpc_set_confirmed(self, participant_ids):
        """Ultra-robust method to set participants as confirmed with direct qty_delivered update"""
        try:
            participants = self.browse(participant_ids)
            affected_sale_lines = {}  # Use dict to store line info
            
            import logging
            _logger = logging.getLogger(__name__)
            _logger.info(f"=== RPC CONFIRMED START: {len(participants)} participants ===")
            
            for participant in participants:
                # Update participant state
                old_state = participant.state
                participant.write({
                    'state': 'confirmed',
                    'completion_date': fields.Date.today()
                })
                _logger.info(f"Updated participant {participant.id} from {old_state} to confirmed")
                
                # Collect sale lines that need qty_delivered update
                if participant.sale_line_id and participant.sale_line_id.qty_delivered_method == 'participants':
                    line = participant.sale_line_id
                    if line.id not in affected_sale_lines:
                        affected_sale_lines[line.id] = line
            
            # Update qty_delivered for each affected sale line
            for line_id, line in affected_sale_lines.items():
                _logger.info(f"Processing sale line {line_id}")
                
                # Get all participants for this line
                if line.auto_link_participants and not line.related_participants_ids:
                    line_participants = line.all_order_participants_ids
                    _logger.info(f"Using all order participants: {len(line_participants)}")
                else:
                    line_participants = line.related_participants_ids
                    _logger.info(f"Using linked participants: {len(line_participants)}")
                
                # Count completed participants
                completed_participants = line_participants.filtered(lambda p: p.state == 'confirmed')
                completed_count = len(completed_participants)
                old_qty = line.qty_delivered
                
                _logger.info(f"Completed participants: {completed_count}, Old qty_delivered: {old_qty}")
                
                # Method 1: Try ORM update first
                try:
                    line.invalidate_cache(['qty_delivered'])
                    line._compute_qty_delivered()
                    if line.qty_delivered != completed_count:
                        # Method 2: Direct assignment
                        line.qty_delivered = completed_count
                    _logger.info(f"Updated qty_delivered to {line.qty_delivered}")
                except Exception as orm_error:
                    _logger.error(f"ORM update failed: {orm_error}")
                    # Method 3: Direct SQL as last resort
                    self.env.cr.execute(
                        "UPDATE sale_order_line SET qty_delivered = %s WHERE id = %s",
                        (completed_count, line.id)
                    )
                    _logger.info(f"Used SQL update to set qty_delivered = {completed_count}")
            
            _logger.info(f"=== RPC CONFIRMED END ===")
            return {'success': True, 'count': len(participants), 'affected_lines': len(affected_sale_lines)}
            
        except Exception as e:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.error(f"Error in rpc_set_confirmed: {e}")
            return {'success': False, 'error': str(e)}

    # Add similar methods for other states...
    @api.model  
    def rpc_set_rescheduled(self, participant_ids):
        """Ultra-robust method to set participants as rescheduled"""
        try:
            participants = self.browse(participant_ids)
            affected_sale_lines = {}
            
            for participant in participants:
                participant.write({
                    'state': 'rescheduled',
                    'completion_date': False
                })
                
                if participant.sale_line_id and participant.sale_line_id.qty_delivered_method == 'participants':
                    line = participant.sale_line_id
                    if line.id not in affected_sale_lines:
                        affected_sale_lines[line.id] = line
            
            for line_id, line in affected_sale_lines.items():
                if line.auto_link_participants and not line.related_participants_ids:
                    line_participants = line.all_order_participants_ids
                else:
                    line_participants = line.related_participants_ids
                
                completed_count = len(line_participants.filtered(lambda p: p.state == 'confirmed'))
                
                try:
                    line.invalidate_cache(['qty_delivered'])
                    line._compute_qty_delivered()
                    if line.qty_delivered != completed_count:
                        line.qty_delivered = completed_count
                except:
                    self.env.cr.execute(
                        "UPDATE sale_order_line SET qty_delivered = %s WHERE id = %s",
                        (completed_count, line.id)
                    )
            
            return {'success': True, 'count': len(participants)}
        except Exception as e:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.error(f"Error in rpc_set_rescheduled: {e}")
            return {'success': False, 'error': str(e)}
    
    def rpc_set_cancelled(self, participant_ids):
        """Ultra-robust method to set participants as cancelled"""
        try:
            participants = self.browse(participant_ids)
            affected_sale_lines = {}
            
            for participant in participants:
                participant.write({
                    'state': 'cancelled',
                    'completion_date': False
                })
                
                if participant.sale_line_id and participant.sale_line_id.qty_delivered_method == 'participants':
                    line = participant.sale_line_id
                    if line.id not in affected_sale_lines:
                        affected_sale_lines[line.id] = line
            
            for line_id, line in affected_sale_lines.items():
                if line.auto_link_participants and not line.related_participants_ids:
                    line_participants = line.all_order_participants_ids
                else:
                    line_participants = line.related_participants_ids
                
                completed_count = len(line_participants.filtered(lambda p: p.state == 'confirmed'))
                
                try:
                    line.invalidate_cache(['qty_delivered'])
                    line._compute_qty_delivered()
                    if line.qty_delivered != completed_count:
                        line.qty_delivered = completed_count
                except:
                    self.env.cr.execute(
                        "UPDATE sale_order_line SET qty_delivered = %s WHERE id = %s",
                        (completed_count, line.id)
                    )
            
            return {'success': True, 'count': len(participants)}
        except Exception as e:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.error(f"Error in rpc_set_cancelled: {e}")
            return {'success': False, 'error': str(e)}
        