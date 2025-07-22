# -*- coding: utf-8 -*-

import logging
import json
from odoo import http, fields, _
from odoo.http import request

_logger = logging.getLogger(__name__)


class AuditController(http.Controller):
    """Enhanced controller for comprehensive audit session management"""

    @http.route('/audit/session/info', type='json', auth='user', methods=['POST'])
    def get_session_info(self):
        """Get current session information"""
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
                return {
                    'session_id': audit_session.session_id,
                    'audit_session_id': audit_session.id,
                    'login_time': audit_session.login_time.isoformat() if audit_session.login_time else None,
                    'ip_address': audit_session.ip_address,
                    'device_type': audit_session.device_type,
                    'browser': audit_session.browser,
                    'os': audit_session.os,
                    'country': audit_session.country,
                    'city': audit_session.city,
                    'log_count': audit_session.log_count,
                    'status': audit_session.status
                }
            else:
                return {'error': 'No active session found'}
                
        except Exception as e:
            _logger.error(f"Failed to get session info: {e}")
            return {'error': str(e)}

    @http.route('/audit/session/close', type='json', auth='user', methods=['POST'])
    def close_session(self, reason=None, timestamp=None):
        """Close current audit session with reason tracking"""
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
                # Close session with additional context
                close_reason = reason or 'manual'
                audit_session.sudo().write({
                    'logout_time': fields.Datetime.now(),
                    'status': 'logged_out',
                    'error_message': f'Closed: {close_reason}' if reason else None
                })
                
                # Log the session close action
                self._log_session_action(audit_session, 'close', reason)
                
                _logger.info(f"Audit session {audit_session.id} closed by {close_reason} for user {request.env.user.login}")
                return {
                    'success': True, 
                    'message': 'Session closed successfully',
                    'reason': close_reason
                }
            else:
                return {'success': False, 'message': 'No active session found'}
                
        except Exception as e:
            _logger.error(f"Failed to close audit session: {e}")
            return {'success': False, 'error': str(e)}

    @http.route('/audit/session/end', type='http', auth='user', methods=['POST'])
    def handle_session_end(self):
        """Handle session end via sendBeacon (browser close)"""
        try:
            # This is called via navigator.sendBeacon, so we get raw data
            data = request.httprequest.get_data()
            if data:
                try:
                    parsed_data = json.loads(data.decode('utf-8'))
                    reason = parsed_data.get('reason', 'browser_close')
                except:
                    reason = 'browser_close'
            else:
                reason = 'browser_close'
            
            # Close the session
            result = self.close_session(reason=reason)
            
            # Return a simple response for sendBeacon
            return "OK"
            
        except Exception as e:
            _logger.warning(f"Failed to handle session end: {e}")
            return "ERROR"

    @http.route('/audit/dashboard', type='http', auth='user', website=True)
    def audit_dashboard(self, **kwargs):
        """Enhanced audit dashboard with session status"""
        if not request.env.user.has_group('peepl_audit_session.group_audit_user'):
            return request.not_found()
            
        session_id = getattr(request.session, 'sid', None)
        user_id = request.env.user.id
        
        current_session = None
        if session_id:
            current_session = request.env['audit.session'].search([
                ('session_id', '=', session_id),
                ('user_id', '=', user_id),
                ('status', '=', 'active')
            ], limit=1)
        
        # Get user's recent sessions with enhanced info
        recent_sessions = request.env['audit.session'].search([
            ('user_id', '=', user_id)
        ], limit=10, order='login_time desc')
        
        # Get user's recent activity
        recent_activity = request.env['audit.log.entry'].search([
            ('user_id', '=', user_id)
        ], limit=20, order='action_date desc')
        
        # Session statistics
        total_sessions = request.env['audit.session'].search_count([
            ('user_id', '=', user_id)
        ])
        
        active_sessions = request.env['audit.session'].search_count([
            ('user_id', '=', user_id),
            ('status', '=', 'active')
        ])
        
        values = {
            'current_session': current_session,
            'recent_sessions': recent_sessions,
            'recent_activity': recent_activity,
            'total_sessions': total_sessions,
            'active_sessions': active_sessions,
        }
        
        return request.render('peepl_audit_session.audit_dashboard', values)

    @http.route('/audit/api/stats', type='json', auth='user', methods=['POST'])
    def get_audit_stats(self):
        """Get comprehensive audit statistics for dashboard"""
        if not request.env.user.has_group('peepl_audit_session.group_audit_manager'):
            return {'error': 'Access denied'}
            
        try:
            from datetime import datetime, date, timedelta
            
            # Basic counts
            total_logs = request.env['audit.log.entry'].search_count([])
            total_sessions = request.env['audit.session'].search_count([])
            
            # Today's activity
            today = date.today()
            today_logs = request.env['audit.log.entry'].search_count([
                ('action_date', '>=', datetime.combine(today, datetime.min.time()))
            ])
            
            # Active sessions
            active_sessions = request.env['audit.session'].search_count([
                ('status', '=', 'active')
            ])
            
            # Session status breakdown
            session_stats = {}
            for status in ['active', 'logged_out', 'expired', 'error']:
                session_stats[status] = request.env['audit.session'].search_count([
                    ('status', '=', status)
                ])
            
            # Top users by activity (last 7 days)
            query = """
                SELECT u.name, COUNT(l.id) as log_count
                FROM audit_log_entry l
                JOIN res_users u ON l.user_id = u.id
                WHERE l.action_date >= NOW() - INTERVAL '7 days'
                GROUP BY u.id, u.name
                ORDER BY log_count DESC
                LIMIT 5
            """
            request.env.cr.execute(query)
            top_users = request.env.cr.dictfetchall()
            
            # Activity by type (last 7 days)
            query = """
                SELECT action_type, COUNT(*) as count
                FROM audit_log_entry
                WHERE action_date >= NOW() - INTERVAL '7 days'
                GROUP BY action_type
                ORDER BY count DESC
            """
            request.env.cr.execute(query)
            activity_by_type = request.env.cr.dictfetchall()
            
            # Model activity (last 7 days)
            query = """
                SELECT m.name as model_name, COUNT(l.id) as log_count
                FROM audit_log_entry l
                JOIN ir_model m ON l.model_id = m.id
                WHERE l.action_date >= NOW() - INTERVAL '7 days'
                GROUP BY m.id, m.name
                ORDER BY log_count DESC
                LIMIT 10
            """
            request.env.cr.execute(query)
            top_models = request.env.cr.dictfetchall()
            
            return {
                'total_logs': total_logs,
                'total_sessions': total_sessions,
                'today_logs': today_logs,
                'active_sessions': active_sessions,
                'session_stats': session_stats,
                'top_users': top_users,
                'activity_by_type': activity_by_type,
                'top_models': top_models
            }
            
        except Exception as e:
            _logger.error(f"Failed to get audit stats: {e}")
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
                'session_duration': audit_session.duration if action == 'close' else None
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