# -*- coding: utf-8 -*-
import logging
from odoo import http, fields
from odoo.http import request
from odoo.addons.web.controllers.main import Home, Session

_logger = logging.getLogger(__name__)


class EnhancedLoginController(Home):
    """Enhanced login controller with multiple session creation hooks"""

    @http.route('/web/login', type='http', auth="none")
    def web_login(self, redirect=None, **kw):
        """Enhanced web login with comprehensive session tracking"""
        _logger.info(f"ENHANCED_LOGIN - Login attempt started")
        
        # Log the login attempt
        if kw.get('login'):
            try:
                self.env['audit.login.attempt'].log_login_attempt(
                    login=kw.get('login'),
                    success=False,  # Will update later if successful
                    error_message="Login attempt started"
                )
            except Exception as e:
                _logger.warning(f"ENHANCED_LOGIN - Failed to log attempt: {e}")
        
        # Call the original login method
        response = super().web_login(redirect, **kw)
        
        # Check if login was successful
        if request.session.uid:
            try:
                _logger.info(f"ENHANCED_LOGIN - Login successful for user {request.session.uid}")
                
                # Ensure audit session is created
                self._ensure_audit_session_creation(request.session.uid)
                
                # Update login attempt record
                if kw.get('login'):
                    try:
                        user = request.env['res.users'].sudo().browse(request.session.uid)
                        session_created = self._check_session_creation(request.session.uid)
                        
                        self.env['audit.login.attempt'].log_login_attempt(
                            login=kw.get('login'),
                            user_id=request.session.uid,
                            success=True,
                            session_created=session_created,
                            error_message=None if session_created else "Session creation may have failed"
                        )
                    except Exception as e:
                        _logger.warning(f"ENHANCED_LOGIN - Failed to update login attempt: {e}")
                        
            except Exception as e:
                _logger.error(f"ENHANCED_LOGIN - Post-login processing failed: {e}")
        else:
            _logger.info(f"ENHANCED_LOGIN - Login failed or not completed")
            
            # Log failed attempt
            if kw.get('login'):
                try:
                    error_msg = "Login failed - invalid credentials or other error"
                    # Try to get more specific error from response
                    if hasattr(response, 'data') and 'error' in str(response.data):
                        error_msg = "Login failed - see response for details"
                    
                    self.env['audit.login.attempt'].log_login_attempt(
                        login=kw.get('login'),
                        success=False,
                        session_created=False,
                        error_message=error_msg
                    )
                except Exception as e:
                    _logger.warning(f"ENHANCED_LOGIN - Failed to log failed attempt: {e}")
        
        return response

    def _ensure_audit_session_creation(self, user_id):
        """Ensure audit session is created with multiple fallback strategies"""
        try:
            _logger.info(f"ENSURE_SESSION - Starting for user {user_id}")
            
            # Strategy 1: Try standard creation through user model
            user = request.env['res.users'].sudo().browse(user_id)
            if user.exists():
                _logger.info(f"ENSURE_SESSION - Attempting standard creation for {user.login}")
                user._create_audit_session_on_login()
                
                # Verify creation
                if self._check_session_creation(user_id):
                    _logger.info(f"ENSURE_SESSION - Standard creation successful")
                    return True
            
            # Strategy 2: Direct session creation
            _logger.warning(f"ENSURE_SESSION - Standard creation failed, trying direct creation")
            session_sid = getattr(request.session, 'sid', None)
            
            if session_sid:
                audit_session = request.env['audit.session'].sudo().create_session_for_login(
                    user_id=user_id,
                    session_id=session_sid,
                    request_obj=request
                )
                
                if audit_session:
                    _logger.info(f"ENSURE_SESSION - Direct creation successful: {audit_session.id}")
                    return True
            
            # Strategy 3: Emergency session creation
            _logger.error(f"ENSURE_SESSION - Direct creation failed, trying emergency creation")
            emergency_session = request.env['audit.session'].sudo().emergency_session_creation(user_id)
            
            if emergency_session:
                _logger.warning(f"ENSURE_SESSION - Emergency creation successful: {emergency_session.id}")
                return True
            
            _logger.error(f"ENSURE_SESSION - All strategies failed for user {user_id}")
            return False
            
        except Exception as e:
            _logger.error(f"ENSURE_SESSION - Critical error: {e}")
            import traceback
            _logger.error(f"ENSURE_SESSION - Traceback: {traceback.format_exc()}")
            return False

    def _check_session_creation(self, user_id):
        """Check if audit session was successfully created"""
        try:
            session_sid = getattr(request.session, 'sid', None)
            
            # Look for active session for this user
            session = request.env['audit.session'].sudo().search([
                ('user_id', '=', user_id),
                ('status', '=', 'active')
            ], limit=1)
            
            if session:
                _logger.info(f"CHECK_SESSION - Found active session {session.id} for user {user_id}")
                return True
            else:
                _logger.warning(f"CHECK_SESSION - No active session found for user {user_id}")
                return False
                
        except Exception as e:
            _logger.error(f"CHECK_SESSION - Error checking session: {e}")
            return False


