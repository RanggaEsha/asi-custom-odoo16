import logging
_logger = logging.getLogger(__name__)


def close_audit_session_on_logout(reason='logout'):
    try:
        from odoo.http import request
        from odoo import fields
        session_sid = getattr(request.session, 'sid', None)
        user_id = getattr(request.session, 'uid', None)
        if not session_sid or not user_id:
            return
        active_session = request.env['audit.session'].sudo().search([
            ('session_id', '=', session_sid),
            ('user_id', '=', user_id),
            ('status', '=', 'active')
        ], limit=1)
        if not active_session:
            active_session = request.env['audit.session'].sudo().search([
                ('user_id', '=', user_id),
                ('status', '=', 'active')
            ], limit=1)
        if active_session:
            active_session.write({
                'logout_time': fields.Datetime.now(),
                'status': 'logged_out',
                'error_message': f'Session closed: {reason}'
            })
            _logger.info(f"Closed audit session {active_session.id} - {reason}")
    except Exception as e:
        _logger.warning(f"Failed to close audit session on logout (standalone): {e}")

def monkey_patch_logout():
    try:
        from odoo.addons.web.controllers.session import Session
        original_logout = Session.logout

        def custom_logout(self, redirect='/web/login', **kw):
            _logger.warning("=== CUSTOM LOGOUT CONTROLLER (MONKEY PATCH) TRIGGERED ===")
            close_audit_session_on_logout('user_logout_monkeypatch')
            return original_logout(self, redirect, **kw)

        Session.logout = custom_logout
        _logger.warning("=== MONKEY PATCHED Session.logout SUCCESSFULLY ===")
    except Exception as e:
        _logger.error(f"Failed to monkey patch Session.logout: {e}")

# Apply the monkey patch at import time
monkey_patch_logout()

from odoo import http, fields
from odoo.http import request
from odoo.addons.web.controllers.main import Home


class SimpleLogoutController(Home):
    """Simple logout controller with reliable session closure"""

    @http.route('/web/session/logout_custom', type='http', auth="public", website=True, csrf=False)
    def logout_custom(self, redirect='/web/login', **kw):
        """Custom logout route for testing override precedence"""
        _logger.warning("=== CUSTOM LOGOUT CONTROLLER (CUSTOM ROUTE) TRIGGERED ===")
        try:
            self._close_audit_session('user_logout_custom')
        except Exception as e:
            _logger.warning(f"Failed to close audit session on logout: {e}")
        return super().logout(redirect, **kw)

    @http.route('/audit/test_controller_load', type='http', auth="public", website=True, csrf=False)
    def test_controller_load(self, **kw):
        _logger.warning("=== TEST CONTROLLER ROUTE TRIGGERED ===")
        return "Test controller route hit. Check logs for confirmation."
    
    def _close_audit_session(self, reason='logout'):
        """Close the current audit session"""
        if not request or not hasattr(request, 'session'):
            return
            
        session_sid = getattr(request.session, 'sid', None)
        user_id = getattr(request.session, 'uid', None)
        
        if not session_sid or not user_id:
            return
            
        # Find active session
        active_session = request.env['audit.session'].sudo().search([
            ('session_id', '=', session_sid),
            ('user_id', '=', user_id),
            ('status', '=', 'active')
        ], limit=1)
        
        if not active_session:
            # Fallback: find any active session for this user
            active_session = request.env['audit.session'].sudo().search([
                ('user_id', '=', user_id),
                ('status', '=', 'active')
            ], limit=1)
        
        if active_session:
            active_session.write({
                'logout_time': fields.Datetime.now(),
                'status': 'logged_out',
                'error_message': f'Session closed: {reason}'
            })
            _logger.info(f"Closed audit session {active_session.id} - {reason}")


class SimpleSessionController(http.Controller):
    """Simple session management endpoints"""

    @http.route('/audit/session/close', type='json', auth='user', methods=['POST'])
    def close_session(self, reason='manual'):
        """Close current session via AJAX"""
        try:
            if not request or not hasattr(request, 'session'):
                return {'success': False, 'message': 'No session context'}
                
            session_sid = getattr(request.session, 'sid', None)
            user_id = request.env.user.id
            
            if not session_sid:
                return {'success': False, 'message': 'No session ID'}
            
            # Find and close session
            session = request.env['audit.session'].search([
                ('session_id', '=', session_sid),
                ('user_id', '=', user_id),
                ('status', '=', 'active')
            ], limit=1)
            
            if session:
                session.write({
                    'logout_time': fields.Datetime.now(),
                    'status': 'logged_out',
                    'error_message': f'Session closed: {reason}'
                })
                return {'success': True, 'message': 'Session closed successfully'}
            else:
                return {'success': False, 'message': 'No active session found'}
                
        except Exception as e:
            _logger.error(f"Failed to close session: {e}")
            return {'success': False, 'error': str(e)}

    @http.route('/audit/session/end', type='http', auth='user', methods=['POST'])
    def handle_session_end(self):
        """Handle session end via sendBeacon (browser close)"""
        try:
            session_sid = getattr(request.session, 'sid', None)
            user_id = request.env.user.id
            
            if session_sid and user_id:
                session = request.env['audit.session'].sudo().search([
                    ('session_id', '=', session_sid),
                    ('user_id', '=', user_id),
                    ('status', '=', 'active')
                ], limit=1)
                
                if session:
                    session.write({
                        'logout_time': fields.Datetime.now(),
                        'status': 'logged_out',
                        'browser_closed': True,
                        'error_message': 'Session closed: browser close'
                    })
            
            return "OK"
        except Exception as e:
            _logger.warning(f"Failed to handle session end: {e}")
            return "ERROR"