# -*- coding: utf-8 -*-
import logging
from odoo import http, fields
from odoo.http import request
from odoo.addons.web.controllers.main import Home

_logger = logging.getLogger(__name__)


class AuditLogoutController(Home):
    """
    Override Odoo's core logout method to track session endings.
    This ensures audit tracking works regardless of how logout is triggered.
    """
    
    def logout(self, redirect='/web'):
        """
        Override the core logout method to track audit session ending.
        This method is called by Odoo's standard logout flow via JSON-RPC.
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
        """Track audit session logout"""
        if not request or not hasattr(request, 'session'):
            return
            
        session_id = getattr(request.session, 'sid', None)
        user_id = getattr(request.session, 'uid', None)
        
        if not session_id:
            _logger.debug("No session ID found for logout tracking")
            return
            
        try:
            # Find active audit sessions for this web session
            env = request.env
            active_sessions = env['audit.session'].sudo().search([
                ('session_id', '=', session_id),
                ('status', '=', 'active')
            ])
            
            if active_sessions:
                # Update all active sessions to logged_out status
                logout_time = fields.Datetime.now()
                active_sessions.sudo().write({
                    'logout_time': logout_time,
                    'status': 'logged_out'
                })
                
                _logger.info(f"User logout tracked: closed {len(active_sessions)} audit sessions for session {session_id}")
                
                # Log the logout action itself as an audit entry
                self._log_logout_action(user_id, session_id, active_sessions[0].id if active_sessions else None)
                
            else:
                _logger.debug(f"No active audit sessions found for logout of session {session_id}")
                
        except Exception as e:
            _logger.error(f"Failed to track audit logout for session {session_id}: {e}")
    
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
            env['audit.log.entry'].sudo().create({
                'user_id': user_id,
                'session_id': audit_session_id,
                'model_id': users_model.id,
                'res_id': user_id,
                'res_name': f"User Logout",
                'action_type': 'write',  # Logout is essentially a session state change
                'action_date': fields.Datetime.now(),
                'method': 'logout',
                'new_values': '{"session_status": "logged_out"}',
                'context_info': f'User logged out from session {session_id}'
            })
            
            _logger.debug(f"Logged logout action for user {user_id}")
            
        except Exception as e:
            _logger.warning(f"Failed to log logout action: {e}")