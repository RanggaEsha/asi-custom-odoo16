# -*- coding: utf-8 -*-

from num2words import num2words
from collections import defaultdict
from contextlib import ExitStack, contextmanager
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from hashlib import sha256
from json import dumps
import re
from textwrap import shorten
from unittest.mock import patch

from odoo import api, fields, models, _, Command
from odoo.addons.base.models.decimal_precision import DecimalPrecision
from odoo.addons.account.tools import format_rf_reference
from odoo.exceptions import UserError, ValidationError, AccessError, RedirectWarning

class GatransAirline(models.Model):
    _name = 'gatrans.airline'

    name = fields.Char('Airline')
    awb_code = fields.Char('AWB Code')

class GatransDestination(models.Model):
    _name = 'gatrans.destination'

    name = fields.Char('Destination Name')

class GatransFlight(models.Model):
    _name = 'gatrans.flight'

    name = fields.Char('Flight Code')
    # airline_id = fields.Many2one('gatrans.airline', 'Airline')

class GatransDriver(models.Model):
    _name = 'gatrans.driver'

    name = fields.Char('Driver Name')

class GatransLabel(models.Model):
    _name = 'gatrans.label'

    name = fields.Char('Label No.')

class GatransSeal(models.Model):
    _name = 'gatrans.seal'

    name = fields.Char('Seal No.')

class GatransMethod(models.Model):
    _name = 'gatrans.method'

    name = fields.Char('Method Name')

class GatransConsignmentLine(models.Model):
    _name = 'gatrans.consignment.line'
    _order = 'id desc'

    reference = fields.Many2one('gatrans.consignment', 'CSD')
    product_id = fields.Many2one('product.product', string='Commodity (Nature of Goods)')
    quantity = fields.Char('Quantity', default=1)
    weight = fields.Float('Weight (Kg)')
    weight_actual = fields.Float('Weight Actual (Kg)')

    def action_get_scale(self):
        self.weight = 16

