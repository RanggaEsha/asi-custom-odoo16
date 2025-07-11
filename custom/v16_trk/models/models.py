# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import odoo.addons.decimal_precision as dp
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from odoo.osv import expression
from odoo.tools import float_is_zero
import time

class SaleAdvancePaymentInv(models.TransientModel):
    _inherit = 'sale.advance.payment.inv'
    _description = "Sales Advance Payment Invoice"

    def _prepare_down_payment_section_values(self, order):
        context = {'lang': order.partner_id.lang}

        so_values = {
            'name': _('Down Payments'),
            'product_uom_qty': 0.0,
            'order_id': order.id,
            'display_type': 'line_section',
            'is_downpayment': True,
            # 'sequence': order.order_line and order.order_line[-1].sequence + 1 or 10,
        }

        del context
        return so_values

    def _prepare_so_line_values(self, order):
        self.ensure_one()
        analytic_distribution = {}
        amount_total = sum(order.order_line.mapped("price_total"))
        if not float_is_zero(amount_total, precision_rounding=self.currency_id.rounding):
            for line in order.order_line:
                distrib_dict = line.analytic_distribution or {}
                for account, distribution in distrib_dict.items():
                    analytic_distribution[account] = distribution * line.price_total + analytic_distribution.get(account, 0)
            for account, distribution_amount in analytic_distribution.items():
                analytic_distribution[account] = distribution_amount/amount_total
        context = {'lang': order.partner_id.lang}
        so_values = {
            'name': _('Down Payment: %s (Draft)', time.strftime('%m %Y')),
            'price_unit': self._get_down_payment_amount(order),
            'product_uom_qty': 0.0,
            'order_id': order.id,
            'discount': 0.0,
            'product_id': self.product_id.id,
            'analytic_distribution': analytic_distribution,
            'is_downpayment': True,
            # 'sequence': order.order_line and order.order_line[-1].sequence + 1 or 10,
        }
        del context
        return so_values

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    valve_type_id = fields.Many2one('trk.valve.type', string='Valve Type')
    end_user_id = fields.Many2one('res.partner', string='End User', domain="[('is_end_user', '=', True)]")

class TrkValveTypeComponent(models.Model):
    _name = 'trk.valve.type.component'

    name = fields.Char('Component Name')
    code = fields.Char('Code')
    
class TrkValveType(models.Model):
    _name = 'trk.valve.type'

    name = fields.Char('Valve Type')
    code = fields.Char('Code')
    component_ids = fields.Many2many('trk.valve.type.component', 'valve_type_component_rel', 'valve_type_id', 
        'component_id', string='Valve Type Component')

class TrkBranch(models.Model):
    _name = 'trk.branch'

    name = fields.Char('Branch Name')
    code = fields.Char('Code')

class TrkProject(models.Model):
    _name = 'trk.project'

    name = fields.Char('Project Name')
    code = fields.Char('Code')

class TrkShip(models.Model):
    _name = 'trk.ship'

    name = fields.Char('Ship To')
    code = fields.Char('Code')

class TrkDeliveryTerm(models.Model):
    _name = 'trk.delivery.term'

    name = fields.Char('Term of Delivery')
    code = fields.Char('Code')

class TrkBlanketOrderSale(models.Model):
    _name = 'trk.blanket.order.sale'

    reference = fields.Many2one('trk.blanket.order', string='Blanket Order')
    order_id = fields.Many2one('sale.order', string='Sales Order')
    date = fields.Date('Date')

class TrkBlanketOrderLine(models.Model):
    _name = 'trk.blanket.order.line'

    reference = fields.Many2one('trk.blanket.order', string='Blanket Order')
    quotation_id = fields.Many2one('trk.quotation', string='Quotation No.')
    product_id = fields.Many2one('product.product', string='Product')
    product_uom_qty = fields.Float('Qty')
    price_unit = fields.Float('Price Unit')
    valve_type_id = fields.Many2one('trk.valve.type', string='Valve Type')
    remarks = fields.Char('Remarks')
    sequence = fields.Char('Customer Item #', default="0") 

