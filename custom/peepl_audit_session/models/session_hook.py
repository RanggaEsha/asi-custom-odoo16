# Enhanced session_hook.py with better session management

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
        result = super()._update_last_login()
        
        # Skip during module installation
        if self.env.context.get('module') or self.env.context.get('install_mode'):
            return result
        
        if request and hasattr(request, 'session'):
            try:
                # Quick check if audit tables exist
                if not hasattr(self.env, '_audit_tables_exist'):
                    self.env.cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'audit_session' LIMIT 1")
                    self.env._audit_tables_exist = bool(self.env.cr.fetchone())
                
                if not self.env._audit_tables_exist:
                    return result
                
                session_sid = getattr(request.session, 'sid', None)
                user_id = self.id
                
                _logger.info(f"LOGIN - User {self.login} (ID: {user_id}) with SID: {session_sid}")
                
                if not session_sid:
                    _logger.warning(f"No session SID for user {self.login}")
                    return result
                
                # ENHANCED: Handle concurrent sessions and cleanup old ones
                self._handle_user_session_login(user_id, session_sid)
                    
            except Exception as e:
                _logger.error(f"Failed to track login for user {self.login}: {e}")
                
        return result

    def _handle_user_session_login(self, user_id, session_sid):
        """Enhanced session login handling with concurrent session management"""
        current_time = fields.Datetime.now()
        
        # STEP 1: Close any existing sessions for this specific session ID
        # This handles the case where the same session ID is reused
        existing_session_same_sid = self.env['audit.session'].sudo().search([
            ('session_id', '=', session_sid),
            ('status', '=', 'active')
        ])
        
        if existing_session_same_sid:
            _logger.info(f"LOGIN - Reactivating existing session {existing_session_same_sid.id}")
            # Update existing session instead of creating new one
            existing_session_same_sid.write({
                'login_time': current_time,
                'logout_time': False,
                'status': 'active',
                'error_message': False,
            })
            return existing_session_same_sid
        
        # STEP 2: Handle old sessions for this user
        old_active_sessions = self.env['audit.session'].sudo().search([
            ('user_id', '=', user_id),
            ('status', '=', 'active'),
            ('session_id', '!=', session_sid)
        ])
        
        if old_active_sessions:
            _logger.info(f"LOGIN - Found {len(old_active_sessions)} old active sessions for user {user_id}")
            
            # Determine session timeout from config
            timeout_hours = 24  # default
            config = self.env['audit.config'].sudo().search([('active', '=', True)], limit=1)
            if config and config.session_timeout_hours:
                timeout_hours = config.session_timeout_hours
            
            cutoff_time = current_time - timedelta(hours=timeout_hours)
            
            for old_session in old_active_sessions:
                # Determine how to close the old session based on age
                if old_session.login_time < cutoff_time:
                    # Session is old - mark as expired
                    status = 'expired'
                    reason = f'Session expired due to new login (timeout: {timeout_hours}h)'
                else:
                    # Session is recent - likely browser close without proper logout
                    status = 'logged_out'
                    reason = 'Session closed due to new login (likely browser close)'
                
                old_session.write({
                    'logout_time': current_time,
                    'status': status,
                    'error_message': reason
                })
                
                _logger.info(f"LOGIN - Closed old session {old_session.id} with status: {status}")
        
        # STEP 3: Create new session
        _logger.info(f"LOGIN - Creating new session for user {self.login}")
        new_session = self.env['audit.session'].sudo().create_session(
            user_id=user_id,
            session_id=session_sid,
            request_obj=request
        )
        
        if new_session:
            _logger.info(f"LOGIN - Created session {new_session.id}")
            return new_session
        else:
            _logger.error(f"LOGIN - Failed to create session")
            return None


class AuditSession(models.Model):
    """Enhanced Audit Session Model with better session lifecycle management"""
    _inherit = 'audit.session'

    # Add fields for better session tracking
    last_activity = fields.Datetime('Last Activity', default=fields.Datetime.now)
    heartbeat_count = fields.Integer('Heartbeat Count', default=0)
    browser_closed = fields.Boolean('Browser Closed Detected', default=False)
    concurrent_sessions = fields.Integer('Concurrent Sessions', 
                                       help="Number of concurrent sessions detected for this user")

    @api.model
    def cleanup_expired_sessions(self):
        """Enhanced cleanup with better session status detection"""
        try:
            # Get configuration
            config = self.env['audit.config'].search([('active', '=', True)], limit=1)
            timeout_hours = config.session_timeout_hours if config else 24
            
            current_time = datetime.now()
            cutoff_time = current_time - timedelta(hours=timeout_hours)
            
            # Find sessions that should be expired
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
                _logger.info(f"Marked {len(expired_sessions)} sessions as expired")
            
            # ENHANCED: Detect sessions that are likely browser-closed
            # Sessions active for more than 30 minutes without heartbeat updates
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
                    _logger.info(f"Detected browser close for session {session.id}")
            
            return len(expired_sessions) + len(stale_sessions)
            
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