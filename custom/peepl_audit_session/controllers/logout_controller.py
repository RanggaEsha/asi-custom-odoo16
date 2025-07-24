# -*- coding: utf-8 -*-
import logging
from odoo import http, fields
from odoo.http import request
from odoo.addons.web.controllers.main import Home

_logger = logging.getLogger(__name__)


class AuditLogoutController(Home):
    """
    Enhanced logout controller that can find sessions regardless of how they were created
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
        """Enhanced audit session logout tracking with multiple session finding strategies"""
        if not request or not hasattr(request, 'session'):
            return
            
        session_id = getattr(request.session, 'sid', None)
        user_id = getattr(request.session, 'uid', None)
        
        _logger.info(f"LOGOUT ATTEMPT - SID: {session_id}, User: {user_id}")
        
        if not session_id and not user_id:
            _logger.debug("No session ID or user ID found for logout tracking")
            return
            
        try:
            env = request.env
            env.clear_caches()  # Clear ORM caches
            
            # STRATEGY 1: Find by exact session ID match
            sessions_by_sid = []
            if session_id:
                sessions_by_sid = env['audit.session'].sudo().search([
                    ('session_id', '=', session_id),
                    ('status', '=', 'active')
                ])
                _logger.info(f"LOGOUT - Found {len(sessions_by_sid)} sessions by SID {session_id}")
            
            # STRATEGY 2: Find by user ID (for emergency-created sessions)
            sessions_by_user = []
            if user_id and not sessions_by_sid:
                sessions_by_user = env['audit.session'].sudo().search([
                    ('user_id', '=', user_id),
                    ('status', '=', 'active')
                ])
                _logger.info(f"LOGOUT - Found {len(sessions_by_user)} active sessions for user {user_id}")
            
            # STRATEGY 3: Find recent sessions for this user (last 1 hour)
            recent_sessions = []
            if not sessions_by_sid and not sessions_by_user and user_id:
                from datetime import datetime, timedelta
                recent_cutoff = datetime.now() - timedelta(hours=1)
                recent_sessions = env['audit.session'].sudo().search([
                    ('user_id', '=', user_id),
                    ('status', '=', 'active'),
                    ('login_time', '>=', recent_cutoff)
                ])
                _logger.info(f"LOGOUT - Found {len(recent_sessions)} recent sessions for user {user_id}")
            
            # Choose the best sessions to close
            sessions_to_close = sessions_by_sid or sessions_by_user or recent_sessions
            
            if sessions_to_close:
                logout_time = fields.Datetime.now()
                
                _logger.info(f"LOGOUT - Closing {len(sessions_to_close)} sessions")
                
                for session in sessions_to_close:
                    _logger.info(f"LOGOUT - Closing session {session.id} (SID: {session.session_id}, User: {session.user_id.id})")
                
                # Update sessions with logout info
                update_vals = {
                    'logout_time': logout_time,
                    'status': 'logged_out',
                    'error_message': f'User logout via UI at {logout_time} (found via {"SID" if sessions_by_sid else "user" if sessions_by_user else "recent"})'
                }
                
                sessions_to_close.sudo().write(update_vals)
                
                # CRITICAL: Force immediate commit
                env.cr.commit()
                
                _logger.info(f"LOGOUT TRACKED - {len(sessions_to_close)} sessions closed for user {user_id}")
                
                # Log the logout action
                self._log_logout_action(user_id, session_id, sessions_to_close[0].id)
                env.cr.commit()
                
            else:
                _logger.warning(f"LOGOUT - No active sessions found for SID {session_id} or user {user_id}")
                
                # Debug: Check what sessions exist
                if user_id:
                    all_user_sessions = env['audit.session'].sudo().search([
                        ('user_id', '=', user_id)
                    ], order='login_time desc', limit=5)
                    _logger.info(f"LOGOUT DEBUG - User {user_id} has {len(all_user_sessions)} total sessions:")
                    for session in all_user_sessions:
                        _logger.info(f"  Session {session.id}: SID={session.session_id}, Status={session.status}, Login={session.login_time}")
                
        except Exception as e:
            _logger.error(f"Failed to track audit logout: {e}")
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
            try:
                env.cr.rollback()
            except:
                pass
    
    def _log_logout_action(self, user_id, session_id, audit_session_id):
        """Log the logout action as an audit entry"""
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
                'context_info': f'User logged out from session {session_id} via UI'
            })
            
            _logger.debug(f"Logged logout action for user {user_id}: entry {log_entry.id}")
            
        except Exception as e:
            _logger.warning(f"Failed to log logout action: {e}")


# ADDITIONAL: Enhanced session close endpoint
from odoo.addons.web.controllers.main import Session as WebSession

class EnhancedWebSession(WebSession):
    """Enhanced web session controller to catch session destruction"""
    
    @http.route('/web/session/destroy', type='json', auth="user")
    def destroy(self):
        """Override session destroy to ensure logout tracking"""
        _logger.info("SESSION DESTROY - Called via /web/session/destroy")
        
        # Track logout before destroying session
        try:
            logout_controller = AuditLogoutController()
            logout_controller._track_audit_logout()
        except Exception as e:
            _logger.error(f"Failed to track logout in session destroy: {e}")
        
        # Call original destroy method
        return super().destroy()


# ADDITIONAL: JavaScript logout detection endpoint
class AuditJSController(http.Controller):
    """Controller for JavaScript-triggered logout detection"""
    
    @http.route('/audit/logout/detect', type='json', auth='user', methods=['POST'])
    def detect_logout(self):
        """Endpoint for JavaScript logout detection"""
        _logger.info("JS LOGOUT - Detected via JavaScript")
        
        try:
            logout_controller = AuditLogoutController()
            logout_controller._track_audit_logout()
            return {'success': True, 'message': 'Logout tracked'}
        except Exception as e:
            _logger.error(f"JS logout detection failed: {e}")
            return {'success': False, 'error': str(e)}