# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime, timedelta


class AuditClearWizard(models.TransientModel):
    """Wizard to clear audit logs"""
    _name = 'audit.clear.wizard'
    _description = 'Clear Audit Logs Wizard'

    # Clear options
    clear_all = fields.Boolean('Clear All Logs', default=False,
                              help="Clear all audit logs regardless of other filters")
    
    # Date filters
    to_date = fields.Date('Clear Logs Before', 
                         default=lambda self: fields.Date.today() - timedelta(days=30),
                         help="Clear logs before this date")
    
    # Action type filters
    clear_read = fields.Boolean('Clear Read Operations', default=True)
    clear_write = fields.Boolean('Clear Write Operations', default=False) 
    clear_create = fields.Boolean('Clear Create Operations', default=False)
    clear_unlink = fields.Boolean('Clear Delete Operations', default=False)
    
    # Model filter
    model_id = fields.Many2one('ir.model', 'Specific Model',
                              help="Clear logs for specific model only. Leave empty for all models")
    
    # User filter
    user_id = fields.Many2one('res.users', 'Specific User',
                             help="Clear logs for specific user only. Leave empty for all users")
    
    # Session filter
    session_id = fields.Many2one('audit.session', 'Specific Session',
                                help="Clear logs for specific session only. Leave empty for all sessions")
    
    # Results
    preview_count = fields.Integer('Records to Delete', readonly=True)
    is_preview = fields.Boolean('Preview Mode', default=True)

    @api.onchange('clear_all', 'to_date', 'clear_read', 'clear_write', 'clear_create', 
                  'clear_unlink', 'model_id', 'user_id', 'session_id')
    def _onchange_filters(self):
        """Update preview count when filters change"""
        self._compute_preview_count()

    def _compute_preview_count(self):
        """Compute how many records would be deleted"""
        domain = self._build_domain()
        self.preview_count = self.env['audit.log.entry'].search_count(domain)

    def _build_domain(self):
        """Build domain for filtering logs"""
        domain = []
        
        # If clear all is checked, return empty domain (all records)
        if self.clear_all:
            return domain
            
        # Date filter
        if self.to_date:
            domain.append(('action_date', '<', self.to_date))
            
        # Action type filters
        action_types = []
        if self.clear_read:
            action_types.append('read')
        if self.clear_write:
            action_types.append('write') 
        if self.clear_create:
            action_types.append('create')
        if self.clear_unlink:
            action_types.append('unlink')
            
        if action_types:
            domain.append(('action_type', 'in', action_types))
        else:
            # If no action types selected, don't match anything
            domain.append(('id', '=', False))
            
        # Model filter
        if self.model_id:
            domain.append(('model_id', '=', self.model_id.id))
            
        # User filter
        if self.user_id:
            domain.append(('user_id', '=', self.user_id.id))
            
        # Session filter
        if self.session_id:
            domain.append(('session_id', '=', self.session_id.id))
            
        return domain

    def action_preview(self):
        """Preview the logs that would be deleted"""
        self._compute_preview_count()
        self.is_preview = True
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Clear Audit Logs - Preview'),
            'res_model': 'audit.clear.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': self.env.context
        }

    def action_clear_logs(self):
        """Actually clear the logs"""
        if not self.env.user.has_group('peepl_audit_session.group_audit_manager'):
            raise UserError(_("Only Audit Managers can clear logs."))
            
        domain = self._build_domain()
        logs_to_delete = self.env['audit.log.entry'].search(domain)
        count = len(logs_to_delete)
        
        if count == 0:
            raise UserError(_("No logs found matching the specified criteria."))
            
        # Confirm deletion
        if self.is_preview:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Confirm Clear Audit Logs'),
                'res_model': 'audit.clear.wizard',
                'view_mode': 'form', 
                'res_id': self.id,
                'target': 'new',
                'context': dict(self.env.context, confirm_delete=True)
            }
        
        # Perform deletion
        logs_to_delete.unlink()
        
        # Also clear orphaned sessions if requested
        if self.clear_all:
            orphaned_sessions = self.env['audit.session'].search([
                ('log_entry_ids', '=', False)
            ])
            orphaned_sessions.unlink()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('%d audit log entries have been deleted.') % count,
                'type': 'success'
            }
        }

    def action_confirm_clear(self):
        """Confirm and execute the clear operation"""
        self.is_preview = False
        return self.action_clear_logs()

    def action_view_logs(self):
        """View the logs that match current filters"""
        domain = self._build_domain()
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Audit Logs - Filtered'),
            'res_model': 'audit.log.entry',
            'view_mode': 'tree,form',
            'domain': domain,
            'context': {'search_default_group_by_action_type': 1}
        }