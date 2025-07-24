import logging
from datetime import datetime, timedelta
from odoo import models, api, fields
from odoo.http import request

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    """Enhanced res.users with multiple login hooks for reliable session creation"""
    _inherit = 'res.users'

    def _update_last_login(self):
        """Primary login hook - called during standard login process"""
        _logger.info(f"LOGIN_HOOK_1 - _update_last_login called for user {self.login}")
        
        result = super()._update_last_login()
        
        # Skip during module installation
        if self.env.context.get('module') or self.env.context.get('install_mode'):
            _logger.info("LOGIN_HOOK_1 - Skipping audit during module installation")
            return result
        
        try:
            self._create_audit_session_on_login()
        except Exception as e:
            _logger.error(f"LOGIN_HOOK_1 - Failed to track login for user {self.login}: {e}")
                
        return result

    @api.model
    def authenticate(self, db, login, password, user_agent_env=None):
        """Secondary login hook - called during authentication"""
        _logger.info(f"LOGIN_HOOK_2 - authenticate called for login {login}")
        
        try:
            # Call original authenticate
            result = super().authenticate(db, login, password, user_agent_env)
            
            if result:  # Successful authentication
                _logger.info(f"LOGIN_HOOK_2 - Authentication successful for user ID {result}")
                
                # Create session for authenticated user
                user = self.browse(result)
                if user.exists():
                    user._create_audit_session_on_login()
                    
            return result
            
        except Exception as e:
            _logger.error(f"LOGIN_HOOK_2 - Authentication hook failed: {e}")
            # Don't interfere with authentication, just log the error
            return super().authenticate(db, login, password, user_agent_env)

    def _create_audit_session_on_login(self):
        """Enhanced session creation with multiple fallback strategies"""
        
        # Quick table existence check with caching
        if not hasattr(self.env, '_audit_tables_checked'):
            try:
                self.env.cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'audit_session' LIMIT 1")
                self.env._audit_tables_exist = bool(self.env.cr.fetchone())
                self.env._audit_tables_checked = True
                _logger.info(f"LOGIN_CREATE - Audit tables exist: {self.env._audit_tables_exist}")
            except Exception as e:
                _logger.error(f"LOGIN_CREATE - Failed to check audit tables: {e}")
                self.env._audit_tables_exist = False
                self.env._audit_tables_checked = True

        if not self.env._audit_tables_exist:
            _logger.warning("LOGIN_CREATE - Audit tables do not exist, skipping session creation")
            return

        # Enhanced request context checking
        session_sid = None
        user_id = self.id
        
        _logger.info(f"LOGIN_CREATE - Starting session creation for user {self.login} (ID: {user_id})")
        
        # STRATEGY 1: Try to get session from current request
        if request and hasattr(request, 'session'):
            session_sid = getattr(request.session, 'sid', None)
            _logger.info(f"LOGIN_CREATE - STRATEGY 1: Got SID from request: {session_sid}")
        
        # STRATEGY 2: If no request context, try to find recent session
        if not session_sid:
            _logger.warning(f"LOGIN_CREATE - STRATEGY 2: No request context, looking for recent session")
            # Look for recent sessions for this user that might need to be activated
            recent_cutoff = datetime.now() - timedelta(minutes=5)
            recent_session = self.env['audit.session'].sudo().search([
                ('user_id', '=', user_id),
                ('login_time', '>=', recent_cutoff),
                ('status', 'in', ['active', 'logged_out'])
            ], order='login_time desc', limit=1)
            
            if recent_session:
                session_sid = recent_session.session_id
                _logger.info(f"LOGIN_CREATE - STRATEGY 2: Found recent session {recent_session.id} with SID {session_sid}")
        
        # STRATEGY 3: Generate emergency session ID if still none
        if not session_sid:
            import uuid
            session_sid = f"emergency_{uuid.uuid4().hex[:16]}"
            _logger.warning(f"LOGIN_CREATE - STRATEGY 3: Generated emergency SID: {session_sid}")

        try:
            # Create or update session
            new_session = self._handle_login_session_creation(user_id, session_sid)
            if new_session:
                _logger.info(f"LOGIN_CREATE - Successfully created/updated session {new_session.id} for user {self.login}")
                
                # CRITICAL: Ensure session is available for immediate use
                self.env.cr.commit()
                
                # Optional: Store session reference for later use
                if request and hasattr(request, 'session'):
                    request.session['audit_session_id'] = new_session.id
                    
            else:
                _logger.error(f"LOGIN_CREATE - Failed to create session for user {self.login}")
                
        except Exception as e:
            _logger.error(f"LOGIN_CREATE - Exception during session creation: {e}")
            import traceback
            _logger.error(f"LOGIN_CREATE - Traceback: {traceback.format_exc()}")

    def _handle_login_session_creation(self, user_id, session_sid):
        """Enhanced login session creation with comprehensive logic"""
        current_time = fields.Datetime.now()
        
        _logger.info(f"LOGIN_HANDLE - Processing login for user {user_id}, SID {session_sid}")
        
        try:
            # Clear caches for fresh data
            self.env.clear_caches()
            
            # ===== PHASE 1: Analyze existing sessions =====
            _logger.info(f"LOGIN_HANDLE - PHASE 1: Analyzing existing sessions")
            
            # Check for existing session with same SID
            existing_sid_sessions = self.env['audit.session'].sudo().search([
                ('session_id', '=', session_sid)
            ])
            
            _logger.info(f"LOGIN_HANDLE - Found {len(existing_sid_sessions)} sessions with SID {session_sid}")
            for session in existing_sid_sessions:
                _logger.info(f"LOGIN_HANDLE - Existing SID session {session.id}: "
                           f"User={session.user_id.id}, Status={session.status}, "
                           f"Login={session.login_time}")
            
            # Check for active sessions for this user
            active_user_sessions = self.env['audit.session'].sudo().search([
                ('user_id', '=', user_id),
                ('status', '=', 'active')
            ])
            
            _logger.info(f"LOGIN_HANDLE - Found {len(active_user_sessions)} active sessions for user {user_id}")
            for session in active_user_sessions:
                _logger.info(f"LOGIN_HANDLE - Active user session {session.id}: "
                           f"SID={session.session_id}, Login={session.login_time}")
            
            # ===== PHASE 2: Session reuse logic =====
            _logger.info(f"LOGIN_HANDLE - PHASE 2: Determining session strategy")
            
            # Strategy A: Reuse exact match (same SID, same user, active)
            exact_matches = [s for s in existing_sid_sessions 
                           if s.user_id.id == user_id and s.status == 'active']
            
            if exact_matches:
                session_to_update = exact_matches[0]
                _logger.info(f"LOGIN_HANDLE - STRATEGY A: Reusing exact match session {session_to_update.id}")
                
                # Update session with fresh login time and device info
                update_vals = {
                    'login_time': current_time,
                    'logout_time': False,
                    'status': 'active',
                    'error_message': False,
                    'last_activity': current_time,
                    'heartbeat_count': 0,
                    'browser_closed': False,
                }
                
                # Get fresh device info if available
                try:
                    request_info = self.env['audit.session'].extract_request_info(request)
                    update_vals.update(request_info)
                    _logger.info(f"LOGIN_HANDLE - Updated with fresh device info")
                except Exception as e:
                    _logger.warning(f"LOGIN_HANDLE - Could not get fresh device info: {e}")
                
                session_to_update.sudo().write(update_vals)
                self.env.cr.commit()
                
                return session_to_update
            
            # Strategy B: Reuse recent session with same SID (recently logged out)
            recent_logged_out = [s for s in existing_sid_sessions 
                               if s.user_id.id == user_id and s.status == 'logged_out' 
                               and s.logout_time and 
                               (current_time - s.logout_time).total_seconds() < 600]  # 10 minutes
            
            if recent_logged_out:
                session_to_reuse = recent_logged_out[0]
                _logger.info(f"LOGIN_HANDLE - STRATEGY B: Reusing recent logout session {session_to_reuse.id}")
                
                # Update with fresh info
                update_vals = {
                    'login_time': current_time,
                    'logout_time': False,
                    'status': 'active',
                    'error_message': False,
                    'last_activity': current_time,
                    'heartbeat_count': 0,
                    'browser_closed': False,
                }
                
                try:
                    request_info = self.env['audit.session'].extract_request_info(request)
                    update_vals.update(request_info)
                except Exception as e:
                    _logger.warning(f"LOGIN_HANDLE - Could not get device info: {e}")
                
                session_to_reuse.sudo().write(update_vals)
                self.env.cr.commit()
                
                return session_to_reuse
            
            # ===== PHASE 3: Handle conflicting sessions =====
            _logger.info(f"LOGIN_HANDLE - PHASE 3: Handling conflicting sessions")
            
            # Mark sessions with same SID but different user as replaced
            different_user_sessions = [s for s in existing_sid_sessions 
                                     if s.user_id.id != user_id]
            
            if different_user_sessions:
                _logger.warning(f"LOGIN_HANDLE - Found {len(different_user_sessions)} sessions with SID conflict")
                for session in different_user_sessions:
                    session.sudo().write({
                        'status': 'replaced',
                        'logout_time': current_time,
                        'error_message': f'Session SID conflict - replaced by user {user_id} at {current_time}'
                    })
                    _logger.warning(f"LOGIN_HANDLE - Marked session {session.id} as replaced (user conflict)")
            
            # Handle old active sessions for this user
            if active_user_sessions:
                _logger.info(f"LOGIN_HANDLE - Handling {len(active_user_sessions)} old active sessions")
                
                # Get timeout configuration
                timeout_hours = 24  # default
                try:
                    config = self.env['audit.config'].sudo().search([('active', '=', True)], limit=1)
                    if config and config.session_timeout_hours:
                        timeout_hours = config.session_timeout_hours
                except Exception as e:
                    _logger.warning(f"LOGIN_HANDLE - Could not get timeout config: {e}")
                
                cutoff_time = current_time - timedelta(hours=timeout_hours)
                
                for old_session in active_user_sessions:
                    if old_session.login_time < cutoff_time:
                        status = 'expired'
                        reason = f'Expired due to new login (timeout: {timeout_hours}h)'
                    else:
                        status = 'logged_out'
                        reason = 'Closed due to new login (new session started)'
                    
                    old_session.sudo().write({
                        'logout_time': current_time,
                        'status': status,
                        'error_message': reason,
                        'browser_closed': (status == 'logged_out')
                    })
                    
                    _logger.info(f"LOGIN_HANDLE - Closed old session {old_session.id} with status: {status}")
            
            # ===== PHASE 4: Create new session =====
            _logger.info(f"LOGIN_HANDLE - PHASE 4: Creating new session")
            
            new_session = self.env['audit.session'].sudo().create_session_for_login(
                user_id=user_id,
                session_id=session_sid,
                request_obj=request
            )
            
            if new_session:
                _logger.info(f"LOGIN_HANDLE - Successfully created new session {new_session.id}")
                return new_session
            else:
                _logger.error(f"LOGIN_HANDLE - Failed to create new session")
                return None
                
        except Exception as e:
            _logger.error(f"LOGIN_HANDLE - Critical error in session creation: {e}")
            import traceback
            _logger.error(f"LOGIN_HANDLE - Traceback: {traceback.format_exc()}")
            return None


