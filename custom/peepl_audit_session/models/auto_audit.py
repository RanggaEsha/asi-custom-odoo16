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
            
        # PERFORMANCE: Cache config check with better cache key
        cache_key = f'_audit_config_cache_{self.env.user.id}'
        if not hasattr(self.env, cache_key):
            try:
                config = self.env['audit.config'].sudo().search([('active', '=', True)], limit=1)
                setattr(self.env, cache_key, config)
            except Exception:
                setattr(self.env, cache_key, None)
                return False
        
        config = getattr(self.env, cache_key)
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
            user_cache_key = f'_audit_users_cache_{config.id}'
            if not hasattr(self.env, user_cache_key):
                try:
                    audit_users = set(config.user_ids.mapped('user_id.id'))
                    setattr(self.env, user_cache_key, audit_users)
                except Exception:
                    return False
            audit_users = getattr(self.env, user_cache_key)
            if self.env.user.id not in audit_users:
                return False
                
        # Quick model check
        if not config.all_objects:
            model_cache_key = f'_audit_models_cache_{config.id}'
            if not hasattr(self.env, model_cache_key):
                try:
                    audit_models = set(config.object_ids.mapped('model_id.model'))
                    setattr(self.env, model_cache_key, audit_models)
                except Exception:
                    return False
            audit_models = getattr(self.env, model_cache_key)
            if self._name not in audit_models:
                return False
                
        return True

    @api.model_create_multi  
    def create(self, vals_list):
        """Override create with performance optimization"""
        records = super().create(vals_list)
        
        if self._should_audit_operation('create'):
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
            
        old_values_by_record = {}
        if self._should_audit_operation('write'):
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
        records_info = []
        if self._should_audit_operation('unlink'):
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

    def _get_current_session_id(self):
        """ROBUST: Get current session ID with fallback session creation"""
        try:
            if not request or not hasattr(request, 'session'):
                _logger.debug("No request or session context available")
                return None
                
            session_sid = getattr(request.session, 'sid', None)
            user_id = self.env.user.id
            
            # Debug logging
            _logger.info(f"SESSION LOOKUP - SID: {session_sid}, User ID: {user_id}")
            
            if not session_sid or not user_id:
                _logger.warning(f"Missing session_sid ({session_sid}) or user_id ({user_id})")
                return None
            
            # STEP 1: Look for exact match (preferred)
            session = self.env['audit.session'].sudo().search([
                ('session_id', '=', session_sid),
                ('user_id', '=', user_id),
                ('status', '=', 'active')
            ], limit=1)
            
            if session:
                _logger.info(f"SESSION FOUND - Exact match: {session.id}")
                return session.id
            
            # STEP 2: Look for any active session for this user (session ID might have changed)
            user_sessions = self.env['audit.session'].sudo().search([
                ('user_id', '=', user_id),
                ('status', '=', 'active')
            ])
            
            _logger.warning(f"NO EXACT MATCH - Found {len(user_sessions)} active sessions for user {user_id}")
            
            if user_sessions:
                # Use the most recent active session
                latest_session = user_sessions.sorted('login_time', reverse=True)[0]
                _logger.warning(f"USING LATEST SESSION - {latest_session.id} (SID: {latest_session.session_id})")
                
                # Update the session SID to current one (session might have been regenerated)
                latest_session.sudo().write({'session_id': session_sid})
                return latest_session.id
            
            # STEP 3: FALLBACK - Create emergency session with comprehensive device info
            _logger.error(f"EMERGENCY SESSION CREATION - No active session found for user {user_id}")
            
            # Use the same device extraction method as regular session creation
            session_model = self.env['audit.session']
            request_info = session_model.extract_request_info()
            
            session_values = {
                'user_id': user_id,
                'session_id': session_sid,
                'login_time': fields.Datetime.now(),
                'status': 'active',
                'error_message': 'Emergency session created during action (login hook may have failed)'
            }
            session_values.update(request_info)
            
            emergency_session = self.env['audit.session'].sudo().create(session_values)
            
            # Commit immediately to ensure availability
            self.env.cr.commit()
            _logger.error(f"EMERGENCY SESSION CREATED - {emergency_session.id}")
            return emergency_session.id
                
        except Exception as e:
            _logger.error(f"CRITICAL: Failed to get/create session: {e}")
            return None

    def _create_audit_log(self, action_type, res_id, old_values=None, new_values=None, session_id=None):
        """ROBUST: Create audit log with enhanced error handling"""
        try:
            user_id = self.env.user.id
            _logger.info(f"AUDIT LOG ATTEMPT - {action_type} on {self._name}({res_id}) by user {user_id}")
            
            # If no session_id, try to get one
            if not session_id:
                session_id = self._get_current_session_id()
                _logger.info(f"AUDIT LOG - Retrieved session_id: {session_id}")
            
            # Get model ID (cached per model)
            model_cache_key = f'_model_id_cache_{self._name}'
            if not hasattr(self.env, model_cache_key):
                model = self.env['ir.model'].sudo().search([('model', '=', self._name)], limit=1)
                setattr(self.env, model_cache_key, model.id if model else None)
            
            model_id = getattr(self.env, model_cache_key)
            if not model_id:
                _logger.error(f"AUDIT LOG FAILED - No model found for {self._name}")
                return
            
            # Prepare audit values
            audit_vals = {
                'user_id': user_id,
                'model_id': model_id,
                'res_id': res_id,
                'action_type': action_type,
                'action_date': fields.Datetime.now(),
                'method': action_type,
            }
            
            # Add session if available (but don't fail if missing)
            if session_id:
                audit_vals['session_id'] = session_id
            else:
                _logger.warning(f"AUDIT LOG - No session available for {action_type} on {self._name}({res_id})")
                # Continue without session - better to have partial log than no log
            
            # Get record name for better identification
            try:
                if action_type != 'unlink':
                    record = self.browse(res_id)
                    if record.exists():
                        audit_vals['res_name'] = record.display_name
                    else:
                        audit_vals['res_name'] = f"ID: {res_id} (deleted)"
                else:
                    audit_vals['res_name'] = f"ID: {res_id} (deleted)"
            except Exception as e:
                audit_vals['res_name'] = f"ID: {res_id} (error: {str(e)[:50]})"
            
            # Add values if provided
            if old_values:
                try:
                    audit_vals['old_values'] = json.dumps(old_values, default=str)
                except Exception as e:
                    audit_vals['old_values'] = f"Error serializing: {str(e)}"
                    
            if new_values:
                try:
                    audit_vals['new_values'] = json.dumps(new_values, default=str)
                except Exception as e:
                    audit_vals['new_values'] = f"Error serializing: {str(e)}"
                    
            # Create log entry
            log_entry = self.env['audit.log.entry'].sudo().create(audit_vals)
            _logger.info(f"AUDIT LOG SUCCESS - Created log {log_entry.id} for {action_type} on {self._name}({res_id})")
            
            return log_entry
                
        except Exception as e:
            _logger.error(f"AUDIT LOG CRITICAL FAILURE - {action_type} on {self._name}({res_id}): {e}")
            # Don't re-raise - audit failures shouldn't break business operations