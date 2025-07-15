# -*- coding: utf-8 -*-
from odoo import models, fields, api


class CrmActivityDashboardWizard(models.TransientModel):
    _name = 'crm.activity.dashboard.wizard'
    _description = 'CRM Activity Dashboard Configuration Wizard'

    @api.model
    def default_get(self, fields):
        result = super().default_get(fields)
        # Set default values based on current user preferences
        result.update({
            'enable_notifications': True,
            'default_view': 'tree',
            'auto_refresh': True,
            'show_revenue': True,
        })
        return result

    # Configuration options
    enable_notifications = fields.Boolean(
        'Enable Activity Notifications',
        default=True,
        help='Send notifications for overdue activities'
    )
    
    default_view = fields.Selection([
        ('tree', 'List View'),
        ('kanban', 'Kanban View'),
        ('calendar', 'Calendar View'),
    ], string='Default View', default='tree',
       help='Default view when opening the dashboard')
    
    auto_refresh = fields.Boolean(
        'Auto Refresh Dashboard',
        default=True,
        help='Automatically refresh dashboard data'
    )
    
    show_revenue = fields.Boolean(
        'Show Revenue Information',
        default=True,
        help='Display expected revenue in activity views'
    )
    
    filter_my_activities = fields.Boolean(
        'Filter My Activities by Default',
        default=True,
        help='Show only activities assigned to current user by default'
    )
    
    filter_active_only = fields.Boolean(
        'Show Active Activities Only',
        default=True,
        help='Hide completed activities by default'
    )
    
    color_scheme = fields.Selection([
        ('default', 'Default Colors'),
        ('high_contrast', 'High Contrast'),
        ('colorblind', 'Colorblind Friendly'),
    ], string='Color Scheme', default='default',
       help='Choose color scheme for activity status')

    def action_configure(self):
        """Apply configuration and open dashboard"""
        # Store user preferences
        user_config = {
            'crm_activity_dashboard_notifications': self.enable_notifications,
            'crm_activity_dashboard_default_view': self.default_view,
            'crm_activity_dashboard_auto_refresh': self.auto_refresh,
            'crm_activity_dashboard_show_revenue': self.show_revenue,
            'crm_activity_dashboard_filter_my': self.filter_my_activities,
            'crm_activity_dashboard_filter_active': self.filter_active_only,
            'crm_activity_dashboard_color_scheme': self.color_scheme,
        }
        
        # Save configuration for current user
        for key, value in user_config.items():
            self.env['ir.config_parameter'].sudo().set_param(
                f'{key}_{self.env.user.id}', value
            )
        
        # Build context for dashboard based on configuration
        context = {}
        if self.filter_my_activities:
            context['search_default_my_activities'] = 1
        if self.filter_active_only:
            context['search_default_active_activities'] = 1
        
        # Open the dashboard with configured settings
        return {
            'type': 'ir.actions.act_window',
            'name': 'CRM Activity Dashboard',
            'res_model': 'crm.activity.dashboard',
            'view_mode': self.default_view + ',tree,kanban,form,calendar,pivot,graph',
            'target': 'current',
            'context': context,
        }

    def action_skip(self):
        """Skip configuration and open dashboard with defaults"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'CRM Activity Dashboard',
            'res_model': 'crm.activity.dashboard',
            'view_mode': 'tree,kanban,form,calendar,pivot,graph',
            'target': 'current',
            'context': {
                'search_default_my_activities': 1,
                'search_default_active_activities': 1,
            },
        }
