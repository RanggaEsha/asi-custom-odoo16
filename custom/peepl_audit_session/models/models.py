# -*- coding: utf-8 -*-

import json
import logging
import requests
from datetime import datetime, timedelta
from user_agents import parse
from odoo import models, fields, api, _, exceptions
from odoo.http import request
from odoo.tools import config

_logger = logging.getLogger(__name__)


class AuditConfig(models.Model):
    """Audit Configuration Model"""
    _name = 'audit.config'
    _description = 'Audit Configuration'
    _order = 'name desc'

    name = fields.Char('Configuration Name', required=True)
    active = fields.Boolean('Active', default=True)
    
    # Performance control
    enable_auditing = fields.Boolean('Enable Auditing', default=True, 
                                   help="Master switch to completely disable auditing for performance")
    
    # Operation toggles
    log_read = fields.Boolean('Log Read Operations', default=False)
    log_write = fields.Boolean('Log Write Operations', default=True)
    log_create = fields.Boolean('Log Create Operations', default=True)
    log_unlink = fields.Boolean('Log Delete Operations', default=True)
    
    # User configuration
    all_users = fields.Boolean('Audit All Users', default=True)
    user_ids = fields.One2many('audit.config.user', 'config_id', string='Specific Users')
    
    # Object configuration  
    all_objects = fields.Boolean('Audit All Models', default=False)
    object_ids = fields.One2many('audit.config.object', 'config_id', string='Specific Models')
    
    # Additional settings
    auto_cleanup_days = fields.Integer('Auto Cleanup After (Days)', default=90, 
                                     help="Automatically delete logs older than specified days. 0 = No auto cleanup")
    session_timeout_hours = fields.Integer('Session Timeout (Hours)', default=24,
                                         help="Mark sessions as expired after specified hours")

    @api.onchange('all_users')
    def _onchange_all_users(self):
        if self.all_users:
            self.user_ids = [(5, 0, 0)]  # Clear specific users

    @api.onchange('all_objects')  
    def _onchange_all_objects(self):
        if self.all_objects:
            self.object_ids = [(5, 0, 0)]  # Clear specific models

    def get_active_config(self):
        """Get the active audit configuration with performance optimization"""
        try:
            # Check if we're in module installation/upgrade mode
            if self.env.context.get('module') or self.env.context.get('install_mode'):
                return None
            # Performance: Cache the result in env context
            if not hasattr(self.env, '_audit_config_cache'):
                # Check if the table exists (safety check during installation)
                self.env.cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'audit_config' LIMIT 1")
                if not self.env.cr.fetchone():
                    self.env._audit_config_cache = None
                    return None
                config = self.search([('active', '=', True)], limit=1)
                self.env._audit_config_cache = config
            return self.env._audit_config_cache
        except Exception:
            # During installation, the table might not exist yet
            return None

    def should_audit_user(self, user_id):
        """Check if user should be audited"""
        try:
            if self.all_users:
                return True
            return user_id in self.user_ids.mapped('user_id.id')
        except Exception:
            return False

    def should_audit_model(self, model_name):
        """Check if model should be audited"""
        try:
            if self.all_objects:
                return True
            return model_name in self.object_ids.mapped('model_id.model')
        except Exception:
            return False
        
    def action_clear_audit_cache(self):
        """Manual action to clear all audit caches - useful for debugging"""
        # Clear all possible audit caches
        cache_keys_to_clear = ['_audit_config_cache']
        
        # Add specific caches for all configs
        all_configs = self.env['audit.config'].search([])
        for config in all_configs:
            cache_keys_to_clear.extend([
                f'_audit_users_cache_{config.id}',
                f'_audit_models_cache_{config.id}',
                f'_audit_config_cache_{config.id}'
            ])
        
        cleared_count = 0
        for cache_key in cache_keys_to_clear:
            if hasattr(self.env, cache_key):
                delattr(self.env, cache_key)
                cleared_count += 1
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Cache Cleared',
                'message': f'Cleared {cleared_count} audit cache entries. Configuration changes will now take effect.',
                'type': 'success'
            }
        }

    def get_audit_debug_info(self):
        """Get debug information about current audit configuration"""
        debug_info = {
            'config_active': self.active,
            'enable_auditing': self.enable_auditing,
            'all_users': self.all_users,
            'all_objects': self.all_objects,
            'audit_users': [],
            'audit_models': [],
            'current_user_audited': False,
        }
        
        if not self.all_users:
            debug_info['audit_users'] = [
                {'id': user.user_id.id, 'name': user.user_id.name} 
                for user in self.user_ids
            ]
            debug_info['current_user_audited'] = self.env.user.id in [u.user_id.id for u in self.user_ids]
        else:
            debug_info['current_user_audited'] = True
        
        if not self.all_objects:
            debug_info['audit_models'] = [
                {'id': obj.model_id.id, 'model': obj.model_id.model, 'name': obj.model_id.name} 
                for obj in self.object_ids
            ]
        
        return debug_info
    
    def write(self, vals):
        """Override write to invalidate caches when config changes"""
        result = super().write(vals)
        
        # Invalidate audit caches when configuration changes
        cache_keys_to_clear = [
            '_audit_config_cache',
            f'_audit_users_cache_{self.id}',
            f'_audit_models_cache_{self.id}'
        ]
        
        for cache_key in cache_keys_to_clear:
            if hasattr(self.env, cache_key):
                delattr(self.env, cache_key)
        
        return result

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to invalidate caches"""
        records = super().create(vals_list)
        
        # Clear global audit config cache
        if hasattr(self.env, '_audit_config_cache'):
            delattr(self.env, '_audit_config_cache')
            
        return records

    def unlink(self):
        """Override unlink to invalidate caches"""
        config_ids = self.ids
        result = super().unlink()
        
        # Clear caches for deleted configs
        cache_keys_to_clear = ['_audit_config_cache']
        for config_id in config_ids:
            cache_keys_to_clear.extend([
                f'_audit_users_cache_{config_id}',
                f'_audit_models_cache_{config_id}'
            ])
        
        for cache_key in cache_keys_to_clear:
            if hasattr(self.env, cache_key):
                delattr(self.env, cache_key)
                
        return result

    def cleanup_old_logs(self):
        """Cleanup old audit logs based on configuration (called by cron)"""
        try:
            from datetime import datetime, timedelta
            import logging
            _logger = logging.getLogger(__name__)
            
            total_deleted = 0
            configs = self.search([('active', '=', True), ('auto_cleanup_days', '>', 0)])
            
            for config in configs:
                if config.auto_cleanup_days > 0:
                    cutoff_date = datetime.now() - timedelta(days=config.auto_cleanup_days)
                    old_logs = self.env['audit.log.entry'].search([
                        ('action_date', '<', cutoff_date)
                    ])
                    
                    if old_logs:
                        count = len(old_logs)
                        old_logs.unlink()
                        total_deleted += count
                        _logger.info(f"Config '{config.name}': Cleaned up {count} old audit logs (older than {config.auto_cleanup_days} days)")
            
            if total_deleted > 0:
                _logger.info(f"Total audit log cleanup: {total_deleted} logs deleted")
            
            return total_deleted
            
        except Exception as e:
            _logger.error(f"Failed to cleanup old logs: {e}")
            return 0


class AuditConfigUser(models.Model):
    """Audit Configuration Users"""
    _name = 'audit.config.user'
    _description = 'Audit Configuration Users'

    config_id = fields.Many2one('audit.config', 'Configuration', required=True, ondelete='cascade')
    user_id = fields.Many2one('res.users', 'User', required=True)

    def write(self, vals):
        """Override write to invalidate user cache"""
        result = super().write(vals)
        
        # Invalidate user cache for affected configs
        for record in self:
            cache_key = f'_audit_users_cache_{record.config_id.id}'
            if hasattr(self.env, cache_key):
                delattr(self.env, cache_key)
                
        return result

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to invalidate user cache"""
        records = super().create(vals_list)
        
        # Invalidate user cache for affected configs
        config_ids = set(record.config_id.id for record in records)
        for config_id in config_ids:
            cache_key = f'_audit_users_cache_{config_id}'
            if hasattr(self.env, cache_key):
                delattr(self.env, cache_key)
                
        return records

    def unlink(self):
        """Override unlink to invalidate user cache"""
        config_ids = set(record.config_id.id for record in self)
        result = super().unlink()
        
        # Invalidate user cache for affected configs
        for config_id in config_ids:
            cache_key = f'_audit_users_cache_{config_id}'
            if hasattr(self.env, cache_key):
                delattr(self.env, cache_key)
                
        return result

