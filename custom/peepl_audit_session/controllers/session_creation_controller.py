# -*- coding: utf-8 -*-
import logging
from odoo import http
from odoo.http import request
from odoo.addons.web.controllers.main import Home, Session

_logger = logging.getLogger(__name__)


class SessionCreationController(Home):
    """Enhanced session creation on web login"""

    @http.route('/web/login', type='http', auth="none")
    def web_login(self, redirect=None, **kw):
        """Override web login to ensure session creation"""
        _logger.info(f"WEB_LOGIN - Login request received")
        
        # Call original login
        response = super().web_login(redirect, **kw)
        
        # Check if login was successful
        if request.session.uid:
            try:
                _logger.info(f"WEB_LOGIN - Login successful for user {request.session.uid}")
                
                # Small delay to ensure session is established
                import time
                time.sleep(0.1)
                
                # Get user and create session
                user = request.env['res.users'].sudo().browse(request.session.uid)
                if user.exists():
                    _logger.info(f"WEB_LOGIN - Creating session for user {user.login}")
                    session_created = user._ensure_audit_session()
                    
                    if session_created:
                        _logger.info(f"WEB_LOGIN - Session created: {session_created.id}")
                    else:
                        _logger.error(f"WEB_LOGIN - Failed to create session for {user.login}")
                        
            except Exception as e:
                _logger.error(f"WEB_LOGIN - Error creating session: {e}")
        else:
            _logger.info(f"WEB_LOGIN - Login failed or not completed")
        
        return response


class EnhancedSessionController(Session):
    """Enhanced session controller to catch authentication"""
    
    @http.route('/web/session/authenticate', type='json', auth="none")
    def authenticate(self, db, login, password, base_location=None):
        """Override authenticate to ensure session creation"""
        _logger.info(f"SESSION_AUTH - Authentication request for login: {login}")
        
        # Call original authenticate
        result = super().authenticate(db, login, password, base_location)
        
        # If authentication successful, ensure audit session
        if result and result.get('uid'):
            try:
                _logger.info(f"SESSION_AUTH - Authentication successful for user {result['uid']}")
                
                # Small delay to ensure context is ready
                import time
                time.sleep(0.1)
                
                # Get user and create session
                user = request.env['res.users'].sudo().browse(result['uid'])
                if user.exists():
                    session_created = user._ensure_audit_session()
                    
                    if session_created:
                        _logger.info(f"SESSION_AUTH - Session created: {session_created.id}")
                        # Add audit session info to result
                        result['audit_session_id'] = session_created.id
                    else:
                        _logger.error(f"SESSION_AUTH - Failed to create session")
                        
            except Exception as e:
                _logger.error(f"SESSION_AUTH - Error creating session: {e}")
        
        return result


class SessionDebugController(http.Controller):
    """Debug endpoints for session management"""

    @http.route('/audit/debug/session', type='json', auth='user', methods=['POST'])
    def debug_session(self):
        """Debug current session state"""
        try:
            session_sid = getattr(request.session, 'sid', None)
            user_id = request.env.user.id
            
            # Find current session
            current_session = request.env['audit.session'].search([
                ('session_id', '=', session_sid),
                ('user_id', '=', user_id),
                ('status', '=', 'active')
            ], limit=1)
            
            # Find any sessions for this user
            user_sessions = request.env['audit.session'].search([
                ('user_id', '=', user_id)
            ], order='login_time desc', limit=5)
            
            return {
                'session_sid': session_sid,
                'user_id': user_id,
                'current_session': {
                    'id': current_session.id if current_session else None,
                    'status': current_session.status if current_session else None,
                    'login_time': current_session.login_time.isoformat() if current_session and current_session.login_time else None
                },
                'user_sessions_count': len(user_sessions),
                'user_sessions': [
                    {
                        'id': s.id,
                        'session_id': s.session_id,
                        'status': s.status,
                        'login_time': s.login_time.isoformat() if s.login_time else None
                    } for s in user_sessions
                ]
            }
            
        except Exception as e:
            return {'error': str(e)}

    @http.route('/audit/debug/create_session', type='json', auth='user', methods=['POST'])
    def force_create_session(self):
        """Force create session for current user"""
        try:
            user = request.env.user
            session_created = user._ensure_audit_session()
            
            if session_created:
                return {
                    'success': True,
                    'session_id': session_created.id,
                    'message': f'Session created successfully: {session_created.id}'
                }
            else:
                return {
                    'success': False,
                    'message': 'Failed to create session'
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    @http.route('/audit/test/session_creation', type='http', auth='user', website=True)
    def test_session_creation(self):
        """Test page for session creation"""
        session_sid = getattr(request.session, 'sid', None)
        user_id = request.env.user.id
        
        # Check current session
        current_session = request.env['audit.session'].search([
            ('session_id', '=', session_sid),
            ('user_id', '=', user_id),
            ('status', '=', 'active')
        ], limit=1)
        
        html = f"""
        <html>
        <head><title>Session Creation Test</title></head>
        <body>
            <h1>Session Creation Test</h1>
            <p><strong>User ID:</strong> {user_id}</p>
            <p><strong>Session SID:</strong> {session_sid}</p>
            <p><strong>Current Audit Session:</strong> {current_session.id if current_session else 'None'}</p>
            
            <h2>Actions</h2>
            <button onclick="debugSession()">Debug Session</button>
            <button onclick="forceCreateSession()">Force Create Session</button>
            
            <div id="result"></div>
            
            <script>
                function debugSession() {{
                    fetch('/audit/debug/session', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{jsonrpc: '2.0', method: 'call', params: {{}}}})
                    }})
                    .then(response => response.json())
                    .then(data => {{
                        document.getElementById('result').innerHTML = '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
                    }});
                }}
                
                function forceCreateSession() {{
                    fetch('/audit/debug/create_session', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{jsonrpc: '2.0', method: 'call', params: {{}}}})
                    }})
                    .then(response => response.json())
                    .then(data => {{
                        document.getElementById('result').innerHTML = '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
                        if (data.result && data.result.success) {{
                            alert('Session created successfully!');
                            location.reload();
                        }}
                    }});
                }}
            </script>
        </body>
        </html>
        """
        
        return html