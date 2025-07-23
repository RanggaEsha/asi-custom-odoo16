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


    @api.model
    def extract_request_info(self, request_obj=None):
        """Extract comprehensive request information including device details"""
        info = {
            'ip_address': 'unknown',
            'user_agent': '',
            'device_name': '',
            'device_type': 'unknown',
            'browser': 'Unknown',
            'os': 'Unknown',
            'country': None,
            'city': None,
            'latitude': None,
            'longitude': None
        }
        
        try:
            if not request_obj:
                # Try to get from current request context
                from odoo.http import request
                request_obj = request
                
            if request_obj and hasattr(request_obj, 'httprequest'):
                # Extract basic request info
                info['ip_address'] = getattr(request_obj.httprequest, 'remote_addr', 'unknown')
                headers = getattr(request_obj.httprequest, 'headers', {})
                info['user_agent'] = headers.get('User-Agent', '') if headers else ''
                
                # Parse user agent for device information
                if info['user_agent']:
                    device_info = self.parse_user_agent(info['user_agent'])
                    info.update(device_info)
                
                # Get location information (if IP is available and not local)
                if info['ip_address'] and info['ip_address'] not in ['127.0.0.1', 'localhost', 'unknown']:
                    location_info = self.get_location_from_ip(info['ip_address'])
                    info.update(location_info)
                    
        except Exception as e:
            _logger.warning(f"Failed to extract request info: {e}")
            
        return info

    def parse_user_agent(self, user_agent_string):
        """Enhanced user agent parsing with fallbacks"""
        if not user_agent_string:
            return {
                'browser': 'Unknown',
                'os': 'Unknown', 
                'device_name': '',
                'device_type': 'unknown'
            }
            
        try:
            # Try to import user_agents library
            from user_agents import parse
            ua = parse(user_agent_string)
            
            return {
                'browser': f"{ua.browser.family} {ua.browser.version_string}".strip(),
                'os': f"{ua.os.family} {ua.os.version_string}".strip(),
                'device_name': ua.device.family if ua.device.family != 'Other' else '',
                'device_type': 'mobile' if ua.is_mobile else 'tablet' if ua.is_tablet else 'desktop'
            }
            
        except ImportError:
            _logger.warning("user_agents library not available, using basic parsing")
            # Fallback to basic parsing
            return self._basic_user_agent_parse(user_agent_string)
        except Exception as e:
            _logger.warning(f"Failed to parse user agent '{user_agent_string}': {e}")
            return self._basic_user_agent_parse(user_agent_string)

    def _basic_user_agent_parse(self, user_agent_string):
        """Basic user agent parsing fallback"""
        ua_lower = user_agent_string.lower()
        
        # Detect browser
        browser = 'Unknown'
        if 'chrome' in ua_lower:
            browser = 'Chrome'
        elif 'firefox' in ua_lower:
            browser = 'Firefox'
        elif 'safari' in ua_lower and 'chrome' not in ua_lower:
            browser = 'Safari'
        elif 'edge' in ua_lower:
            browser = 'Edge'
        elif 'opera' in ua_lower:
            browser = 'Opera'
        
        # Detect OS
        os_name = 'Unknown'
        if 'windows' in ua_lower:
            os_name = 'Windows'
        elif 'mac' in ua_lower or 'osx' in ua_lower:
            os_name = 'macOS'
        elif 'linux' in ua_lower:
            os_name = 'Linux'
        elif 'android' in ua_lower:
            os_name = 'Android'
        elif 'ios' in ua_lower or 'iphone' in ua_lower or 'ipad' in ua_lower:
            os_name = 'iOS'
        
        # Detect device type
        device_type = 'desktop'
        if any(mobile in ua_lower for mobile in ['mobile', 'android', 'iphone']):
            device_type = 'mobile'
        elif any(tablet in ua_lower for tablet in ['tablet', 'ipad']):
            device_type = 'tablet'
        
        return {
            'browser': browser,
            'os': os_name,
            'device_name': '',
            'device_type': device_type
        }

    def get_location_from_ip(self, ip_address):
        """Enhanced IP geolocation with multiple fallbacks"""
        if not ip_address or ip_address in ['127.0.0.1', 'localhost', 'unknown']:
            return {}
            
        try:
            # Try primary service (ip-api.com)
            import requests
            response = requests.get(f'http://ip-api.com/json/{ip_address}', timeout=3)
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
            _logger.debug(f"Primary geolocation service failed for {ip_address}: {e}")
            
        try:
            # Fallback service (ipinfo.io)
            response = requests.get(f'http://ipinfo.io/{ip_address}/json', timeout=3)
            if response.status_code == 200:
                data = response.json()
                location = data.get('loc', '').split(',')
                return {
                    'country': data.get('country'),
                    'city': data.get('city'),
                    'latitude': float(location[0]) if len(location) >= 2 else None,
                    'longitude': float(location[1]) if len(location) >= 2 else None
                }
        except Exception as e:
            _logger.debug(f"Fallback geolocation service failed for {ip_address}: {e}")
            
        return {}

    @api.model
    def create_session(self, user_id, session_id, request_obj=None):
        """ENHANCED: Create session with comprehensive device information"""
        try:
            # Skip during module installation
            if self.env.context.get('module') or self.env.context.get('install_mode'):
                return None
            
            # Check if audit tables exist
            self.env.cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'audit_session' LIMIT 1")
            if not self.env.cr.fetchone():
                return None
        
            _logger.info(f"CREATE_SESSION - Creating session for user {user_id} with session_id {session_id}")
            
            # Check if session already exists
            existing_session = self.sudo().search([
                ('session_id', '=', session_id),
                ('user_id', '=', user_id)
            ], limit=1)
            
            if existing_session:
                _logger.info(f"CREATE_SESSION - Updating existing session {existing_session.id}")
                
                # Extract fresh request info for the update
                request_info = self.extract_request_info(request_obj)
                
                existing_session.sudo().write({
                    'login_time': fields.Datetime.now(),
                    'status': 'active',
                    'error_message': False,
                    # Update technical info in case it changed
                    'ip_address': request_info['ip_address'],
                    'user_agent': request_info['user_agent'],
                    'device_name': request_info['device_name'],
                    'device_type': request_info['device_type'],
                    'browser': request_info['browser'],
                    'os': request_info['os'],
                    'country': request_info['country'],
                    'city': request_info['city'],
                    'latitude': request_info['latitude'],
                    'longitude': request_info['longitude'],
                })
                return existing_session
            
            # Extract comprehensive request information
            request_info = self.extract_request_info(request_obj)
            
            # Create session values
            values = {
                'user_id': user_id,
                'session_id': session_id,
                'login_time': fields.Datetime.now(),
                'status': 'active'
            }
            values.update(request_info)
            
            # Create the session
            session = self.sudo().create(values)
            _logger.info(f"CREATE_SESSION - Successfully created session {session.id} with device info: "
                        f"Type={session.device_type}, Browser={session.browser}, OS={session.os}")
            
            # Immediate commit to ensure availability
            self.env.cr.commit()
            return session
            
        except Exception as e:
            _logger.error(f"Failed to create audit session: {e}")
            # Rollback to prevent database corruption
            self.env.cr.rollback()
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

    old_values_readable = fields.Text('Old Values (Readable)', compute='_compute_readable_values', store=True)
    new_values_readable = fields.Text('New Values (Readable)', compute='_compute_readable_values', store=True)
    changes_summary = fields.Text('Changes Summary', compute='_compute_readable_values', store=True)
    
    @api.depends('old_values', 'new_values', 'model_name', 'action_type')
    def _compute_readable_values(self):
        """Compute human-readable versions of the values"""
        for record in self:
            try:
                # Parse the JSON values
                old_dict = json.loads(record.old_values) if record.old_values else {}
                new_dict = json.loads(record.new_values) if record.new_values else {}
                
                # Generate readable versions
                record.old_values_readable = record._format_values_readable(old_dict, 'old')
                record.new_values_readable = record._format_values_readable(new_dict, 'new')
                record.changes_summary = record._generate_changes_summary(old_dict, new_dict)
                
            except Exception as e:
                # Fallback to original values if parsing fails
                record.old_values_readable = record.old_values or ''
                record.new_values_readable = record.new_values or ''
                record.changes_summary = f"Error formatting changes: {str(e)}"
    
    def _format_values_readable(self, values_dict, value_type='new'):
        """Convert a values dictionary to human-readable format"""
        if not values_dict:
            return ''
        
        try:
            # Get the model for field information
            target_model = self.env[self.model_name] if self.model_name else None
            if not target_model:
                return str(values_dict)
            
            readable_parts = []
            
            for field_name, value in values_dict.items():
                try:
                    readable_part = self._format_single_field(target_model, field_name, value, value_type)
                    if readable_part:
                        readable_parts.append(readable_part)
                except Exception as e:
                    # Fallback for problematic fields
                    readable_parts.append(f"{field_name}: {value}")
            
            return '\n'.join(readable_parts) if readable_parts else 'No changes recorded'
            
        except Exception as e:
            return f"Error formatting values: {str(e)}"
    
    def _format_single_field(self, target_model, field_name, value, value_type='new'):
        """Format a single field value to human-readable format"""
        try:
            # Skip if field doesn't exist in model
            if field_name not in target_model._fields:
                return f"{field_name.title()}: {value}"
            
            field = target_model._fields[field_name]
            field_label = field.string or field_name.replace('_', ' ').title()
            
            # Handle different field types
            if field.type == 'many2one':
                return self._format_many2one_field(field_label, value, field.comodel_name)
            
            elif field.type == 'one2many' or field.type == 'many2many':
                return self._format_relation_field(field_label, value, field.comodel_name, field.type)
            
            elif field.type == 'selection':
                return self._format_selection_field(field_label, value, field.selection)
            
            elif field.type == 'boolean':
                return self._format_boolean_field(field_label, value)
            
            elif field.type in ['date', 'datetime']:
                return self._format_date_field(field_label, value, field.type)
            
            elif field.type in ['float', 'monetary']:
                return self._format_numeric_field(field_label, value, field.type)
            
            elif field.type == 'text':
                return self._format_text_field(field_label, value)
            
            else:
                # Default formatting for other field types
                return f"{field_label}: {value}"
                
        except Exception as e:
            return f"{field_name}: {value} (formatting error: {str(e)})"
    
    def _format_many2one_field(self, field_label, value, comodel_name):
        """Format many2one field value"""
        if not value:
            return f"{field_label}: (empty)"
        
        try:
            if isinstance(value, (list, tuple)) and len(value) >= 2:
                # Value is [id, name] format
                return f"{field_label}: {value[1]} (ID: {value[0]})"
            elif isinstance(value, int):
                # Value is just ID, try to get the name
                try:
                    record = self.env[comodel_name].sudo().browse(value)
                    if record.exists():
                        return f"{field_label}: {record.display_name} (ID: {value})"
                    else:
                        return f"{field_label}: (deleted record, ID: {value})"
                except:
                    return f"{field_label}: ID {value}"
            else:
                return f"{field_label}: {value}"
        except:
            return f"{field_label}: {value}"
    
    def _format_relation_field(self, field_label, value, comodel_name, field_type):
        """Format one2many/many2many field values"""
        if not value:
            return f"{field_label}: (empty)"
        
        try:
            if isinstance(value, list):
                if len(value) == 0:
                    return f"{field_label}: (empty)"
                elif len(value) <= 3:
                    # Show individual records for small lists
                    names = []
                    for item_id in value:
                        try:
                            record = self.env[comodel_name].sudo().browse(item_id)
                            if record.exists():
                                names.append(record.display_name)
                            else:
                                names.append(f"ID: {item_id}")
                        except:
                            names.append(f"ID: {item_id}")
                    return f"{field_label}: {', '.join(names)}"
                else:
                    # Show count for large lists
                    return f"{field_label}: {len(value)} records"
            else:
                return f"{field_label}: {value}"
        except:
            return f"{field_label}: {value}"
    
    def _format_selection_field(self, field_label, value, selection):
        """Format selection field value"""
        if not value:
            return f"{field_label}: (not set)"
        
        try:
            # Find the human-readable label for the selection value
            if selection:
                if callable(selection):
                    # Dynamic selection - can't easily resolve
                    return f"{field_label}: {value}"
                else:
                    # Static selection
                    for sel_value, sel_label in selection:
                        if sel_value == value:
                            return f"{field_label}: {sel_label}"
            
            return f"{field_label}: {value}"
        except:
            return f"{field_label}: {value}"
    
    def _format_boolean_field(self, field_label, value):
        """Format boolean field value"""
        if value is True:
            return f"{field_label}: Yes"
        elif value is False:
            return f"{field_label}: No"
        else:
            return f"{field_label}: {value}"
    
    def _format_date_field(self, field_label, value, field_type):
        """Format date/datetime field value"""
        if not value:
            return f"{field_label}: (not set)"
        
        try:
            if field_type == 'datetime':
                # Parse datetime and format nicely
                if isinstance(value, str):
                    dt = fields.Datetime.from_string(value)
                    return f"{field_label}: {dt.strftime('%Y-%m-%d %H:%M:%S')}"
            elif field_type == 'date':
                # Parse date and format nicely
                if isinstance(value, str):
                    dt = fields.Date.from_string(value)
                    return f"{field_label}: {dt.strftime('%Y-%m-%d')}"
            
            return f"{field_label}: {value}"
        except:
            return f"{field_label}: {value}"
    
    def _format_numeric_field(self, field_label, value, field_type):
        """Format numeric field value"""
        if value is None or value == '':
            return f"{field_label}: (not set)"
        
        try:
            if field_type == 'monetary':
                # Format as currency (basic formatting)
                return f"{field_label}: {float(value):,.2f}"
            elif field_type == 'float':
                # Format as float
                return f"{field_label}: {float(value):,.2f}"
            else:
                return f"{field_label}: {value}"
        except:
            return f"{field_label}: {value}"
    
    def _format_text_field(self, field_label, value):
        """Format text field value"""
        if not value:
            return f"{field_label}: (empty)"
        
        # Truncate long text values
        if len(str(value)) > 100:
            return f"{field_label}: {str(value)[:100]}... (truncated)"
        else:
            return f"{field_label}: {value}"
    
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