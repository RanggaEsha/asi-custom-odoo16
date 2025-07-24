import logging
from datetime import datetime, timedelta
from odoo import models, api, fields
from odoo.http import request
from odoo.addons.web.controllers.main import Session

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    """Extend res.users to track login/logout with enhanced session management"""
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
        """Create audit session on login with comprehensive error handling"""
        
        # Quick check if audit tables exist
        if not hasattr(self.env, '_audit_tables_exist'):
            try:
                self.env.cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'audit_session' LIMIT 1")
                self.env._audit_tables_exist = bool(self.env.cr.fetchone())
                _logger.info(f"Audit tables exist: {self.env._audit_tables_exist}")
            except Exception as e:
                _logger.error(f"Failed to check audit tables: {e}")
                return

        if not self.env._audit_tables_exist:
            _logger.warning("Audit tables do not exist, skipping session creation")
            return

        # Check if we have request context
        if not request:
            _logger.warning("No request context available for session creation")
            return

        if not hasattr(request, 'session'):
            _logger.warning("No session object in request")
            return

        session_sid = getattr(request.session, 'sid', None)
        user_id = self.id

        _logger.info(f"LOGIN ATTEMPT - User {self.login} (ID: {user_id}) with SID: {session_sid}")

        if not session_sid:
            _logger.error(f"No session SID for user {self.login}")
            return

        # Enhanced session creation with better error handling
        try:
            new_session = self._handle_user_session_login(user_id, session_sid)
            if new_session:
                _logger.info(f"LOGIN SUCCESS - Created/updated session {new_session.id} for user {self.login}")
            else:
                _logger.error(f"LOGIN FAILED - No session created for user {self.login}")
        except Exception as e:
            _logger.error(f"LOGIN ERROR - Exception during session creation for user {self.login}: {e}")
            import traceback
            _logger.error(f"LOGIN ERROR - Traceback: {traceback.format_exc()}")

    def _handle_user_session_login(self, user_id, session_sid):
        """Enhanced session login handling with comprehensive logging"""
        current_time = fields.Datetime.now()
        
        _logger.info(f"HANDLE_LOGIN - Starting for user {user_id}, session {session_sid}")
        
        # CRITICAL: Clear caches to ensure fresh data
        self.env.clear_caches()
        
        try:
            # STEP 1: Check for ANY existing sessions with this session ID
            all_sessions_same_sid = self.env['audit.session'].sudo().search([
                ('session_id', '=', session_sid)
            ])
            
            _logger.info(f"HANDLE_LOGIN - Found {len(all_sessions_same_sid)} existing sessions with SID {session_sid}")
            
            if all_sessions_same_sid:
                # Log details of existing sessions
                for session in all_sessions_same_sid:
                    _logger.info(f"HANDLE_LOGIN - Existing session {session.id}: status={session.status}, user={session.user_id.id}, login={session.login_time}")
                
                # Check the status of existing sessions
                active_sessions = all_sessions_same_sid.filtered(lambda s: s.status == 'active')
                recent_logged_out = all_sessions_same_sid.filtered(
                    lambda s: s.status == 'logged_out' and s.logout_time and 
                             (current_time - s.logout_time).total_seconds() < 300  # Within 5 minutes
                )
                
                _logger.info(f"HANDLE_LOGIN - Active: {len(active_sessions)}, Recent logout: {len(recent_logged_out)}")
                
                if active_sessions:
                    # Reactivate existing active session
                    session_to_update = active_sessions[0]
                    _logger.info(f"HANDLE_LOGIN - Reactivating existing active session {session_to_update.id}")
                    
                    session_to_update.write({
                        'login_time': current_time,
                        'logout_time': False,
                        'status': 'active',
                        'error_message': False,
                        'last_activity': current_time,
                    })
                    self.env.cr.commit()
                    return session_to_update
                    
                elif recent_logged_out:
                    # Handle recently logged out session with same session ID
                    session_to_reuse = recent_logged_out[0]
                    _logger.info(f"HANDLE_LOGIN - Converting recently logged out session {session_to_reuse.id} to new login")
                    
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
                    
                    _logger.info(f"HANDLE_LOGIN - Successfully reused session {session_to_reuse.id}")
                    return session_to_reuse
                else:
                    # Old sessions with same SID but different status
                    _logger.info(f"HANDLE_LOGIN - Marking {len(all_sessions_same_sid)} old sessions as replaced")
                    all_sessions_same_sid.write({
                        'status': 'replaced',
                        'error_message': f'Session replaced by new login at {current_time}'
                    })
            
            # STEP 2: Handle old active sessions for this user (different session IDs)
            old_active_sessions = self.env['audit.session'].sudo().search([
                ('user_id', '=', user_id),
                ('status', '=', 'active'),
                ('session_id', '!=', session_sid)
            ])
            
            if old_active_sessions:
                _logger.info(f"HANDLE_LOGIN - Found {len(old_active_sessions)} old active sessions for user {user_id}")
                
                # Determine session timeout from config
                timeout_hours = 24  # default
                try:
                    config = self.env['audit.config'].sudo().search([('active', '=', True)], limit=1)
                    if config and config.session_timeout_hours:
                        timeout_hours = config.session_timeout_hours
                except Exception as e:
                    _logger.warning(f"Could not get config, using default timeout: {e}")
                
                cutoff_time = current_time - timedelta(hours=timeout_hours)
                
                for old_session in old_active_sessions:
                    if old_session.login_time < cutoff_time:
                        status = 'expired'
                        reason = f'Session expired due to new login (timeout: {timeout_hours}h)'
                    else:
                        status = 'logged_out'
                        reason = 'Session closed due to new login (likely browser close)'
                    
                    old_session.write({
                        'logout_time': current_time,
                        'status': status,
                        'error_message': reason,
                        'browser_closed': (status == 'logged_out')
                    })
                    
                    _logger.info(f"HANDLE_LOGIN - Closed old session {old_session.id} with status: {status}")
            
            # STEP 3: Create new session
            _logger.info(f"HANDLE_LOGIN - Creating new session for user {user_id}")
            new_session = self.env['audit.session'].sudo().create_session(
                user_id=user_id,
                session_id=session_sid,
                request_obj=request
            )
            
            if new_session:
                _logger.info(f"HANDLE_LOGIN - Successfully created new session {new_session.id}")
                return new_session
            else:
                _logger.error(f"HANDLE_LOGIN - Failed to create new session")
                return None
                
        except Exception as e:
            _logger.error(f"HANDLE_LOGIN - Critical error: {e}")
            import traceback
            _logger.error(f"HANDLE_LOGIN - Traceback: {traceback.format_exc()}")
            return None


