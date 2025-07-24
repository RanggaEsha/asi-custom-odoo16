import logging
from datetime import datetime
from odoo import models, api, fields
from odoo.http import request

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _update_last_login(self):
        """Create audit session immediately on login with better error handling"""
        result = super()._update_last_login()
        
        # Skip during installation or if no request context
        if self.env.context.get('install_mode'):
            return result
            
        try:
            _logger.info(f"LOGIN_HOOK - Login detected for user {self.login} (ID: {self.id})")
            session_created = self._ensure_audit_session()
            if session_created:
                _logger.info(f"LOGIN_HOOK - Session created successfully: {session_created.id}")
            else:
                _logger.error(f"LOGIN_HOOK - Failed to create session for user {self.login}")
        except Exception as e:
            _logger.error(f"LOGIN_HOOK - Error creating audit session for {self.login}: {e}")
            import traceback
            _logger.error(f"LOGIN_HOOK - Traceback: {traceback.format_exc()}")
                
        return result

    def _ensure_audit_session(self):
        """Create audit session with improved reliability"""
        # Check if we have request context
        if not request:
            _logger.warning("LOGIN_HOOK - No request context available")
            return None
            
        if not hasattr(request, 'session'):
            _logger.warning("LOGIN_HOOK - No session in request")
            return None
            
        session_sid = getattr(request.session, 'sid', None)
        if not session_sid:
            _logger.warning("LOGIN_HOOK - No session SID found")
            return None
            
        _logger.info(f"LOGIN_HOOK - Processing session SID: {session_sid} for user {self.id}")
        
        # Check if session already exists (exact match)
        existing_session = self.env['audit.session'].sudo().search([
            ('session_id', '=', session_sid),
            ('user_id', '=', self.id),
            ('status', '=', 'active')
        ], limit=1)
        
        if existing_session:
            _logger.info(f"LOGIN_HOOK - Updating existing session {existing_session.id}")
            existing_session.write({
                'login_time': fields.Datetime.now(),
                'last_activity': fields.Datetime.now(),
                'error_message': False
            })
            # Commit immediately to ensure availability
            self.env.cr.commit()
            return existing_session
        
        # Close any other active sessions for this user
        old_sessions = self.env['audit.session'].sudo().search([
            ('user_id', '=', self.id),
            ('status', '=', 'active')
        ])
        if old_sessions:
            _logger.info(f"LOGIN_HOOK - Closing {len(old_sessions)} old sessions")
            old_sessions.write({
                'status': 'replaced',
                'logout_time': fields.Datetime.now(),
                'error_message': 'Replaced by new login session'
            })
        
        # Create new session
        session_data = self._extract_session_info()
        session_data.update({
            'user_id': self.id,
            'session_id': session_sid,
            'login_time': fields.Datetime.now(),
            'last_activity': fields.Datetime.now(),
            'status': 'active',
            'browser_closed': False,
            'error_message': False
        })
        
        _logger.info(f"LOGIN_HOOK - Creating new session with data: {session_data}")
        
        try:
            new_session = self.env['audit.session'].sudo().create(session_data)
            # Critical: Commit immediately
            self.env.cr.commit()
            _logger.info(f"LOGIN_HOOK - Successfully created session {new_session.id} for user {self.login}")
            
            # Verify session was created
            verify_session = self.env['audit.session'].sudo().search([
                ('id', '=', new_session.id)
            ], limit=1)
            if verify_session:
                _logger.info(f"LOGIN_HOOK - Verified session {new_session.id} exists in database")
            else:
                _logger.error(f"LOGIN_HOOK - Session {new_session.id} not found after creation!")
            
            return new_session
        except Exception as e:
            _logger.error(f"LOGIN_HOOK - Failed to create session: {e}")
            # Rollback on error
            self.env.cr.rollback()
            return None

    def _extract_session_info(self):
        """Extract session information with better error handling"""
        info = {
            'ip_address': 'unknown',
            'device_type': 'unknown',
            'browser': 'Unknown',
            'os': 'Unknown'
        }
        
        try:
            if request and hasattr(request, 'httprequest'):
                # Get IP address
                info['ip_address'] = getattr(request.httprequest, 'remote_addr', 'unknown')
                
                # Get user agent
                headers = getattr(request.httprequest, 'headers', {})
                user_agent = headers.get('User-Agent', '') if headers else ''
                
                if user_agent:
                    ua_lower = user_agent.lower()
                    
                    # Browser detection
                    if 'chrome' in ua_lower and 'edge' not in ua_lower:
                        info['browser'] = 'Chrome'
                    elif 'firefox' in ua_lower:
                        info['browser'] = 'Firefox'
                    elif 'safari' in ua_lower and 'chrome' not in ua_lower:
                        info['browser'] = 'Safari'
                    elif 'edge' in ua_lower:
                        info['browser'] = 'Edge'
                    elif 'opera' in ua_lower:
                        info['browser'] = 'Opera'
                    
                    # OS detection
                    if 'windows' in ua_lower:
                        info['os'] = 'Windows'
                    elif 'mac' in ua_lower or 'osx' in ua_lower:
                        info['os'] = 'macOS'
                    elif 'linux' in ua_lower:
                        info['os'] = 'Linux'
                    elif 'android' in ua_lower:
                        info['os'] = 'Android'
                    elif 'ios' in ua_lower or 'iphone' in ua_lower or 'ipad' in ua_lower:
                        info['os'] = 'iOS'
                    
                    # Device type detection
                    if any(mobile in ua_lower for mobile in ['mobile', 'android', 'iphone']):
                        info['device_type'] = 'mobile'
                    elif any(tablet in ua_lower for tablet in ['tablet', 'ipad']):
                        info['device_type'] = 'tablet'
                    else:
                        info['device_type'] = 'desktop'
                        
                _logger.debug(f"LOGIN_HOOK - Extracted session info: {info}")
                        
        except Exception as e:
            _logger.warning(f"LOGIN_HOOK - Failed to extract session info: {e}")
            
        return info