class EnhancedSessionController(Session):
    """Enhanced session controller with audit session integration"""

    @http.route('/web/session/authenticate', type='json', auth="none")
    def authenticate(self, db, login, password, base_location=None):
        """Enhanced authentication with audit session creation"""
        _logger.info(f"SESSION_AUTH - Authentication request for login: {login}")
        
        # Call original authenticate
        result = super().authenticate(db, login, password, base_location)
        
        # If authentication successful, ensure audit session
        if result and result.get('uid'):
            try:
                _logger.info(f"SESSION_AUTH - Authentication successful for user {result['uid']}")
                
                # Ensure audit session creation
                controller = EnhancedLoginController()
                controller._ensure_audit_session_creation(result['uid'])
                
                # Add audit session info to result
                audit_session = request.env['audit.session'].sudo().search([
                    ('user_id', '=', result['uid']),
                    ('status', '=', 'active')
                ], limit=1)
                
                if audit_session:
                    result['audit_session_id'] = audit_session.id
                    _logger.info(f"SESSION_AUTH - Added audit session {audit_session.id} to result")
                else:
                    _logger.warning(f"SESSION_AUTH - No audit session found after creation")
                    
            except Exception as e:
                _logger.error(f"SESSION_AUTH - Failed to ensure audit session: {e}")
        
        return result

    @http.route('/web/session/get_session_info', type='json', auth="user")
    def get_session_info(self):
        """Enhanced session info including audit session details"""
        result = super().get_session_info()
        
        try:
            # Add audit session information
            user_id = request.env.user.id
            session_sid = getattr(request.session, 'sid', None)
            
            audit_session = request.env['audit.session'].search([
                ('user_id', '=', user_id),
                ('status', '=', 'active')
            ], limit=1)
            
            if audit_session:
                result['audit_session'] = {
                    'id': audit_session.id,
                    'session_id': audit_session.session_id,
                    'login_time': audit_session.login_time.isoformat() if audit_session.login_time else None,
                    'device_type': audit_session.device_type,
                    'browser': audit_session.browser,
                    'ip_address': audit_session.ip_address,
                    'country': audit_session.country,
                    'city': audit_session.city,
                    'heartbeat_count': audit_session.heartbeat_count,
                    'log_count': audit_session.log_count
                }
                _logger.debug(f"SESSION_INFO - Added audit session info for user {user_id}")
            else:
                result['audit_session'] = None
                _logger.warning(f"SESSION_INFO - No audit session found for user {user_id}")
            
        except Exception as e:
            _logger.error(f"SESSION_INFO - Failed to get audit session info: {e}")
            result['audit_session'] = None
        
        return result