class AuditSession(models.Model):
    """Enhanced Audit Session Model"""
    _inherit = 'audit.session'

    @api.model
    def create_session(self, user_id, session_id, request_obj=None):
        """Enhanced session creation with comprehensive error handling"""
        _logger.info(f"CREATE_SESSION - Starting for user {user_id}, session {session_id}")
        
        try:
            # Skip during module installation
            if self.env.context.get('module') or self.env.context.get('install_mode'):
                _logger.info("CREATE_SESSION - Skipping during module installation")
                return None
            
            # Double-check if audit tables exist
            try:
                self.env.cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'audit_session' LIMIT 1")
                if not self.env.cr.fetchone():
                    _logger.error("CREATE_SESSION - audit_session table does not exist")
                    return None
            except Exception as e:
                _logger.error(f"CREATE_SESSION - Error checking table existence: {e}")
                return None
        
            # Extract comprehensive request information
            try:
                request_info = self.extract_request_info(request_obj)
                _logger.info(f"CREATE_SESSION - Extracted request info: IP={request_info.get('ip_address')}, Device={request_info.get('device_type')}")
            except Exception as e:
                _logger.warning(f"CREATE_SESSION - Failed to extract request info: {e}")
                request_info = {
                    'ip_address': 'unknown',
                    'device_type': 'unknown',
                    'browser': 'Unknown',
                    'os': 'Unknown'
                }
            
            # Create session values
            values = {
                'user_id': user_id,
                'session_id': session_id,
                'login_time': fields.Datetime.now(),
                'last_activity': fields.Datetime.now(),
                'status': 'active',
                'heartbeat_count': 0,
                'browser_closed': False,
            }
            values.update(request_info)
            
            _logger.info(f"CREATE_SESSION - Creating session with values: {values}")
            
            # Create the session
            session = self.sudo().create(values)
            _logger.info(f"CREATE_SESSION - Successfully created session {session.id}")
            
            # Immediate commit to ensure availability
            self.env.cr.commit()
            _logger.info(f"CREATE_SESSION - Committed session {session.id} to database")
            
            return session
            
        except Exception as e:
            _logger.error(f"CREATE_SESSION - Critical error: {e}")
            import traceback
            _logger.error(f"CREATE_SESSION - Traceback: {traceback.format_exc()}")
            # Rollback to prevent database corruption
            try:
                self.env.cr.rollback()
            except:
                pass
            return None

    @api.model
    def cleanup_expired_sessions(self):
        """Enhanced cleanup with better session status detection"""
        try:
            from datetime import datetime, timedelta
            import logging
            _logger = logging.getLogger(__name__)
            
            # Get configuration
            config = self.env['audit.config'].search([('active', '=', True)], limit=1)
            timeout_hours = config.session_timeout_hours if config else 24
            
            current_time = datetime.now()
            cutoff_time = current_time - timedelta(hours=timeout_hours)
            cleanup_count = 0
            
            # 1. Mark expired sessions (older than timeout)
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
                cleanup_count += len(expired_sessions)
                _logger.info(f"Marked {len(expired_sessions)} sessions as expired")
            
            # 2. ENHANCED: Detect sessions that are likely browser-closed
            stale_cutoff = current_time - timedelta(minutes=30)
            stale_sessions = self.search([
                ('status', '=', 'active'),
                ('last_activity', '<', stale_cutoff),
                ('login_time', '>', cutoff_time)  # Not expired yet, but stale
            ])
            
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
                    cleanup_count += 1
                    _logger.info(f"Detected browser close for session {session.id}")
            
            # 3. Heartbeat-based cleanup
            if hasattr(self, 'last_activity'):  # Check if enhanced fields exist
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
                
                if heartbeat_cleanup_count > 0:
                    _logger.info(f"Heartbeat cleanup: closed {heartbeat_cleanup_count} stale sessions")
                    cleanup_count += heartbeat_cleanup_count
            
            _logger.info(f"Session cleanup completed: {cleanup_count} sessions processed")
            return cleanup_count
            
        except Exception as e:
            _logger.error(f"Failed to cleanup expired sessions: {e}")
            return 0

    @api.model
    def update_session_heartbeat(self, session_id=None):
        """Update session heartbeat to track activity"""
        try:
            if not session_id and request and hasattr(request, 'session'):
                session_id = getattr(request.session, 'sid', None)
                user_id = self.env.user.id
            
            if session_id:
                session = self.sudo().search([
                    ('session_id', '=', session_id),
                    ('status', '=', 'active')
                ], limit=1)
                
                if session:
                    session.write({
                        'last_activity': fields.Datetime.now(),
                        'heartbeat_count': session.heartbeat_count + 1
                    })
                    return True
            return False
            
        except Exception as e:
            _logger.debug(f"Failed to update session heartbeat: {e}")
            return False

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