class AuditSession(models.Model):
    """Enhanced Audit Session Model with login-specific creation"""
    _inherit = 'audit.session'

    @api.model
    def create_session_for_login(self, user_id, session_id, request_obj=None):
        """Specialized session creation method for login scenarios"""
        _logger.info(f"CREATE_LOGIN_SESSION - Starting for user {user_id}, session {session_id}")
        
        try:
            # Validate inputs
            if not user_id or not session_id:
                _logger.error(f"CREATE_LOGIN_SESSION - Invalid inputs: user_id={user_id}, session_id={session_id}")
                return None
            
            # Skip during module installation
            if self.env.context.get('module') or self.env.context.get('install_mode'):
                _logger.info("CREATE_LOGIN_SESSION - Skipping during module installation")
                return None
            
            # Double-check table existence
            try:
                self.env.cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'audit_session' LIMIT 1")
                if not self.env.cr.fetchone():
                    _logger.error("CREATE_LOGIN_SESSION - audit_session table does not exist")
                    return None
            except Exception as e:
                _logger.error(f"CREATE_LOGIN_SESSION - Table check failed: {e}")
                return None
            
            # Validate user exists
            user = self.env['res.users'].sudo().browse(user_id)
            if not user.exists():
                _logger.error(f"CREATE_LOGIN_SESSION - User {user_id} does not exist")
                return None
        
            # Extract comprehensive request information
            request_info = self._extract_enhanced_request_info(request_obj)
            _logger.info(f"CREATE_LOGIN_SESSION - Device info: {request_info.get('device_type')} | "
                       f"Browser: {request_info.get('browser')} | "
                       f"IP: {request_info.get('ip_address')} | "
                       f"Location: {request_info.get('city')}, {request_info.get('country')}")
            
            # Count concurrent sessions
            concurrent_count = self.sudo().search_count([
                ('user_id', '=', user_id),
                ('status', '=', 'active')
            ])
            
            # Prepare session values
            session_values = {
                'user_id': user_id,
                'session_id': session_id,
                'login_time': fields.Datetime.now(),
                'last_activity': fields.Datetime.now(),
                'status': 'active',
                'heartbeat_count': 0,
                'browser_closed': False,
                'concurrent_sessions': concurrent_count,
            }
            
            # Add device/request info
            session_values.update(request_info)
            
            _logger.info(f"CREATE_LOGIN_SESSION - Creating session with {len(session_values)} fields")
            
            # Create the session
            session = self.sudo().create(session_values)
            
            if session and session.id:
                _logger.info(f"CREATE_LOGIN_SESSION - Successfully created session {session.id}")
                
                # Immediate commit to ensure availability
                self.env.cr.commit()
                _logger.info(f"CREATE_LOGIN_SESSION - Session {session.id} committed to database")
                
                # Validate session was created
                validation_session = self.sudo().search([('id', '=', session.id)], limit=1)
                if validation_session:
                    _logger.info(f"CREATE_LOGIN_SESSION - Session {session.id} validated in database")
                else:
                    _logger.error(f"CREATE_LOGIN_SESSION - Session {session.id} not found after creation!")
                
                return session
            else:
                _logger.error(f"CREATE_LOGIN_SESSION - Session creation returned None or invalid ID")
                return None
                
        except Exception as e:
            _logger.error(f"CREATE_LOGIN_SESSION - Critical error: {e}")
            import traceback
            _logger.error(f"CREATE_LOGIN_SESSION - Traceback: {traceback.format_exc()}")
            
            # Rollback to prevent database corruption
            try:
                self.env.cr.rollback()
                _logger.info(f"CREATE_LOGIN_SESSION - Rolled back transaction after error")
            except Exception as rollback_error:
                _logger.error(f"CREATE_LOGIN_SESSION - Rollback failed: {rollback_error}")
            
            return None

    def _extract_enhanced_request_info(self, request_obj=None):
        """Enhanced request info extraction with better fallbacks"""
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
            # Try to get from provided request object
            if not request_obj:
                # Try to import and use current request
                try:
                    from odoo.http import request as current_request
                    request_obj = current_request
                except ImportError:
                    _logger.warning("CREATE_LOGIN_SESSION - Could not import request")
                except Exception as e:
                    _logger.warning(f"CREATE_LOGIN_SESSION - Could not get current request: {e}")
                    
            if request_obj and hasattr(request_obj, 'httprequest'):
                # Extract basic info
                try:
                    info['ip_address'] = getattr(request_obj.httprequest, 'remote_addr', 'unknown')
                    headers = getattr(request_obj.httprequest, 'headers', {})
                    info['user_agent'] = headers.get('User-Agent', '') if headers else ''
                    
                    _logger.debug(f"CREATE_LOGIN_SESSION - Extracted IP: {info['ip_address']}")
                    
                    # Parse user agent if available
                    if info['user_agent']:
                        device_info = self.parse_user_agent(info['user_agent'])
                        info.update(device_info)
                        _logger.debug(f"CREATE_LOGIN_SESSION - Parsed device: {device_info}")
                    
                    # Get location info if IP is valid
                    if info['ip_address'] and info['ip_address'] not in ['127.0.0.1', 'localhost', 'unknown']:
                        try:
                            location_info = self.get_location_from_ip(info['ip_address'])
                            info.update(location_info)
                            _logger.debug(f"CREATE_LOGIN_SESSION - Location: {location_info}")
                        except Exception as e:
                            _logger.debug(f"CREATE_LOGIN_SESSION - Location lookup failed: {e}")
                            
                except Exception as e:
                    _logger.warning(f"CREATE_LOGIN_SESSION - Request info extraction failed: {e}")
            else:
                _logger.warning("CREATE_LOGIN_SESSION - No valid request object for device info")
                
        except Exception as e:
            _logger.warning(f"CREATE_LOGIN_SESSION - Failed to extract request info: {e}")
            
        return info

    @api.model
    def emergency_session_creation(self, user_id):
        """Emergency session creation when normal flow fails"""
        _logger.warning(f"EMERGENCY_SESSION - Creating emergency session for user {user_id}")
        
        try:
            import uuid
            emergency_sid = f"emergency_{uuid.uuid4().hex[:16]}"
            
            emergency_session = self.sudo().create({
                'user_id': user_id,
                'session_id': emergency_sid,
                'login_time': fields.Datetime.now(),
                'last_activity': fields.Datetime.now(),
                'status': 'active',
                'heartbeat_count': 0,
                'browser_closed': False,
                'device_type': 'unknown',
                'browser': 'Unknown',
                'os': 'Unknown',
                'ip_address': 'unknown',
                'error_message': 'Emergency session created - normal session creation failed'
            })
            
            self.env.cr.commit()
            _logger.warning(f"EMERGENCY_SESSION - Created emergency session {emergency_session.id}")
            
            return emergency_session
            
        except Exception as e:
            _logger.error(f"EMERGENCY_SESSION - Failed to create emergency session: {e}")
            return None

    @api.model
    def validate_session_creation(self, user_id, session_sid):
        """Validate that session creation was successful"""
        try:
            # Look for session created in last 5 minutes
            recent_cutoff = fields.Datetime.now() - timedelta(minutes=5)
            
            session = self.sudo().search([
                ('user_id', '=', user_id),
                ('session_id', '=', session_sid),
                ('status', '=', 'active'),
                ('login_time', '>=', recent_cutoff)
            ], limit=1)
            
            if session:
                _logger.info(f"VALIDATE_SESSION - Found valid session {session.id} for user {user_id}")
                return session
            else:
                _logger.warning(f"VALIDATE_SESSION - No valid session found for user {user_id}, SID {session_sid}")
                
                # Try emergency creation
                return self.emergency_session_creation(user_id)
                
        except Exception as e:
            _logger.error(f"VALIDATE_SESSION - Validation failed: {e}")
            return None

    def action_force_close(self):
        """Manual action to force close a session"""
        for session in self:
            if session.status == 'active':
                session.write({
                    'status': 'forced_logout',
                    'logout_time': fields.Datetime.now(),
                    'error_message': f'Session manually closed by {self.env.user.name}'
                })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Sessions Closed',
                'message': f'{len(self)} session(s) have been forcefully closed.',
                'type': 'success'
            }
        }

    def get_session_stats(self):
        """Get session statistics for monitoring"""
        return {
            'total_sessions': self.search_count([]),
            'active_sessions': self.search_count([('status', '=', 'active')]),
            'expired_sessions': self.search_count([('status', '=', 'expired')]),
            'logged_out_sessions': self.search_count([('status', '=', 'logged_out')]),
            'error_sessions': self.search_count([('status', '=', 'error')]),
            'browser_closed_sessions': self.search_count([('browser_closed', '=', True)]),
        }
    
