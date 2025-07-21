# -*- coding: utf-8 -*-

import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    log_note_count = fields.Integer(
        string='Log Notes Count',
        compute='_compute_log_note_count',
        store=False
    )

    @api.depends('message_ids', 'message_ids.message_type', 'message_ids.model', 'message_ids.res_id', 'message_ids.subtype_id')
    def _compute_log_note_count(self):
        """Compute the number of all mail.message logs for this partner (all types)"""
        for partner in self:
            count = self.env['mail.message'].search_count([
                ('model', '=', 'res.partner'),
                ('res_id', '=', partner.id),
            ])
            _logger.debug(f"Partner {partner.name} (ID: {partner.id}): {count} log notes found (all types)")
            partner.log_note_count = count

    def action_open_log_note_dashboard(self):
        """Open the log note dashboard for this partner"""
        self.ensure_one()
        
        # Force recompute before opening to ensure fresh count
        self._compute_log_note_count()
        
        # Include all mail.message logs (all types)
        domain = [
            ('model', '=', 'res.partner'),
            ('res_id', '=', self.id),
        ]

        # Get the note subtype for default creation
        note_subtype = self.env.ref('mail.mt_note', raise_if_not_found=False)

        return {
            'type': 'ir.actions.act_window',
            'name': _('Log Notes - %s') % self.display_name,
            'res_model': 'mail.message',
            'view_mode': 'tree,form',
            'target': 'current',
            'domain': domain,
            'context': {
                'default_model': 'res.partner',
                'default_res_id': self.id,
                'default_message_type': 'comment',
                'default_subtype_id': note_subtype.id if note_subtype else False,
                'search_default_group_by_date': 1,
            },
        }

    @api.model
    def recompute_all_log_note_counts(self):
        """Recompute log note counts for all partners - can be called manually"""
        partners = self.with_context(active_test=False).search([])
        partners._compute_log_note_count()
        _logger.info(f"Manually recomputed log note counts for {len(partners)} partners")
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Log note counts updated for %d partners') % len(partners),
                'type': 'success'
            }
        }

    def refresh_log_note_count(self):
        """Refresh log note count for this partner"""
        self.ensure_one()
        self._compute_log_note_count()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Refreshed'),
                'message': _('Log note count refreshed: %d notes found') % self.log_note_count,
                'type': 'info'
            }
        }


class MailMessage(models.Model):
    _inherit = 'mail.message'

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to trigger partner log note count recomputation"""
        messages = super(MailMessage, self).create(vals_list)
        
        # Collect partners that need count updates
        partners_to_update = set()
        for message in messages:
            if message.model == 'res.partner':
                partners_to_update.add(message.res_id)
                _logger.debug(f"Log created for partner {message.res_id}: {message.subtype_id.name if message.subtype_id else 'No subtype'}, type: {message.message_type}")
        
        # Trigger recomputation for affected partners
        if partners_to_update:
            partners = self.env['res.partner'].browse(list(partners_to_update))
            partners._compute_log_note_count()
            _logger.info(f"Recomputed log note counts for {len(partners)} partners after message creation")
        
        return messages

    def unlink(self):
        """Override unlink to trigger partner log note count recomputation"""
        # Store partner info before deletion
        partners_to_update = set()
        for message in self:
            if message.model == 'res.partner':
                partners_to_update.add(message.res_id)
        
        result = super(MailMessage, self).unlink()
        
        # Update partner counts after deletion
        if partners_to_update:
            partners = self.env['res.partner'].browse(list(partners_to_update))
            partners.exists()._compute_log_note_count()
        
        return result

    def write(self, vals):
        """Override write to handle message_type changes"""
        # Store partners that might be affected before the update
        partners_before = set()
        for message in self:
            if message.model == 'res.partner':
                partners_before.add(message.res_id)
        
        result = super(MailMessage, self).write(vals)
        
        # If message_type or model changed, recompute affected partners
        if 'message_type' in vals or 'model' in vals or 'res_id' in vals:
            partners_after = set()
            for message in self:
                if message.model == 'res.partner':
                    partners_after.add(message.res_id)
            
            all_affected_partners = partners_before | partners_after
            if all_affected_partners:
                partners = self.env['res.partner'].browse(list(all_affected_partners))
                partners.exists()._compute_log_note_count()
        
        return result