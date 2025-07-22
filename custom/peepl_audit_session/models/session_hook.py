# -*- coding: utf-8 -*-

import logging
from odoo import models, api, fields
from odoo.http import request

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
                        self.env['audit.session'].sudo().create({
                            'user_id': self.id,
                            'session_id': request.session.sid,
                            'login_time': fields.Datetime.now(),
                            'status': 'error',
                            'error_message': f"Login failed: {str(e)[:100]}",  # Limit error message length
                            'ip_address': request.httprequest.remote_addr if request.httprequest else None,
                        })
                except Exception as audit_error:
                    _logger.debug(f"Failed to log failed login attempt: {audit_error}")
            raise


# Disable other performance-heavy overrides for now
# class IrHttp(models.AbstractModel):
#     """Disabled for performance"""
#     pass

# class IrModelAccess(models.Model):
#     """Disabled for performance"""  
#     pass