class AuditLoginAttempt(models.Model):
    """Track all login attempts for debugging"""
    _name = 'audit.login.attempt'
    _description = 'Audit Login Attempt'
    _order = 'attempt_time desc'

    user_id = fields.Many2one('res.users', 'User')
    login = fields.Char('Login')
    attempt_time = fields.Datetime('Attempt Time', default=fields.Datetime.now)
    success = fields.Boolean('Success')
    session_created = fields.Boolean('Session Created')
    session_id = fields.Many2one('audit.session', 'Created Session')
    error_message = fields.Text('Error Message')
    ip_address = fields.Char('IP Address')
    user_agent = fields.Text('User Agent')

    @api.model
    def log_login_attempt(self, login, user_id=None, success=False, session_created=False, 
                         session_id=None, error_message=None):
        """Log a login attempt for debugging purposes"""
        try:
            # Extract request info if available
            ip_address = 'unknown'
            user_agent = ''
            
            if request and hasattr(request, 'httprequest'):
                ip_address = getattr(request.httprequest, 'remote_addr', 'unknown')
                headers = getattr(request.httprequest, 'headers', {})
                user_agent = headers.get('User-Agent', '') if headers else ''
            
            attempt = self.create({
                'login': login,
                'user_id': user_id,
                'success': success,
                'session_created': session_created,
                'session_id': session_id,
                'error_message': error_message,
                'ip_address': ip_address,
                'user_agent': user_agent
            })
            
            _logger.info(f"LOGIN_ATTEMPT - Logged attempt {attempt.id}: "
                       f"Login={login}, Success={success}, SessionCreated={session_created}")
            
            return attempt
            
        except Exception as e:
            _logger.error(f"LOGIN_ATTEMPT - Failed to log attempt: {e}")
            return None