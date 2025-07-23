# -*- coding: utf-8 -*-

from odoo import models, fields, api
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Documents section fields
    sla = fields.Binary(string='SLA Document', help='Service Level Agreement document')
    sla_filename = fields.Char(string='SLA Filename')
    
    ncif = fields.Binary(string='NCIF Document', help='NCIF document')
    ncif_filename = fields.Char(string='NCIF Filename')
    
    kontrak_kerja = fields.Binary(string='Kontrak Kerja Document', help='Work Contract document')
    kontrak_kerja_filename = fields.Char(string='Kontrak Kerja Filename')
    
    # Description field for documents
    document_description = fields.Text(string='Description', help='Description of the uploaded documents')
    
    # Reminder section fields
    agreement_date = fields.Date(string='Agreement Date', help='Date when the agreement was made')
    select_date = fields.Boolean(string='Select Exact Reminder Date', help='Check to set exact reminder date, uncheck to calculate from agreement date')
    reminder_number = fields.Integer(string='Number', help='Number of days/months/years before agreement date')
    reminder_period = fields.Selection([
        ('days', 'Days'),
        ('months', 'Months'),
        ('years', 'Years')
    ], string='Period', default='days', help='Period type for reminder calculation')
    reminder_date_manual = fields.Date(string='Manual Reminder Date', help='Manually set reminder date (only when select_date is True)')
    reminder_date = fields.Date(string='Reminder Date', compute='_compute_reminder_date', store=True, help='Date when reminder will be sent')
    email_template = fields.Html(string='Email Template', help='Customizable email template for reminder')
    reminder_sent = fields.Boolean(string='Reminder Sent', default=False, help='Track if reminder has been sent')
    reminder_active = fields.Boolean(string='Reminder Active', default=True, help='Enable/disable reminder for this contact')

    @api.depends('agreement_date', 'reminder_number', 'reminder_period', 'select_date', 'reminder_date_manual')
    def _compute_reminder_date(self):
        """Compute reminder date based on agreement date and period settings"""
        for record in self:
            if record.select_date:
                # Use manually set date when select_date is True
                record.reminder_date = record.reminder_date_manual
            elif record.agreement_date and record.reminder_number and record.reminder_period:
                # Calculate date when select_date is False
                agreement_date = record.agreement_date
                
                if record.reminder_period == 'days':
                    record.reminder_date = agreement_date - timedelta(days=record.reminder_number)
                elif record.reminder_period == 'months':
                    record.reminder_date = agreement_date - relativedelta(months=record.reminder_number)
                elif record.reminder_period == 'years':
                    record.reminder_date = agreement_date - relativedelta(years=record.reminder_number)
                else:
                    record.reminder_date = False
            else:
                record.reminder_date = False

    @api.onchange('select_date')
    def _onchange_select_date(self):
        """Reset reminder_sent when changing reminder settings and clear manual date"""
        if self.reminder_sent:
            self.reminder_sent = False
        if not self.select_date:
            self.reminder_date_manual = False

    def send_reminder_notification(self):
        """Send reminder via email and create internal notification"""
        for record in self:
            if not record.reminder_active or record.reminder_sent:
                continue
                
            # Create internal activity/notification
            self.env['mail.activity'].create({
                'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
                'summary': f'Contract Reminder for {record.name}',
                'note': f'Reminder: Agreement date is approaching for {record.name} on {record.agreement_date}',
                'res_id': record.id,
                'res_model_id': self.env.ref('base.model_res_partner').id,
                'user_id': self.env.user.id,
                'date_deadline': fields.Date.today(),
            })
            
            # Send email if template is provided
            if record.email_template and record.email:
                self._send_reminder_email(record)
            
            # Send push notification to web client
            self._send_push_notification(record)
            
            # Mark as sent
            record.reminder_sent = True
            
            # Log the reminder activity
            message = f"<b>🔔 Reminder Sent:</b><br/>• Agreement Date: {record.agreement_date}<br/>• Reminder Date: {record.reminder_date}<br/>• Sent to: {record.email or 'No email'}"
            record.message_post(body=message, message_type='notification')

    def _send_reminder_email(self, record):
        """Send customized email reminder"""
        try:
            # Prepare email template variables
            template_vars = {
                'partner_name': record.name,
                'agreement_date': record.agreement_date,
                'reminder_date': record.reminder_date,
                'company_name': self.env.company.name,
            }
            
            # Replace template variables in email content
            email_body = record.email_template
            for var, value in template_vars.items():
                email_body = email_body.replace(f'{{{{{var}}}}}', str(value or ''))
            
            # Create and send email
            mail_values = {
                'subject': f'Contract Reminder - {record.name}',
                'body_html': email_body,
                'email_to': record.email,
                'email_from': self.env.company.email or self.env.user.email,
                'reply_to': self.env.company.email or self.env.user.email,
            }
            
            mail = self.env['mail.mail'].create(mail_values)
            mail.send()
            
        except Exception as e:
            # Log error but don't break the process
            record.message_post(body=f"<b>❌ Email Error:</b> {str(e)}", message_type='comment')

    def _send_push_notification(self, record):
        """Send push notification to web client"""
        try:
            notification_message = f"Contract reminder for {record.name} - Agreement date: {record.agreement_date}"
            
            # Send notification to all users who can access this partner
            users = self.env['res.users'].search([('groups_id', 'in', [self.env.ref('base.group_user').id])])
            
            for user in users:
                self.env['bus.bus']._sendone(
                    f'res.users/{user.id}',
                    'simple_notification',
                    {
                        'title': 'Contract Reminder',
                        'message': notification_message,
                        'type': 'info',
                        'sticky': False,
                    }
                )
        except Exception as e:
            # Log error but don't break the process
            record.message_post(body=f"<b>❌ Notification Error:</b> {str(e)}", message_type='comment')

    @api.model
    def _cron_check_reminders(self):
        """Cron job to check and send due reminders"""
        today = fields.Date.today()
        
        # Find partners with due reminders
        partners_to_remind = self.search([
            ('reminder_active', '=', True),
            ('reminder_sent', '=', False),
            ('reminder_date', '<=', today),
            ('reminder_date', '!=', False),
        ])
        
        for partner in partners_to_remind:
            partner.send_reminder_notification()

    def reset_reminder(self):
        """Reset reminder status to allow sending again"""
        for record in self:
            record.reminder_sent = False
            message = f"<b>🔄 Reminder Reset:</b><br/>Reminder status has been reset and can be sent again."
            record.message_post(body=message, message_type='notification')
        """Override create to log initial document uploads"""
        record = super(ResPartner, self).create(vals)
        
        # Log initial document uploads
        document_fields = {
            'sla': 'SLA Document',
            'ncif': 'NCIF Document', 
            'kontrak_kerja': 'Kontrak Kerja Document'
        }
        
        upload_logs = []
        for field_name, field_label in document_fields.items():
            if vals.get(field_name):
                filename = vals.get(f'{field_name}_filename', 'Unknown file')
                upload_logs.append(f"• {field_label}: {filename}")
        
        # Log initial description if provided
        if vals.get('document_description'):
            description = vals['document_description']
            preview = description[:50] + '...' if len(description) > 50 else description
            upload_logs.append(f"• Document Description: \"{preview}\"")
        
        if upload_logs:
            message = f"<b>📄 Documents Uploaded:</b><br/>{'<br/>'.join(upload_logs)}"
            record.message_post(body=message, message_type='notification')
        
        return record

    def write(self, vals):
        """Override write to log document changes"""
        document_fields = {
            'sla': 'SLA Document',
            'ncif': 'NCIF Document',
            'kontrak_kerja': 'Kontrak Kerja Document'
        }
        
        # Track changes for each record
        for record in self:
            change_logs = []
            
            # Track document file changes
            for field_name, field_label in document_fields.items():
                if field_name in vals:
                    old_file = getattr(record, field_name)
                    new_file = vals[field_name]
                    old_filename = getattr(record, f'{field_name}_filename') or 'Unknown file'
                    new_filename = vals.get(f'{field_name}_filename', 'Unknown file')
                    
                    # Determine the type of change
                    if not old_file and new_file:
                        # File uploaded
                        change_logs.append(f"• ⬆️ <b>Uploaded</b> {field_label}: {new_filename}")
                    elif old_file and not new_file:
                        # File deleted
                        change_logs.append(f"• 🗑️ <b>Deleted</b> {field_label}: {old_filename}")
                    elif old_file and new_file and old_filename != new_filename:
                        # File replaced
                        change_logs.append(f"• 🔄 <b>Replaced</b> {field_label}: {old_filename} → {new_filename}")
                    elif old_file and new_file:
                        # File updated (same name but different content)
                        change_logs.append(f"• ✏️ <b>Updated</b> {field_label}: {new_filename}")
            
            # Track description changes
            if 'document_description' in vals:
                old_description = record.document_description or ''
                new_description = vals['document_description'] or ''
                
                if not old_description and new_description:
                    # Description added
                    preview = new_description[:50] + '...' if len(new_description) > 50 else new_description
                    change_logs.append(f"• ➕ <b>Added</b> Document Description: \"{preview}\"")
                elif old_description and not new_description:
                    # Description removed
                    preview = old_description[:50] + '...' if len(old_description) > 50 else old_description
                    change_logs.append(f"• ➖ <b>Removed</b> Document Description: \"{preview}\"")
                elif old_description != new_description:
                    # Description updated
                    new_preview = new_description[:50] + '...' if len(new_description) > 50 else new_description
                    change_logs.append(f"• ✏️ <b>Updated</b> Document Description: \"{new_preview}\"")
            
            # Post log message if there are changes
            if change_logs:
                user_name = self.env.user.name
                message = f"<b>📝 Document Changes by {user_name}:</b><br/>{'<br/>'.join(change_logs)}"
                record.message_post(body=message, message_type='notification')
        
        return super(ResPartner, self).write(vals)