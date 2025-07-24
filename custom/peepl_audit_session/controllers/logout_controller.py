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


class EnhancedAuditController(http.Controller):
    """Enhanced controller with heartbeat and better session management"""

    @http.route('/audit/session/heartbeat', type='json', auth='user', methods=['POST'])
    def session_heartbeat(self, timestamp=None, last_activity=None):
        """Handle session heartbeat from client"""
        try:
            session_id = getattr(request.session, 'sid', None)
            user_id = request.env.user.id
            
            if not session_id:
                return {'success': False, 'error': 'No session ID found'}
                
            audit_session = request.env['audit.session'].search([
                ('session_id', '=', session_id),
                ('user_id', '=', user_id),
                ('status', '=', 'active')
            ], limit=1)
            
            if audit_session:
                # Update heartbeat
                update_vals = {
                    'last_activity': fields.Datetime.now(),
                    'heartbeat_count': audit_session.heartbeat_count + 1
                }
                
                audit_session.sudo().write(update_vals)
                
                _logger.debug(f"Heartbeat received for session {audit_session.id}")
                
                return {
                    'success': True,
                    'session_id': audit_session.id,
                    'heartbeat_count': audit_session.heartbeat_count,
                    'status': audit_session.status
                }
            else:
                _logger.warning(f"No active session found for heartbeat: SID={session_id}, User={user_id}")
                return {'success': False, 'error': 'No active session found'}
                
        except Exception as e:
            _logger.error(f"Failed to process session heartbeat: {e}")
            return {'success': False, 'error': str(e)}

    @http.route('/audit/session/info', type='json', auth='user', methods=['POST'])
    def get_session_info(self):
        """Get current session information with enhanced details"""
        try:
            session_id = getattr(request.session, 'sid', None)
            user_id = request.env.user.id
            
            if not session_id:
                return {'error': 'No session ID found'}
                
            audit_session = request.env['audit.session'].search([
                ('session_id', '=', session_id),
                ('user_id', '=', user_id),
                ('status', '=', 'active')
            ], limit=1)
            
            if audit_session:
                # Calculate session duration
                login_time = audit_session.login_time
                current_time = fields.Datetime.now()
                duration_hours = 0
                if login_time:
                    duration_delta = current_time - login_time
                    duration_hours = duration_delta.total_seconds() / 3600
                
                # Get concurrent session count
                concurrent_count = request.env['audit.session'].search_count([
                    ('user_id', '=', user_id),
                    ('status', '=', 'active'),
                    ('id', '!=', audit_session.id)
                ])
                
                return {
                    'session_id': audit_session.session_id,
                    'audit_session_id': audit_session.id,
                    'login_time': audit_session.login_time.isoformat() if audit_session.login_time else None,
                    'last_activity': audit_session.last_activity.isoformat() if audit_session.last_activity else None,
                    'duration_hours': round(duration_hours, 2),
                    'ip_address': audit_session.ip_address,
                    'device_type': audit_session.device_type,
                    'browser': audit_session.browser,
                    'os': audit_session.os,
                    'country': audit_session.country,
                    'city': audit_session.city,
                    'log_count': audit_session.log_count,
                    'heartbeat_count': audit_session.heartbeat_count,
                    'status': audit_session.status,
                    'concurrent_sessions': concurrent_count
                }
            else:
                return {'error': 'No active session found'}
                
        except Exception as e:
            _logger.error(f"Failed to get session info: {e}")
            return {'error': str(e)}

    @http.route('/audit/session/close', type='json', auth='user', methods=['POST'])
    def close_session(self, reason=None, timestamp=None, last_activity=None):
        """Close current audit session with enhanced tracking"""
        try:
            session_id = getattr(request.session, 'sid', None)
            user_id = request.env.user.id
            
            if not session_id:
                return {'success': False, 'message': 'No session ID found'}
                
            audit_session = request.env['audit.session'].search([
                ('session_id', '=', session_id),
                ('user_id', '=', user_id),
                ('status', '=', 'active')
            ], limit=1)
            
            if audit_session:
                # Determine browser close vs manual logout
                is_browser_close = reason and 'browser_close' in reason
                
                close_vals = {
                    'logout_time': fields.Datetime.now(),
                    'status': 'logged_out',
                    'browser_closed': is_browser_close,
                }
                
                # Add reason to error message for tracking
                if reason:
                    close_vals['error_message'] = f'Session closed: {reason}'
                
                # Update last activity if provided
                if last_activity:
                    try:
                        # Convert timestamp to datetime
                        if isinstance(last_activity, str):
                            last_activity_dt = datetime.fromisoformat(last_activity.replace('Z', '+00:00'))
                        elif isinstance(last_activity, (int, float)):
                            last_activity_dt = datetime.fromtimestamp(last_activity / 1000)
                        else:
                            last_activity_dt = fields.Datetime.now()
                        close_vals['last_activity'] = last_activity_dt
                    except:
                        pass
                
                audit_session.sudo().write(close_vals)
                
                # Log the session close action
                self._log_session_action(audit_session, 'close', reason)
                
                _logger.info(f"Session {audit_session.id} closed: {reason} (browser_close: {is_browser_close})")
                
                return {
                    'success': True, 
                    'message': 'Session closed successfully',
                    'reason': reason,
                    'browser_closed': is_browser_close
                }
            else:
                return {'success': False, 'message': 'No active session found'}
                
        except Exception as e:
            _logger.error(f"Failed to close audit session: {e}")
            return {'success': False, 'error': str(e)}

    @http.route('/audit/session/end', type='http', auth='user', methods=['POST'])
    def handle_session_end(self):
        """Handle session end via sendBeacon with enhanced processing"""
        try:
            data = request.httprequest.get_data()
            reason = 'browser_close_beacon'
            
            if data:
                try:
                    parsed_data = json.loads(data.decode('utf-8'))
                    reason = parsed_data.get('reason', 'browser_close_beacon')
                except:
                    pass
            
            # Close the session
            result = self.close_session(reason=reason)
            
            # Return appropriate response
            if result.get('success'):
                return "OK"
            else:
                return "ERROR"
            
        except Exception as e:
            _logger.warning(f"Failed to handle session end: {e}")
            return "ERROR"

    @http.route('/audit/session/force_close/<int:session_id>', type='json', auth='user', methods=['POST'])
    def force_close_session(self, session_id):
        """Force close a specific session (admin only)"""
        try:
            if not request.env.user.has_group('peepl_audit_session.group_audit_manager'):
                return {'success': False, 'error': 'Access denied'}
            
            audit_session = request.env['audit.session'].browse(session_id)
            if not audit_session.exists():
                return {'success': False, 'error': 'Session not found'}
            
            if audit_session.status != 'active':
                return {'success': False, 'error': 'Session is not active'}
            
            audit_session.sudo().write({
                'logout_time': fields.Datetime.now(),
                'status': 'forced_logout',
                'error_message': f'Session forcefully closed by {request.env.user.name}'
            })
            
            _logger.info(f"Session {session_id} forcefully closed by {request.env.user.name}")
            
            return {
                'success': True,
                'message': f'Session for {audit_session.user_id.name} has been closed'
            }
            
        except Exception as e:
            _logger.error(f"Failed to force close session {session_id}: {e}")
            return {'success': False, 'error': str(e)}

    @http.route('/audit/session/stats', type='json', auth='user', methods=['POST'])
    def get_session_stats(self):
        """Get session statistics for dashboard"""
        try:
            if not request.env.user.has_group('peepl_audit_session.group_audit_manager'):
                return {'error': 'Access denied'}
            
            stats = request.env['audit.session'].get_session_stats()
            
            # Add real-time information
            current_time = fields.Datetime.now()
            
            # Recent activity (last hour)
            recent_cutoff = current_time - timedelta(hours=1)
            recent_activity = request.env['audit.log.entry'].search_count([
                ('action_date', '>=', recent_cutoff)
            ])
            
            # Sessions by status breakdown
            status_breakdown = {}
            for status in ['active', 'logged_out', 'expired', 'error', 'forced_logout']:
                count = request.env['audit.session'].search_count([
                    ('status', '=', status)
                ])
                status_breakdown[status] = count
            
            # Browser close detection stats
            browser_closed_count = request.env['audit.session'].search_count([
                ('browser_closed', '=', True)
            ])
            
            # Sessions with heartbeat in last 10 minutes
            heartbeat_cutoff = current_time - timedelta(minutes=10)
            active_heartbeat_count = request.env['audit.session'].search_count([
                ('status', '=', 'active'),
                ('last_activity', '>=', heartbeat_cutoff)
            ])
            
            stats.update({
                'recent_activity_count': recent_activity,
                'status_breakdown': status_breakdown,
                'browser_closed_sessions': browser_closed_count,
                'active_with_recent_heartbeat': active_heartbeat_count,
                'timestamp': current_time.isoformat()
            })
            
            return stats
            
        except Exception as e:
            _logger.error(f"Failed to get session stats: {e}")
            return {'error': str(e)}

    def _log_session_action(self, audit_session, action, reason=None):
        """Log session-related actions as audit entries"""
        try:
            # Get the audit.session model ID
            session_model = request.env['ir.model'].search([('model', '=', 'audit.session')], limit=1)
            if not session_model:
                return
            
            context_info = {
                'action': action,
                'reason': reason,
                'session_duration': audit_session.duration if action == 'close' else None,
                'browser_closed': getattr(audit_session, 'browser_closed', False),
                'heartbeat_count': getattr(audit_session, 'heartbeat_count', 0)
            }
            
            request.env['audit.log.entry'].sudo().create({
                'user_id': audit_session.user_id.id,
                'session_id': audit_session.id,
                'model_id': session_model.id,
                'res_id': audit_session.id,
                'res_name': f"Session {action.title()}",
                'action_type': 'write',
                'action_date': fields.Datetime.now(),
                'method': f'session_{action}',
                'context_info': json.dumps(context_info, default=str)
            })
            
        except Exception as e:
            _logger.warning(f"Failed to log session action: {e}")