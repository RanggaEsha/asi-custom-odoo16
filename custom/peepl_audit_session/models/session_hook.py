import logging
from datetime import datetime, timedelta
from odoo import models, api, fields
from odoo.http import request
from odoo.addons.web.controllers.main import Session

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    """Extend res.users to track login/logout with enhanced session management and comprehensive logging"""
    _inherit = 'res.users'

    def _update_last_login(self):
        """Override to track session start with improved session management"""
        _logger.info(f"_update_last_login called for user {self.login}")
        
        result = super()._update_last_login()
        
        # Skip during module installation
        if self.env.context.get('module') or self.env.context.get('install_mode'):
            _logger.info("Skipping audit during module installation")
            return result
        
        try:
            self._create_audit_session_on_login()
        except Exception as e:
            _logger.error(f"Failed to track login for user {self.login}: {e}")
                
        return result

    def _create_audit_session_on_login(self):
        """Create audit session on login with comprehensive error handling and enhanced logging"""
        
        # Quick check if audit tables exist
        if not hasattr(self.env, '_audit_tables_exist'):
            try:
                self.env.cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'audit_session' LIMIT 1")
                self.env._audit_tables_exist = bool(self.env.cr.fetchone())
                _logger.info(f"LOGIN_CREATE - Audit tables exist: {self.env._audit_tables_exist}")
            except Exception as e:
                _logger.error(f"LOGIN_CREATE - Failed to check audit tables: {e}")
                return

        if not self.env._audit_tables_exist:
            _logger.warning("LOGIN_CREATE - Audit tables do not exist, skipping session creation")
            return

        # Check if we have request context
        if not request:
            _logger.warning("LOGIN_CREATE - No request context available for session creation")
            return

        if not hasattr(request, 'session'):
            _logger.warning("LOGIN_CREATE - No session object in request")
            return

        session_sid = getattr(request.session, 'sid', None)
        user_id = self.id

        _logger.info(f"LOGIN_CREATE - User {self.login} (ID: {user_id}) with SID: {session_sid}")

        if not session_sid:
            _logger.error(f"LOGIN_CREATE - No session SID for user {self.login}")
            return

        # Enhanced session creation with comprehensive logging
        try:
            new_session = self._handle_user_session_login_enhanced(user_id, session_sid)
            if new_session:
                _logger.info(f"LOGIN_CREATE - Successfully created/updated session {new_session.id} for user {self.login}")
            else:
                _logger.error(f"LOGIN_CREATE - No session created for user {self.login}")
        except Exception as e:
            _logger.error(f"LOGIN_CREATE - Exception during session creation for user {self.login}: {e}")
            import traceback
            _logger.error(f"LOGIN_CREATE - Traceback: {traceback.format_exc()}")

    def _handle_user_session_login_enhanced(self, user_id, session_sid):
        """ENHANCED session login handling with comprehensive logging and multiple strategies"""
        current_time = fields.Datetime.now()
        
        _logger.info(f"LOGIN_HANDLE - Starting enhanced login handling for user {user_id}, session {session_sid}")
        
        # CRITICAL: Clear caches to ensure fresh data
        self.env.clear_caches()
        
        try:
            # ===== ENHANCED LOGGING: Log system state =====
            self._log_system_state("LOGIN_START", user_id, session_sid)
            
            # ===== STEP 1: Comprehensive existing session analysis =====
            _logger.info(f"LOGIN_HANDLE - STEP 1: Analyzing existing sessions")
            
            # Find ALL sessions with this session ID (any status, any user)
            all_sessions_same_sid = self.env['audit.session'].sudo().search([
                ('session_id', '=', session_sid)
            ])
            _logger.info(f"LOGIN_HANDLE - Found {len(all_sessions_same_sid)} total sessions with SID {session_sid}")
            
            for session in all_sessions_same_sid:
                _logger.info(f"LOGIN_HANDLE - Existing SID session {session.id}: "
                           f"User={session.user_id.id}, Status={session.status}, "
                           f"Login={session.login_time}, Logout={session.logout_time}")
            
            # Find ALL active sessions for this user (any session ID)
            all_user_active_sessions = self.env['audit.session'].sudo().search([
                ('user_id', '=', user_id),
                ('status', '=', 'active')
            ])
            _logger.info(f"LOGIN_HANDLE - Found {len(all_user_active_sessions)} active sessions for user {user_id}")
            
            for session in all_user_active_sessions:
                _logger.info(f"LOGIN_HANDLE - Active user session {session.id}: "
                           f"SID={session.session_id}, Login={session.login_time}")
            
            # ===== STEP 2: Smart session reuse logic =====
            _logger.info(f"LOGIN_HANDLE - STEP 2: Determining session reuse strategy")
            
            # Strategy A: Exact match (same SID, same user, active)
            exact_match_sessions = [s for s in all_sessions_same_sid 
                                   if s.user_id.id == user_id and s.status == 'active']
            
            if exact_match_sessions:
                session_to_reuse = exact_match_sessions[0]
                _logger.info(f"LOGIN_HANDLE - STRATEGY A: Reusing exact match session {session_to_reuse.id}")
                
                session_to_reuse.write({
                    'login_time': current_time,
                    'logout_time': False,
                    'status': 'active',
                    'error_message': False,
                    'last_activity': current_time,
                    'heartbeat_count': 0,
                    'browser_closed': False,
                })
                self.env.cr.commit()
                return session_to_reuse
            
            # Strategy B: Same SID, different user (session hijacking protection)
            different_user_sessions = [s for s in all_sessions_same_sid 
                                     if s.user_id.id != user_id]
            
            if different_user_sessions:
                _logger.warning(f"LOGIN_HANDLE - STRATEGY B: Session ID conflict detected! "
                              f"SID {session_sid} used by different users")
                for session in different_user_sessions:
                    _logger.warning(f"LOGIN_HANDLE - Conflicting session {session.id}: "
                                  f"User={session.user_id.id} (current: {user_id})")
                    session.write({
                        'status': 'replaced',
                        'logout_time': current_time,
                        'error_message': f'Session replaced due to user conflict at {current_time}'
                    })
            
            # Strategy C: Same SID, same user, but logged out (recent logout/login cycle)
            recent_logout_sessions = [s for s in all_sessions_same_sid 
                                    if s.user_id.id == user_id and s.status == 'logged_out' 
                                    and s.logout_time and 
                                    (current_time - s.logout_time).total_seconds() < 300]  # 5 minutes
            
            if recent_logout_sessions:
                session_to_reuse = recent_logout_sessions[0]
                _logger.info(f"LOGIN_HANDLE - STRATEGY C: Reusing recent logout session {session_to_reuse.id}")
                
                # Update with fresh device info
                request_info = self.env['audit.session'].extract_request_info(request)
                
                update_vals = {
                    'login_time': current_time,
                    'logout_time': False,
                    'status': 'active',
                    'error_message': False,
                    'last_activity': current_time,
                    'heartbeat_count': 0,
                    'browser_closed': False,
                }
                update_vals.update(request_info)
                
                session_to_reuse.write(update_vals)
                self.env.cr.commit()
                return session_to_reuse
            
            # ===== STEP 3: Handle old active sessions for this user =====
            _logger.info(f"LOGIN_HANDLE - STEP 3: Handling old active sessions")
            
            if all_user_active_sessions:
                _logger.info(f"LOGIN_HANDLE - Found {len(all_user_active_sessions)} old active sessions for user {user_id}")
                
                # Determine session timeout from config
                timeout_hours = 24  # default
                try:
                    config = self.env['audit.config'].sudo().search([('active', '=', True)], limit=1)
                    if config and config.session_timeout_hours:
                        timeout_hours = config.session_timeout_hours
                except Exception as e:
                    _logger.warning(f"LOGIN_HANDLE - Could not get config, using default timeout: {e}")
                
                cutoff_time = current_time - timedelta(hours=timeout_hours)
                
                for old_session in all_user_active_sessions:
                    if old_session.login_time < cutoff_time:
                        status = 'expired'
                        reason = f'Session expired due to new login (timeout: {timeout_hours}h)'
                    else:
                        status = 'logged_out'
                        reason = 'Session closed due to new login (likely new browser/tab)'
                    
                    old_session.write({
                        'logout_time': current_time,
                        'status': status,
                        'error_message': reason,
                        'browser_closed': (status == 'logged_out')
                    })
                    
                    _logger.info(f"LOGIN_HANDLE - Closed old session {old_session.id} with status: {status}")
            
            # ===== STEP 4: Create new session =====
            _logger.info(f"LOGIN_HANDLE - STEP 4: Creating new session for user {user_id}")
            new_session = self.env['audit.session'].sudo().create_session_enhanced(
                user_id=user_id,
                session_id=session_sid,
                request_obj=request
            )
            
            if new_session:
                _logger.info(f"LOGIN_HANDLE - Successfully created new session {new_session.id}")
                self._log_system_state("LOGIN_SUCCESS", user_id, session_sid, new_session.id)
                return new_session
            else:
                _logger.error(f"LOGIN_HANDLE - Failed to create new session")
                self._log_system_state("LOGIN_FAILURE", user_id, session_sid)
                return None
                
        except Exception as e:
            _logger.error(f"LOGIN_HANDLE - Critical error: {e}")
            import traceback
            _logger.error(f"LOGIN_HANDLE - Traceback: {traceback.format_exc()}")
            self._log_system_state("LOGIN_ERROR", user_id, session_sid, error=str(e))
            return None

    def _log_system_state(self, event, user_id, session_sid, session_id=None, error=None):
        """Log comprehensive system state for debugging"""
        try:
            state_info = {
                'event': event,
                'timestamp': fields.Datetime.now(),
                'user_id': user_id,
                'session_sid': session_sid,
                'session_id': session_id,
                'error': error
            }
            
            # Count sessions by status
            if user_id:
                session_counts = {}
                for status in ['active', 'logged_out', 'expired', 'replaced', 'error']:
                    count = self.env['audit.session'].sudo().search_count([
                        ('user_id', '=', user_id),
                        ('status', '=', status)
                    ])
                    session_counts[status] = count
                
                state_info['user_session_counts'] = session_counts
            
            # Total system sessions
            total_active = self.env['audit.session'].sudo().search_count([('status', '=', 'active')])
            state_info['total_active_sessions'] = total_active
            
            _logger.info(f"SYSTEM_STATE - {event}: {state_info}")
            
        except Exception as e:
            _logger.warning(f"SYSTEM_STATE - Failed to log state: {e}")