class TrkBlanketOrder(models.Model):
    _name = 'trk.blanket.order'
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char('Blanket Order No.')
    date = fields.Date('Transaction Date', default=fields.Date.today())
    branch_id = fields.Many2one('trk.branch', string='Branch')
    partner_id = fields.Many2one('res.partner', string='Customer', domain="[('is_customer', '=', True)]")
    end_user_id = fields.Many2one('res.partner', string='End User', domain="[('is_end_user', '=', True)]")
    user_id = fields.Many2one('res.users', 'Salesperson')
    project_id = fields.Many2one('trk.project', string='Project')   
    customer_purchase_id = fields.Many2one('trk.customer.purchase', string='Customer PO No.') 
    line_ids = fields.One2many('trk.blanket.order.line', 'reference', string='Items')
    sale_ids = fields.One2many('trk.blanket.order.sale', 'reference', string='Sales Orders')
    state = fields.Selection([
        ('Open','Open'),
        ('Closed','Closed')
    ], string='Status', default='Open')

    def action_close(self):
        for res in self:
            self.write({'state' : 'Closed'})

    def action_sales_order(self):
        for res in self:
            order_id = self.env['sale.order'].create({
                'partner_id' : res.partner_id.id,
                'partner_invoice_id' : res.partner_id.id,
                'partner_shipping_id' : res.partner_id.id,
                'user_id' : res.user_id.id,
            })            

            for line in res.line_ids:
                self.env['sale.order.line'].create({
                    'order_id' : order_id.id,
                    'product_id' : line.product_id.id,
                    'name' : line.product_id.name,
                    'product_uom' : line.product_id.uom_id.id,
                    'price_unit' : line.product_id.list_price,
                })

            self.env['trk.blanket.order.sale'].create({
                'reference' : res.id,
                'order_id' : order_id.id,
                'date' : order_id.date_order
            })

    def get_sequence(self, name=False, obj=False, context=None):
        sequence_id = self.env['ir.sequence'].search([
            ('name', '=', name),
            ('code', '=', obj),
            ('prefix', '=', 'BOD/%(month)s/%(y)s/')
        ])
        if not sequence_id :
            sequence_id = self.env['ir.sequence'].sudo().create({
                'name': name,
                'code': obj,
                'implementation': 'standard',
                'prefix': 'BOD/%(month)s/%(y)s/',
                'padding': 3
            })
        return sequence_id.next_by_id()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.update({'name': self.get_sequence('Blanket Order', 'trk.blanket.order')})
        return super(TrkBlanketOrder, self).create(vals_list)

class TrkCustomerPurchaseLine(models.Model):
    _name = 'trk.customer.purchase.line'
    _order = 'sequence asc'

    reference = fields.Many2one('trk.customer.purchase', string='Customer PO No.')
    quotation_id = fields.Many2one('trk.quotation', string='Quotation No.')
    product_id = fields.Many2one('product.product', string='Product')
    product_uom_qty = fields.Float('Qty')
    price_unit = fields.Float('Price Unit')
    valve_type_id = fields.Many2one('trk.valve.type', string='Valve Type')
    remarks = fields.Char('Remarks') 
    sequence = fields.Char('Customer Item #', default="0")
    price_subtotal = fields.Float(compute="_get_price_subtotal", string="Subtotal")

    @api.depends('product_uom_qty', 'price_unit')
    def _get_price_subtotal(self):
        for res in self:
            res.price_subtotal = res.price_unit * res.product_uom_qty

