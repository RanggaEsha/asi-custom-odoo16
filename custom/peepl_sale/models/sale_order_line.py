# -*- coding: utf-8 -*-
# Part of Peepl Sale Module - Extends sale order line for participant invoicing

from odoo import api, fields, models, _


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    qty_delivered_method = fields.Selection(
        selection_add=[('participants', 'Participants')],
        ondelete={'participants': 'set null'}
    )
    
    # Link to existing participants via sale_order_id (existing relationship)
    related_participants_ids = fields.One2many(
        'participant', 
        'sale_line_id', 
        string='Linked Participants',
        help='Participants specifically linked to this sale order line'
    )
    
    # Also get participants from sale order for backward compatibility
    all_order_participants_ids = fields.One2many(
        related='order_id.participant_ids',
        string='All Order Participants'
    )
    
    completed_participants_ids = fields.One2many(
        'participant', 
        'sale_line_id', 
        string='Completed Participants', 
        domain=[('state', '=', 'confirmed')]
    )
    
    participants_count = fields.Integer(
        string='Total Participants',
        compute='_compute_participants_count'
    )
    
    completed_participants_count = fields.Integer(
        string='Completed Participants',
        compute='_compute_participants_count'
    )
    
    # For linking participants to specific SOL
    auto_link_participants = fields.Boolean(
        string='Auto-link Order Participants',
        default=True,
        help='Automatically link sale order participants to this line when using participant delivery method'
    )

    @api.depends('related_participants_ids', 'completed_participants_ids', 'all_order_participants_ids', 'auto_link_participants')
    def _compute_participants_count(self):
        for line in self:
            if line.qty_delivered_method == 'participants':
                if line.auto_link_participants and not line.related_participants_ids:
                    # Use all order participants if no specific linking
                    all_participants = line.all_order_participants_ids
                    completed_participants = all_participants.filtered(lambda p: p.state == 'confirmed')
                else:
                    # Use specifically linked participants
                    all_participants = line.related_participants_ids
                    completed_participants = line.completed_participants_ids
                line.participants_count = len(all_participants)
                line.completed_participants_count = len(completed_participants)
            else:
                line.participants_count = 0
                line.completed_participants_count = 0

    @api.depends('product_id')
    def _compute_qty_delivered_method(self):
        """Override to set participants method for participant products"""
        participant_lines = self.filtered(lambda sol:
            not sol.is_expense
            and sol.product_id.type == 'service'
            and sol.product_id.service_type == 'participants'
        )
        participant_lines.qty_delivered_method = 'participants'
        super(SaleOrderLine, self - participant_lines)._compute_qty_delivered_method()

    @api.depends('qty_delivered_method', 'product_uom_qty', 'completed_participants_ids', 'all_order_participants_ids', 'auto_link_participants')
    def _compute_qty_delivered(self):
        """Override to compute delivered quantity based on participants"""
        lines_by_participants = self.filtered(lambda sol: sol.qty_delivered_method == 'participants')
        super(SaleOrderLine, self - lines_by_participants)._compute_qty_delivered()

        if not lines_by_participants:
            return

        for line in lines_by_participants:
            if line.auto_link_participants and not line.related_participants_ids:
                # Use all order participants
                completed_count = len(line.all_order_participants_ids.filtered(lambda p: p.state == 'confirmed'))
            else:
                # Use specifically linked participants
                completed_count = len(line.completed_participants_ids)
            # For participants, we deliver the exact number of completed participants
            line.qty_delivered = completed_count

    def _link_order_participants_to_line(self):
        """Link existing order participants to this sale order line"""
        self.ensure_one()
        if (self.qty_delivered_method == 'participants' and 
            self.auto_link_participants and 
            not self.related_participants_ids and
            self.all_order_participants_ids):
            
            # Link all order participants to this line
            self.all_order_participants_ids.write({'sale_line_id': self.id})

    def _generate_participants_from_quantity(self):
        """Generate participants based on ordered quantity if none exist"""
        self.ensure_one()
        if (self.product_id.service_policy == 'delivered_participants' and
            self.qty_delivered_method == 'participants' and
            not self.related_participants_ids and
            not self.all_order_participants_ids):
            
            # Create participants based on ordered quantity
            participants_to_create = []
            for i in range(int(self.product_uom_qty)):
                participants_to_create.append({
                    'first_name': f'Participant',
                    'last_name': f'{i + 1}',
                    'sale_order_id': self.order_id.id,
                    'sale_line_id': self.id,
                    'job_title_requiring_assessment': self.product_id.name,
                    'sequence': (i + 1) * 10,
                })
            
            if participants_to_create:
                self.env['participant'].create(participants_to_create)

    def _timesheet_service_generation(self):
        """Override to handle participant generation after project/task creation"""
        result = super()._timesheet_service_generation()
        
        # Handle participant linking/generation for participant-based lines
        for line in self.filtered(lambda sol: sol.product_id.service_policy == 'delivered_participants'):
            if line.auto_link_participants:
                line._link_order_participants_to_line()
            else:
                line._generate_participants_from_quantity()
        
        return result

    def action_view_participants(self):
        """Action to view participants for this sale order line"""
        self.ensure_one()
        
        if self.auto_link_participants and not self.related_participants_ids:
            participants = self.all_order_participants_ids
            domain = [('sale_order_id', '=', self.order_id.id)]
        else:
            participants = self.related_participants_ids
            domain = [('sale_line_id', '=', self.id)]
        
        action = {
            'name': _('Participants - %s') % self.product_id.name,
            'type': 'ir.actions.act_window',
            'res_model': 'participant',
            'view_mode': 'tree,form',
            'domain': domain,
            'context': {
                'default_sale_order_id': self.order_id.id,
                'default_sale_line_id': self.id,
                'default_job_title_requiring_assessment': self.product_id.name,
            },
            'help': _("""
                <p class="o_view_nocontent_smiling_face">
                    No participants found. Let's create some!
                </p><p>
                    Add participants who will take the test. 
                    Mark them as completed when they finish to trigger invoicing.
                </p>
            """),
        }
        
        if len(participants) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': participants.id,
            })
        
        return action

    def action_link_all_order_participants(self):
        """Manually link all order participants to this line"""
        self.ensure_one()
        if self.all_order_participants_ids:
            self.all_order_participants_ids.write({'sale_line_id': self.id})
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('%d participants linked to this line!') % len(self.all_order_participants_ids),
                    'type': 'success',
                }
            }

    def _prepare_invoice_line(self, **optional_values):
        """Override to ensure participant-based lines use correct analytics"""
        values = super()._prepare_invoice_line(**optional_values)
        
        # For participant-based lines, ensure proper analytic account
        if self.qty_delivered_method == 'participants':
            if not values.get('analytic_distribution'):
                if hasattr(self, 'project_id') and self.project_id and self.project_id.analytic_account_id:
                    values['analytic_distribution'] = {self.project_id.analytic_account_id.id: 100}
        
        return values