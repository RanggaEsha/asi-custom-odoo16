import logging
from odoo import http, fields
from odoo.http import request
from odoo.addons.web.controllers.main import Home

_logger = logging.getLogger(__name__)


class AuditLogoutController(Home):
    """
    Enhanced logout controller with comprehensive session finding and logging
    """

    @http.route('/web/login', type='http', auth="none")
    def web_login(self, redirect=None, **kw):
        """Override login route to ensure audit session creation"""
        response = super().web_login(redirect, **kw)
        
        # Check if login was successful
        if request.session.uid:
            try:
                _logger.info(f"WEB_LOGIN - Successful login detected for user {request.session.uid}")
                user = request.env['res.users'].sudo().browse(request.session.uid)
                if user.exists():
                    user._create_audit_session_on_login()
            except Exception as e:
                _logger.error(f"WEB_LOGIN - Failed to create audit session: {e}")
        
        return response

    def logout(self, redirect='/web/login'):
        """
        Override the core logout method to track audit session ending.
        """
        try:
            # Track logout BEFORE calling super().logout() which clears the session
            self._track_audit_logout()
        except Exception as e:
            # Don't let audit tracking failures break the logout process
            _logger.warning(f"Audit logout tracking failed: {e}")
        
        # Call the original logout method
        return super().logout(redirect)
    
    def _track_audit_logout(self):
        """ENHANCED audit session logout tracking with comprehensive logging and fallback strategies"""
        if not request or not hasattr(request, 'session'):
            _logger.warning("LOGOUT_TRACK - No request or session context available")
            return
            
        session_id = getattr(request.session, 'sid', None)
        user_id = getattr(request.session, 'uid', None)
        
        _logger.info(f"LOGOUT_TRACK - Starting logout tracking for SID: {session_id}, User: {user_id}")
        
        if not session_id and not user_id:
            _logger.warning("LOGOUT_TRACK - No session ID or user ID found for logout tracking")
            return
            
        try:
            env = request.env
            env.clear_caches()  # Clear ORM caches
            
            # ENHANCED LOGGING: Log all session search attempts and results
            all_sessions_found = []
            sessions_to_close = []
            
            # ===== STRATEGY 1: Find by exact session ID match =====
            _logger.info(f"LOGOUT_TRACK - STRATEGY 1: Searching by exact SID match: {session_id}")
            sessions_by_sid = []
            if session_id:
                sessions_by_sid = env['audit.session'].sudo().search([
                    ('session_id', '=', session_id),
                    ('status', '=', 'active')
                ])
                _logger.info(f"LOGOUT_TRACK - STRATEGY 1 RESULT: Found {len(sessions_by_sid)} sessions by SID {session_id}")
                for session in sessions_by_sid:
                    _logger.info(f"LOGOUT_TRACK - STRATEGY 1 SESSION: ID={session.id}, User={session.user_id.id}, Status={session.status}, Login={session.login_time}")
                    all_sessions_found.append(session)
            
            # ===== STRATEGY 2: Find by user ID for active sessions =====
            _logger.info(f"LOGOUT_TRACK - STRATEGY 2: Searching by user ID: {user_id}")
            sessions_by_user = []
            if user_id:
                sessions_by_user = env['audit.session'].sudo().search([
                    ('user_id', '=', user_id),
                    ('status', '=', 'active')
                ])
                _logger.info(f"LOGOUT_TRACK - STRATEGY 2 RESULT: Found {len(sessions_by_user)} active sessions for user {user_id}")
                for session in sessions_by_user:
                    _logger.info(f"LOGOUT_TRACK - STRATEGY 2 SESSION: ID={session.id}, SID={session.session_id}, Status={session.status}, Login={session.login_time}")
                    if session not in all_sessions_found:
                        all_sessions_found.append(session)
            
            # ===== STRATEGY 3: Find recent sessions for this user (last 2 hours) =====
            _logger.info(f"LOGOUT_TRACK - STRATEGY 3: Searching for recent sessions (last 2 hours) for user {user_id}")
            recent_sessions = []
            if user_id:
                from datetime import datetime, timedelta
                recent_cutoff = datetime.now() - timedelta(hours=2)
                recent_sessions = env['audit.session'].sudo().search([
                    ('user_id', '=', user_id),
                    ('status', '=', 'active'),
                    ('login_time', '>=', recent_cutoff)
                ])
                _logger.info(f"LOGOUT_TRACK - STRATEGY 3 RESULT: Found {len(recent_sessions)} recent sessions for user {user_id}")
                for session in recent_sessions:
                    _logger.info(f"LOGOUT_TRACK - STRATEGY 3 SESSION: ID={session.id}, SID={session.session_id}, Status={session.status}, Login={session.login_time}")
                    if session not in all_sessions_found:
                        all_sessions_found.append(session)
            
            # ===== STRATEGY 4: Find ANY sessions with matching session ID (regardless of status) =====
            _logger.info(f"LOGOUT_TRACK - STRATEGY 4: Searching for ANY sessions with SID {session_id} (any status)")
            any_sessions_same_sid = []
            if session_id:
                any_sessions_same_sid = env['audit.session'].sudo().search([
                    ('session_id', '=', session_id)
                ])
                _logger.info(f"LOGOUT_TRACK - STRATEGY 4 RESULT: Found {len(any_sessions_same_sid)} sessions with SID {session_id} (any status)")
                for session in any_sessions_same_sid:
                    _logger.info(f"LOGOUT_TRACK - STRATEGY 4 SESSION: ID={session.id}, User={session.user_id.id}, Status={session.status}, Login={session.login_time}, Logout={session.logout_time}")
                    if session not in all_sessions_found:
                        all_sessions_found.append(session)
            
            # ===== DECISION LOGIC: Choose the best sessions to close =====
            _logger.info(f"LOGOUT_TRACK - DECISION: Analyzing {len(all_sessions_found)} total sessions found")
            
            # Priority 1: Sessions with exact SID match and active status
            priority_1 = [s for s in sessions_by_sid if s.status == 'active']
            if priority_1:
                sessions_to_close = priority_1
                _logger.info(f"LOGOUT_TRACK - DECISION: Using PRIORITY 1 - {len(sessions_to_close)} exact SID active sessions")
            
            # Priority 2: If no exact SID match, use active sessions for this user
            elif sessions_by_user:
                sessions_to_close = sessions_by_user
                _logger.info(f"LOGOUT_TRACK - DECISION: Using PRIORITY 2 - {len(sessions_to_close)} active user sessions (SID mismatch)")
            
            # Priority 3: Recent sessions for this user
            elif recent_sessions:
                sessions_to_close = recent_sessions
                _logger.info(f"LOGOUT_TRACK - DECISION: Using PRIORITY 3 - {len(sessions_to_close)} recent user sessions")
            
            # ===== RECOMMENDATION 2: Force close ALL active sessions for user =====
            # Priority 4: EMERGENCY - Close ALL active sessions for this user
            elif user_id:
                _logger.warning(f"LOGOUT_TRACK - EMERGENCY: No suitable sessions found, closing ALL active sessions for user {user_id}")
                emergency_sessions = env['audit.session'].sudo().search([
                    ('user_id', '=', user_id),
                    ('status', '=', 'active')
                ])
                sessions_to_close = emergency_sessions
                _logger.warning(f"LOGOUT_TRACK - EMERGENCY: Found {len(sessions_to_close)} active sessions to force close")
                for session in sessions_to_close:
                    _logger.warning(f"LOGOUT_TRACK - EMERGENCY SESSION: ID={session.id}, SID={session.session_id}, Login={session.login_time}")
            
            # ===== EXECUTE SESSION CLOSURE =====
            if sessions_to_close:
                logout_time = fields.Datetime.now()
                
                _logger.info(f"LOGOUT_TRACK - EXECUTING: Closing {len(sessions_to_close)} sessions")
                
                for session in sessions_to_close:
                    _logger.info(f"LOGOUT_TRACK - CLOSING: Session {session.id} (SID: {session.session_id}, User: {session.user_id.id})")
                
                # Determine closure reason based on how sessions were found
                if sessions_by_sid:
                    closure_reason = f'User logout via UI (exact SID match)'
                elif sessions_by_user:
                    closure_reason = f'User logout via UI (SID mismatch, found by user ID)'
                elif recent_sessions:
                    closure_reason = f'User logout via UI (found via recent activity)'
                else:
                    closure_reason = f'User logout via UI (emergency closure - all active sessions)'
                
                # Update sessions with logout info
                update_vals = {
                    'logout_time': logout_time,
                    'status': 'logged_out',
                    'error_message': f'{closure_reason} at {logout_time}'
                }
                
                sessions_to_close.sudo().write(update_vals)
                
                # CRITICAL: Force immediate commit
                env.cr.commit()
                
                _logger.info(f"LOGOUT_TRACK - SUCCESS: {len(sessions_to_close)} sessions closed for user {user_id}")
                
                # Log the logout action
                self._log_logout_action(user_id, session_id, sessions_to_close[0].id, closure_reason)
                env.cr.commit()
                
            else:
                _logger.error(f"LOGOUT_TRACK - FAILURE: No sessions found to close for SID {session_id} or user {user_id}")
                
                # ===== COMPREHENSIVE DEBUG INFO =====
                self._log_debug_session_info(user_id, session_id, env)
                
        except Exception as e:
            _logger.error(f"LOGOUT_TRACK - CRITICAL ERROR: Failed to track audit logout: {e}")
            import traceback
            _logger.error(f"LOGOUT_TRACK - TRACEBACK: {traceback.format_exc()}")
            try:
                env.cr.rollback()
            except:
                pass
    
    def _log_debug_session_info(self, user_id, session_id, env):
        """Enhanced debug logging to understand session state"""
        try:
            _logger.error(f"LOGOUT_DEBUG - Starting comprehensive session analysis")
            
            if user_id:
                # Check ALL sessions for this user (any status)
                all_user_sessions = env['audit.session'].sudo().search([
                    ('user_id', '=', user_id)
                ], order='login_time desc', limit=10)
                _logger.error(f"LOGOUT_DEBUG - User {user_id} has {len(all_user_sessions)} total sessions:")
                for session in all_user_sessions:
                    _logger.error(f"LOGOUT_DEBUG - Session {session.id}: SID={session.session_id}, Status={session.status}, Login={session.login_time}, Logout={session.logout_time}")
                
                # Check for sessions with similar timestamps
                from datetime import datetime, timedelta
                recent_cutoff = datetime.now() - timedelta(minutes=10)
                recent_sessions = env['audit.session'].sudo().search([
                    ('user_id', '=', user_id),
                    ('login_time', '>=', recent_cutoff)
                ])
                _logger.error(f"LOGOUT_DEBUG - Recent sessions (last 10 min): {len(recent_sessions)}")
                
            if session_id:
                # Check for any sessions with this SID
                sid_sessions = env['audit.session'].sudo().search([
                    ('session_id', '=', session_id)
                ])
                _logger.error(f"LOGOUT_DEBUG - Sessions with SID {session_id}: {len(sid_sessions)}")
                for session in sid_sessions:
                    _logger.error(f"LOGOUT_DEBUG - SID Session {session.id}: User={session.user_id.id}, Status={session.status}")
                    
            # Check active sessions
            active_sessions = env['audit.session'].sudo().search([
                ('status', '=', 'active')
            ], limit=20)
            _logger.error(f"LOGOUT_DEBUG - Total active sessions in system: {len(active_sessions)}")
            
        except Exception as e:
            _logger.error(f"LOGOUT_DEBUG - Error during debug logging: {e}")
    
    def _log_logout_action(self, user_id, session_id, audit_session_id, closure_reason):
        """Enhanced logout action logging"""
        try:
            if not user_id:
                return
                
            env = request.env
            
            # Get the res.users model ID
            users_model = env['ir.model'].sudo().search([('model', '=', 'res.users')], limit=1)
            if not users_model:
                return
            
            # Create audit log entry for logout action
            log_entry = env['audit.log.entry'].sudo().create({
                'user_id': user_id,
                'session_id': audit_session_id,
                'model_id': users_model.id,
                'res_id': user_id,
                'res_name': f"User Logout",
                'action_type': 'write',
                'action_date': fields.Datetime.now(),
                'method': 'logout',
                'new_values': '{"session_status": "logged_out"}',
                'context_info': f'User logged out from session {session_id} via UI. Reason: {closure_reason}'
            })
            
            _logger.info(f"LOGOUT_TRACK - LOG_ACTION: Created audit entry {log_entry.id} for user {user_id}")
            
        except Exception as e:
            _logger.warning(f"LOGOUT_TRACK - LOG_ACTION_ERROR: Failed to log logout action: {e}")