class AuditSessionManagementController(http.Controller):
    """Controller for audit session management and fallback creation"""

    @http.route('/audit/session/create', type='json', auth='user', methods=['POST'])
    def create_audit_session(self, force=False):
        """Manual audit session creation endpoint"""
        try:
            user_id = request.env.user.id
            session_sid = getattr(request.session, 'sid', None)
            
            _logger.info(f"MANUAL_CREATE - Request to create session for user {user_id}, force={force}")
            
            # Check if session already exists
            if not force:
                existing_session = request.env['audit.session'].search([
                    ('user_id', '=', user_id),
                    ('status', '=', 'active')
                ], limit=1)
                
                if existing_session:
                    _logger.info(f"MANUAL_CREATE - Session already exists: {existing_session.id}")
                    return {
                        'success': True,
                        'session_id': existing_session.id,
                        'message': 'Session already exists',
                        'created': False
                    }
            
            # Create new session
            if session_sid:
                audit_session = request.env['audit.session'].sudo().create_session_for_login(
                    user_id=user_id,
                    session_id=session_sid,
                    request_obj=request
                )
                
                if audit_session:
                    _logger.info(f"MANUAL_CREATE - Successfully created session {audit_session.id}")
                    return {
                        'success': True,
                        'session_id': audit_session.id,
                        'message': 'Session created successfully',
                        'created': True
                    }
            
            # Fallback to emergency creation
            emergency_session = request.env['audit.session'].sudo().emergency_session_creation(user_id)
            
            if emergency_session:
                _logger.warning(f"MANUAL_CREATE - Created emergency session {emergency_session.id}")
                return {
                    'success': True,
                    'session_id': emergency_session.id,
                    'message': 'Emergency session created',
                    'created': True
                }
            
            _logger.error(f"MANUAL_CREATE - Failed to create any session for user {user_id}")
            return {
                'success': False,
                'message': 'Failed to create audit session',
                'error': 'All creation methods failed'
            }
            
        except Exception as e:
            _logger.error(f"MANUAL_CREATE - Error: {e}")
            return {
                'success': False,
                'message': 'Exception during session creation',
                'error': str(e)
            }

    @http.route('/audit/session/check', type='json', auth='user', methods=['POST'])
    def check_audit_session(self):
        """Check if audit session exists and is valid"""
        try:
            user_id = request.env.user.id
            session_sid = getattr(request.session, 'sid', None)
            
            # Look for active session
            active_session = request.env['audit.session'].search([
                ('user_id', '=', user_id),
                ('status', '=', 'active')
            ], limit=1)
            
            if active_session:
                return {
                    'exists': True,
                    'session_id': active_session.id,
                    'audit_session_sid': active_session.session_id,
                    'browser_session_sid': session_sid,
                    'sid_match': active_session.session_id == session_sid,
                    'login_time': active_session.login_time.isoformat() if active_session.login_time else None,
                    'heartbeat_count': active_session.heartbeat_count
                }
            else:
                return {
                    'exists': False,
                    'session_id': None,
                    'browser_session_sid': session_sid,
                    'message': 'No active audit session found'
                }
                
        except Exception as e:
            _logger.error(f"CHECK_SESSION - Error: {e}")
            return {
                'exists': False,
                'error': str(e)
            }

    @http.route('/audit/session/repair', type='json', auth='user', methods=['POST'])
    def repair_audit_session(self):
        """Repair or recreate audit session if missing"""
        try:
            user_id = request.env.user.id
            _logger.info(f"REPAIR_SESSION - Starting repair for user {user_id}")
            
            # Check current state
            check_result = self.check_audit_session()
            
            if check_result.get('exists'):
                return {
                    'success': True,
                    'action': 'no_repair_needed',
                    'session_id': check_result['session_id'],
                    'message': 'Session already exists and is valid'
                }
            
            # Attempt repair
            create_result = self.create_audit_session(force=True)
            
            if create_result.get('success'):
                _logger.info(f"REPAIR_SESSION - Successfully repaired session for user {user_id}")
                return {
                    'success': True,
                    'action': 'session_created',
                    'session_id': create_result['session_id'],
                    'message': 'Audit session repaired successfully'
                }
            else:
                _logger.error(f"REPAIR_SESSION - Failed to repair session for user {user_id}")
                return {
                    'success': False,
                    'action': 'repair_failed',
                    'message': 'Failed to repair audit session',
                    'error': create_result.get('error')
                }
                
        except Exception as e:
            _logger.error(f"REPAIR_SESSION - Error: {e}")
            return {
                'success': False,
                'action': 'repair_error',
                'error': str(e)
            }

    @http.route('/audit/login/attempts', type='json', auth='user', methods=['POST'])
    def get_login_attempts(self, limit=10):
        """Get recent login attempts for debugging"""
        try:
            if not request.env.user.has_group('peepl_audit_session.group_audit_manager'):
                return {'error': 'Access denied'}
            
            attempts = request.env['audit.login.attempt'].search([], 
                                                               order='attempt_time desc', 
                                                               limit=limit)
            
            result = []
            for attempt in attempts:
                result.append({
                    'id': attempt.id,
                    'login': attempt.login,
                    'user_id': attempt.user_id.id if attempt.user_id else None,
                    'user_name': attempt.user_id.name if attempt.user_id else None,
                    'attempt_time': attempt.attempt_time.isoformat() if attempt.attempt_time else None,
                    'success': attempt.success,
                    'session_created': attempt.session_created,
                    'session_id': attempt.session_id.id if attempt.session_id else None,
                    'error_message': attempt.error_message,
                    'ip_address': attempt.ip_address
                })
            
            return {'attempts': result}
            
        except Exception as e:
            _logger.error(f"GET_LOGIN_ATTEMPTS - Error: {e}")
            return {'error': str(e)}