class TrkCustomerPurchase(models.Model):
    _name = 'trk.customer.purchase'
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char('Customer PO No.')
    date = fields.Date('Transaction Date', default=fields.Date.today())
    branch_id = fields.Many2one('trk.branch', string='Branch')
    partner_id = fields.Many2one('res.partner', string='Customer', domain="[('is_customer', '=', True)]")
    end_user_id = fields.Many2one('res.partner', string='End User', domain="[('is_end_user', '=', True)]")
    user_id = fields.Many2one('res.users', 'Salesperson')
    project_id = fields.Many2one('trk.project', string='Project')
    order_status = fields.Selection([
        ('Blanket Order','Blanket Order'),
        ('Sales Order','Sales Order')
    ], string='Order Status', default='Sales Order')
    ref_no = fields.Char('Ref No.')
    remarks = fields.Text('Remarks')
    order_id = fields.Many2one('sale.order', string="Sales Order No.")
    blanket_id = fields.Many2one('trk.blanket.order', string="Blanket Order No.")
    line_ids = fields.One2many('trk.customer.purchase.line', 'reference', string='Items')
    quotation_ids = fields.Many2many('trk.quotation', 
        'customer_purchase_quotation_rel', 
        'customer_purchase_id', 
        'quotation_id', 
        string='Sales Quotations')
    state = fields.Selection([
        ('Pending','Pending'),
        ('Sales Order','Sales Order'),
        ('Blanket Order','Blanket Order')
    ], string='Status', default='Pending')
    amount_total = fields.Float(compute="_get_total", string="Total Amount")

    @api.depends('line_ids.price_subtotal')
    def _get_total(self):
        for res in self:
            amount_total = 0
            if res.line_ids:
                for line in res.line_ids:
                    amount_total += line.price_subtotal
            res.amount_total = amount_total

    def action_reload_product(self):
        for res in self:
            if res.quotation_ids:
                sequence = 1
                for quotation in res.quotation_ids:
                    for line in quotation.line_ids:
                        self.env['trk.customer.purchase.line'].create({
                            'reference' : res.id,
                            'sequence' : sequence,
                            'quotation_id' : quotation.id,
                            'valve_type_id' : line.valve_type_id.id,
                            'product_uom_qty' : line.product_uom_qty,
                            'price_unit' : line.price_unit,
                            'remarks' : quotation.remarks
                        })

                        sequence += 1

    def action_sales_order(self):
        for res in self:
            order_id = self.env['sale.order'].create({
                'partner_id' : res.partner_id.id,
                'partner_invoice_id' : res.partner_id.id,
                'partner_shipping_id' : res.partner_id.id,
                'user_id' : res.user_id.id,
            })            

            for line in res.line_ids:
                self.env['sale.order.line'].create({
                    'order_id' : order_id.id,
                    'product_id' : line.product_id.id,
                    'name' : line.product_id.name,
                    'product_uom' : line.product_id.uom_id.id,
                    'product_uom_qty' : line.product_uom_qty,
                    'price_unit' : line.price_unit,
                    'sequence' : line.sequence
                })

            res.write({
                'state' : 'Sales Order',
                'order_id' : order_id.id
            })

    def action_blanket_order(self):
        for res in self:
            blanket_order_id = self.env['trk.blanket.order'].create({
                'partner_id' : res.partner_id.id,
                'branch_id' : res.branch_id.id,
                'partner_id' : res.partner_id.id,
                'end_user_id' : res.end_user_id.id,
                'user_id' : res.user_id.id,
                'project_id' : res.project_id.id,   
                'customer_purchase_id' : res.id
            })            

            for line in res.line_ids:
                self.env['trk.blanket.order.line'].create({
                    'reference' : blanket_order_id.id,
                    'product_id' : line.product_id.id,
                    'product_uom_qty' : line.product_uom_qty,
                    'price_unit' : line.price_unit,
                    'quotation_id' : line.quotation_id.id,
                    'valve_type_id' : line.valve_type_id.id,
                    'remarks' : line.remarks,
                    'sequence' : line.sequence
                })

            res.write({
                'state' : 'Blanket Order',
                'blanket_id' : blanket_order_id.id
            })

    def get_sequence(self, name=False, obj=False, context=None):
        sequence_id = self.env['ir.sequence'].search([
            ('name', '=', name),
            ('code', '=', obj),
            ('prefix', '=', 'CPO/%(month)s/%(y)s/')
        ])
        if not sequence_id :
            sequence_id = self.env['ir.sequence'].sudo().create({
                'name': name,
                'code': obj,
                'implementation': 'standard',
                'prefix': 'CPO/%(month)s/%(y)s/',
                'padding': 3
            })
        return sequence_id.next_by_id()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.update({'name': self.get_sequence('Customer PO No.', 'trk.customer.purchase')})
        return super(TrkCustomerPurchase, self).create(vals_list)

