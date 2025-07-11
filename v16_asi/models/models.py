# -*- coding: utf-8 -*-
# Test comment to verify git change detection

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
from odoo.tools import (
    date_utils,
    email_re,
    email_split,
    float_compare,
    float_is_zero,
    format_amount,
    format_date,
    formatLang,
    frozendict,
    get_lang,
    is_html_empty,
    sql
)

class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'

    def _message_auto_subscribe_notify(self, partner_ids, template):
        return True

class AccountFollowupReport(models.AbstractModel):
    _inherit = 'account.followup.report'

    def get_followup_report_html(self, options):
        """
        Return the html of the followup report, based on the report options.
        """
        template = 'account_followup.template_followup_report'
        render_values = self._get_followup_report_html_render_values(options)

        headers = [self._get_followup_report_columns_name()]
        # lines = self._get_followup_report_lines(options)

        # Catch negative numbers when present
        # for line in lines:
        #     for col in line['columns']:
        #         if self.env.company.currency_id.compare_amounts(col.get('no_format', 0.0), 0.0) == -1:
        #             col['class'] = 'number color-red'

        # render_values['lines'] = {'columns_header': headers, 'lines': lines}

        return self.env['ir.qweb']._render(template, render_values)

    @api.model
    def _send_email(self, options):
        """
        Send by email the followup to the customer's followup contacts
        """
        partner = self.env['res.partner'].browse(options.get('partner_id'))
        followup_contacts = partner._get_all_followup_contacts() or partner
        followup_recipients = options.get('email_recipients_ids', followup_contacts)
        sent_at_least_once = False
        for to_send_partner in followup_recipients:
            email = to_send_partner.email
            if email and email.strip():
                self = self.with_context(lang=partner.lang or self.env.user.lang)
                body_html = self.with_context(mail=True).get_followup_report_html(options)

                attachment_ids = options.get('attachment_ids', partner.unpaid_invoice_ids.message_main_attachment_id.ids)

                partner.with_context(mail_post_autofollow=True, lang=partner.lang or self.env.user.lang).message_post(
                    partner_ids=[to_send_partner.id],
                    body=body_html,
                    subject=self._get_email_subject(options),
                    subtype_id=self.env.ref('mail.mt_note').id,
                    model_description=_('payment reminder'),
                    email_layout_xmlid='mail.mail_notification_light',
                    attachment_ids=attachment_ids,
                )
                sent_at_least_once = True
        if not sent_at_least_once:
            raise UserError(_('You are trying to send an Email, but no follow-up contact has any email address set'))
            
class ResCompany(models.Model):
    _inherit = 'res.company'

    submitted_user_id = fields.Many2one('res.users', 'Submitted by')
    checked_user_id = fields.Many2one('res.users', 'Checked by')
    approved_user_id = fields.Many2one('res.users', 'Approved by')
    payment_user_id = fields.Many2one('res.users', 'Payment by')

class ResPartner(models.Model):
    _inherit = 'res.partner'

    attention = fields.Char('Attention')
    attention_title = fields.Char('Title Attention')
    fax_number = fields.Char('Fax')

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    submitted_user_id = fields.Many2one(related="company_id.submitted_user_id", comodel_name='res.users', string='Submitted by')
    checked_user_id = fields.Many2one(related="company_id.checked_user_id", comodel_name='res.users', string='Checked by')
    approved_user_id = fields.Many2one(related="company_id.approved_user_id", comodel_name='res.users', string='Approved by')
    payment_user_id = fields.Many2one(related="company_id.payment_user_id", comodel_name='res.users', string='Payment by')
    amount_bank_terbilang = fields.Char(compute="_get_amount_bank_terbilang", string="Amount Bank Terbilang", track_visibility="always")
    amount_total_invoice = fields.Float(compute="_get_amount_total_invoice", string="Amount Invoice")

    @api.depends('amount')
    def _get_amount_total_invoice(self):
        for res in self:
            amount = 0 
            if res.reconciled_bill_ids:
                for bill in res.reconciled_bill_ids:
                    amount = bill.amount_total
            res.amount_total_invoice = amount

    @api.depends('amount_total_invoice','amount')
    def _get_amount_bank_terbilang(self):
        for res in self:
            amount = num2words(res.amount)
            if res.amount_total_invoice:
                amount = num2words(res.amount_total_invoice)
            
            currency_word = " Rupiah"
            if res.currency_id.name != 'IDR':
                currency_word = " Dollar"

            res.amount_bank_terbilang = amount + " " + res.currency_id.full_name

class AccountTax(models.Model):
    _inherit = 'account.tax'

    tax_group = fields.Selection([('VAT','VAT'),('PPh','PPh')])

class ResUsers(models.Model):
    _inherit = 'res.users'

    is_approval_user = fields.Boolean('Penandatangan')
    
class PurchaseRequestLine(models.Model):
    _name = 'purchase.request.line'

    reference = fields.Many2one('purchase.request', 'Purchase Request')
    product_id = fields.Many2one('product.product', 'Product')
    qty = fields.Float('Quantity')
    product_uom = fields.Many2one('uom.uom', 'Unit of Measure')
    price_unit = fields.Float('Price Unit')
    amount_total = fields.Float(compute="_get_subtotal", string='Total Amount')
    
    @api.onchange('product_id')
    def _onchange_product_id_purchase_request(self):
        if self.product_id:
            self.product_uom = self.product_id.uom_id.id

    @api.depends('qty','price_unit')
    def _get_subtotal(self):
        for res in self:
            res.amount_total = res.qty * res.price_unit