class GatransConsignment(models.Model):
    _name = 'gatrans.consignment'
    _order = 'id desc'

    name = fields.Char('Document No.', tracking=True)
    csd_number = fields.Char('CSD Number', tracking=True)
    date = fields.Char('Date', default=fields.Date.today(), tracking=True)
    consignee_id = fields.Many2one('res.partner', string='Consignee', tracking=True)
    airline_id = fields.Many2one('gatrans.airline', string='Airline', tracking=True)
    awb_code = fields.Char(related='airline_id.awb_code', string='AWB Code', tracking=True)
    awb_number = fields.Char('AWB No.', tracking=True)
    destination_id = fields.Many2one('gatrans.destination', string='Destination', tracking=True)
    flight_id = fields.Many2one('gatrans.flight', string='Flight', tracking=True)
    remarks = fields.Char('Remarks', default='/ID/BDG/', tracking=True)
    screening_method = fields.Selection([
        ('X-RAY','X-RAY'),
        ('MANUAL','MANUAL')
    ], string='Screening Method', default='X-RAY', tracking=True)
    other_method = fields.Many2one('gatrans.method', string='Other Method', tracking=True)
    driver_id = fields.Many2one('gatrans.driver', string='Driver', tracking=True)
    label_id = fields.Many2one('gatrans.label', string='Label No.', tracking=True)
    seal_id = fields.Many2one('gatrans.seal', string='Seal No.', tracking=True)
    origin = fields.Char('Origin', default='CGK', tracking=True)
    transit = fields.Char('Transit', tracking=True)
    security_status = fields.Char('Security Status', default='SPX', tracking=True)
    received_from = fields.Char('Received From', default='RA', tracking=True)
    grounds = fields.Char('Grounds for Exception', tracking=True)
    scale_input = fields.Integer('Scale Input', tracking=True)
    avsec = fields.Many2one('res.users', string='Avsec', default=lambda self: self._uid)
    product_id = fields.Many2one('product.product', 'Commodity', tracking=True)
    quantity = fields.Integer('Quantity', tracking=True)
    weight = fields.Integer('Weight', tracking=True)
    line_ids = fields.One2many('gatrans.consignment.line', 'reference', 'Lines', tracking=True)
    move_id = fields.Many2one('account.move', string='Invoice Number', tracking=True)
    move_status = fields.Char(compute="_get_move_status", string='Invoice Status', tracking=True)
    state = fields.Selection([
        ('Draft','Draft'),
        ('Passed','Passed'),
        ('Waiting Driver','Waiting Driver'),
        ('CSD Generated', 'CSD Generated'),
        ('Confirmed','Confirmed'),
        ('Invoiced','Invoiced'),
        # ('Paid','Paid'),
        ('Failed','Failed'),
    ], string='Status', default='Draft', tracking=True, copy=False)

    def get_sequence(self, name=False, obj=False, context=None):
        sequence_id = self.env['ir.sequence'].search([
            ('name', '=', name),
            ('code', '=', obj),
            ('prefix', '=', 'DOC/%(month)s/%(y)s/')
        ])
        if not sequence_id :
            sequence_id = self.env['ir.sequence'].sudo().create({
                'name': name,
                'code': obj,
                'implementation': 'standard',
                'prefix': 'DOC/%(month)s/%(y)s/',
                'padding': 3
            })
        return sequence_id.next_by_id()

    @api.depends('move_id')
    def _get_move_status(self):
        for res in self:
            move_status = ''
            if res.move_id:
                if res.move_id.payment_state == "not_paid":
                    move_status = "Not Paid"
                elif res.move_id.payment_state == "paid":
                    move_status = "Paid"
            res.move_status = move_status

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.update({'name': self.get_sequence('Gatrans Document', 'gatrans.document')})
        return super(GatransConsignment, self).create(vals_list)

    def action_draft(self):
        self.write({'state' : 'Draft'})

    def action_get_scale(self):
        # for res in self:
        self.weight = 16

    def action_add_item(self):
        for res in self:
            self.env['gatrans.consignment.line'].create({
                'reference' : res.id,
                'product_id' : res.product_id.id,
                'quantity' : res.quantity,
                'weight' : res.weight
            })

            res.write({
                'product_id' : False,
                'quantity' : False,
                'weight' : False
            })

    def action_pass(self):
        for res in self:
            res.write({
                'state' : 'Passed',
                'csd_number' : res.get_sequence('Gatrans Consignment', 'gatrans.consignment')
            })

    def action_fail(self):
        for res in self:
            res.write({'state' : 'Failed'})

    def action_waiting(self):
        for res in self:
            res.write({'state' : 'Waiting Driver'})

    def action_delivery(self):
        for res in self:
            res.write({'state' : 'CSD Generated'})

    def action_confirm(self):
        for res in self:
            res.write({'state' : 'Confirmed'})

    def _prepare_move(self):
        self.ensure_one()
        invoice_vals = {}
        journal_ids = self.env['account.journal'].search([('type', '=', 'sale')])
        if not journal_ids:
            raise UserError(_('Please define Customer Invoice Journal for the company %s (%s).') % (self.company_id.name, self.company_id.id))

        invoice_vals = {
            'partner_id': self.consignee_id.id,
            'invoice_date': fields.Date.today(),
            'journal_id': journal_ids[0].id,
            'move_type': 'out_invoice',
            'invoice_line_ids': []
        }

        return invoice_vals

    def _prepare_move_line(self, line):
        self.ensure_one()
        invoice_line_vals = {}

        # if self.line_ids:
        #     for line in self.line_ids:
        price_unit = 0  

        pricelist_item_ids = self.env['product.pricelist.item'].search([
            ('pricelist_id', '=', self.consignee_id.property_product_pricelist.id),
            ('product_tmpl_id', '=', line.product_id.product_tmpl_id.id)
        ])

        if pricelist_item_ids:
            price_unit = pricelist_item_ids[0].fixed_price

        invoice_line_vals = {
            'product_id': line.product_id.id,
            'product_uom_id': line.product_id.uom_id.id,
            'name': line.product_id.name,
            'account_id': line.product_id.categ_id.property_account_income_categ_id.id,
            'quantity': line.weight_actual,
            'price_unit': price_unit,
        }

        return invoice_line_vals

    def action_create_invoices(self):
        for res in self:
            invoice_vals = self._prepare_move()
            invoice_vals_list = []
            invoice_line_vals = []
            
            if res.line_ids:
                for line in res.line_ids:
                    if not line.weight_actual:
                        raise UserError(_('Please input Actual Weight for Product %s before Create Invoice.') % (line.product_id.name))
                    invoice_line_vals.append((0, 0, self._prepare_move_line(line)))

            # Create Invoices
            invoice_vals['invoice_line_ids'] += invoice_line_vals
            invoice_vals_list.append(invoice_vals)
            move_id = self.env['account.move'].sudo().with_context(default_move_type='out_invoice').create(invoice_vals_list)
            
            action = {
                'name': _('Customer Invoices'),
                'type': 'ir.actions.act_window',
                'res_model': 'account.move',
                'target': 'current',
            }
            
            action['res_id'] = move_id.id
            action['view_mode'] = 'form'

            # Confirm Invoice
            move_id.action_post()

            # Update Invoice in CSD
            res.write({
                'move_id' : move_id.id,
                'state' : 'Invoiced'
            })

            return action