class TrkQuotationLine(models.Model):
    _name = 'trk.quotation.line'

    reference = fields.Many2one('trk.quotation', string='Quotation')
    valve_type_id = fields.Many2one('trk.valve.type', 'Valve Type')
    valve_tag = fields.Char('Valve Tag')
    datasheet = fields.Char('Datasheet')
    description = fields.Char('Description')
    body_construction = fields.Char('Body Construction')
    type_design = fields.Char('Type Design')
    seat_design = fields.Char('Seat Design')
    size = fields.Char('Size')
    rating = fields.Char('Rating')
    bore = fields.Char('Bore')
    end_con = fields.Char('End Con')
    body = fields.Char('Body')
    ball = fields.Char('Ball')
    seat = fields.Char('Seat')
    seat_insert = fields.Char('Seat Insert')
    stem = fields.Char('Stem')
    seal = fields.Char('Seal')
    bolt = fields.Char('Bolt')
    disc = fields.Char('Disc')
    shaft = fields.Char('Shaft')
    arm_pin = fields.Char('Arm Pin')
    backseat = fields.Char('Backseat')
    plates = fields.Char('Plates')
    spring = fields.Char('Spring')
    arm = fields.Char('Arm')
    hinge_pin = fields.Char('Hinge Pin')
    stop_pin = fields.Char('Stop Pin')
    operator = fields.Char('Operator')
    product_uom_qty = fields.Float('Qty')
    price_unit = fields.Float('Price Unit')
    price_subtotal = fields.Float(compute="_get_price_subtotal", string="Subtotal")

    @api.depends('product_uom_qty', 'price_unit')
    def _get_price_subtotal(self):
        for res in self:
            res.price_subtotal = res.price_unit * res.product_uom_qty

class TrkQuotation(models.Model):
    _name = 'trk.quotation'
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char('Quotation No.')
    date = fields.Date('Transaction Date', default=fields.Date.today())
    request_id = fields.Many2one('trk.request.sale', string="RFQ No.", domain="[('state', '=', 'Approved')]")
    branch_id = fields.Many2one('trk.branch', string='Branch')
    project_id = fields.Many2one('trk.project', string='Project')
    subject = fields.Char('Subject')
    order_status = fields.Selection([
        ('Blanket Order','Blanket Order'),
        ('Sales Order','Sales Order')
    ], string='Order Status', default='Sales Order')
    currency_id = fields.Many2one('res.currency', string='Currency')
    partner_id = fields.Many2one('res.partner', string='Customer', 
        domain="[('is_customer', '=', True)]")
    end_user_id = fields.Many2one('res.partner', string='End User', 
        domain="[('is_end_user', '=', True)]")
    attn = fields.Char('Attn')
    user_id = fields.Many2one('res.users', 'Salesperson')
    ship_id = fields.Many2one('trk.ship', 'Ship To')
    delivery_term_id = fields.Many2one('trk.delivery.term', 'Term of Delivery')
    price_validity = fields.Char('Price Validity')
    certificate_documentation = fields.Text('Certificate Doc')
    testing = fields.Text('Testing')
    inspection = fields.Text('Inspection')
    painting = fields.Text('Painting')
    packing = fields.Char('Packing')
    tagging = fields.Char('Tagging')
    warranty = fields.Char('Warranty')
    payment = fields.Text('Payment')
    ref_no = fields.Char('Ref No.')
    remarks = fields.Text('Remarks')
    line_ids = fields.One2many('trk.quotation.line', 'reference', string='Valve Type')
    valve_type_component_ids = fields.Many2many('trk.valve.type.component', 
        'quotation_valve_type_component_rel', 
        'quotation_id', 
        'valve_type_component_id', 
        string='Valve Type Components')
    state = fields.Selection([
        ('Pending','Pending'),
        ('Approved','Approved'),
        ('Declined','Declined')
    ], string='Status', default='Pending')
    amount_total = fields.Float(compute="_get_total", string="Total Amount")

    @api.depends('line_ids.price_subtotal')
    def _get_total(self):
        for res in self:
            amount_total = 0
            if res.line_ids:
                for line in res.line_ids:
                    amount_total += line.price_subtotal
            res.amount_total = amount_total

    def action_approve(self):
        for res in self:
            res.write({'state' : 'Approved'})

    def action_decline(self):
        for res in self:
            res.write({'state' : 'Declined'})

    @api.onchange('request_id')
    def _onchange_request_id(self):
        if self.request_id:
            values["branch_id"] = self.request_id.branch_id.id,
            values["project_id"] = self.request_id.project_id.id,
            values["subject"] = self.request_id.subject,
            values["currency_id"] = self.request_id.currency_id.id,
            values["partner_id"] = self.request_id.partner_id.id,
            values["end_user_id"] = self.request_id.end_user_id.id,
            values["attn"] = self.request_id.attn,
            values["user_id"] = self.request_id.user_id.id
            values["order_status"] = self.request_id.order_status
            
            self.update(values)

    def get_sequence(self, name=False, obj=False, context=None):
        sequence_id = self.env['ir.sequence'].search([
            ('name', '=', name),
            ('code', '=', obj),
            ('prefix', '=', 'QUO/%(month)s/%(y)s/')
        ])
        if not sequence_id :
            sequence_id = self.env['ir.sequence'].sudo().create({
                'name': name,
                'code': obj,
                'implementation': 'standard',
                'prefix': 'QUO/%(month)s/%(y)s/',
                'padding': 3
            })
        return sequence_id.next_by_id()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.update({'name': self.get_sequence('Quotation', 'trk.quotation')})
        return super(TrkQuotation, self).create(vals_list)

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    sequence = fields.Char('Customer Item #', default="0")

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    branch_id = fields.Many2one('trk.branch', string='Branch')
    partner_id = fields.Many2one('res.partner', string='Customer', 
        domain="[('is_customer', '=', True)]")
    end_user_id = fields.Many2one('res.partner', string='End User', 
        domain="[('is_end_user', '=', True)]")
    customer_purchase_id = fields.Many2one('trk.customer.purchase', string='Customer PO No.')
    blanket_order_id = fields.Many2one('trk.blanket.order', string='Blanket Order No.') 
    user_id = fields.Many2one('res.users', 'Salesperson')
    project_id = fields.Many2one('trk.project', string='Project')
    ref_no = fields.Char('Ref No.')
    remarks = fields.Text('Remarks')
    quotation_ids = fields.Many2many('trk.quotation', 
        'sale_quotation_rel', 
        'sale_id', 
        'quotation_id', 
        string='Sales Quotations')