class AuditConfigObject(models.Model):
    """Audit Configuration Objects"""
    _name = 'audit.config.object'
    _description = 'Audit Configuration Objects'

    config_id = fields.Many2one('audit.config', 'Configuration', required=True, ondelete='cascade')
    model_id = fields.Many2one('ir.model', string='Model', ondelete='cascade', required=True)
    model_name = fields.Char(related='model_id.model', store=True)

    def write(self, vals):
        """Override write to invalidate model cache"""
        result = super().write(vals)
        
        # Invalidate model cache for affected configs
        for record in self:
            cache_key = f'_audit_models_cache_{record.config_id.id}'
            if hasattr(self.env, cache_key):
                delattr(self.env, cache_key)
                
        return result

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to invalidate model cache"""
        records = super().create(vals_list)
        
        # Invalidate model cache for affected configs
        config_ids = set(record.config_id.id for record in records)
        for config_id in config_ids:
            cache_key = f'_audit_models_cache_{config_id}'
            if hasattr(self.env, cache_key):
                delattr(self.env, cache_key)
                
        return records

    def unlink(self):
        """Override unlink to invalidate model cache"""
        config_ids = set(record.config_id.id for record in self)
        result = super().unlink()
        
        # Invalidate model cache for affected configs
        for config_id in config_ids:
            cache_key = f'_audit_models_cache_{config_id}'
            if hasattr(self.env, cache_key):
                delattr(self.env, cache_key)
                
        return result


class AuditSession(models.Model):
    """Simplified Audit Session Model"""
    _name = 'audit.session'
    _description = 'User Audit Session'
    _order = 'login_time desc'

    name = fields.Char('Session Reference', compute='_compute_name', store=True)
    user_id = fields.Many2one('res.users', 'User', required=True, index=True)
    session_id = fields.Char('Session ID', required=True, index=True)
    
    # Timing
    login_time = fields.Datetime('Login Time', default=fields.Datetime.now, required=True)
    logout_time = fields.Datetime('Logout Time')
    duration = fields.Float('Duration (Hours)', compute='_compute_duration', store=True)
    last_activity = fields.Datetime('Last Activity', default=fields.Datetime.now)
    
    # Technical Info
    ip_address = fields.Char('IP Address')
    device_type = fields.Selection([
        ('desktop', 'Desktop'),
        ('mobile', 'Mobile'), 
        ('tablet', 'Tablet'),
        ('unknown', 'Unknown')
    ], 'Device Type', default='unknown')
    browser = fields.Char('Browser')
    os = fields.Char('Operating System')
    
    # Status
    status = fields.Selection([
        ('active', 'Active'),
        ('logged_out', 'Logged Out'),
        ('expired', 'Expired'),
        ('replaced', 'Replaced'),
        ('error', 'Error')
    ], 'Status', default='active', required=True)
    
    browser_closed = fields.Boolean('Browser Closed', default=False)
    error_message = fields.Text('Error Message')
    
    # Relations
    log_entry_ids = fields.One2many('audit.log.entry', 'session_id', 'Log Entries')
    log_count = fields.Integer('Log Count', compute='_compute_log_count')

    @api.depends('user_id', 'login_time')
    def _compute_name(self):
        for record in self:
            if record.user_id and record.login_time:
                record.name = f"{record.user_id.name} - {record.login_time.strftime('%Y-%m-%d %H:%M:%S')}"
            else:
                record.name = "Session"

    @api.depends('login_time', 'logout_time')
    def _compute_duration(self):
        for record in self:
            if record.login_time and record.logout_time:
                delta = record.logout_time - record.login_time
                record.duration = delta.total_seconds() / 3600.0
            else:
                record.duration = 0.0

    @api.depends('log_entry_ids')
    def _compute_log_count(self):
        for record in self:
            record.log_count = len(record.log_entry_ids)

    def action_view_logs(self):
        """View session logs"""
        return {
            'name': 'Session Activity Logs',
            'type': 'ir.actions.act_window',
            'res_model': 'audit.log.entry',
            'view_mode': 'tree,form',
            'domain': [('session_id', '=', self.id)],
            'context': {'default_session_id': self.id}
        }

    @api.model
    def cleanup_expired_sessions(self):
        """Simple cleanup for expired sessions (called by cron)"""
        try:
            from datetime import datetime, timedelta
            
            # Get timeout from config (default 24 hours)
            config = self.env['audit.config'].search([('active', '=', True)], limit=1)
            timeout_hours = config.session_timeout_hours if config else 24
            
            cutoff_time = datetime.now() - timedelta(hours=timeout_hours)
            
            # Mark old active sessions as expired
            expired_sessions = self.search([
                ('status', '=', 'active'),
                ('login_time', '<', cutoff_time)
            ])
            
            if expired_sessions:
                expired_sessions.write({
                    'status': 'expired',
                    'logout_time': fields.Datetime.now(),
                    'error_message': f'Session expired after {timeout_hours} hours'
                })
                _logger.info(f"Expired {len(expired_sessions)} old sessions")
            
            return len(expired_sessions)
            
        except Exception as e:
            _logger.error(f"Failed to cleanup sessions: {e}")
            return 0

    def action_force_close(self):
        """Force close session"""
        for session in self:
            if session.status == 'active':
                session.write({
                    'status': 'logged_out',
                    'logout_time': fields.Datetime.now(),
                    'error_message': f'Manually closed by {self.env.user.name}'
                })
        return True

class AuditLogEntry(models.Model):
    """Audit Log Entry Model"""
    _name = 'audit.log.entry'
    _description = 'Audit Log Entry'
    _order = 'create_date desc'

    name = fields.Char('Reference', compute='_compute_name', store=True)
    user_id = fields.Many2one('res.users', 'User', required=True, index=True)
    session_id = fields.Many2one('audit.session', 'Session', index=True)
    
    # Record Information
    model_id = fields.Many2one(
        'ir.model',
        string='Model',
        ondelete='cascade',  # <-- change from 'set null' to 'cascade'
        required=True,
    )
    model_name = fields.Char(related='model_id.model', store=True, index=True)
    res_id = fields.Integer('Record ID', required=True, index=True)
    res_name = fields.Char('Record Name')
    
    # Action Information  
    action_type = fields.Selection([
        ('create', 'Create'),
        ('write', 'Update'), 
        ('read', 'Read'),
        ('unlink', 'Delete')
    ], 'Action Type', required=True, index=True)
    
    action_date = fields.Datetime('Action Date', default=fields.Datetime.now, required=True)
    
    # Changes
    old_values = fields.Text('Old Values')
    new_values = fields.Text('New Values') 
    changed_fields = fields.Text('Changed Fields')
    
    # Additional context
    method = fields.Char('Method')
    context_info = fields.Text('Context Info')

    @api.depends('user_id', 'model_name', 'action_type', 'res_id')
    def _compute_name(self):
        for record in self:
            if record.user_id and record.model_name and record.action_type:
                record.name = f"{record.user_id.name} - {record.action_type.title()} {record.model_name}({record.res_id})"
            else:
                record.name = "Audit Log"

    @api.model
    def log_action(self, user_id, model_name, res_id, action_type, old_values=None, new_values=None, 
                   changed_fields=None, method=None, session_id=None):
        """Create an audit log entry"""
        
        try:
            # Skip during module installation
            if self.env.context.get('module') or self.env.context.get('install_mode'):
                return False
            
            # Check if audit tables exist
            self.env.cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'audit_log_entry' LIMIT 1")
            if not self.env.cr.fetchone():
                return False
        
            # Get current session if not provided
            if not session_id and request and hasattr(request, 'session'):
                session = self.env['audit.session'].search([
                    ('session_id', '=', request.session.sid),
                    ('status', '=', 'active')
                ], limit=1)
                session_id = session.id if session else None

            # Get model
            model = self.env['ir.model'].search([('model', '=', model_name)], limit=1)
            if not model:
                _logger.warning(f"Model {model_name} not found for audit logging")
                return False

            # Get record name
            res_name = ''
            try:
                if hasattr(self.env[model_name], '_rec_name'):
                    record = self.env[model_name].browse(res_id)
                    res_name = record.display_name if record.exists() else f"ID: {res_id}"
            except Exception:
                res_name = f"ID: {res_id}"

            values = {
                'user_id': user_id,
                'session_id': session_id,
                'model_id': model.id,
                'res_id': res_id,
                'res_name': res_name,
                'action_type': action_type,
                'method': method,
                'old_values': json.dumps(old_values) if old_values else None,
                'new_values': json.dumps(new_values) if new_values else None,
                'changed_fields': json.dumps(changed_fields) if changed_fields else None,
            }

            return self.create(values)
            
        except Exception as e:
            _logger.debug(f"Failed to log action: {e}")
            return False

    old_values_readable = fields.Text('Old Values (Readable)', compute='_compute_readable_values', store=True)
    new_values_readable = fields.Text('New Values (Readable)', compute='_compute_readable_values', store=True)
    changes_summary = fields.Text('Changes Summary', compute='_compute_readable_values', store=True)
    
    @api.depends('old_values', 'new_values', 'model_name', 'action_type')
    def _compute_readable_values(self):
        """Compute human-readable versions of the values with robust error handling"""
        for record in self:
            # Initialize with safe defaults
            record.old_values_readable = ''
            record.new_values_readable = ''
            record.changes_summary = ''
            
            try:
                # Parse the JSON values safely
                old_dict = {}
                new_dict = {}
                
                try:
                    if record.old_values:
                        old_dict = json.loads(record.old_values)
                except Exception as e:
                    _logger.debug(f"Failed to parse old_values: {e}")
                    old_dict = {}
                
                try:
                    if record.new_values:
                        new_dict = json.loads(record.new_values)
                except Exception as e:
                    _logger.debug(f"Failed to parse new_values: {e}")
                    new_dict = {}
                
                # Generate readable versions with fallback
                try:
                    record.old_values_readable = record._format_values_readable_safe(old_dict, 'old')
                except Exception as e:
                    _logger.debug(f"Failed to format old values: {e}")
                    record.old_values_readable = record._format_values_basic(old_dict) if old_dict else ''
                
                try:
                    record.new_values_readable = record._format_values_readable_safe(new_dict, 'new')
                except Exception as e:
                    _logger.debug(f"Failed to format new values: {e}")
                    record.new_values_readable = record._format_values_basic(new_dict) if new_dict else ''
                
                try:
                    record.changes_summary = record._generate_changes_summary_safe(old_dict, new_dict)
                except Exception as e:
                    _logger.debug(f"Failed to generate summary: {e}")
                    record.changes_summary = record._generate_basic_summary(old_dict, new_dict)
                    
            except Exception as e:
                # Ultimate fallback - this should never happen now
                _logger.warning(f"Critical error in _compute_readable_values: {e}")
                record.old_values_readable = record.old_values or ''
                record.new_values_readable = record.new_values or ''
                record.changes_summary = f"Unable to format audit data"

    def _format_values_readable_safe(self, values_dict, value_type='new'):
        """Safely convert a values dictionary to human-readable format"""
        if not values_dict:
            return ''
        
        # First, check if we can safely access the model
        target_model = None
        can_access_model = False
        
        try:
            if self.model_name:
                # Check if model exists in registry first
                if self.model_name in self.env.registry:
                    # Try to access the model
                    target_model = self.env[self.model_name]
                    can_access_model = True
                else:
                    _logger.debug(f"Model {self.model_name} not found in registry")
        except Exception as e:
            _logger.debug(f"Cannot access model {self.model_name}: {e}")
            can_access_model = False
        
        # If we can't access the model, use basic formatting
        if not can_access_model or not target_model:
            return self._format_values_basic(values_dict)
        
        # Try advanced formatting with the model
        try:
            readable_parts = []
            
            for field_name, value in values_dict.items():
                try:
                    readable_part = self._format_single_field_safe(target_model, field_name, value, value_type)
                    if readable_part:
                        readable_parts.append(readable_part)
                except Exception as e:
                    # Fallback to basic formatting for this field
                    _logger.debug(f"Error formatting field {field_name}: {e}")
                    readable_parts.append(self._format_field_basic(field_name, value))
            
            return '\n'.join(readable_parts) if readable_parts else 'No changes recorded'
            
        except Exception as e:
            _logger.debug(f"Advanced formatting failed, using basic: {e}")
            return self._format_values_basic(values_dict)

    def _format_values_basic(self, values_dict):
        """Basic formatting when model access fails or isn't available"""
        if not values_dict:
            return ''
        
        readable_parts = []
        for field_name, value in values_dict.items():
            try:
                readable_parts.append(self._format_field_basic(field_name, value))
            except Exception as e:
                # Ultra-safe fallback
                readable_parts.append(f"{field_name}: {str(value)}")
        
        return '\n'.join(readable_parts)

    def _format_field_basic(self, field_name, value):
        """Ultra-safe basic field formatting without any model dependencies"""
        try:
            # Clean up field name
            field_label = field_name.replace('_', ' ').title()
            
            # Handle None/empty values
            if value is None:
                return f"{field_label}: (not set)"
            elif value == '':
                return f"{field_label}: (empty)"
            
            # Handle different value types
            if isinstance(value, bool):
                return f"{field_label}: {'Yes' if value else 'No'}"
            
            elif isinstance(value, (list, tuple)):
                if len(value) == 0:
                    return f"{field_label}: (empty)"
                elif len(value) == 2 and field_name.endswith('_id'):
                    # Likely [id, name] format for many2one
                    return f"{field_label}: {value[1]} (ID: {value[0]})"
                elif len(value) <= 5:
                    return f"{field_label}: {', '.join(map(str, value))}"
                else:
                    return f"{field_label}: {len(value)} items"
            
            elif isinstance(value, (int, float)):
                if field_name.endswith('_id'):
                    return f"{field_label}: ID {value}"
                elif isinstance(value, float):
                    return f"{field_label}: {value:,.2f}"
                else:
                    return f"{field_label}: {value:,}"
            
            elif isinstance(value, str):
                if len(value) > 100:
                    return f"{field_label}: {value[:100]}... (truncated)"
                else:
                    return f"{field_label}: {value}"
            
            else:
                # Fallback for any other type
                return f"{field_label}: {str(value)}"
                
        except Exception as e:
            # Ultimate fallback
            return f"{field_name}: {str(value)}"

    def _format_single_field_safe(self, target_model, field_name, value, value_type='new'):
        """Safely format a single field with model information"""
        try:
            # Check if field exists in model
            if not hasattr(target_model, '_fields') or field_name not in target_model._fields:
                return self._format_field_basic(field_name, value)
            
            field = target_model._fields[field_name]
            field_label = getattr(field, 'string', None) or field_name.replace('_', ' ').title()
            
            # Handle different field types safely
            if field.type == 'many2one':
                return self._format_many2one_field_ultra_safe(field_label, value, getattr(field, 'comodel_name', None))
            elif field.type in ['one2many', 'many2many']:
                return self._format_relation_field_ultra_safe(field_label, value, getattr(field, 'comodel_name', None))
            elif field.type == 'selection':
                return self._format_selection_field_ultra_safe(field_label, value, getattr(field, 'selection', None))
            elif field.type == 'boolean':
                return f"{field_label}: {'Yes' if value else 'No'}"
            elif field.type in ['date', 'datetime']:
                return self._format_date_field_ultra_safe(field_label, value, field.type)
            elif field.type in ['float', 'monetary']:
                return self._format_numeric_field_ultra_safe(field_label, value, field.type)
            elif field.type == 'text':
                return self._format_text_field_safe(field_label, value)
            else:
                return f"{field_label}: {value}"
                
        except Exception as e:
            # Fallback to basic formatting
            return self._format_field_basic(field_name, value)

    def _format_many2one_field_ultra_safe(self, field_label, value, comodel_name):
        """Ultra-safe many2one formatting"""
        if not value:
            return f"{field_label}: (empty)"
        
        try:
            if isinstance(value, (list, tuple)) and len(value) >= 2:
                return f"{field_label}: {value[1]} (ID: {value[0]})"
            elif isinstance(value, int):
                return f"{field_label}: ID {value}"
            else:
                return f"{field_label}: {value}"
        except Exception:
            return f"{field_label}: {str(value)}"

    def _format_relation_field_ultra_safe(self, field_label, value, comodel_name):
        """Ultra-safe relation field formatting"""
        if not value:
            return f"{field_label}: (empty)"
        
        try:
            if isinstance(value, list):
                if len(value) == 0:
                    return f"{field_label}: (empty)"
                elif len(value) <= 3:
                    return f"{field_label}: {', '.join(map(str, value))}"
                else:
                    return f"{field_label}: {len(value)} records"
            else:
                return f"{field_label}: {value}"
        except Exception:
            return f"{field_label}: {str(value)}"

    def _format_selection_field_ultra_safe(self, field_label, value, selection):
        """Ultra-safe selection field formatting"""
        if not value:
            return f"{field_label}: (not set)"
        
        try:
            if selection and not callable(selection):
                for sel_value, sel_label in selection:
                    if sel_value == value:
                        return f"{field_label}: {sel_label}"
            return f"{field_label}: {value}"
        except Exception:
            return f"{field_label}: {str(value)}"

    def _format_date_field_ultra_safe(self, field_label, value, field_type):
        """Ultra-safe date formatting"""
        if not value:
            return f"{field_label}: (not set)"
        
        try:
            return f"{field_label}: {str(value)}"
        except Exception:
            return f"{field_label}: {str(value)}"

    def _format_numeric_field_ultra_safe(self, field_label, value, field_type):
        """Ultra-safe numeric formatting"""
        if value is None or value == '':
            return f"{field_label}: (not set)"
        
        try:
            if isinstance(value, (int, float)):
                return f"{field_label}: {float(value):,.2f}"
            else:
                return f"{field_label}: {value}"
        except Exception:
            return f"{field_label}: {str(value)}"

    def _format_text_field_safe(self, field_label, value):
        """Safe text field formatting"""
        if not value:
            return f"{field_label}: (empty)"
        
        try:
            if len(str(value)) > 100:
                return f"{field_label}: {str(value)[:100]}... (truncated)"
            else:
                return f"{field_label}: {value}"
        except Exception:
            return f"{field_label}: {str(value)}"

    def _generate_changes_summary_safe(self, old_dict, new_dict):
        """Safely generate changes summary with enhanced delete handling"""
        try:
            if self.action_type == 'create':
                return self._generate_basic_create_summary(new_dict)
            elif self.action_type == 'write':
                return self._generate_basic_update_summary(old_dict, new_dict)
            elif self.action_type == 'unlink':
                return self._generate_delete_summary(old_dict)  # Enhanced delete summary
            elif self.action_type == 'read':
                return "Record was accessed"
            else:
                return f"Action: {self.action_type}"
        except Exception as e:
            return self._generate_basic_summary(old_dict, new_dict)

    def _generate_basic_summary(self, old_dict, new_dict):
        """Enhanced basic summary generation"""
        try:
            if self.action_type == 'create':
                return f"New record created with {len(new_dict)} fields set"
            elif self.action_type == 'write':
                return f"Record updated - {len(new_dict)} fields modified"
            elif self.action_type == 'unlink':
                if old_dict:
                    return f"Record deleted (had {len(old_dict)} fields)"
                else:
                    return "Record was deleted"
            else:
                return f"Action: {self.action_type}"
        except Exception:
            return "Record was modified"

    def _generate_basic_create_summary(self, new_dict):
        """Basic create summary"""
        if not new_dict:
            return "New record was created"
        
        # Look for common important fields
        key_fields = ['name', 'title', 'subject', 'email']
        important_values = []
        
        for field in key_fields:
            if field in new_dict and new_dict[field]:
                important_values.append(f"{field.title()}: {new_dict[field]}")
        
        if important_values:
            return f"New record created with {', '.join(important_values[:2])}"
        else:
            return f"New record created with {len(new_dict)} fields set"

    def _generate_basic_update_summary(self, old_dict, new_dict):
        """Basic update summary"""
        if not new_dict:
            return "Record was updated"
        
        try:
            changed_count = len([k for k in new_dict.keys() if old_dict.get(k) != new_dict.get(k)])
            if changed_count == 0:
                return "Record was updated (no field changes detected)"
            elif changed_count == 1:
                field_name = list(new_dict.keys())[0]
                field_label = field_name.replace('_', ' ').title()
                return f"{field_label} was modified"
            else:
                return f"{changed_count} fields were modified"
        except Exception:
            return f"Record was updated"
        
    def _generate_delete_summary(self, old_dict):
        """Generate meaningful summary for delete operations"""
        if not old_dict:
            return "Record was deleted"
        
        try:
            # Look for identifying information in the deleted record
            identifying_fields = ['name', 'title', 'subject', 'email', 'login', 'display_name']
            identity_info = []
            
            for field in identifying_fields:
                if field in old_dict and old_dict[field]:
                    value = str(old_dict[field])
                    if len(value) > 50:
                        value = value[:50] + "..."
                    identity_info.append(f"{field.title()}: {value}")
            
            if identity_info:
                # Show the most important identifying information
                return f"Deleted record: {', '.join(identity_info[:2])}"
            else:
                # Fallback: count of fields that were set
                field_count = len([v for v in old_dict.values() if v is not None and v != ''])
                return f"Record was deleted (had {field_count} fields set)"
                
        except Exception as e:
            return "Record was deleted"
    
    def _generate_changes_summary(self, old_dict, new_dict):
        """Generate a summary of what changed"""
        if not old_dict and not new_dict:
            return "No changes recorded"
        
        if self.action_type == 'create':
            return self._generate_create_summary(new_dict)
        elif self.action_type == 'write':
            return self._generate_update_summary(old_dict, new_dict)
        elif self.action_type == 'unlink':
            return f"Record was deleted"
        elif self.action_type == 'read':
            return f"Record was accessed"
        else:
            return f"Action: {self.action_type}"
    
    def _generate_create_summary(self, new_dict):
        """Generate summary for create action"""
        if not new_dict:
            return "New record was created"
        
        # Try to identify key fields that were set
        key_fields = ['name', 'title', 'subject', 'description', 'email', 'phone']
        important_values = []
        
        for field in key_fields:
            if field in new_dict and new_dict[field]:
                important_values.append(f"{field.title()}: {new_dict[field]}")
        
        if important_values:
            return f"New record created with {', '.join(important_values[:2])}"
        else:
            return f"New record created with {len(new_dict)} fields set"
    
    def _generate_update_summary(self, old_dict, new_dict):
        """Generate summary for update action"""
        if not old_dict or not new_dict:
            return "Record was updated"
        
        changes = []
        for field_name in new_dict.keys():
            old_value = old_dict.get(field_name)
            new_value = new_dict.get(field_name)
            
            if old_value != new_value:
                field_label = field_name.replace('_', ' ').title()
                
                # Special handling for some field types
                if field_name.endswith('_id') and isinstance(old_value, str) and isinstance(new_value, int):
                    # Many2one field change
                    changes.append(f"{field_label} changed")
                elif isinstance(old_value, bool) and isinstance(new_value, bool):
                    # Boolean field change
                    changes.append(f"{field_label} {'enabled' if new_value else 'disabled'}")
                else:
                    # General change
                    changes.append(f"{field_label} modified")
        
        if changes:
            if len(changes) == 1:
                return f"{changes[0]}"
            elif len(changes) <= 3:
                return f"{', '.join(changes)}"
            else:
                return f"{len(changes)} fields were modified: {', '.join(changes[:2])}, and {len(changes)-2} others"
        else:
            return "Record was updated (no field changes detected)"

    def get_changed_fields_list(self):
        """Get changed fields as list"""
        return json.loads(self.changed_fields) if self.changed_fields else []