class AuditSession(models.Model):
    """Enhanced Audit Session Model with comprehensive logging"""
    _inherit = 'audit.session'

    @api.model
    def create_session_enhanced(self, user_id, session_id, request_obj=None):
        """Enhanced session creation with comprehensive error handling and logging"""
        _logger.info(f"CREATE_SESSION_ENHANCED - Starting for user {user_id}, session {session_id}")
        
        try:
            # Skip during module installation
            if self.env.context.get('module') or self.env.context.get('install_mode'):
                _logger.info("CREATE_SESSION_ENHANCED - Skipping during module installation")
                return None
            
            # Double-check if audit tables exist
            try:
                self.env.cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'audit_session' LIMIT 1")
                if not self.env.cr.fetchone():
                    _logger.error("CREATE_SESSION_ENHANCED - audit_session table does not exist")
                    return None
            except Exception as e:
                _logger.error(f"CREATE_SESSION_ENHANCED - Error checking table existence: {e}")
                return None
        
            # Extract comprehensive request information
            try:
                request_info = self.extract_request_info(request_obj)
                _logger.info(f"CREATE_SESSION_ENHANCED - Extracted request info: "
                           f"IP={request_info.get('ip_address')}, "
                           f"Device={request_info.get('device_type')}, "
                           f"Browser={request_info.get('browser')}, "
                           f"OS={request_info.get('os')}, "
                           f"Country={request_info.get('country')}")
            except Exception as e:
                _logger.warning(f"CREATE_SESSION_ENHANCED - Failed to extract request info: {e}")
                request_info = {
                    'ip_address': 'unknown',
                    'device_type': 'unknown',
                    'browser': 'Unknown',
                    'os': 'Unknown'
                }
            
            # Check for concurrent sessions
            concurrent_sessions = self.sudo().search_count([
                ('user_id', '=', user_id),
                ('status', '=', 'active')
            ])
            
            # Create session values
            values = {
                'user_id': user_id,
                'session_id': session_id,
                'login_time': fields.Datetime.now(),
                'last_activity': fields.Datetime.now(),
                'status': 'active',
                'heartbeat_count': 0,
                'browser_closed': False,
                'concurrent_sessions': concurrent_sessions,
            }
            values.update(request_info)
            
            _logger.info(f"CREATE_SESSION_ENHANCED - Creating session with {len(values)} fields")
            _logger.debug(f"CREATE_SESSION_ENHANCED - Session values: {values}")
            
            # Create the session
            session = self.sudo().create(values)
            _logger.info(f"CREATE_SESSION_ENHANCED - Successfully created session {session.id}")
            
            # Immediate commit to ensure availability
            self.env.cr.commit()
            _logger.info(f"CREATE_SESSION_ENHANCED - Committed session {session.id} to database")
            
            return session
            
        except Exception as e:
            _logger.error(f"CREATE_SESSION_ENHANCED - Critical error: {e}")
            import traceback
            _logger.error(f"CREATE_SESSION_ENHANCED - Traceback: {traceback.format_exc()}")
            # Rollback to prevent database corruption
            try:
                self.env.cr.rollback()
            except:
                pass
            return None

    @api.model
    def cleanup_expired_sessions_enhanced(self):
        """Enhanced cleanup with comprehensive logging and better session status detection"""
        try:
            from datetime import datetime, timedelta
            import logging
            _logger = logging.getLogger(__name__)
            
            cleanup_start_time = datetime.now()
            _logger.info(f"CLEANUP_ENHANCED - Starting session cleanup at {cleanup_start_time}")
            
            # Get configuration
            config = self.env['audit.config'].search([('active', '=', True)], limit=1)
            timeout_hours = config.session_timeout_hours if config else 24
            _logger.info(f"CLEANUP_ENHANCED - Using timeout: {timeout_hours} hours")
            
            current_time = datetime.now()
            cutoff_time = current_time - timedelta(hours=timeout_hours)
            total_cleanup_count = 0
            
            # ===== CLEANUP PHASE 1: Mark expired sessions =====
            _logger.info(f"CLEANUP_ENHANCED - PHASE 1: Marking expired sessions (older than {timeout_hours}h)")
            expired_sessions = self.search([
                ('status', '=', 'active'),
                ('login_time', '<', cutoff_time)
            ])
            
            if expired_sessions:
                expired_sessions.write({
                    'status': 'expired',
                    'logout_time': fields.Datetime.now(),
                    'error_message': f'Session expired after {timeout_hours} hours of inactivity'
                })
                total_cleanup_count += len(expired_sessions)
                _logger.info(f"CLEANUP_ENHANCED - PHASE 1: Marked {len(expired_sessions)} sessions as expired")
                
                for session in expired_sessions:
                    _logger.debug(f"CLEANUP_ENHANCED - Expired session {session.id}: "
                                f"User={session.user_id.id}, Login={session.login_time}")
            
            # ===== CLEANUP PHASE 2: Detect browser-closed sessions =====
            _logger.info(f"CLEANUP_ENHANCED - PHASE 2: Detecting browser-closed sessions")
            stale_cutoff = current_time - timedelta(minutes=30)
            stale_sessions = self.search([
                ('status', '=', 'active'),
                ('last_activity', '<', stale_cutoff),
                ('login_time', '>', cutoff_time)  # Not expired yet, but stale
            ])
            
            browser_close_count = 0
            for session in stale_sessions:
                # Check if user has newer active sessions
                newer_sessions = self.search([
                    ('user_id', '=', session.user_id.id),
                    ('status', '=', 'active'),
                    ('login_time', '>', session.login_time),
                    ('id', '!=', session.id)
                ])
                
                if newer_sessions:
                    # User has newer session, mark this as browser closed
                    session.write({
                        'status': 'logged_out',
                        'logout_time': fields.Datetime.now(),
                        'browser_closed': True,
                        'error_message': 'Session closed due to browser close (detected via new session)'
                    })
                    browser_close_count += 1
                    total_cleanup_count += 1
                    _logger.debug(f"CLEANUP_ENHANCED - Browser close detected for session {session.id}")
            
            if browser_close_count > 0:
                _logger.info(f"CLEANUP_ENHANCED - PHASE 2: Detected {browser_close_count} browser-closed sessions")
            
            # ===== CLEANUP PHASE 3: Heartbeat-based cleanup =====
            _logger.info(f"CLEANUP_ENHANCED - PHASE 3: Heartbeat-based cleanup")
            heartbeat_cutoff = current_time - timedelta(hours=1)
            stale_heartbeat_sessions = self.search([
                ('status', '=', 'active'),
                ('last_activity', '<', heartbeat_cutoff),
                ('heartbeat_count', '>', 0)  # Had heartbeats before
            ])
            
            heartbeat_cleanup_count = 0
            for session in stale_heartbeat_sessions:
                # Check if this is really a browser close vs network issue
                time_since_activity = current_time - session.last_activity
                
                if time_since_activity.total_seconds() > 3600:  # 1 hour
                    session.write({
                        'status': 'logged_out',
                        'logout_time': fields.Datetime.now(),
                        'browser_closed': True,
                        'error_message': f'No heartbeat for {int(time_since_activity.total_seconds()/60)} minutes'
                    })
                    heartbeat_cleanup_count += 1
                    total_cleanup_count += 1
            
            if heartbeat_cleanup_count > 0:
                _logger.info(f"CLEANUP_ENHANCED - PHASE 3: Heartbeat cleanup closed {heartbeat_cleanup_count} stale sessions")
            
            # ===== CLEANUP PHASE 4: Database maintenance =====
            _logger.info(f"CLEANUP_ENHANCED - PHASE 4: Database maintenance")
            very_old_cutoff = current_time - timedelta(days=90)
            very_old_sessions = self.search([
                ('login_time', '<', very_old_cutoff),
                ('status', 'in', ['logged_out', 'expired', 'replaced'])
            ])
            
            maintenance_count = 0
            if len(very_old_sessions) > 1000:  # Only if too many old records
                # Delete oldest first, keep some for historical data
                to_delete = very_old_sessions.sorted('login_time')[:500]
                maintenance_count = len(to_delete)
                to_delete.unlink()
                _logger.info(f"CLEANUP_ENHANCED - PHASE 4: Deleted {maintenance_count} very old session records")
            
            # ===== CLEANUP SUMMARY =====
            cleanup_end_time = datetime.now()
            cleanup_duration = (cleanup_end_time - cleanup_start_time).total_seconds()
            
            _logger.info(f"CLEANUP_ENHANCED - COMPLETED: Processed {total_cleanup_count} sessions in {cleanup_duration:.2f} seconds")
            _logger.info(f"CLEANUP_ENHANCED - SUMMARY: Expired={len(expired_sessions)}, "
                       f"BrowserClose={browser_close_count}, Heartbeat={heartbeat_cleanup_count}, "
                       f"Maintenance={maintenance_count}")
            
            return total_cleanup_count
            
        except Exception as e:
            _logger.error(f"CLEANUP_ENHANCED - Failed to cleanup expired sessions: {e}")
            import traceback
            _logger.error(f"CLEANUP_ENHANCED - Traceback: {traceback.format_exc()}")
            return 0

    @api.model
    def update_session_heartbeat_enhanced(self, session_id=None):
        """Enhanced session heartbeat with comprehensive logging"""
        try:
            if not session_id and request and hasattr(request, 'session'):
                session_id = getattr(request.session, 'sid', None)
                user_id = self.env.user.id
                _logger.debug(f"HEARTBEAT_ENHANCED - Using request session: SID={session_id}, User={user_id}")
            
            if session_id:
                session = self.sudo().search([
                    ('session_id', '=', session_id),
                    ('status', '=', 'active')
                ], limit=1)
                
                if session:
                    old_count = session.heartbeat_count
                    session.write({
                        'last_activity': fields.Datetime.now(),
                        'heartbeat_count': session.heartbeat_count + 1
                    })
                    _logger.debug(f"HEARTBEAT_ENHANCED - Updated session {session.id}: "
                                f"count {old_count} -> {session.heartbeat_count}")
                    return True
                else:
                    _logger.warning(f"HEARTBEAT_ENHANCED - No active session found for SID {session_id}")
                    return False
            else:
                _logger.warning(f"HEARTBEAT_ENHANCED - No session ID provided")
                return False
            
        except Exception as e:
            _logger.error(f"HEARTBEAT_ENHANCED - Failed to update heartbeat: {e}")
            return False

    def get_session_debug_info(self):
        """Get comprehensive debug information about sessions"""
        try:
            debug_info = {
                'session_id': self.id,
                'user_id': self.user_id.id,
                'user_name': self.user_id.name,
                'session_sid': self.session_id,
                'status': self.status,
                'login_time': self.login_time,
                'logout_time': self.logout_time,
                'last_activity': self.last_activity,
                'heartbeat_count': self.heartbeat_count,
                'browser_closed': self.browser_closed,
                'concurrent_sessions': self.concurrent_sessions,
                'ip_address': self.ip_address,
                'device_type': self.device_type,
                'browser': self.browser,
                'os': self.os,
                'country': self.country,
                'log_count': self.log_count,
                'error_message': self.error_message,
            }
            
            return debug_info
            
        except Exception as e:
            _logger.error(f"Failed to get session debug info: {e}")
            return {'error': str(e)}

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