class AuditJSController(http.Controller):
    """Enhanced controller for JavaScript-triggered logout detection"""
    
    @http.route('/audit/logout/detect', type='json', auth='user', methods=['POST'])
    def detect_logout(self):
        """Endpoint for JavaScript logout detection"""
        _logger.info("JS_LOGOUT - Detected via JavaScript /audit/logout/detect")
        
        try:
            logout_controller = AuditLogoutController()
            logout_controller._track_audit_logout()
            return {'success': True, 'message': 'Logout tracked via JS detection'}
        except Exception as e:
            _logger.error(f"JS_LOGOUT - Detection failed: {e}")
            return {'success': False, 'error': str(e)}
    
    @http.route('/audit/session/close/force', type='json', auth='user', methods=['POST'])
    def force_close_session(self, reason=None):
        """Force close current session endpoint"""
        _logger.info(f"FORCE_CLOSE - Called with reason: {reason}")
        
        try:
            session_id = getattr(request.session, 'sid', None)
            user_id = request.env.user.id
            
            if not session_id or not user_id:
                return {'success': False, 'message': 'No session or user context'}
            
            # Force close ALL active sessions for this user
            env = request.env
            active_sessions = env['audit.session'].sudo().search([
                ('user_id', '=', user_id),
                ('status', '=', 'active')
            ])
            
            _logger.info(f"FORCE_CLOSE - Found {len(active_sessions)} active sessions to close")
            
            if active_sessions:
                logout_time = fields.Datetime.now()
                force_reason = reason or 'Force close via API'
                
                active_sessions.sudo().write({
                    'logout_time': logout_time,
                    'status': 'forced_logout',
                    'error_message': f'{force_reason} at {logout_time}'
                })
                
                env.cr.commit()
                _logger.info(f"FORCE_CLOSE - Successfully closed {len(active_sessions)} sessions")
                
                return {
                    'success': True, 
                    'message': f'Force closed {len(active_sessions)} sessions',
                    'sessions_closed': len(active_sessions)
                }
            else:
                return {'success': False, 'message': 'No active sessions found to close'}
                
        except Exception as e:
            _logger.error(f"FORCE_CLOSE - Error: {e}")
            return {'success': False, 'error': str(e)}
    
    @http.route('/audit/session/heartbeat', type='json', auth='user', methods=['POST'])
    def session_heartbeat(self, timestamp=None, last_activity=None):
        """Enhanced session heartbeat endpoint"""
        try:
            session_id = getattr(request.session, 'sid', None)
            user_id = request.env.user.id
            
            if not session_id:
                return {'success': False, 'message': 'No session ID'}
            
            # Find and update session
            session = request.env['audit.session'].sudo().search([
                ('session_id', '=', session_id),
                ('user_id', '=', user_id),
                ('status', '=', 'active')
            ], limit=1)
            
            if session:
                session.write({
                    'last_activity': fields.Datetime.now(),
                    'heartbeat_count': session.heartbeat_count + 1
                })
                
                _logger.debug(f"HEARTBEAT - Updated session {session.id}, count: {session.heartbeat_count}")
                return {'success': True, 'heartbeat_count': session.heartbeat_count}
            else:
                _logger.warning(f"HEARTBEAT - No active session found for SID {session_id}, user {user_id}")
                return {'success': False, 'message': 'No active session found'}
                
        except Exception as e:
            _logger.error(f"HEARTBEAT - Error: {e}")
            return {'success': False, 'error': str(e)}
        