class PurchaseRequest(models.Model):
    _name = 'purchase.request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'

    @api.depends('line_ids.amount_total', 'amount_discount', 'amount_pph_editable', 
        'amount_tax_editable', 'amount_discount_percent', 'tax_vat_id', 'tax_pph_id')
    def _amount_all(self):
        for order in self:
            amount_untaxed = amount_tax = amount_vat = amount_pph = 0.0
            for line in order.line_ids:
                amount_untaxed += line.amount_total

            currency = order.currency_id or order.partner_id.property_purchase_currency_id or self.env.company.currency_id
            discount = order.amount_discount
            if order.amount_discount_percent > 0:
                discount = amount_untaxed * order.amount_discount_percent / 100

            if order.tax_vat_id:
                amount_vat = (amount_untaxed - discount) * order.tax_vat_id.amount / 100
            if order.tax_pph_id:
                amount_pph = (amount_untaxed - discount) * order.tax_pph_id.amount / 100

            order.update({
                'amount_untaxed': currency.round(amount_untaxed),
                'amount_tax': currency.round(amount_vat + amount_pph),
                'amount_vat': currency.round(amount_vat),
                'amount_pph': currency.round(amount_pph),
                'amount_total': amount_untaxed + order.amount_tax_editable + order.amount_pph_editable - discount,
            })

    company_id = fields.Many2one('res.company', 'Company', default=lambda self: self.env.company.id)
    name = fields.Char('Purchase Request No.')
    reason = fields.Char('Cancel Reason')
    date = fields.Date('Request Date', default=fields.Date.today())
    currency_id = fields.Many2one('res.currency', 'Currency')
    purchase_id = fields.Many2one('purchase.order', 'Purchase Order')
    purchase_purpose = fields.Char('Purpose Purchase')
    partner_id = fields.Many2one('res.partner', 'Vendor')
    contact_person = fields.Char('Contact Person')
    expected_date = fields.Date('Expected Date')
    
    payment_method = fields.Char('Payment Method')
    payment_term_id = fields.Many2one('account.payment.term', 'Payment Terms')
    due_date = fields.Date('Due Date')
    account_info = fields.Char('Account Info')
    tax_ids = fields.Many2one('account.tax', 'Taxes')
    amount_total = fields.Float(compute="_get_total", string='Total')
    budget_id = fields.Many2one('budget.budget', 'Budget')
    analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account')
    budget_post_id = fields.Many2one('account.budget.post', string='Budget Position')
    remaining_budget = fields.Float(string='Remaining Budget')
    line_ids = fields.One2many('purchase.request.line', 'reference', 'Lines')
    is_approve2 = fields.Boolean('2nd Approval')
    is_approve3 = fields.Boolean('3rd Approval')
    approver1_id = fields.Many2one('res.users', 'Approver 1')
    approver2_id = fields.Many2one('res.users', 'Approver 2')
    approver3_id = fields.Many2one('res.users', 'Approver 3')
    is_required_seleksi = fields.Boolean(compute='_get_seleksi', string='Required Seleksi')
    
    purchase_flow = fields.Selection([('Create PO','Create PO'),('Direct to Finance','Direct to Finance')]
        , default='Create PO', string='Flow Purchasing')

    tax_vat_id = fields.Many2one('account.tax', 'VAT')
    tax_pph_id = fields.Many2one('account.tax', 'Withholding Tax')
    amount_untaxed = fields.Monetary(string='Untaxed Amount', store=True, readonly=True, compute='_amount_all', tracking=True)
    amount_tax = fields.Monetary(string='Taxes', store=True, readonly=True, compute='_amount_all')
    amount_vat = fields.Monetary(string='VAT', store=True, readonly=True, compute='_amount_all')
    amount_pph = fields.Monetary(string='PPh', store=True, readonly=True, compute='_amount_all')
    amount_total = fields.Monetary(string='Total', store=True, readonly=True, compute='_amount_all')
    amount_tax_editable = fields.Monetary(string='VAT (Editable)')
    amount_pph_editable = fields.Monetary(string='PPh (Editable)')    
    amount_discount = fields.Monetary('Discount')
    amount_discount_percent = fields.Float('Discount (%)')
    notes = fields.Text('Notes')
    seleksi_vendor = fields.Binary('Seleksi Vendor')
    seleksi_vendor_name = fields.Char('Filename', readonly=True)
    uji_kelayakan = fields.Binary('Uji Kelayakan')
    uji_kelayakan_name = fields.Char('Filename', readonly=True)
    is_required_seleksi = fields.Boolean(string='Required Seleksi')
    state = fields.Selection([
        ('Draft','Draft'),
        ('Submitted','Submitted'),
        ('Dept Head Approval','1st Approval'),
        ('BOD Approval','2nd Approval'),
        ('Final Approval','3rd Approval'),
        ('Approved','Approved'),
        ('Cancelled','Cancelled')
    ], string='Status', default='Draft')
    method = fields.Selection([
        ('Delivery by Supplier at No Cost', 'Delivery by Supplier at No Cost'),
        ('Delivery by Supplier at Cost of Rp. ', 'Delivery by Supplier at Cost of Rp. '),
        ('Pick up by ASI at No Cost','Pick up by ASI at No Cost'),
        ('Pick up by ASI at Cost of ','Pick up by ASI at Cost of ')
    ], string='Method')

    @api.depends('amount_total')
    def _get_seleksi(self):
        for res in self:
            is_required_seleksi= False
            if res.amount_total > 10000000:
                is_required_seleksi = True
            res.is_required_seleksi = is_required_seleksi

    @api.onchange('amount_vat', 'amount_pph')
    def _onchange_amount_tax(self):
        self.amount_tax_editable = self.amount_vat
        self.amount_pph_editable = self.amount_pph

    @api.depends('analytic_account_id', 'budget_post_id')
    def _get_remaining_budget(self):
        for res in self:
            remaining_budget = 0
            budget_lines_ids = self.env['budget.lines'].search([
                ('analytic_account_id', '=', res.analytic_account_id.id),
                ('general_budget_id', '=', res.budget_post_id.id)
            ])

            if budget_lines_ids:
                remaining_budget = budget_lines_ids[0].planned_amount - budget_lines_ids[0].practical_amount
            res.remaining_budget = remaining_budget

    @api.model
    def create(self, vals):
        # if vals.get('amount_total') > vals.get('remaining_budget'):
        #     raise UserError(_('Amount Purchase Request more than Remaining Budget'))
        vals['name'] = self.env['ir.sequence'].next_by_code('purchase.request') or 'New'
        return super(PurchaseRequest, self).create(vals)

    @api.depends('line_ids.amount_total')
    def _get_total(self):
        for res in self:
            amount_total = 0 
            if res.line_ids:
                for line in res.line_ids:
                    amount_total += line.amount_total
            res.amount_total = amount_total

    def action_draft(self):
        for res in self:
            res.write({'state': 'Draft'})

    def action_reset_purchase(self):
        for res in self:
            res.write({'purchase_id': False})

    def action_cancel(self):
        return {
            'name': _('Cancel Purchase Request'),
            'type': 'ir.actions.act_window',
            'res_model': 'cancel.purchase.request',
            'view_mode': 'form',
            'target': 'new',
        }

    def action_submit(self):
        for res in self:
            mail_to = res.approver1_id.login
            data_template = self.env.ref('v16_asi.mail_template_purchase_request_approval1')
            template = self.env['mail.template'].browse(data_template.id)
            email_values = {'email_to': mail_to}
            template.send_mail(self.id, force_send=True, email_values=email_values)
            res.write({'state': 'Submitted'})
            
    def action_approve(self):
        for res in self:
            if self.env.user.id == res.approver1_id.id:
                if res.is_approve2:
                    mail_to = res.approver2_id.login
                    data_template = self.env.ref('v16_asi.mail_template_purchase_request_approval2')
                    template = self.env['mail.template'].browse(data_template.id)
                    email_values = {'email_to': mail_to}
                    template.send_mail(self.id, force_send=True, email_values=email_values)                
                    res.write({'state': 'BOD Approval'})
                else:
                    mail_to = res.create_uid.login
                    data_template = self.env.ref('v16_asi.mail_template_purchase_request_approved')
                    template = self.env['mail.template'].browse(data_template.id)
                    email_values = {'email_to': mail_to}
                    template.send_mail(self.id, force_send=True, email_values=email_values)
                    res.write({'state': 'Approved'})
            else:
                raise UserError(_('You are not allowed to approve this Document'))

    def action_approve2(self):
        for res in self:
            if self.env.user.id == res.approver2_id.id:
                if res.is_approve3:
                    mail_to = res.approver3_id.login
                    data_template = self.env.ref('v16_asi.mail_template_purchase_request_approval3')
                    template = self.env['mail.template'].browse(data_template.id)
                    email_values = {'email_to': mail_to}
                    template.send_mail(self.id, force_send=True, email_values=email_values)
                    res.write({'state': 'Final Approval'})
                else:
                    mail_to = res.create_uid.login
                    data_template = self.env.ref('v16_asi.mail_template_purchase_request_approved')
                    template = self.env['mail.template'].browse(data_template.id)
                    email_values = {'email_to': mail_to}
                    template.send_mail(self.id, force_send=True, email_values=email_values)    
                    res.write({'state': 'Approved'})
            else:
                raise UserError(_('You are not allowed to approve this Document'))

    def action_approve3(self):
        for res in self:
            if self.env.user.id == res.approver3_id.id:
                mail_to = res.create_uid.login
                data_template = self.env.ref('v16_asi.mail_template_purchase_request_approved')
                template = self.env['mail.template'].browse(data_template.id)
                email_values = {'email_to': mail_to}
                template.send_mail(self.id, force_send=True, email_values=email_values)
                res.write({'state': 'Approved'})
            else:
                raise UserError(_('You are not allowed to approve this Document'))

    def action_create_purchase(self):
        for res in self:
            purchase_id = self.env['purchase.order'].create({
                'partner_id': res.partner_id.id,
                'date_order': res.date,
                'date_planned': res.expected_date,
                'purchase_flow': res.purchase_flow,
                'currency_id': res.currency_id.id,
                'amount_discount': res.amount_discount,
                'amount_discount_percent': res.amount_discount_percent,
                'amount_tax_editable': res.amount_tax_editable,
                'amount_pph_editable': res.amount_pph_editable,
                'request_id': res.id
            })

            for line in res.line_ids:
                self.env['purchase.order.line'].create({
                    'order_id': purchase_id.id,
                    'product_id': line.product_id.id,
                    'name': line.product_id.name,
                    'product_qty': line.qty,
                    'product_uom': line.product_uom.id,
                    'price_unit': line.price_unit
                })

            res.write({'purchase_id': purchase_id.id})


