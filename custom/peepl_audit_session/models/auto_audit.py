# -*- coding: utf-8 -*-


import json
import logging
from datetime import datetime
from odoo import models, api, fields
from odoo.http import request
try:
    from user_agents import parse as parse_ua
    USER_AGENTS_AVAILABLE = True
except ImportError:
    USER_AGENTS_AVAILABLE = False

_logger = logging.getLogger(__name__)


class BaseModelOptimized(models.AbstractModel):
    """Optimized BaseModel extension with minimal performance impact"""
    _inherit = 'base'

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
    
    def read(self, fields=None, load='_classic_read'):
        """Override read with performance optimization"""
        # Execute the read first
        result = super().read(fields, load)
        
        # Only audit if read logging is enabled and conditions are met
        if self._should_audit_operation('read'):
            try:
                session_id = self._get_current_session_id()
                # Log read operation for each record
                for record in self:
                    self._create_audit_log('read', record.id, session_id=session_id)
            except Exception as e:
                _logger.debug(f"Audit logging failed for read {self._name}: {e}")
                    
        return result

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
        """Override unlink with enhanced data capture for better audit trails"""
        records_info = []
        if self._should_audit_operation('unlink'):
            try:
                session_id = self._get_current_session_id()
                for record in self:
                    # ENHANCED: Capture all important field data before deletion
                    old_values = {}
                    try:
                        # Get all readable fields from the record
                        for field_name, field in record._fields.items():
                            # Skip fields that can't be read or aren't useful for audit
                            if (field.store and 
                                not field.compute and 
                                field_name not in ['__last_update', 'create_uid', 'create_date', 'write_uid', 'write_date']):
                                try:
                                    value = getattr(record, field_name, None)
                                    if value is not None:
                                        old_values[field_name] = value
                                except Exception:
                                    # Skip fields that can't be read
                                    continue
                    except Exception as e:
                        _logger.debug(f"Failed to capture complete record data: {e}")
                        # Fallback: capture basic fields
                        try:
                            old_values = {
                                'id': record.id,
                                'display_name': getattr(record, 'display_name', f"ID: {record.id}")
                            }
                            # Try to get name field if it exists
                            if hasattr(record, 'name'):
                                old_values['name'] = getattr(record, 'name', '')
                        except Exception:
                            old_values = {'id': record.id}
                    
                    records_info.append({
                        'id': record.id,
                        'name': getattr(record, 'display_name', f"ID: {record.id}"),
                        'session_id': session_id,
                        'old_values': old_values
                    })
            except Exception as e:
                _logger.debug(f"Audit preparation failed for unlink {self._name}: {e}")
        
        result = super().unlink()
        
        # Log after successful unlink with captured data
        if records_info:
            try:
                for record_info in records_info:
                    self._create_audit_log(
                        'unlink', 
                        record_info['id'], 
                        old_values=record_info['old_values'],  # Pass the captured data
                        session_id=record_info['session_id']
                    )
            except Exception as e:
                _logger.debug(f"Audit logging failed for unlink {self._name}: {e}")
                    
        return result

    def _get_current_session_id(self):
        """FIXED: Get current session ID with better session detection and creation"""
        try:
            # Check if we have request context
            if not request or not hasattr(request, 'session'):
                _logger.debug("AUDIT_SESSION - No request or session context available")
                return None
                
            session_sid = getattr(request.session, 'sid', None)
            user_id = self.env.user.id
            
            _logger.debug(f"AUDIT_SESSION - Looking for session: SID={session_sid}, User={user_id}")
            
            if not session_sid or not user_id:
                _logger.warning(f"AUDIT_SESSION - Missing SID ({session_sid}) or user_id ({user_id})")
                return None
            
            # STEP 1: Look for exact match (preferred)
            session = self.env['audit.session'].sudo().search([
                ('session_id', '=', session_sid),
                ('user_id', '=', user_id),
                ('status', '=', 'active')
            ], limit=1)
            
            if session:
                _logger.debug(f"AUDIT_SESSION - Found exact match: {session.id}")
                # Update last activity
                try:
                    session.sudo().write({'last_activity': fields.Datetime.now()})
                except:
                    pass  # Don't fail if update fails
                return session.id
            
            # STEP 2: Look for any active session for this user
            user_sessions = self.env['audit.session'].sudo().search([
                ('user_id', '=', user_id),
                ('status', '=', 'active')
            ])
            
            _logger.info(f"AUDIT_SESSION - Found {len(user_sessions)} active sessions for user {user_id}")
            
            if user_sessions:
                # Use the most recent one and update its session ID
                latest_session = user_sessions.sorted('login_time', reverse=True)[0]
                _logger.info(f"AUDIT_SESSION - Using latest session {latest_session.id}, updating SID to {session_sid}")
                
                try:
                    latest_session.sudo().write({
                        'session_id': session_sid,
                        'last_activity': fields.Datetime.now()
                    })
                    return latest_session.id
                except Exception as e:
                    _logger.warning(f"AUDIT_SESSION - Failed to update session SID: {e}")
                    return latest_session.id
            
            # STEP 3: Create emergency session if none found
            _logger.warning(f"AUDIT_SESSION - No active session found, creating emergency session for user {user_id}")
            
            try:
                # Try to extract real values from request headers if available

                device_type = 'unknown'
                browser = 'Unknown'
                os_name = 'Unknown'
                ip_address = 'unknown'
                user_agent_str = None

                if request and hasattr(request, 'httprequest'):
                    httpreq = request.httprequest
                    # IP address: prefer X-Forwarded-For, fallback to remote_addr
                    ip_address = httpreq.headers.get('X-Forwarded-For')
                    if ip_address:
                        # X-Forwarded-For can be a comma-separated list, take the first
                        ip_address = ip_address.split(',')[0].strip()
                    else:
                        ip_address = httpreq.remote_addr or 'unknown'

                    # User-Agent
                    user_agent_str = httpreq.headers.get('User-Agent', None)
                    if user_agent_str and USER_AGENTS_AVAILABLE:
                        try:
                            ua = parse_ua(user_agent_str)
                            # Device type
                            if ua.is_mobile:
                                device_type = 'mobile'
                            elif ua.is_tablet:
                                device_type = 'tablet'
                            elif ua.is_pc:
                                device_type = 'desktop'
                            else:
                                device_type = 'unknown'
                            # Browser
                            browser = ua.browser.family or 'Unknown'
                            # OS
                            os_name = ua.os.family or 'Unknown'
                        except Exception as e:
                            _logger.debug(f"AUDIT_SESSION - Failed to parse user agent: {e}")
                            browser = user_agent_str[:50] if user_agent_str else 'Unknown'
                    elif user_agent_str:
                        # user_agents not available, fallback to raw string
                        browser = user_agent_str[:50]

                # Fallbacks if still unknown or empty
                if not ip_address or ip_address.lower() == 'unknown':
                    ip_address = 'unknown'
                if not browser or browser.lower() == 'unknown':
                    browser = 'Unknown'
                if not os_name or os_name.lower() == 'unknown':
                    os_name = 'Unknown'
                if not device_type or device_type.lower() == 'unknown':
                    device_type = 'unknown'

                emergency_session = self.env['audit.session'].sudo().create({
                    'user_id': user_id,
                    'session_id': session_sid,
                    'login_time': fields.Datetime.now(),
                    'last_activity': fields.Datetime.now(),
                    'status': 'active',
                    'device_type': device_type,
                    'browser': browser,
                    'os': os_name,
                    'ip_address': ip_address,
                    'browser_closed': False,
                    'error_message': 'Emergency session created during CRUD operation'
                })

                _logger.warning(f"AUDIT_SESSION - Created emergency session {emergency_session.id}")
                return emergency_session.id
                
            except Exception as e:
                _logger.error(f"AUDIT_SESSION - Failed to create emergency session: {e}")
                return None
                
        except Exception as e:
            _logger.error(f"AUDIT_SESSION - Critical error: {e}")
            return None

    # Rest of the methods remain the same but with enhanced logging
    def _should_audit_operation(self, operation):
        """Enhanced audit check with session verification, supporting multiple configs"""
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
        # Skip if no user context
        if not self.env.user:
            return False

        # Get all active configs
        try:
            configs = self.env['audit.config'].sudo().search([('active', '=', True)])
        except Exception:
            return False
        if not configs:
            return False

        # If any config allows auditing, return True
        for config in configs:
            # Master switch check
            if not config.enable_auditing:
                continue
            # Quick operation check
            if operation == 'read' and not config.log_read:
                continue
            elif operation == 'write' and not config.log_write:
                continue
            elif operation == 'create' and not config.log_create:
                continue
            elif operation == 'unlink' and not config.log_unlink:
                continue
            # Quick user check
            if not config.all_users:
                user_cache_key = f'_audit_users_cache_{config.id}'
                if not hasattr(self.env, user_cache_key):
                    try:
                        audit_users = set(config.user_ids.mapped('user_id.id'))
                        setattr(self.env, user_cache_key, audit_users)
                    except Exception:
                        continue
                audit_users = getattr(self.env, user_cache_key)
                if self.env.user.id not in audit_users:
                    continue
            else:
                # Skip public user unless explicitly configured
                if self.env.user.id == 2:
                    continue
            # Quick model check
            if not config.all_objects:
                model_cache_key = f'_audit_models_cache_{config.id}'
                if not hasattr(self.env, model_cache_key):
                    try:
                        audit_models = set(config.object_ids.mapped('model_id.model'))
                        setattr(self.env, model_cache_key, audit_models)
                    except Exception:
                        continue
                audit_models = getattr(self.env, model_cache_key)
                if self._name not in audit_models:
                    continue
            # If all checks pass for this config, audit is enabled
            return True
        # If no config allows auditing, return False
        return False

    def _create_audit_log(self, action_type, res_id, old_values=None, new_values=None, session_id=None):
        """Enhanced audit log creation with better session handling"""
        try:
            user_id = self.env.user.id
            _logger.debug(f"AUDIT LOG - {action_type} on {self._name}({res_id}) by user {user_id}")
            
            # If no session_id, try to get one (this will create emergency session if needed)
            if not session_id:
                session_id = self._get_current_session_id()
                _logger.debug(f"AUDIT LOG - Retrieved/created session_id: {session_id}")
            
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
            
            # Add session if available
            if session_id:
                audit_vals['session_id'] = session_id
            else:
                _logger.warning(f"AUDIT LOG - No session available for {action_type} on {self._name}({res_id})")
            
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
            
            # Enhanced value processing
            if old_values:
                try:
                    processed_old = self._process_values_for_audit(old_values, res_id)
                    audit_vals['old_values'] = json.dumps(processed_old, default=str)
                except Exception as e:
                    _logger.warning(f"Error processing old values: {e}")
                    audit_vals['old_values'] = json.dumps(old_values, default=str)
                    
            if new_values:
                try:
                    processed_new = self._process_values_for_audit(new_values, res_id)
                    audit_vals['new_values'] = json.dumps(processed_new, default=str)
                except Exception as e:
                    _logger.warning(f"Error processing new values: {e}")
                    audit_vals['new_values'] = json.dumps(new_values, default=str)
                    
            # Create log entry
            log_entry = self.env['audit.log.entry'].sudo().create(audit_vals)
            _logger.debug(f"AUDIT LOG SUCCESS - Created log {log_entry.id} for {action_type} on {self._name}({res_id})")
            
            return log_entry
                
        except Exception as e:
            _logger.error(f"AUDIT LOG CRITICAL FAILURE - {action_type} on {self._name}({res_id}): {e}")


    def _process_values_for_audit(self, values, res_id=None):
        """Process values to make them more suitable for human-readable formatting"""
        if not values or not isinstance(values, dict):
            return values
        
        processed = {}
        
        for field_name, value in values.items():
            try:
                # Skip if field doesn't exist in model
                if field_name not in self._fields:
                    processed[field_name] = value
                    continue
                
                field = self._fields[field_name]
                processed_value = self._process_single_field_value(field, value, res_id)
                processed[field_name] = processed_value
                
            except Exception as e:
                # Fallback to original value if processing fails
                processed[field_name] = value
                _logger.debug(f"Failed to process field {field_name}: {e}")
        
        return processed

    def _process_single_field_value(self, field, value, res_id=None):
        """Process a single field value for better audit formatting"""
        try:
            if field.type == 'many2one':
                # Convert many2one ID to [id, name] format for better readability
                if isinstance(value, int) and value:
                    try:
                        related_record = self.env[field.comodel_name].sudo().browse(value)
                        if related_record.exists():
                            return [value, related_record.display_name]
                        else:
                            return [value, f"(deleted {field.comodel_name})"]
                    except:
                        return value
                return value
            
            elif field.type in ['one2many', 'many2many']:
                # Keep list format but ensure it's a proper list
                if isinstance(value, (list, tuple)):
                    return list(value)
                return value
            
            elif field.type == 'selection':
                # Keep original value - will be formatted in display
                return value
            
            elif field.type in ['date', 'datetime']:
                # Ensure consistent date format
                if value:
                    try:
                        if field.type == 'datetime':
                            # Convert to string format that's easily parseable
                            dt = fields.Datetime.to_datetime(value)
                            return dt.strftime('%Y-%m-%d %H:%M:%S')
                        elif field.type == 'date':
                            dt = fields.Date.to_date(value)
                            return dt.strftime('%Y-%m-%d')
                    except:
                        pass
                return value
            
            elif field.type in ['float', 'monetary']:
                # Ensure numeric values are properly formatted
                if value is not None:
                    try:
                        return float(value)
                    except:
                        pass
                return value
            
            elif field.type == 'text':
                # Truncate very long text for storage efficiency
                if isinstance(value, str) and len(value) > 1000:
                    return value[:1000] + '... (truncated)'
                return value
            
            else:
                # Default: return as-is
                return value
                
        except Exception as e:
            # Fallback to original value
            return value