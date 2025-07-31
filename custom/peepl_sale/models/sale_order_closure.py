# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    state = fields.Selection(
        selection_add=[('closed', 'Closed')], 
        ondelete={'closed': 'set default'}
    )
    
    closed_date = fields.Datetime(
        string='Closed Date', 
        readonly=True,
        help='Date and time when the order was closed'
    )
    
    closed_by = fields.Many2one(
        'res.users',
        string='Closed By',
        readonly=True,
        help='User who closed this order'
    )
    
    close_reason = fields.Text(
        string='Close Reason',
        readonly=True,
        help='Reason for closing this order'
    )
    
    is_closed = fields.Boolean(
        string='Is Closed',
        compute='_compute_is_closed',
        store=True,
        help='Technical field to identify closed orders'
    )

    @api.depends('state')
    def _compute_is_closed(self):
        """Compute if order is closed"""
        for order in self:
            order.is_closed = (order.state == 'closed')

    def action_close_order(self):
        """Quick close without wizard"""
        if self.state != 'sale':
            raise UserError(_('Only confirmed sale orders can be closed.'))
        self.write({
            'state': 'closed',
            'closed_date': fields.Datetime.now(),
            'closed_by': self.env.user.id,
            'close_reason': _('Order closed by %s') % self.env.user.name,
        })
        # Post message in chatter
        message = _('Sale order has been closed by %s') % self.env.user.name
        self.message_post(body=message, subject=_('Order Closed'))
        # Show notification, close wizard, and refresh parent view
        return [
            {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Order Closed'),
                    'message': _('Sale order %s has been closed successfully.') % self.name,
                    'type': 'success',
                }
            },
            {'type': 'ir.actions.act_window_close'},
            {'type': 'ir.actions.client', 'tag': 'reload'},
        ]

    def action_reopen_order(self):
        """Reopen a closed order back to sale state"""
        if self.state != 'closed':
            raise UserError(_('Only closed orders can be reopened.'))
        self.write({
            'state': 'sale',
            'closed_date': False,
            'closed_by': False,
            'close_reason': False,
        })
        # Post message in chatter
        message = _('Sale order has been reopened by %s') % self.env.user.name
        self.message_post(body=message, subject=_('Order Reopened'))
        # Show notification, close wizard, and refresh parent view
        return [
            {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Order Reopened'),
                    'message': _('Sale order %s has been reopened.') % self.name,
                    'type': 'success',
                }
            },
            {'type': 'ir.actions.act_window_close'},
            {'type': 'ir.actions.client', 'tag': 'reload'},
        ]

    def action_close_with_reason(self):
        """Open wizard to close order with reason"""
        return {
            'name': _('Close Order'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order.close.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_order_id': self.id},
        }

    @api.depends('state')
    def _compute_type_name(self):
        """Override to show proper name for closed orders"""
        super()._compute_type_name()
        for order in self:
            if order.state == 'closed':
                order.type_name = _('Closed Order')

    def _track_subtype(self, init_values):
        """Add tracking for closed state"""
        self.ensure_one()
        if 'state' in init_values and self.state == 'closed':
            return self.env.ref('sale.mt_order_sent')  # You can create a specific subtype
        return super()._track_subtype(init_values)

    @api.model
    def _get_closed_orders_count(self):
        """Get count of closed orders for dashboard/reports"""
        return self.search_count([('state', '=', 'closed')])

    def write(self, vals):
        """Override to handle closure state changes"""
        result = super().write(vals)
        
        # If closing order, check for any pending tasks
        if vals.get('state') == 'closed':
            for order in self:
                # You can add additional checks here
                # e.g., check if all invoices are paid, deliveries completed, etc.
                pass
                
        return result

    def unlink(self):
        """Prevent deletion of closed orders"""
        closed_orders = self.filtered(lambda o: o.state == 'closed')
        if closed_orders:
            raise UserError(_(
                'You cannot delete closed orders. '
                'Please reopen them first if deletion is necessary.\n'
                'Closed orders: %s'
            ) % ', '.join(closed_orders.mapped('name')))
        return super().unlink()
    
    # send BAST to customer
    def action_send_bast(self):
        """Send BAST to customer"""
        self.ensure_one()
        if self.state != 'closed':
            raise UserError(_('Only closed orders can send BAST.'))
        # Logic to send BAST (e.g., email, notification)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('BAST Sent'),
                'message': _('BAST for sale order %s has been sent.') % self.name,
                'type': 'success',
            }
        }