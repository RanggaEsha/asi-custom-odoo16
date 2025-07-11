# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import odoo.addons.decimal_precision as dp
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from odoo.osv import expression

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    is_approved_1 = fields.Boolean('1st Approved')
    is_approved_2 = fields.Boolean('2nd Approved')
    is_approved_3 = fields.Boolean('3rd Approved')

class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    discount = fields.Float(string='Discount')

    def _convert_to_tax_base_line_dict(self):
        """ Convert the current record to a dictionary in order to use the generic taxes computation method
        defined on account.tax.

        :return: A python dictionary.
        """
        self.ensure_one()
        return self.env['account.tax']._convert_to_tax_base_line_dict(
            self,
            partner=self.order_id.partner_id,
            currency=self.order_id.currency_id,
            product=self.product_id,
            taxes=self.taxes_id,
            price_unit=self.price_unit - self.discount,
            quantity=self.product_qty,
            price_subtotal=self.price_subtotal,
        )

    @api.depends('product_qty', 'price_unit', 'taxes_id')
    def _compute_amount(self):
        for line in self:
            tax_results = self.env['account.tax']._compute_taxes([line._convert_to_tax_base_line_dict()])
            totals = list(tax_results['totals'].values())[0]
            amount_untaxed = totals['amount_untaxed']
            amount_tax = totals['amount_tax']

            line.update({
                'price_subtotal': amount_untaxed,
                'price_tax': amount_tax,
                'price_total': amount_untaxed + amount_tax,
            })