class AccountContractType(models.Model):
    _name = 'account.contract.type'

    name = fields.Text('Contract Type')

class AccountLevel(models.Model):
    _name = 'account.level'

    name = fields.Text('Level')

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'
    _order = 'id asc, debit desc'

    name = fields.Text('Description')
    level_id = fields.Many2one('account.level', 'Level')
    product_category_id = fields.Many2one(related='product_id.categ_id', comodel_name='product.category', string='Category')

class AccountMove(models.Model):
    _inherit = 'account.move'

    account_manager = fields.Char('Account Manager')
    contract_number = fields.Char('Contract Number')
    contract_type_id = fields.Many2one('account.contract.type', 'Contract Type')
    contract_date = fields.Date('Contract Date')
    is_bukti_potong = fields.Boolean('Terima Bukti Potong')
    bukti_potong_number = fields.Char('No. Bukti Potong')
    bukti_potong_date = fields.Date('Tgl Bukti Potong')
    masa_pajak = fields.Char('Masa Pajak')
    nilai_bruto = fields.Float('Nilai Bruto')
    pph23_terpotong = fields.Float('PPh 23 terpotong')
    amount_tax_editable = fields.Monetary(string='VAT (Editable)', track_visibility="onchange")
    amount_pph_editable = fields.Monetary(string='PPh (Editable)')
    ppn_editable = fields.Monetary(string='Ppn (Editable)')    
    print_vat = fields.Boolean('Print VAT')
    print_pph = fields.Boolean('Print PPh')
    sign_user_id = fields.Many2one('res.users', 'Penandatangan')
    bank_ids = fields.Many2many('account.journal', 'account_move_journal_rel', 'journal_id', 'move_id', string='Bank Accounts')
    amount_vat = fields.Monetary(compute="_get_amount_asi", string="Amount VAT", store=True)
    amount_pph = fields.Monetary(compute="_get_amount_asi", string="Amount PPh", store=True)
    amount_before_pph = fields.Monetary(string='Amount before PPh', compute="_get_amount_before_pph")
    attention = fields.Char('Attention')
    attention_title = fields.Char('Title Attention')
    submitted_user_id = fields.Many2one(related="company_id.submitted_user_id", comodel_name='res.users', string='Submitted by')
    checked_user_id = fields.Many2one(related="company_id.checked_user_id", comodel_name='res.users', string='Checked by')
    approved_user_id = fields.Many2one(related="company_id.approved_user_id", comodel_name='res.users', string='Approved by')
    payment_user_id = fields.Many2one(related="company_id.payment_user_id", comodel_name='res.users', string='Payment by')
    
    def _post(self, soft=True):
        """Post/Validate the documents.

        Posting the documents will give it a number, and check that the document is
        complete (some fields might not be required if not posted but are required
        otherwise).
        If the journal is locked with a hash table, it will be impossible to change
        some fields afterwards.

        :param soft (bool): if True, future documents are not immediately posted,
            but are set to be auto posted automatically at the set accounting date.
            Nothing will be performed on those documents before the accounting date.
        :return Model<account.move>: the documents that have been posted
        """
        # if not self.env.su and not self.env.user.has_group('account.group_account_invoice'):
        #     raise AccessError(_("You don't have the access rights to post an invoice."))

        for invoice in self.filtered(lambda move: move.is_invoice(include_receipts=True)):
            if invoice.quick_edit_mode and invoice.quick_edit_total_amount and invoice.quick_edit_total_amount != invoice.amount_total:
                raise UserError(_(
                    "The current total is %s but the expected total is %s. In order to post the invoice/bill, "
                    "you can adjust its lines or the expected Total (tax inc.).",
                    formatLang(self.env, invoice.amount_total, currency_obj=invoice.currency_id),
                    formatLang(self.env, invoice.quick_edit_total_amount, currency_obj=invoice.currency_id),
                ))
            if invoice.partner_bank_id and not invoice.partner_bank_id.active:
                raise UserError(_(
                    "The recipient bank account linked to this invoice is archived.\n"
                    "So you cannot confirm the invoice."
                ))
            if float_compare(invoice.amount_total, 0.0, precision_rounding=invoice.currency_id.rounding) < 0:
                raise UserError(_(
                    "You cannot validate an invoice with a negative total amount. "
                    "You should create a credit note instead. "
                    "Use the action menu to transform it into a credit note or refund."
                ))

            if not invoice.partner_id:
                if invoice.is_sale_document():
                    raise UserError(_("The field 'Customer' is required, please complete it to validate the Customer Invoice."))
                elif invoice.is_purchase_document():
                    raise UserError(_("The field 'Vendor' is required, please complete it to validate the Vendor Bill."))

            # Handle case when the invoice_date is not set. In that case, the invoice_date is set at today and then,
            # lines are recomputed accordingly.
            if not invoice.invoice_date:
                if invoice.is_sale_document(include_receipts=True):
                    invoice.invoice_date = fields.Date.context_today(self)
                elif invoice.is_purchase_document(include_receipts=True):
                    raise UserError(_("The Bill/Refund date is required to validate this document."))

        if soft:
            future_moves = self.filtered(lambda move: move.date > fields.Date.context_today(self))
            for move in future_moves:
                if move.auto_post == 'no':
                    move.auto_post = 'at_date'
                msg = _('This move will be posted at the accounting date: %(date)s', date=format_date(self.env, move.date))
                move.message_post(body=msg)
            to_post = self - future_moves
        else:
            to_post = self

        for move in to_post:
            if move.state == 'posted':
                raise UserError(_('The entry %s (id %s) is already posted.') % (move.name, move.id))
            if not move.line_ids.filtered(lambda line: line.display_type not in ('line_section', 'line_note')):
                raise UserError(_('You need to add a line before posting.'))
            if move.auto_post != 'no' and move.date > fields.Date.context_today(self):
                date_msg = move.date.strftime(get_lang(self.env).date_format)
                raise UserError(_("This move is configured to be auto-posted on %s", date_msg))
            if not move.journal_id.active:
                raise UserError(_(
                    "You cannot post an entry in an archived journal (%(journal)s)",
                    journal=move.journal_id.display_name,
                ))
            if move.display_inactive_currency_warning:
                raise UserError(_(
                    "You cannot validate a document with an inactive currency: %s",
                    move.currency_id.name
                ))

            if move.line_ids.account_id.filtered(lambda account: account.deprecated):
                raise UserError(_("A line of this move is using a deprecated account, you cannot post it."))

            affects_tax_report = move._affect_tax_report()
            lock_dates = move._get_violated_lock_dates(move.date, affects_tax_report)
            if lock_dates:
                move.date = move._get_accounting_date(move.invoice_date or move.date, affects_tax_report)

        # Create the analytic lines in batch is faster as it leads to less cache invalidation.
        to_post.line_ids._create_analytic_lines()

        # Trigger copying for recurring invoices
        to_post.filtered(lambda m: m.auto_post not in ('no', 'at_date'))._copy_recurring_entries()

        for invoice in to_post:
            # Fix inconsistencies that may occure if the OCR has been editing the invoice at the same time of a user. We force the
            # partner on the lines to be the same as the one on the move, because that's the only one the user can see/edit.
            wrong_lines = invoice.is_invoice() and invoice.line_ids.filtered(lambda aml:
                aml.partner_id != invoice.commercial_partner_id
                and aml.display_type not in ('line_note', 'line_section')
            )
            if wrong_lines:
                wrong_lines.write({'partner_id': invoice.commercial_partner_id.id})

        to_post.write({
            'state': 'posted',
            'posted_before': True,
        })

        for invoice in to_post:
            invoice.message_subscribe([
                p.id
                for p in [invoice.partner_id]
                if p not in invoice.sudo().message_partner_ids
            ])

            # Compute 'ref' for 'out_invoice'.
            if invoice.move_type == 'out_invoice' and not invoice.payment_reference:
                to_write = {
                    'payment_reference': invoice._get_invoice_computed_reference(),
                    'line_ids': []
                }
                for line in invoice.line_ids.filtered(lambda line: line.account_id.account_type in ('asset_receivable', 'liability_payable')):
                    to_write['line_ids'].append((1, line.id, {'name': to_write['payment_reference']}))
                invoice.write(to_write)

            if (
                invoice.is_sale_document()
                and invoice.journal_id.sale_activity_type_id
                and (invoice.journal_id.sale_activity_user_id or invoice.invoice_user_id).id not in (self.env.ref('base.user_root').id, False)
            ):
                invoice.activity_schedule(
                    date_deadline=min((date for date in invoice.line_ids.mapped('date_maturity') if date), default=invoice.date),
                    activity_type_id=invoice.journal_id.sale_activity_type_id.id,
                    summary=invoice.journal_id.sale_activity_note,
                    user_id=invoice.journal_id.sale_activity_user_id.id or invoice.invoice_user_id.id,
                )

        customer_count, supplier_count = defaultdict(int), defaultdict(int)
        for invoice in to_post:
            if invoice.is_sale_document():
                customer_count[invoice.partner_id] += 1
            elif invoice.is_purchase_document():
                supplier_count[invoice.partner_id] += 1
        for partner, count in customer_count.items():
            (partner | partner.commercial_partner_id)._increase_rank('customer_rank', count)
        for partner, count in supplier_count.items():
            (partner | partner.commercial_partner_id)._increase_rank('supplier_rank', count)

        # Trigger action for paid invoices if amount is zero
        to_post.filtered(
            lambda m: m.is_invoice(include_receipts=True) and m.currency_id.is_zero(m.amount_total)
        )._invoice_paid_hook()

        return to_post

    @api.onchange('l10n_id_tax_number')
    def _onchange_l10n_id_tax_number(self):
        for record in self:
            record.l10n_id_tax_number = record.l10n_id_tax_number
            # print ("Nothing happened")
            # return True
            # if record.l10n_id_tax_number and record.move_type not in self.get_purchase_types():
                # raise UserError(_("You can only change the number manually for a Vendor Bills and Credit Notes"))

    # @api.onchange('amount_untaxed','invoice_line_ids','amount_vat','amount_pph')
    # def _onchange_amount_untaxed(self):
    #     self.amount_tax_editable = self.amount_vat
    #     self.amount_pph_editable = self.amount_pph

    # @api.depends(
    #     'line_ids.matched_debit_ids.debit_move_id.move_id.payment_id.is_matched',
    #     'line_ids.matched_debit_ids.debit_move_id.move_id.line_ids.amount_residual',
    #     'line_ids.matched_debit_ids.debit_move_id.move_id.line_ids.amount_residual_currency',
    #     'line_ids.matched_credit_ids.credit_move_id.move_id.payment_id.is_matched',
    #     'line_ids.matched_credit_ids.credit_move_id.move_id.line_ids.amount_residual',
    #     'line_ids.matched_credit_ids.credit_move_id.move_id.line_ids.amount_residual_currency',
    #     'line_ids.debit',
    #     'line_ids.credit',
    #     'line_ids.currency_id',
    #     'line_ids.amount_currency',
    #     'line_ids.amount_residual',
    #     'line_ids.amount_residual_currency',
    #     'line_ids.payment_id.state',
    #     'line_ids.full_reconcile_id',
    #     'amount_tax_editable',
    #     'amount_pph_editable')
    # def _compute_amount(self):
    #     for move in self:

    #         if move.payment_state == 'invoicing_legacy':
    #             # invoicing_legacy state is set via SQL when setting setting field
    #             # invoicing_switch_threshold (defined in account_accountant).
    #             # The only way of going out of this state is through this setting,
    #             # so we don't recompute it here.
    #             move.payment_state = move.payment_state
    #             continue

    #         total_untaxed = 0.0
    #         total_untaxed_currency = 0.0
    #         total_tax = 0.0
    #         total_tax_currency = 0.0
    #         total_to_pay = 0.0
    #         total_residual = 0.0
    #         total_residual_currency = 0.0
    #         total = 0.0
    #         total_currency = 0.0
    #         currencies = move._get_lines_onchange_currency().currency_id

    #         for line in move.line_ids:
    #             if move.is_invoice(include_receipts=True):
    #                 # === Invoices ===

    #                 if not line.exclude_from_invoice_tab:
    #                     # Untaxed amount.
    #                     total_untaxed += line.balance
    #                     total_untaxed_currency += line.amount_currency
    #                     total += line.balance
    #                     total_currency += line.amount_currency
    #                 elif line.tax_line_id:
    #                     # Tax amount.
    #                     total_tax += line.balance
    #                     total_tax_currency += line.amount_currency
    #                     total += line.balance
    #                     total_currency += line.amount_currency
    #                 elif line.account_id.user_type_id.type in ('receivable', 'payable'):
    #                     # Residual amount.
    #                     total_to_pay += line.balance
    #                     total_residual += line.amount_residual
    #                     total_residual_currency += line.amount_residual_currency
    #             else:
    #                 # === Miscellaneous journal entry ===
    #                 if line.debit:
    #                     total += line.balance
    #                     total_currency += line.amount_currency

    #         if move.move_type == 'entry' or move.is_outbound():
    #             sign = 1
    #         else:
    #             sign = -1

    #         total_tax = move.amount_tax_editable + move.amount_pph_editable
    #         move.amount_untaxed = sign * (total_untaxed_currency if len(currencies) == 1 else total_untaxed)
    #         # move.amount_tax = sign * (total_tax_currency if len(currencies) == 1 else total_tax)
    #         move.amount_tax = move.amount_tax_editable + move.amount_pph_editable
    #         move.amount_total = sign * (total_currency if len(currencies) == 1 else total)
    #         move.amount_residual = -sign * (total_residual_currency if len(currencies) == 1 else total_residual)
    #         move.amount_untaxed_signed = -total_untaxed
    #         move.amount_tax_signed = -total_tax
    #         move.amount_total_signed = abs(total) if move.move_type == 'entry' else -total
    #         move.amount_residual_signed = total_residual

    #         currency = len(currencies) == 1 and currencies or move.company_id.currency_id

    #         # Compute 'payment_state'.
    #         new_pmt_state = 'not_paid' if move.move_type != 'entry' else False

    #         if move.is_invoice(include_receipts=True) and move.state == 'posted':

    #             if currency.is_zero(move.amount_residual):
    #                 reconciled_payments = move._get_reconciled_payments()
    #                 if not reconciled_payments or all(payment.is_matched for payment in reconciled_payments):
    #                     new_pmt_state = 'paid'
    #                 else:
    #                     new_pmt_state = move._get_invoice_in_payment_state()
    #             elif currency.compare_amounts(total_to_pay, total_residual) != 0:
    #                 new_pmt_state = 'partial'

    #         if new_pmt_state == 'paid' and move.move_type in ('in_invoice', 'out_invoice', 'entry'):
    #             reverse_type = move.move_type == 'in_invoice' and 'in_refund' or move.move_type == 'out_invoice' and 'out_refund' or 'entry'
    #             reverse_moves = self.env['account.move'].search([('reversed_entry_id', '=', move.id), ('state', '=', 'posted'), ('move_type', '=', reverse_type)])

    #             # We only set 'reversed' state in cas of 1 to 1 full reconciliation with a reverse entry; otherwise, we use the regular 'paid' state
    #             reverse_moves_full_recs = reverse_moves.mapped('line_ids.full_reconcile_id')
    #             if reverse_moves_full_recs.mapped('reconciled_line_ids.move_id').filtered(lambda x: x not in (reverse_moves + reverse_moves_full_recs.mapped('exchange_move_id'))) == move:
    #                 new_pmt_state = 'reversed'

    #         move.payment_state = new_pmt_state

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        self = self.with_company(self.journal_id.company_id)

        warning = {}
        if self.partner_id:
            rec_account = self.partner_id.property_account_receivable_id
            pay_account = self.partner_id.property_account_payable_id
            if not rec_account and not pay_account:
                action = self.env.ref('account.action_account_config')
                msg = _('Cannot find a chart of accounts for this company, You should configure it. \nPlease go to Account Configuration.')
                raise RedirectWarning(msg, action.id, _('Go to the configuration panel'))
            p = self.partner_id
            if p.invoice_warn == 'no-message' and p.parent_id:
                p = p.parent_id
            if p.invoice_warn and p.invoice_warn != 'no-message':
                # Block if partner only has warning but parent company is blocked
                if p.invoice_warn != 'block' and p.parent_id and p.parent_id.invoice_warn == 'block':
                    p = p.parent_id
                warning = {
                    'title': _("Warning for %s", p.name),
                    'message': p.invoice_warn_msg
                }
                if p.invoice_warn == 'block':
                    self.partner_id = False
                    return {'warning': warning}

        if self.is_sale_document(include_receipts=True) and self.partner_id:
            self.invoice_payment_term_id = self.partner_id.property_payment_term_id or self.invoice_payment_term_id
            new_term_account = self.partner_id.commercial_partner_id.property_account_receivable_id
            self.narration = self.company_id.with_context(lang=self.partner_id.lang or self.env.lang).invoice_terms
        elif self.is_purchase_document(include_receipts=True) and self.partner_id:
            self.invoice_payment_term_id = self.partner_id.property_supplier_payment_term_id or self.invoice_payment_term_id
            new_term_account = self.partner_id.commercial_partner_id.property_account_payable_id
        else:
            new_term_account = None

        # for line in self.line_ids:
        #     line.partner_id = self.partner_id.commercial_partner_id

        #     if new_term_account and line.account_id.user_type_id.type in ('receivable', 'payable'):
        #         line.account_id = new_term_account

        self._compute_bank_partner_id()

        # Find the new fiscal position.
        # delivery_partner_id = self._get_invoice_delivery_partner_id()
        # self.fiscal_position_id = self.env['account.fiscal.position'].get_fiscal_position(
        #     self.partner_id.id, delivery_id=delivery_partner_id)
        # self._recompute_dynamic_lines()

        # additional
        self.attention = self.partner_id.attention
        self.attention_title = self.partner_id.attention_title
        self.invoice_user_id = self.partner_id.user_id.id
        
        if warning:
            return {'warning': warning}

    @api.depends('amount_vat', 'amount_untaxed')
    def _get_amount_before_pph(self):
        for res in self:
            res.amount_before_pph = res.amount_untaxed + res.amount_vat

    @api.depends('invoice_line_ids.price_unit')
    def _get_amount_asi(self):
        for res in self:
            amount_vat = amount_pph = 0
            for line in res.invoice_line_ids:
                if line.tax_ids:
                    for tax in line.tax_ids:
                        if tax.tax_group == 'VAT':
                            amount_vat += (line.price_subtotal * tax.amount / 100)
                        elif tax.tax_group == 'PPh':
                            amount_pph += (line.price_subtotal * tax.amount / 100)

            res.amount_vat = amount_vat
            res.amount_pph = amount_pph
            
    # @api.onchange('amount_tax','amount_untaxed','amount_vat','amount_pph','line_ids.price_unit')
    # def _onchange_amount_vat_pph(self):
    #     self.amount_tax_editable = self.amount_vat
    #     self.amount_pph_editable = self.amount_pph

