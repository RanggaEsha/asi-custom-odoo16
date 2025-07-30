# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SaleOrderCloseWizard(models.TransientModel):
    _name = 'sale.order.close.wizard'
    _description = 'Close Sale Order Wizard'

    order_id = fields.Many2one(
        'sale.order', 
        string='Sale Order', 
        required=True,
        readonly=True
    )
    
    order_name = fields.Char(
        related='order_id.name',
        string='Order Number',
        readonly=True
    )
    
    partner_id = fields.Many2one(
        related='order_id.partner_id',
        string='Customer',
        readonly=True
    )
    
    amount_total = fields.Monetary(
        related='order_id.amount_total',
        string='Total Amount',
        readonly=True
    )
    
    currency_id = fields.Many2one(
        related='order_id.currency_id',
        readonly=True
    )
    
    close_reason = fields.Text(
        string='Reason for Closing', 
        required=True,
        placeholder='Please provide a detailed reason for closing this order...'
    )
    
    # notify_customer = fields.Boolean(
    #     string='Notify Customer',
    #     default=False,
    #     help='Send an email notification to the customer about order closure'
    # )

    def action_close_order(self):
        """Close the order with reason"""
        self.ensure_one()
        
        if self.order_id.state != 'sale':
            raise UserError(_('Only confirmed sale orders can be closed.'))
        
        # Update order with closure information
        self.order_id.write({
            'state': 'closed',
            'closed_date': fields.Datetime.now(),
            'closed_by': self.env.user.id,
            'close_reason': self.close_reason,
        })
        
        # Post message in chatter
        message = _(
            'Sale order has been closed by %s\n\n'
            'Reason: %s'
        ) % (self.env.user.name, self.close_reason)
        
        self.order_id.message_post(
            body=message,
            subject=_('Order Closed'),
            message_type='comment'
        )
        
        # # Send notification to customer if requested
        # if self.notify_customer:
        #     self._send_customer_notification()
        
        return [
            {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Order Closed'),
                    'message': _('Sale order %s has been closed successfully.') % self.order_id.name,
                    'type': 'success',
                }
            },
            {'type': 'ir.actions.act_window_close'},
            {'type': 'ir.actions.client', 'tag': 'reload'},
        ]

    # def _send_customer_notification(self):
    #     """Send email notification to customer about order closure"""
    #     template = self.env.ref('your_module.email_template_order_closure', False)
    #     if template:
    #         template.send_mail(self.order_id.id, force_send=True)
    #     else:
    #         # Fallback: create a simple message
    #         self.order_id.with_context(
    #             mail_post_autofollow=True
    #         ).message_post(
    #             body=_(
    #                 'Dear %s,\n\n'
    #                 'Your order %s has been closed.\n\n'
    #                 'Reason: %s\n\n'
    #                 'If you have any questions, please contact us.\n\n'
    #                 'Best regards,\n%s'
    #             ) % (
    #                 self.partner_id.name,
    #                 self.order_name,
    #                 self.close_reason,
    #                 self.env.company.name
    #             ),
    #             subject=_('Order %s - Closed') % self.order_name,
    #             partner_ids=[self.partner_id.id],
    #             message_type='email'
    #         )

    @api.onchange('order_id')
    def _onchange_order_id(self):
        """Auto-fill some default reasons based on order state"""
        if self.order_id:
            # You can add logic here to suggest default reasons
            # based on order characteristics
            pass