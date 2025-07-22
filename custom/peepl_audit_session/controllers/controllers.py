# -*- coding: utf-8 -*-

import logging
from odoo import http, _
from odoo.http import request

_logger = logging.getLogger(__name__)


class AuditController(http.Controller):
    """Controller for audit session management"""

    @http.route('/audit/session/info', type='json', auth='user', methods=['POST'])
    def get_session_info(self):
        """Get current session information"""
        try:
            audit_session = request.env['audit.session'].search([
                ('session_id', '=', request.session.sid),
                ('user_id', '=', request.env.user.id),
                ('status', '=', 'active')
            ], limit=1)
            
            if audit_session:
                return {
                    'session_id': audit_session.session_id,
                    'login_time': audit_session.login_time.isoformat() if audit_session.login_time else None,
                    'ip_address': audit_session.ip_address,
                    'device_type': audit_session.device_type,
                    'browser': audit_session.browser,
                    'os': audit_session.os,
                    'country': audit_session.country,
                    'city': audit_session.city,
                    'log_count': audit_session.log_count
                }
            else:
                return {'error': 'No active session found'}
                
        except Exception as e:
            _logger.error(f"Failed to get session info: {e}")
            return {'error': str(e)}

    @http.route('/audit/dashboard', type='http', auth='user', website=True)
    def audit_dashboard(self, **kwargs):
        """Audit dashboard page"""
        if not request.env.user.has_group('peepl_audit_session.group_audit_user'):
            return request.not_found()
            
        # Get user's current session
        current_session = request.env['audit.session'].search([
            ('session_id', '=', request.session.sid),
            ('user_id', '=', request.env.user.id),
            ('status', '=', 'active')
        ], limit=1)
        
        # Get user's recent sessions
        recent_sessions = request.env['audit.session'].search([
            ('user_id', '=', request.env.user.id)
        ], limit=10, order='login_time desc')
        
        # Get user's recent activity
        recent_activity = request.env['audit.log.entry'].search([
            ('user_id', '=', request.env.user.id)
        ], limit=20, order='action_date desc')
        
        values = {
            'current_session': current_session,
            'recent_sessions': recent_sessions,
            'recent_activity': recent_activity,
        }
        
        return request.render('peepl_audit_session.audit_dashboard', values)

    @http.route('/audit/session/close', type='json', auth='user', methods=['POST'])
    def close_session(self):
        """Close current audit session"""
        try:
            # Find and close audit session
            audit_session = request.env['audit.session'].search([
                ('session_id', '=', request.session.sid),
                ('user_id', '=', request.env.user.id),
                ('status', '=', 'active')
            ], limit=1)
            
            if audit_session:
                audit_session.close_session()
                _logger.info(f"Audit session closed for user {request.env.user.login}: {audit_session.id}")
                return {'success': True, 'message': 'Session closed successfully'}
            else:
                return {'success': False, 'message': 'No active session found'}
                
        except Exception as e:
            _logger.error(f"Failed to close audit session: {e}")
            return {'success': False, 'error': str(e)}

    @http.route('/audit/api/stats', type='json', auth='user', methods=['POST'])
    def get_audit_stats(self):
        """Get audit statistics for dashboard"""
        if not request.env.user.has_group('peepl_audit_session.group_audit_manager'):
            return {'error': 'Access denied'}
            
        try:
            # Total logs
            total_logs = request.env['audit.log.entry'].search_count([])
            
            # Today's logs
            today_logs = request.env['audit.log.entry'].search_count([
                ('action_date', '>=', request.env.cr.now().date())
            ])
            
            # Active sessions
            active_sessions = request.env['audit.session'].search_count([
                ('status', '=', 'active')
            ])
            
            # Top users by activity
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
            
            # Activity by type
            query = """
                SELECT action_type, COUNT(*) as count
                FROM audit_log_entry
                WHERE action_date >= NOW() - INTERVAL '7 days'
                GROUP BY action_type
            """
            request.env.cr.execute(query)
            activity_by_type = request.env.cr.dictfetchall()
            
            return {
                'total_logs': total_logs,
                'today_logs': today_logs,
                'active_sessions': active_sessions,
                'top_users': top_users,
                'activity_by_type': activity_by_type
            }
            
        except Exception as e:
            _logger.error(f"Failed to get audit stats: {e}")
            return {'error': str(e)}