class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    qty_done = fields.Float(string='Quantity', default=1, digits='Product Unit of Measure', copy=False)

class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'

    product_owner = fields.Selection([('IT','IT'),('Facility','Facility')], string="Product Owner")

class StockPicking(models.Model):
    _inherit = 'stock.picking'
    _order = 'name desc'

    product_owner = fields.Selection([('IT','IT'),('Facility','Facility')], string="Product Owner")
    is_received = fields.Boolean('Received', copy=False)
    received_date = fields.Datetime('Received Date', tracking=True, index=True, copy=False)
    nama_peminjam = fields.Char('Nama Penerima', copy=False)
    tanggal_peminjaman = fields.Date('Tanggal Peminjaman', default=fields.Date.today())
    rencana_pengembalian = fields.Date('Rencana Pengembalian', default=fields.Date.today())
    product_name_string = fields.Text(compute="_get_product_name_string", string='Products')

    # def button_validate(self):
    #     super(StockPicking, self).button_validate()
    #     # print ("test email")
    #     mail_to = self.partner_id.email
    #     data_template = self.env.ref('v16_asi.mail_template_internal_transfer_receive')
    #     template = self.env['mail.template'].browse(data_template.id)
    #     email_values = {'email_to': mail_to}
    #     template.send_mail(self.id, force_send=True, email_values=email_values)                

    @api.depends('move_ids_without_package')
    def _get_product_name_string(self):
        for res in self:
            product_name_string = ''
            if res.move_ids_without_package:
                for move in res.move_ids_without_package:
                    if not product_name_string:
                        product_name_string += move.product_id.name + ', '
                    elif product_name_string:
                        product_name_string += move.product_id.name
            res.product_name_string = product_name_string

    def action_receive(self):
        for res in self:
            res.write({
                'is_received' : True,
                'received_date' : fields.Datetime.now()
            })

    def action_undo_receive(self):
        for res in self:
            res.write({
                'is_received' : False,
                'received_date' : False
            })

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    product_owner = fields.Selection([('IT','IT'),('Facility','Facility')], string="Product Owner")
    asset_location_id = fields.Many2one('stock.location', 'Asset Location')
    owner_id = fields.Many2one('res.users', 'User')
    warranty_start_date = fields.Date('Warranty Start')
    warranty_end_date = fields.Date('Warranty End')
    assigned_product_ids = fields.Many2many('product.product', 'product_template_product_rel',
        'product_tmpl_id', 'product_id', string='Used on Products')
    integrity = fields.Integer('Integrity')
    availability = fields.Integer('Availability')
    confidentiality = fields.Integer('Confidentiality')
    critical_status = fields.Char(compute="_get_critical", string='Critical Status')
    purchase_request_id = fields.Many2one('purchase.request', 'Purchase Request')
    tanggal_pembelian = fields.Date('Tanggal Pembelian')
    tanggal_perolehan = fields.Date('Tanggal Perolehan')
    tanggal_serah_terima = fields.Date('Tanggal Serah Terima')

    @api.depends('integrity','availability','confidentiality')
    def _get_critical(self):
        for res in self:
            critical_status = 'Non-Critical'
            total = (res.integrity + res.availability + res.confidentiality) / 3
            if total > 1:
                critical_status = 'Critical'
                
            res.critical_status = critical_status                

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'
    _order = 'name desc'
    
    @api.depends('order_line.price_total', 'amount_discount', 'amount_pph_editable', 'amount_tax_editable', 'amount_discount_percent')
    def _amount_all(self):
        for order in self:
            amount_untaxed = amount_tax = 0.0
            for line in order.order_line:
                line._compute_amount()
                amount_untaxed += line.price_subtotal
                amount_tax += line.price_tax
            
            currency = order.currency_id or order.partner_id.property_purchase_currency_id or self.env.company.currency_id
            
            discount = order.amount_discount
            if order.amount_discount_percent > 0:
                discount = amount_untaxed * order.amount_discount_percent / 100

            order.update({
                'amount_untaxed': currency.round(amount_untaxed),
                'amount_tax': currency.round(amount_tax),
                'amount_total': amount_untaxed + order.amount_tax_editable + order.amount_pph_editable - discount,
            })

    is_service = fields.Boolean('Service', default=False)
    agreement_number = fields.Char('Agreement Number')
    agreement_date = fields.Date('Agreement Exp Date')
    approver1_id = fields.Many2one('res.users', 'Approver 1')
    approver2_id = fields.Many2one('res.users', 'Approver 2')
    is_receipt = fields.Boolean('Receipt')
    is_invoice = fields.Boolean('Invoice')
    is_faktur_pajak = fields.Boolean('Faktur Pajak')
    is_delivery = fields.Boolean('Delivery Order')
    purchase_flow = fields.Selection([('Create PO','Create PO'),('Direct to Finance','Direct to Finance')]
        , default='Create PO', string='Flow Purchasing')

    amount_tax_editable = fields.Monetary(string='VAT (Editable)')
    amount_pph_editable = fields.Monetary(string='PPh (Editable)')    
    amount_discount = fields.Monetary('Discount')
    amount_discount_percent = fields.Float('Discount (%)')
    request_id = fields.Many2one('purchase.request', 'Purchase Request #')

    @api.onchange('amount_tax')
    def _onchange_amount_tax(self):
        self.amount_tax_editable = self.amount_tax

    @api.depends('order_line.date_planned')
    def _compute_date_planned(self):
        """ date_planned = the earliest date_planned across all order lines. """
        for order in self:
            dates_list = order.order_line.filtered(lambda x: not x.display_type and x.date_planned).mapped('date_planned')
            if dates_list:
                order.date_planned = min(dates_list)
            else:
                order.date_planned = False

    def button_cancel(self):
        # for order in self:
        #     for inv in order.invoice_ids:
        #         if inv and inv.state not in ('cancel', 'draft'):
        #             raise UserError(_("Unable to cancel this purchase order. You must first cancel the related vendor bills."))

        self.write({'state': 'cancel', 'mail_reminder_confirmed': False})
