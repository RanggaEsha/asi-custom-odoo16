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


class AuditConfigUser(models.Model):
    """Audit Configuration Users"""
    _name = 'audit.config.user'
    _description = 'Audit Configuration Users'

    config_id = fields.Many2one('audit.config', 'Configuration', required=True, ondelete='cascade')
    user_id = fields.Many2one('res.users', 'User', required=True)


class AuditConfigObject(models.Model):
    """Audit Configuration Objects"""
    _name = 'audit.config.object'
    _description = 'Audit Configuration Objects'

    config_id = fields.Many2one('audit.config', 'Configuration', required=True, ondelete='cascade')
    model_id = fields.Many2one(
        'ir.model',
        string='Model',
        ondelete='cascade',  # <-- change from 'set null' to 'cascade'
        required=True,
    )
    model_name = fields.Char(related='model_id.model', store=True)


class AuditSession(models.Model):
    """Audit Session Model"""
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
    
    # Technical Info
    ip_address = fields.Char('IP Address')
    user_agent = fields.Text('User Agent')
    device_name = fields.Char('Device Name')
    device_type = fields.Selection([
        ('desktop', 'Desktop'),
        ('mobile', 'Mobile'), 
        ('tablet', 'Tablet'),
        ('unknown', 'Unknown')
    ], 'Device Type')
    browser = fields.Char('Browser')
    os = fields.Char('Operating System')
    
    # Location
    country = fields.Char('Country')
    city = fields.Char('City')
    latitude = fields.Float('Latitude')
    longitude = fields.Float('Longitude')
    
    # Status
    status = fields.Selection([
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('logged_out', 'Logged Out'),
        ('forced_logout', 'Forced Logout'),
        ('error', 'Error')
    ], 'Status', default='active', required=True)
    
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
        """Smart button action to view session logs"""
        return {
            'name': _('Session Activity Logs'),
            'type': 'ir.actions.act_window',
            'res_model': 'audit.log.entry',
            'view_mode': 'tree,form',
            'domain': [('session_id', '=', self.id)],
            'context': {'default_session_id': self.id}
        }

    def parse_user_agent(self, user_agent_string):
        """Parse user agent string to extract device info"""
        if not user_agent_string:
            return {}
            
        try:
            ua = parse(user_agent_string)
            return {
                'browser': f"{ua.browser.family} {ua.browser.version_string}",
                'os': f"{ua.os.family} {ua.os.version_string}",
                'device_name': ua.device.family,
                'device_type': 'mobile' if ua.is_mobile else 'tablet' if ua.is_tablet else 'desktop'
            }
        except Exception as e:
            _logger.warning(f"Failed to parse user agent: {e}")
            return {}

    def get_location_from_ip(self, ip_address):
        """Get location info from IP address"""
        if not ip_address or ip_address in ['127.0.0.1', 'localhost']:
            return {}
            
        try:
            # Using a free IP geolocation service
            response = requests.get(f'http://ip-api.com/json/{ip_address}', timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'success':
                    return {
                        'country': data.get('country'),
                        'city': data.get('city'),
                        'latitude': data.get('lat'),
                        'longitude': data.get('lon')
                    }
        except Exception as e:
            _logger.warning(f"Failed to get location for IP {ip_address}: {e}")
        return {}

    @api.model
    def create_session(self, user_id, session_id, request_obj=None):
        """FIXED: Create a new audit session with better error handling"""
        try:
            # Skip during module installation
            if self.env.context.get('module') or self.env.context.get('install_mode'):
                return None
            
            # Check if audit tables exist
            self.env.cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'audit_session' LIMIT 1")
            if not self.env.cr.fetchone():
                return None
        
            values = {
                'user_id': user_id,
                'session_id': session_id,
                'login_time': fields.Datetime.now(),
                'status': 'active'
            }
            
            if request_obj and hasattr(request_obj, 'httprequest'):
                # Extract request information safely
                values['ip_address'] = getattr(request_obj.httprequest, 'remote_addr', None)
                headers = getattr(request_obj.httprequest, 'headers', {})
                values['user_agent'] = headers.get('User-Agent', '') if headers else ''
                
                # Parse user agent
                if values['user_agent']:
                    ua_info = self.parse_user_agent(values['user_agent'])
                    values.update(ua_info)
                
                # Get location info
                if values.get('ip_address'):
                    location_info = self.get_location_from_ip(values['ip_address'])
                    values.update(location_info)
            
            # FIXED: Use create instead of self.create for better reliability
            session = self.sudo().create(values)
            _logger.info(f"Created audit session {session.id} for user {user_id} with session_id {session_id}")
            return session
            
        except Exception as e:
            _logger.warning(f"Failed to create audit session: {e}")
            return None

    def close_session(self):
        """Close the session"""
        try:
            self.sudo().write({
                'logout_time': fields.Datetime.now(),
                'status': 'logged_out'
            })
            _logger.info(f"Closed audit session {self.id}")
        except Exception as e:
            _logger.error(f"Failed to close session {self.id}: {e}")

    @api.model
    def cleanup_expired_sessions(self):
        """Cleanup expired sessions (called by cron)"""
        try:
            timeout_hours = 24  # Default timeout
            
            # Get timeout from configuration
            config = self.env['audit.config'].search([('active', '=', True)], limit=1)
            if config and config.session_timeout_hours:
                timeout_hours = config.session_timeout_hours
                
            cutoff_time = datetime.now() - timedelta(hours=timeout_hours)
            expired_sessions = self.search([
                ('status', '=', 'active'),
                ('login_time', '<', cutoff_time)
            ])
            
            if expired_sessions:
                expired_sessions.write({'status': 'expired'})
                _logger.info(f"Marked {len(expired_sessions)} sessions as expired")
                
            return len(expired_sessions)
        except Exception as e:
            _logger.error(f"Failed to cleanup expired sessions: {e}")
            return 0


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

    def get_old_values_dict(self):
        """Get old values as dictionary"""
        return json.loads(self.old_values) if self.old_values else {}

    def get_new_values_dict(self):
        """Get new values as dictionary"""
        return json.loads(self.new_values) if self.new_values else {}

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