# Model Mixin for Audit Tracking
class AuditMixin(models.AbstractModel):
    """Mixin to add audit tracking to any model"""
    _name = 'audit.mixin'
    _description = 'Audit Mixin'

    def _should_audit_action(self, action_type):
        """Check if action should be audited"""
        config = self.env['audit.config'].get_active_config()
        if not config:
            return False
            
        # Check if user should be audited
        if not config.should_audit_user(self.env.user.id):
            return False
            
        # Check if model should be audited
        if not config.should_audit_model(self._name):
            return False
            
        # Check if action type is enabled
        action_checks = {
            'create': config.log_create,
            'write': config.log_write,
            'read': config.log_read,
            'unlink': config.log_unlink
        }
        
        return action_checks.get(action_type, False)

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to log audit"""
        records = super().create(vals_list)
        
        if self._should_audit_action('create'):
            for record, vals in zip(records, vals_list):
                self.env['audit.log.entry'].log_action(
                    user_id=self.env.user.id,
                    model_name=self._name,
                    res_id=record.id,
                    action_type='create',
                    new_values=vals,
                    method='create'
                )
        
        return records

    def write(self, vals):
        """Override write to log audit"""
        if self._should_audit_action('write'):
            old_values = {}
            for record in self:
                old_values[record.id] = {field: record[field] for field in vals.keys() if field in record._fields}
        
        result = super().write(vals)
        
        if self._should_audit_action('write'):
            changed_fields = list(vals.keys())
            for record in self:
                self.env['audit.log.entry'].log_action(
                    user_id=self.env.user.id,
                    model_name=self._name,
                    res_id=record.id,
                    action_type='write',
                    old_values=old_values.get(record.id, {}),
                    new_values=vals,
                    changed_fields=changed_fields,
                    method='write'
                )
        
        return result

    def unlink(self):
        """Override unlink to log audit"""
        if self._should_audit_action('unlink'):
            for record in self:
                old_values = {field.name: record[field.name] for field in record._fields.values() 
                            if field.store and hasattr(record, field.name)}
                self.env['audit.log.entry'].log_action(
                    user_id=self.env.user.id,
                    model_name=self._name,
                    res_id=record.id,
                    action_type='unlink',
                    old_values=old_values,
                    method='unlink'
                )
        
        return super().unlink()

    def read(self, fields=None, load='_classic_read'):
        """Override read to log audit"""
        result = super().read(fields, load)
        
        if self._should_audit_action('read'):
            for record in self:
                self.env['audit.log.entry'].log_action(
                    user_id=self.env.user.id,
                    model_name=self._name,
                    res_id=record.id,
                    action_type='read',
                    method='read'
                )
        
        return result