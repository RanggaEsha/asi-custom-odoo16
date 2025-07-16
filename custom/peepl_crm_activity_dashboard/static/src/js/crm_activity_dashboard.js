/** @odoo-module **/

import { registry } from "@web/core/registry";
import { ListController } from "@web/views/list/list_controller";
import { KanbanController } from "@web/views/kanban/kanban_controller";

/**
 * CRM Activity Dashboard Real-time Updates
 * 
 * This controller handles real-time updates for the CRM Activity Dashboard
 * by listening to bus notifications and refreshing the view when activities change.
 */
export class CrmActivityDashboardController extends ListController {
    setup() {
        super.setup();
        this.busService = this.env.services.bus_service;
        this.notificationService = this.env.services.notification;
        
        // Subscribe to activity updates
        this.busService.subscribe("dashboard_crm_activity_update", (message) => {
            this.handleActivityUpdate(message);
        });
    }

    /**
     * Handle real-time activity updates
     * @param {Object} message - Bus message containing update information
     */
    async handleActivityUpdate(message) {
        if (message.type === 'activity_update') {
            // Refresh the view to show latest data
            await this.model.load();
            
            // Show notification based on operation type
            const operationMessages = {
                'create': 'New activity created',
                'write': 'Activity updated',
                'unlink': 'Activity deleted',
                'done': 'Activity marked as done',
                'schedule_next': 'Next activity scheduled'
            };
            
            const notificationMessage = operationMessages[message.operation] || 'Activity updated';
            
            this.notificationService.add(
                `${notificationMessage} - Dashboard refreshed`,
                { type: 'info', sticky: false }
            );
        }
    }

    /**
     * Auto-refresh the dashboard every 5 minutes for data consistency
     */
    startAutoRefresh() {
        this.autoRefreshInterval = setInterval(() => {
            this.model.load();
        }, 300000); // 5 minutes
    }

    /**
     * Stop auto-refresh when controller is destroyed
     */
    willUnmount() {
        if (this.autoRefreshInterval) {
            clearInterval(this.autoRefreshInterval);
        }
        super.willUnmount();
    }
}

/**
 * Kanban Controller for CRM Activity Dashboard
 */
export class CrmActivityDashboardKanbanController extends KanbanController {
    setup() {
        super.setup();
        this.busService = this.env.services.bus_service;
        this.notificationService = this.env.services.notification;
        
        // Subscribe to activity updates
        this.busService.subscribe("dashboard_crm_activity_update", (message) => {
            this.handleActivityUpdate(message);
        });
    }

    /**
     * Handle real-time activity updates for Kanban view
     */
    async handleActivityUpdate(message) {
        if (message.type === 'activity_update') {
            // Refresh the kanban view
            await this.model.load();
            
            // Visual feedback for the update
            this.notificationService.add(
                'Dashboard updated with latest activities',
                { type: 'success', sticky: false }
            );
        }
    }
}

// Register the controllers
registry.category("controllers").add("crm_activity_dashboard_list", CrmActivityDashboardController);
registry.category("controllers").add("crm_activity_dashboard_kanban", CrmActivityDashboardKanbanController);
