# -*- coding: utf-8 -*-

import logging
from odoo import models, api
from odoo.http import request
from odoo.service import security

_logger = logging.getLogger(__name__)


class AuditSessionHook(models.AbstractModel):
    """Hook into Odoo session management for audit tracking"""
    _name = 'audit.session.hook'
    _description = 'Audit Session Hook'

    @api.model
    def _register_hook(self):
        """Register hooks for session tracking"""
        # Hook into user authentication
        original_authenticate = security.authenticate
        
        def audit_authenticate(db, login, password, user_agent_env):
            """Wrapped authenticate function"""
            result = original_authenticate(db, login, password, user_agent_env)
            
            if result and request:
                try:
                    # Create audit session
                    self.env['audit.session'].sudo().create_session(
                        user_id=result,
                        session_id=request.session.sid if hasattr(request, 'session') else None,
                        request_obj=request
                    )
                except Exception as e:
                    _logger.error(f"Failed to create audit session: {e}")
                    
            return result
        
        # Replace the original function
        security.authenticate = audit_authenticate
        
        return super()._register_hook()


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
                # Check if audit tables exist
                self.env.cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'audit_session' LIMIT 1")
                if not self.env.cr.fetchone():
                    return result
                    
                existing_session = self.env['audit.session'].search([
                    ('session_id', '=', request.session.sid),
                    ('user_id', '=', self.id),
                    ('status', '=', 'active')
                ], limit=1)
                
                if not existing_session:
                    self.env['audit.session'].sudo().create_session(
                        user_id=self.id,
                        session_id=request.session.sid,
                        request_obj=request
                    )
                    
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
                
            # Log failed login attempt
            if request and hasattr(request, 'session'):
                try:
                    # Check if audit tables exist
                    self.env.cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'audit_session' LIMIT 1")
                    if self.env.cr.fetchone():
                        self.env['audit.session'].sudo().create({
                            'user_id': self.id,
                            'session_id': request.session.sid,
                            'login_time': self.env.cr.now(),
                            'status': 'error',
                            'error_message': f"Login failed: {str(e)}",
                            'ip_address': request.httprequest.remote_addr if request.httprequest else None,
                            'user_agent': request.httprequest.headers.get('User-Agent', '') if request.httprequest else ''
                        })
                except Exception as audit_error:
                    _logger.error(f"Failed to log failed login attempt: {audit_error}")
            raise


class IrHttp(models.AbstractModel):
    """Extend ir.http to track session lifecycle"""
    _inherit = 'ir.http'

    @classmethod
    def _authenticate(cls, endpoint):
        """Override to track authentication events"""
        result = super()._authenticate(endpoint)
        
        # Skip during module installation
        if request and request.env.context.get('module') or request.env.context.get('install_mode'):
            return result
        
        # Update session activity timestamp
        if request and hasattr(request, 'session') and request.session.uid:
            try:
                # Check if audit tables exist
                request.env.cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'audit_session' LIMIT 1")
                if request.env.cr.fetchone():
                    audit_session = request.env['audit.session'].sudo().search([
                        ('session_id', '=', request.session.sid),
                        ('user_id', '=', request.session.uid),
                        ('status', '=', 'active')
                    ], limit=1)
                    
                    if audit_session:
                        # Update last activity (you could add a field for this)
                        pass
                        
            except Exception as e:
                _logger.debug(f"Failed to update session activity: {e}")
                
        return result


class IrModelAccess(models.Model):
    """Extend model access to log access attempts"""
    _inherit = 'ir.model.access'

    @api.model
    def check(self, model_name, mode='read', raise_exception=True):
        """Override to log access checks"""
        try:
            result = super().check(model_name, mode, raise_exception)
            
            # Log successful access if configured
            if request and hasattr(request, 'session') and request.session.uid:
                self._log_access_attempt(model_name, mode, True)
                
            return result
            
        except Exception as e:
            # Log failed access
            if request and hasattr(request, 'session') and request.session.uid:
                self._log_access_attempt(model_name, mode, False, str(e))
            raise

    def _log_access_attempt(self, model_name, mode, success, error_msg=None):
        """Log access attempt"""
        try:
            config = self.env['audit.config'].sudo().get_active_config()
            if not config or not config.should_audit_user(request.session.uid):
                return
                
            # Only log if read operations are enabled or it's not a read
            if mode == 'read' and not config.log_read:
                return
                
            context_info = {
                'mode': mode,
                'success': success,
                'error': error_msg,
                'url': request.httprequest.url if request.httprequest else None
            }
            
            self.env['audit.log.entry'].sudo().create({
                'user_id': request.session.uid,
                'model_id': self.env['ir.model'].sudo().search([('model', '=', model_name)], limit=1).id,
                'res_id': 0,  # Access check, not specific record
                'action_type': 'read',  # Access checks are read operations
                'method': 'access_check',
                'context_info': str(context_info),
            })
            
        except Exception as e:
            _logger.debug(f"Failed to log access attempt: {e}")