class AuditDebugController(http.Controller):
    """Debug controller for comprehensive session monitoring and troubleshooting"""

    @http.route('/audit/debug/log', type='json', auth='user', methods=['POST'])
    def debug_log(self, message=None, timestamp=None, user_agent=None, url=None):
        """Log debug information from JavaScript"""
        try:
            user_id = request.env.user.id
            session_id = getattr(request.session, 'sid', None)
            
            # Enhanced debug logging with context
            debug_context = {
                'user_id': user_id,
                'session_id': session_id,
                'user_agent': user_agent,
                'url': url,
                'timestamp': timestamp,
                'server_time': fields.Datetime.now().isoformat()
            }
            
            _logger.info(f"JS_DEBUG - {message} | Context: {debug_context}")
            
            # Store debug info in session for analysis
            if hasattr(request.session, 'audit_debug_logs'):
                request.session.audit_debug_logs.append(debug_context)
            else:
                request.session.audit_debug_logs = [debug_context]
            
            return {'success': True, 'logged_at': debug_context['server_time']}
            
        except Exception as e:
            _logger.error(f"JS_DEBUG - Failed to log debug info: {e}")
            return {'success': False, 'error': str(e)}

    @http.route('/audit/debug/session/info', type='json', auth='user', methods=['POST'])
    def get_session_debug_info(self):
        """Get comprehensive session debug information"""
        try:
            session_id = getattr(request.session, 'sid', None)
            user_id = request.env.user.id
            
            _logger.info(f"DEBUG_INFO - Request for user {user_id}, session {session_id}")
            
            debug_info = {
                'request_info': {
                    'session_sid': session_id,
                    'user_id': user_id,
                    'user_name': request.env.user.name,
                    'server_time': fields.Datetime.now().isoformat(),
                    'remote_addr': getattr(request.httprequest, 'remote_addr', 'unknown'),
                    'user_agent': request.httprequest.headers.get('User-Agent', '') if hasattr(request.httprequest, 'headers') else '',
                },
                'audit_sessions': [],
                'system_stats': {},
                'debug_logs': getattr(request.session, 'audit_debug_logs', [])
            }
            
            # Get all audit sessions for this user
            if user_id:
                user_sessions = request.env['audit.session'].search([
                    ('user_id', '=', user_id)
                ], order='login_time desc', limit=10)
                
                for session in user_sessions:
                    debug_info['audit_sessions'].append(session.get_session_debug_info())
            
            # Get system statistics
            debug_info['system_stats'] = self._get_system_stats()
            
            # Get current active session details
            if session_id:
                current_session = request.env['audit.session'].search([
                    ('session_id', '=', session_id),
                    ('user_id', '=', user_id),
                    ('status', '=', 'active')
                ], limit=1)
                
                if current_session:
                    debug_info['current_session'] = current_session.get_session_debug_info()
                else:
                    debug_info['current_session'] = None
                    _logger.warning(f"DEBUG_INFO - No active session found for SID {session_id}")
            
            return debug_info
            
        except Exception as e:
            _logger.error(f"DEBUG_INFO - Failed to get session debug info: {e}")
            return {'error': str(e)}

    @http.route('/audit/debug/session/search', type='json', auth='user', methods=['POST'])
    def search_sessions_debug(self, session_sid=None, user_id=None):
        """Search and analyze sessions for debugging"""
        try:
            _logger.info(f"DEBUG_SEARCH - Searching sessions: SID={session_sid}, User={user_id}")
            
            search_results = {
                'by_sid': [],
                'by_user': [],
                'recent_active': [],
                'analysis': {}
            }
            
            # Search by session ID
            if session_sid:
                sessions_by_sid = request.env['audit.session'].sudo().search([
                    ('session_id', '=', session_sid)
                ])
                search_results['by_sid'] = [s.get_session_debug_info() for s in sessions_by_sid]
                _logger.info(f"DEBUG_SEARCH - Found {len(sessions_by_sid)} sessions with SID {session_sid}")
            
            # Search by user ID
            if user_id:
                sessions_by_user = request.env['audit.session'].sudo().search([
                    ('user_id', '=', user_id)
                ], order='login_time desc', limit=20)
                search_results['by_user'] = [s.get_session_debug_info() for s in sessions_by_user]
                _logger.info(f"DEBUG_SEARCH - Found {len(sessions_by_user)} sessions for user {user_id}")
                
                # Get recent active sessions for this user
                from datetime import datetime, timedelta
                recent_cutoff = datetime.now() - timedelta(hours=2)
                recent_active = request.env['audit.session'].sudo().search([
                    ('user_id', '=', user_id),
                    ('status', '=', 'active'),
                    ('login_time', '>=', recent_cutoff)
                ])
                search_results['recent_active'] = [s.get_session_debug_info() for s in recent_active]
                
                # Analysis
                search_results['analysis'] = {
                    'total_sessions': len(sessions_by_user),
                    'active_sessions': len([s for s in sessions_by_user if s.status == 'active']),
                    'recent_active_sessions': len(recent_active),
                    'status_breakdown': {}
                }
                
                # Status breakdown
                for status in ['active', 'logged_out', 'expired', 'replaced', 'error']:
                    count = len([s for s in sessions_by_user if s.status == status])
                    search_results['analysis']['status_breakdown'][status] = count
            
            return search_results
            
        except Exception as e:
            _logger.error(f"DEBUG_SEARCH - Failed to search sessions: {e}")
            return {'error': str(e)}

    @http.route('/audit/debug/session/force_close', type='json', auth='user', methods=['POST'])
    def force_close_debug(self, session_ids=None, user_id=None, reason=None):
        """Force close sessions for debugging purposes"""
        try:
            if not request.env.user.has_group('peepl_audit_session.group_audit_manager'):
                return {'error': 'Access denied - Audit Manager role required'}
            
            reason = reason or 'Debug force close'
            closed_sessions = []
            
            # Close specific session IDs
            if session_ids:
                sessions = request.env['audit.session'].sudo().browse(session_ids)
                for session in sessions:
                    if session.status == 'active':
                        session.write({
                            'status': 'forced_logout',
                            'logout_time': fields.Datetime.now(),
                            'error_message': f'{reason} by {request.env.user.name}'
                        })
                        closed_sessions.append(session.id)
                        _logger.info(f"DEBUG_FORCE_CLOSE - Closed session {session.id}")
            
            # Close all sessions for a user
            elif user_id:
                active_sessions = request.env['audit.session'].sudo().search([
                    ('user_id', '=', user_id),
                    ('status', '=', 'active')
                ])
                for session in active_sessions:
                    session.write({
                        'status': 'forced_logout',
                        'logout_time': fields.Datetime.now(),
                        'error_message': f'{reason} by {request.env.user.name}'
                    })
                    closed_sessions.append(session.id)
                    _logger.info(f"DEBUG_FORCE_CLOSE - Closed user session {session.id}")
            
            return {
                'success': True,
                'closed_sessions': closed_sessions,
                'count': len(closed_sessions),
                'reason': reason
            }
            
        except Exception as e:
            _logger.error(f"DEBUG_FORCE_CLOSE - Failed to force close sessions: {e}")
            return {'error': str(e)}

    @http.route('/audit/debug/cleanup/run', type='json', auth='user', methods=['POST'])
    def run_cleanup_debug(self):
        """Run session cleanup manually for debugging"""
        try:
            if not request.env.user.has_group('peepl_audit_session.group_audit_manager'):
                return {'error': 'Access denied - Audit Manager role required'}
            
            _logger.info(f"DEBUG_CLEANUP - Manual cleanup requested by {request.env.user.name}")
            
            # Run enhanced cleanup
            cleanup_count = request.env['audit.session'].cleanup_expired_sessions_enhanced()
            
            return {
                'success': True,
                'cleanup_count': cleanup_count,
                'timestamp': fields.Datetime.now().isoformat()
            }
            
        except Exception as e:
            _logger.error(f"DEBUG_CLEANUP - Failed to run cleanup: {e}")
            return {'error': str(e)}

    @http.route('/audit/debug/test/endpoints', type='json', auth='user', methods=['POST'])
    def test_endpoints_debug(self):
        """Test all audit endpoints for connectivity"""
        try:
            test_results = {
                'endpoints': {},
                'timestamp': fields.Datetime.now().isoformat(),
                'user_id': request.env.user.id,
                'session_id': getattr(request.session, 'sid', None)
            }
            
            endpoints_to_test = [
                '/audit/session/info',
                '/audit/session/close',
                '/audit/logout/detect',
                '/web/session/destroy',
                '/audit/session/heartbeat'
            ]
            
            for endpoint in endpoints_to_test:
                try:
                    # Simple connectivity test
                    test_results['endpoints'][endpoint] = {
                        'status': 'reachable',
                        'tested_at': datetime.now().isoformat()
                    }
                    _logger.info(f"DEBUG_TEST - Endpoint {endpoint}: reachable")
                except Exception as e:
                    test_results['endpoints'][endpoint] = {
                        'status': 'error',
                        'error': str(e),
                        'tested_at': datetime.now().isoformat()
                    }
                    _logger.warning(f"DEBUG_TEST - Endpoint {endpoint}: error - {e}")
            
            return test_results
            
        except Exception as e:
            _logger.error(f"DEBUG_TEST - Failed to test endpoints: {e}")
            return {'error': str(e)}

    def _get_system_stats(self):
        """Get system-wide audit statistics"""
        try:
            stats = {}
            
            # Session counts by status
            for status in ['active', 'logged_out', 'expired', 'replaced', 'error']:
                stats[f'sessions_{status}'] = request.env['audit.session'].search_count([
                    ('status', '=', status)
                ])
            
            # Recent activity (last hour)
            from datetime import datetime, timedelta
            recent_cutoff = datetime.now() - timedelta(hours=1)
            stats['recent_logins'] = request.env['audit.session'].search_count([
                ('login_time', '>=', recent_cutoff)
            ])
            
            stats['recent_activity'] = request.env['audit.log.entry'].search_count([
                ('action_date', '>=', recent_cutoff)
            ])
            
            # Configuration info
            config = request.env['audit.config'].search([('active', '=', True)], limit=1)
            if config:
                stats['audit_config'] = {
                    'enabled': config.enable_auditing,
                    'session_timeout': config.session_timeout_hours,
                    'log_read': config.log_read,
                    'log_write': config.log_write,
                    'log_create': config.log_create,
                    'log_unlink': config.log_unlink
                }
            
            return stats
            
        except Exception as e:
            _logger.warning(f"Failed to get system stats: {e}")
            return {'error': str(e)}