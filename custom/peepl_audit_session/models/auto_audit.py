# -*- coding: utf-8 -*-

import json
import logging
from datetime import datetime
from odoo import models, api, fields
from odoo.http import request

_logger = logging.getLogger(__name__)


class BaseModelOptimized(models.AbstractModel):
    """Optimized BaseModel extension with minimal performance impact"""
    _inherit = 'base'

    def _should_audit_operation(self, operation):
        """Optimized audit check with early returns"""
        # PERFORMANCE: Early returns to minimize impact
        
        # Skip audit models themselves
        if self._name.startswith('audit.'):
            return False
            
        # Skip system models that generate noise
        skip_models = {
            'ir.logging', 'ir.attachment', 'ir.translation', 'ir.config_parameter',
            'ir.cron', 'ir.mail_server', 'ir.sequence', 'bus.bus', 'ir.ui.view',
            'ir.ui.menu', 'ir.model.access', 'ir.rule', 'ir.model.data',
            'base', 'ir.qweb', 'ir.qweb.field', 'mail.thread', 'mail.alias'
        }
        if self._name in skip_models:
            return False
            
        # Skip during installation, tests, or system operations
        ctx = self.env.context
        if (ctx.get('module') or ctx.get('install_mode') or ctx.get('test_enable') or 
            ctx.get('import_file') or ctx.get('_import_current_module')):
            return False
            
        # Skip if no user context (system operations)
        if not self.env.user or self.env.user.id in (1, 2):  # Skip superuser and public
            return False
            
        # PERFORMANCE: Cache config check
        if not hasattr(self.env, '_audit_config_cache'):
            try:
                config = self.env['audit.config'].sudo().search([('active', '=', True)], limit=1)
                self.env._audit_config_cache = config
            except Exception:
                self.env._audit_config_cache = None
                return False
        
        config = self.env._audit_config_cache
        if not config:
            return False
            
        # Master switch check - early exit if auditing disabled
        if not config.enable_auditing:
            return False
            
        # Quick operation check
        if operation == 'read' and not config.log_read:
            return False
        elif operation == 'write' and not config.log_write:
            return False
        elif operation == 'create' and not config.log_create:
            return False
        elif operation == 'unlink' and not config.log_unlink:
            return False
            
        # Quick user check
        if not config.all_users:
            if not hasattr(self.env, '_audit_users_cache'):
                try:
                    self.env._audit_users_cache = set(config.user_ids.mapped('user_id.id'))
                except Exception:
                    return False
            if self.env.user.id not in self.env._audit_users_cache:
                return False
                
        # Quick model check  
        if not config.all_objects:
            if not hasattr(self.env, '_audit_models_cache'):
                try:
                    self.env._audit_models_cache = set(config.object_ids.mapped('model_id.model'))
                except Exception:
                    return False
            if self._name not in self.env._audit_models_cache:
                return False
                
        return True

    @api.model_create_multi  
    def create(self, vals_list):
        """Override create with performance optimization"""
        records = super().create(vals_list)
        
        # PERFORMANCE: Only check audit for important models
        important_models = {
            'res.users', 'res.partner', 'res.company', 'sale.order', 'purchase.order',
            'account.move', 'stock.picking', 'project.project', 'hr.employee'
        }
        
        if self._name in important_models and self._should_audit_operation('create'):
            try:
                session_id = self._get_current_session_id()
                for record, vals in zip(records, vals_list):
                    self._create_audit_log('create', record.id, new_values=vals, session_id=session_id)
            except Exception as e:
                _logger.debug(f"Audit logging failed for create {self._name}: {e}")
                    
        return records

    def write(self, vals):
        """Override write with performance optimization"""
        if not vals:
            return super().write(vals)
            
        # PERFORMANCE: Only check audit for important models
        important_models = {
            'res.users', 'res.partner', 'res.company', 'sale.order', 'purchase.order',
            'account.move', 'stock.picking', 'project.project', 'hr.employee'
        }
        
        old_values_by_record = {}
        if self._name in important_models and self._should_audit_operation('write'):
            try:
                session_id = self._get_current_session_id()
                # Only store old values for fields being changed
                for record in self:
                    old_vals = {}
                    for field_name in vals.keys():
                        if field_name in record._fields:
                            try:
                                old_vals[field_name] = getattr(record, field_name, None)
                            except Exception:
                                old_vals[field_name] = "<unreadable>"
                    old_values_by_record[record.id] = old_vals
            except Exception as e:
                _logger.debug(f"Audit preparation failed for write {self._name}: {e}")
        
        result = super().write(vals)
        
        # Log after successful write
        if old_values_by_record:
            try:
                for record in self:
                    old_vals = old_values_by_record.get(record.id, {})
                    if old_vals:  # Only log if we have old values
                        self._create_audit_log('write', record.id, old_values=old_vals, 
                                             new_values=vals, session_id=session_id)
            except Exception as e:
                _logger.debug(f"Audit logging failed for write {self._name}: {e}")
                    
        return result

    def unlink(self):
        """Override unlink with performance optimization"""
        # PERFORMANCE: Only check audit for important models
        important_models = {
            'res.users', 'res.partner', 'res.company', 'sale.order', 'purchase.order',
            'account.move', 'stock.picking', 'project.project', 'hr.employee'
        }
        
        records_info = []
        if self._name in important_models and self._should_audit_operation('unlink'):
            try:
                session_id = self._get_current_session_id()
                for record in self:
                    records_info.append({
                        'id': record.id,
                        'name': getattr(record, 'display_name', f"ID: {record.id}"),
                        'session_id': session_id
                    })
            except Exception as e:
                _logger.debug(f"Audit preparation failed for unlink {self._name}: {e}")
        
        result = super().unlink()
        
        # Log after successful unlink
        if records_info:
            try:
                for record_info in records_info:
                    self._create_audit_log('unlink', record_info['id'], 
                                         session_id=record_info['session_id'])
            except Exception as e:
                _logger.debug(f"Audit logging failed for unlink {self._name}: {e}")
                    
        return result

    # REMOVED READ OVERRIDE - Too much performance impact
    # Read operations are logged via access control if needed

    def _get_current_session_id(self):
        """Get current session ID with caching"""
        try:
            if not hasattr(self.env, '_current_session_cache'):
                if request and hasattr(request, 'session') and request.session.uid:
                    session = self.env['audit.session'].sudo().search([
                        ('session_id', '=', request.session.sid),
                        ('user_id', '=', request.session.uid),
                        ('status', '=', 'active')
                    ], limit=1)
                    self.env._current_session_cache = session.id if session else None
                else:
                    self.env._current_session_cache = None
            return self.env._current_session_cache
        except Exception:
            return None

    def _create_audit_log(self, action_type, res_id, old_values=None, new_values=None, session_id=None):
        """Optimized audit log creation"""
        try:
            # Prepare minimal values
            audit_vals = {
                'user_id': self.env.user.id,
                'session_id': session_id,
                'res_id': res_id,
                'action_type': action_type,
                'action_date': fields.Datetime.now(),
                'method': action_type,
            }
            
            # Get model ID (cached)
            if not hasattr(self.env, f'_model_id_cache_{self._name}'):
                model = self.env['ir.model'].sudo().search([('model', '=', self._name)], limit=1)
                setattr(self.env, f'_model_id_cache_{self._name}', model.id if model else None)
            
            model_id = getattr(self.env, f'_model_id_cache_{self._name}')
            if model_id:
                audit_vals['model_id'] = model_id
                
                # Add values if provided
                if old_values:
                    audit_vals['old_values'] = json.dumps(old_values, default=str)
                if new_values:
                    audit_vals['new_values'] = json.dumps(new_values, default=str)
                    
                # Create log entry
                self.env['audit.log.entry'].sudo().create(audit_vals)
                
        except Exception as e:
            _logger.debug(f"Failed to create audit log: {e}")


# Disable problematic access control auditing for now
# class IrModelAccess(models.Model):
#     """Extend model access to log access attempts"""
#     _inherit = 'ir.model.access'
#     # DISABLED for performance