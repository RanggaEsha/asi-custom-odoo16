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
        """Override to track session start with improved session management"""
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
                
                session_sid = getattr(request.session, 'sid', None)
                user_id = self.id
                
                # Debug logging
                _logger.info(f"LOGIN DEBUG - User {self.login} (ID: {user_id}) logging in with SID: {session_sid}")
                
                if not session_sid:
                    _logger.warning(f"No session SID available for user {self.login}")
                    return result
                
                # CRITICAL FIX: Better session search and creation logic
                existing_session = self.env['audit.session'].sudo().search([
                    ('session_id', '=', session_sid),
                    ('user_id', '=', user_id)
                ], limit=1)
                
                if existing_session:
                    # Update existing session
                    _logger.info(f"LOGIN DEBUG - Updating existing session {existing_session.id} "
                               f"(Current status: {existing_session.status})")
                    existing_session.sudo().write({
                        'login_time': fields.Datetime.now(),
                        'status': 'active',
                        'error_message': False,  # Clear any previous error
                    })
                    session_id = existing_session.id
                else:
                    # Check for any active sessions with different SID for this user
                    # This helps identify SID changes
                    other_active = self.env['audit.session'].sudo().search([
                        ('user_id', '=', user_id),
                        ('status', '=', 'active'),
                        ('session_id', '!=', session_sid)
                    ])
                    
                    if other_active:
                        _logger.info(f"LOGIN DEBUG - Found {len(other_active)} other active sessions "
                                   f"for user {user_id} with different SIDs. Closing them.")
                        # Close other sessions (user might have multiple tabs or session changed)
                        other_active.sudo().write({
                            'logout_time': fields.Datetime.now(),
                            'status': 'expired',
                            'error_message': 'Session superseded by new login'
                        })
                    
                    # Create new session
                    _logger.info(f"LOGIN DEBUG - Creating new session for user {self.login} with SID: {session_sid}")
                    new_session = self.env['audit.session'].sudo().create_session(
                        user_id=user_id,
                        session_id=session_sid,
                        request_obj=request
                    )
                    
                    if new_session:
                        session_id = new_session.id
                        _logger.info(f"LOGIN DEBUG - Successfully created session {session_id} for user {self.login}")
                    else:
                        _logger.error(f"LOGIN DEBUG - Failed to create session for user {self.login}")
                    
            except Exception as e:
                _logger.error(f"Failed to track login for user {self.login}: {e}")
                
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
                        session_sid = getattr(request.session, 'sid', 'unknown')
                        _logger.info(f"FAILED LOGIN DEBUG - User {self.id} failed login with SID: {session_sid}")
                        
                        self.env['audit.session'].sudo().create({
                            'user_id': self.id,
                            'session_id': session_sid,
                            'login_time': fields.Datetime.now(),
                            'status': 'error',
                            'error_message': f"Login failed: {str(e)[:100]}",
                            'ip_address': request.httprequest.remote_addr if request.httprequest else None,
                        })
                except Exception as audit_error:
                    _logger.debug(f"Failed to log failed login attempt: {audit_error}")
            raise


class IrHttp(models.AbstractModel):
    """Enhanced session logout tracking"""
    _inherit = 'ir.http'

    @classmethod
    def _authenticate(cls, endpoint):
        """Override to track session changes with better debugging"""
        result = super()._authenticate(endpoint)
        
        # Enhanced session state tracking
        if request and hasattr(request, 'session'):
            try:
                session_sid = getattr(request.session, 'sid', None)
                session_uid = getattr(request.session, 'uid', None)
                
                # Debug current session state
                if session_sid and session_uid:
                    _logger.debug(f"AUTH DEBUG - Active session: SID={session_sid}, UID={session_uid}")
                    
                    # Verify our audit session exists and is active
                    env = request.env
                    audit_session = env['audit.session'].sudo().search([
                        ('session_id', '=', session_sid),
                        ('user_id', '=', session_uid),
                        ('status', '=', 'active')
                    ], limit=1)
                    
                    if not audit_session:
                        _logger.warning(f"AUTH DEBUG - No active audit session found for "
                                      f"SID={session_sid}, UID={session_uid}")
                    else:
                        _logger.debug(f"AUTH DEBUG - Found audit session {audit_session.id}")
                        
                elif not session_uid:
                    # User logged out or session expired
                    _logger.debug(f"AUTH DEBUG - No user in session (logged out), SID={session_sid}")
                    cls._handle_session_logout()
                    
            except Exception as e:
                _logger.debug(f"Failed to track session state in _authenticate: {e}")
                
        return result

    @classmethod
    def _handle_session_logout(cls):
        """Handle session logout tracking with debugging"""
        try:
            if request and hasattr(request, 'session'):
                session_sid = getattr(request.session, 'sid', None)
                if session_sid:
                    env = request.env
                    
                    # Find any active sessions for this session ID
                    active_sessions = env['audit.session'].sudo().search([
                        ('session_id', '=', session_sid),
                        ('status', '=', 'active')
                    ])
                    
                    if active_sessions:
                        _logger.info(f"LOGOUT DEBUG - Closing {len(active_sessions)} active sessions for SID: {session_sid}")
                        active_sessions.sudo().write({
                            'logout_time': fields.Datetime.now(),
                            'status': 'logged_out'
                        })
                    else:
                        _logger.debug(f"LOGOUT DEBUG - No active sessions found for SID: {session_sid}")
                        
        except Exception as e:
            _logger.debug(f"Failed to handle session logout: {e}")


# Enhanced logout detection via Session controller override
class AuditSession(Session):
    """Override web session controller to track logout with debugging"""
    
    def destroy(self):
        """Override session destroy to track logout"""
        try:
            if request and hasattr(request, 'session'):
                session_sid = getattr(request.session, 'sid', None)
                session_uid = getattr(request.session, 'uid', None)
                
                _logger.info(f"SESSION DESTROY DEBUG - Destroying session SID={session_sid}, UID={session_uid}")
                
                if session_sid and session_uid:
                    env = request.env
                    active_session = env['audit.session'].sudo().search([
                        ('session_id', '=', session_sid),
                        ('user_id', '=', session_uid),
                        ('status', '=', 'active')
                    ], limit=1)
                    
                    if active_session:
                        active_session.sudo().write({
                            'logout_time': fields.Datetime.now(),
                            'status': 'logged_out'
                        })
                        _logger.info(f"SESSION DESTROY DEBUG - Closed audit session {active_session.id}")
                    else:
                        _logger.warning(f"SESSION DESTROY DEBUG - No active audit session found")
                        
        except Exception as e:
            _logger.debug(f"Failed to track logout in destroy: {e}")
        
        # Call original destroy method
        return super().destroy()