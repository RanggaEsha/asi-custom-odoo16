# -*- coding: utf-8 -*-

import logging
from odoo import models, api, fields
from odoo.http import request
from odoo.addons.web.controllers.main import Session

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    """Extend res.users to track login/logout"""
    _inherit = 'res.users'

    def _update_last_login(self):
        """Override to track session start"""
        result = super()._update_last_login()
        
        # Skip during module installation
        if self.env.context.get('module') or self.env.context.get('install_mode'):
            return result
        
        # Create or update audit session if we have request context
        if request and hasattr(request, 'session'):
            try:
                # Quick check if audit tables exist
                if not hasattr(self.env, '_audit_tables_exist'):
                    self.env.cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'audit_session' LIMIT 1")
                    self.env._audit_tables_exist = bool(self.env.cr.fetchone())
                
                if not self.env._audit_tables_exist:
                    return result
                
                # FIXED: Better session creation/update logic
                session_id = getattr(request.session, 'sid', None)
                if session_id:
                    existing_session = self.env['audit.session'].sudo().search([
                        ('session_id', '=', session_id),
                        ('user_id', '=', self.id),
                        ('status', '=', 'active')
                    ], limit=1)
                    
                    if not existing_session:
                        # Create new session
                        self.env['audit.session'].sudo().create_session(
                            user_id=self.id,
                            session_id=session_id,
                            request_obj=request
                        )
                        _logger.info(f"Created audit session for user {self.login}: {session_id}")
                    else:
                        # Update existing session login time
                        existing_session.sudo().write({
                            'login_time': fields.Datetime.now(),
                            'status': 'active'
                        })
                        _logger.info(f"Updated audit session for user {self.login}: {session_id}")
                    
            except Exception as e:
                _logger.debug(f"Failed to track login for user {self.login}: {e}")
                
        return result

    @api.model
    def check_credentials(self, password):
        """Override to enhance security tracking"""
        try:
            result = super().check_credentials(password)
            return result
        except Exception as e:
            # Skip during module installation
            if self.env.context.get('module') or self.env.context.get('install_mode'):
                raise
                
            # Log failed login attempt (simplified)
            if request and hasattr(request, 'session'):
                try:
                    if hasattr(self.env, '_audit_tables_exist') and self.env._audit_tables_exist:
                        session_id = getattr(request.session, 'sid', 'unknown')
                        self.env['audit.session'].sudo().create({
                            'user_id': self.id,
                            'session_id': session_id,
                            'login_time': fields.Datetime.now(),
                            'status': 'error',
                            'error_message': f"Login failed: {str(e)[:100]}",  # Limit error message length
                            'ip_address': request.httprequest.remote_addr if request.httprequest else None,
                        })
                except Exception as audit_error:
                    _logger.debug(f"Failed to log failed login attempt: {audit_error}")
            raise


class IrHttp(models.AbstractModel):
    """FIXED: Add session logout tracking"""
    _inherit = 'ir.http'

    @classmethod
    def _authenticate(cls, endpoint):
        """Override to track session changes"""
        result = super()._authenticate(endpoint)
        
        # Track logout when session ends
        if request and hasattr(request, 'session'):
            try:
                # Check if user was logged out (session uid changed or cleared)
                if hasattr(request.session, 'uid') and request.session.uid:
                    # User is logged in - this is handled by _update_last_login
                    pass
                else:
                    # User logged out or session expired - close any active sessions
                    cls._handle_session_logout()
            except Exception as e:
                _logger.debug(f"Failed to track session state: {e}")
                
        return result

    @classmethod
    def _handle_session_logout(cls):
        """Handle session logout tracking"""
        try:
            if request and hasattr(request, 'session'):
                session_id = getattr(request.session, 'sid', None)
                if session_id:
                    # Find any active sessions for this session ID
                    env = request.env
                    active_sessions = env['audit.session'].sudo().search([
                        ('session_id', '=', session_id),
                        ('status', '=', 'active')
                    ])
                    
                    if active_sessions:
                        active_sessions.sudo().write({
                            'logout_time': fields.Datetime.now(),
                            'status': 'logged_out'
                        })
                        _logger.info(f"Closed {len(active_sessions)} audit sessions for logout: {session_id}")
                        
        except Exception as e:
            _logger.debug(f"Failed to handle session logout: {e}")


# FIXED: Add proper logout detection via Session controller override
class AuditSession(Session):
    """Override web session controller to track logout"""
    
    def destroy(self):
        """Override session destroy to track logout"""
        try:
            # Close audit session before destroying web session
            if request and hasattr(request, 'session'):
                session_id = getattr(request.session, 'sid', None)
                user_id = getattr(request.session, 'uid', None)
                
                if session_id and user_id:
                    env = request.env
                    active_session = env['audit.session'].sudo().search([
                        ('session_id', '=', session_id),
                        ('user_id', '=', user_id),
                        ('status', '=', 'active')
                    ], limit=1)
                    
                    if active_session:
                        active_session.sudo().write({
                            'logout_time': fields.Datetime.now(),
                            'status': 'logged_out'
                        })
                        _logger.info(f"User {user_id} logged out, closed audit session: {session_id}")
                        
        except Exception as e:
            _logger.debug(f"Failed to track logout: {e}")
        
        # Call original destroy method
        return super().destroy()