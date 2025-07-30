# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    # Link to sale order
    source_sale_order_id = fields.Many2one(
        'sale.order',
        string='Source Sale Order',
        help='Sale order that this invoice is based on',
        states={'draft': [('readonly', False)]},
        readonly=True
    )
    
    # Participant data from sale order
    has_participant_data = fields.Boolean(
        string='Has Participant Data',
        related='source_sale_order_id.has_participant_data',
        readonly=True
    )
    
    participant_ids = fields.One2many(
        'participant',
        compute='_compute_participant_ids',
        string='Participants'
    )
    
    participant_count = fields.Integer(
        string='Participant Count',
        compute='_compute_participant_count'
    )
    
    # Assessment information
    test_start_date = fields.Date(
        string='Test Start Date',
        related='source_sale_order_id.test_start_date',
        readonly=True
    )
    
    test_finish_date = fields.Date(
        string='Test Finish Date', 
        related='source_sale_order_id.test_finish_date',
        readonly=True
    )
    
    type_of_assessment = fields.Many2many(
        'assessment.type',
        related='source_sale_order_id.type_of_assessment',
        string='Type of Assessment',
        readonly=True
    )
    
    assessment_language = fields.Many2many(
        'assessment.language',
        related='source_sale_order_id.assessment_language',
        string='Assessment Language',
        readonly=True
    )
    
    purpose = fields.Text(
        string='Purpose',
        related='source_sale_order_id.purpose',
        readonly=True
    )

    @api.depends('source_sale_order_id')
    def _compute_participant_ids(self):
        """Get participants from linked sale order"""
        for move in self:
            if move.source_sale_order_id:
                move.participant_ids = move.source_sale_order_id.participant_ids
            else:
                move.participant_ids = False

    @api.depends('participant_ids')
    def _compute_participant_count(self):
        """Count participants"""
        for move in self:
            move.participant_count = len(move.participant_ids)

    @api.onchange('source_sale_order_id')
    def _onchange_source_sale_order_id(self):
        """Auto-populate fields when sale order is selected - NO LINE CREATION"""
        if self.source_sale_order_id:
            sale_order = self.source_sale_order_id
            
            # Update partner information (these are writable fields)
            self.partner_id = sale_order.partner_id.id
            if sale_order.partner_shipping_id:
                self.partner_shipping_id = sale_order.partner_shipping_id.id
            
            # Update invoice information (writable fields only)
            if sale_order.payment_term_id:
                self.invoice_payment_term_id = sale_order.payment_term_id.id
            
            # Update currency and fiscal position (writable fields)
            if sale_order.currency_id:
                self.currency_id = sale_order.currency_id.id
            if sale_order.fiscal_position_id:
                self.fiscal_position_id = sale_order.fiscal_position_id.id
            
            # Update reference and dates (writable fields)
            if sale_order.client_order_ref:
                self.ref = sale_order.client_order_ref
            
            # Set invoice date to today if not set
            if not self.invoice_date:
                self.invoice_date = fields.Date.today()
            
            # Update other sale order related fields (writable fields)
            if sale_order.team_id:
                self.team_id = sale_order.team_id.id
            if sale_order.user_id:
                self.invoice_user_id = sale_order.user_id.id
            
            # DON'T create lines here - let it happen during save
        else:
            # Clear lines if no sale order selected
            self.invoice_line_ids = [(5, 0, 0)]

    def action_view_participants(self):
        """Open participants view for this invoice"""
        self.ensure_one()
        if not self.source_sale_order_id:
            raise UserError(_('No source sale order linked to this invoice.'))
            
        return {
            'type': 'ir.actions.act_window',
            'name': f'Participants - {self.source_sale_order_id.name}',
            'res_model': 'participant',
            'view_mode': 'tree,form',
            'domain': [('sale_order_id', '=', self.source_sale_order_id.id)],
            'context': {
                'default_sale_order_id': self.source_sale_order_id.id,
                'create': False,  # Don't allow creating participants from invoice
                'edit': False,    # Don't allow editing participants from invoice
            },
        }


    def _reverse_moves(self, default_values_list=None, cancel=False):
        """Override to maintain sale order link in credit notes"""
        reverse_moves = super()._reverse_moves(default_values_list, cancel)
        
        # Maintain sale order link in credit notes
        for move, reverse_move in zip(self, reverse_moves):
            if move.source_sale_order_id:
                reverse_move.source_sale_order_id = move.source_sale_order_id
                
        return reverse_moves

    @api.model
    def create(self, vals):
        """Override to handle sale order linking on creation"""        
        move = super().create(vals)
        
        # Link with sale order if specified and create lines properly
        if move.source_sale_order_id:
            if move not in move.source_sale_order_id.invoice_ids:
                move.source_sale_order_id.invoice_ids = [(4, move.id)]
            
            # Create proper lines after creation
            move._sync_invoice_lines_with_sale_order()
            
        return move

    def write(self, vals):
        """Override to handle sale order updates"""
        result = super().write(vals)
        
        # If source_sale_order_id was updated, sync lines
        if 'source_sale_order_id' in vals:
            for move in self:
                if move.source_sale_order_id and move.state == 'draft':
                    # Link with sale order
                    if move not in move.source_sale_order_id.invoice_ids:
                        move.source_sale_order_id.invoice_ids = [(4, move.id)]
                    
                    # Sync lines properly
                    move._sync_invoice_lines_with_sale_order()
                
        return result

    def _sync_invoice_lines_with_sale_order(self):
        """Synchronize invoice lines with sale order lines - our custom logic"""
        if not self.source_sale_order_id or self.state != 'draft':
            return
            
        # Clear all existing lines
        self.invoice_line_ids.unlink()
        
        # Create new lines based on sale order
        sale_order = self.source_sale_order_id
        lines_data = []
        
        for line in sale_order.order_line:
            if line.display_type:
                continue  # skip section/note lines
                
            # Calculate quantity to invoice (incremental - not total delivered)
            if line.qty_delivered_method == 'participants':
                # For participants: delivered - already invoiced
                total_delivered = line.completed_participants_count
                already_invoiced = self._get_already_invoiced_qty(line)
                qty_to_invoice = total_delivered - already_invoiced
            else:
                # For regular delivery: delivered - already invoiced  
                total_delivered = line.qty_delivered if line.qty_delivered > 0 else line.product_uom_qty
                already_invoiced = self._get_already_invoiced_qty(line)
                qty_to_invoice = total_delivered - already_invoiced
                
            if qty_to_invoice <= 0:
                continue
                
            # Create line data
            line_vals = {
                'move_id': self.id,
                'product_id': line.product_id.id,
                'name': line.name,
                'quantity': qty_to_invoice,
                'product_uom_id': line.product_uom.id,
                'price_unit': line.price_unit,
                'discount': line.discount,
                'tax_ids': [(6, 0, line.tax_id.ids)],
                'sequence': line.sequence,
                'sale_line_ids': [(6, 0, [line.id])],
            }
            
            # Add analytic distribution if present
            if line.analytic_distribution:
                line_vals['analytic_distribution'] = line.analytic_distribution
                
            # Add participant note if using participant delivery method
            if line.qty_delivered_method == 'participants':
                participant_note = _('\nParticipants completed: %d/%d (invoicing: %d)') % (
                    line.completed_participants_count, 
                    line.participants_count,
                    qty_to_invoice
                )
                line_vals['name'] += participant_note
            
            lines_data.append(line_vals)
        
        # Create all lines at once
        if lines_data:
            self.env['account.move.line'].create(lines_data)

    def _get_already_invoiced_qty(self, sale_line):
        """Calculate how much quantity has already been invoiced for this sale order line"""
        # Find all confirmed/posted invoices linked to this sale order (excluding current draft)
        invoiced_lines = self.env['account.move.line'].search([
            ('sale_line_ids', 'in', sale_line.ids),
            ('move_id.state', 'in', ['posted']),  # Only confirmed invoices
            ('move_id.move_type', '=', 'out_invoice'),  # Only customer invoices
            ('move_id', '!=', self.id),  # Exclude current invoice
        ])
        
        # Sum up quantities already invoiced
        total_invoiced = sum(invoiced_lines.mapped('quantity'))
        
        # Also check draft invoices that are not the current one
        draft_invoiced_lines = self.env['account.move.line'].search([
            ('sale_line_ids', 'in', sale_line.ids),
            ('move_id.state', '=', 'draft'),
            ('move_id.move_type', '=', 'out_invoice'),
            ('move_id', '!=', self.id),  # Exclude current invoice
            ('move_id.source_sale_order_id', '=', self.source_sale_order_id.id),  # Same sale order
        ])
        
        total_invoiced += sum(draft_invoiced_lines.mapped('quantity'))
        
        return total_invoiced


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    # Link to participant data
    related_participant_count = fields.Integer(
        string='Participants',
        compute='_compute_related_participant_count',
        help='Number of participants for this invoice line'
    )

    @api.depends('sale_line_ids', 'sale_line_ids.participants_count')
    def _compute_related_participant_count(self):
        """Compute participant count for invoice lines"""
        for line in self:
            if line.sale_line_ids:
                line.related_participant_count = sum(
                    sale_line.participants_count for sale_line in line.sale_line_ids
                )
            else:
                line.related_participant_count = 0

    def action_view_line_participants(self):
        """View participants for this invoice line"""
        self.ensure_one()
        if not self.sale_line_ids:
            raise UserError(_('No sale order lines linked to this invoice line.'))
            
        participants = self.env['participant']
        for sale_line in self.sale_line_ids:
            participants |= sale_line.related_participants_ids
            
        return {
            'type': 'ir.actions.act_window',
            'name': f'Participants - {self.product_id.name}',
            'res_model': 'participant',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', participants.ids)],
            'context': {'create': False, 'edit': False},
        }


# Override Sale Order to prevent it from creating its own invoice lines
class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _create_invoices(self, grouped=False, final=False, date=None):
        """Override to use our custom line creation for invoices with source_sale_order_id"""
        invoices = super()._create_invoices(grouped=grouped, final=final, date=date)
        
        # For each created invoice, if it has source_sale_order_id, use our custom logic
        for invoice in invoices:
            if invoice.source_sale_order_id:
                invoice._sync_invoice_lines_with_sale_order()
                
        return invoices

    def _prepare_invoice(self):
        """Override to include source_sale_order_id in invoice preparation"""
        invoice_vals = super()._prepare_invoice()
        invoice_vals['source_sale_order_id'] = self.id
        return invoice_vals