class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_customer = fields.Boolean("Customer Status", default=True)
    is_end_user = fields.Boolean("End User Status", default=False)

class TrkRequestSale(models.Model):
    _name = 'trk.request.sale'
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char('RFQ No.')
    ref_number = fields.Char('Ref. No')
    tender_number = fields.Char('Tender No.')
    order_status = fields.Selection([
    	('Blanket Order','Blanket Order'),
    	('Sales Order','Sales Order')
    ], string='Order Status', default='Sales Order')

    branch_id = fields.Many2one('trk.branch', string='Branch')
    transaction_date = fields.Date('Transaction Date')
    registered_date = fields.Date('Registered Date')
    review_status = fields.Boolean('Reviewed Status')
    bidding_date = fields.Date('Pre Bidding Meeting')
    factory_date = fields.Date('Send to Factory')
    customer_date = fields.Date('Submit to Customer')
    scope = fields.Text('Scope of Supply')

    currency_id = fields.Many2one('res.currency', string='Currency')
    partner_id = fields.Many2one('res.partner', string='Customer', 
        domain="[('is_customer', '=', True)]")
    end_user_id = fields.Many2one('res.partner', string='End User', 
        domain="[('is_end_user', '=', True)]")
    attn = fields.Char('Attn')
    user_id = fields.Many2one('res.users', 'Salesperson')
    project_id = fields.Many2one('trk.project', string='Project')
    subject = fields.Char('Subject')
    remarks = fields.Text('Remarks')    
    state = fields.Selection([
    	('Pending','Pending'),
    	('Approved','Approved'),
    	('Declined','Declined')
    ], string='Status', default='Pending')

    def action_approve(self):
        for res in self:
            res.write({'state' : 'Approved'})

    def action_decline(self):
        for res in self:
            res.write({'state' : 'Declined'})

    def get_sequence(self, name=False, obj=False, context=None):
        sequence_id = self.env['ir.sequence'].search([
            ('name', '=', name),
            ('code', '=', obj),
            ('prefix', '=', 'RFQ/%(month)s/%(y)s/')
        ])
        if not sequence_id :
            sequence_id = self.env['ir.sequence'].sudo().create({
                'name': name,
                'code': obj,
                'implementation': 'standard',
                'prefix': 'RFQ/%(month)s/%(y)s/',
                'padding': 3
            })
        return sequence_id.next_by_id()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.update({'name': self.get_sequence('Request for Quotation', 'trk.request.sale')})
        return super(TrkRequestSale, self).create(vals_list)
    