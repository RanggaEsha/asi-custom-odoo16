/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onMounted, onWillUnmount } from "@odoo/owl";
import { FormController } from "@web/views/form/form_controller";
import { ListController } from "@web/views/list/list_controller";

/**
 * Enhanced Activity Done Success Handler
 * Shows success animation and handles form refresh
 */
export class ActivityDoneSuccessAction extends Component {
    setup() {
        const { params } = this.props.action;
        
        // Show success notification with enhanced styling
        this.env.services.notification.add(params.message, {
            title: params.title,
            type: "success",
            sticky: false,
        });
        
        // If there's a next action, execute it after the notification
        if (params.next) {
            setTimeout(() => {
                this.env.services.action.doAction(params.next);
            }, 100);
        } else {
            // Default: close the wizard
            this.env.services.action.doAction({
                type: 'ir.actions.act_window_close'
            });
        }
    }
}

ActivityDoneSuccessAction.template = "crm_activity_dashboard.ActivityDoneSuccess";

/**
 * Enhanced CRM Activity Dashboard Form Controller
 * Handles success animation and state updates
 */
export class CrmActivityDashboardFormController extends FormController {
    setup() {
        super.setup();
        
        onMounted(() => {
            this.checkForCompletionAnimation();
        });
    }

    /**
     * Check if we should show completion animation
     */
    checkForCompletionAnimation() {
        const context = this.props.context || {};
        
        if (context.activity_just_completed) {
            this.showCompletionAnimation(context.completed_activity_summary);
        }
    }

    /**
     * Show completion animation with confetti-like effect
     */
    showCompletionAnimation(activitySummary) {
        // Create success overlay
        const overlay = document.createElement('div');
        overlay.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(76, 175, 80, 0.1);
            z-index: 9999;
            display: flex;
            justify-content: center;
            align-items: center;
            animation: fadeInOut 2s ease-in-out forwards;
        `;

        const successBox = document.createElement('div');
        successBox.style.cssText = `
            background: white;
            padding: 30px;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            text-align: center;
            transform: scale(0);
            animation: bounceIn 0.6s ease-out forwards;
        `;

        successBox.innerHTML = `
            <div style="font-size: 60px; color: #4CAF50; margin-bottom: 15px;">
                ✓
            </div>
            <h3 style="color: #4CAF50; margin-bottom: 10px;">Activity Completed!</h3>
            <p style="color: #666; margin: 0;">${activitySummary || 'Activity'} has been marked as done.</p>
        `;

        overlay.appendChild(successBox);
        document.body.appendChild(overlay);

        // Add CSS animations
        if (!document.getElementById('completion-animations')) {
            const style = document.createElement('style');
            style.id = 'completion-animations';
            style.textContent = `
                @keyframes fadeInOut {
                    0% { opacity: 0; }
                    20% { opacity: 1; }
                    80% { opacity: 1; }
                    100% { opacity: 0; }
                }
                @keyframes bounceIn {
                    0% { transform: scale(0); }
                    50% { transform: scale(1.1); }
                    100% { transform: scale(1); }
                }
            `;
            document.head.appendChild(style);
        }

        // Remove overlay after animation
        setTimeout(() => {
            if (overlay.parentNode) {
                overlay.parentNode.removeChild(overlay);
            }
        }, 2000);

        // Add green glow effect to the form
        this.addSuccessGlow();
    }

    /**
     * Add green glow effect to the form
     */
    addSuccessGlow() {
        const formElement = this.env.config.parentElement || document.querySelector('.o_form_view');
        if (formElement) {
            formElement.style.transition = 'box-shadow 0.5s ease';
            formElement.style.boxShadow = '0 0 20px rgba(76, 175, 80, 0.5)';
            
            setTimeout(() => {
                formElement.style.boxShadow = '';
            }, 3000);
        }
    }

    /**
     * Override to handle refresh after activity completion
     */
    async onRecordSaved() {
        const result = await super.onRecordSaved();
        
        // Check if we need to refresh the view due to state change
        const record = this.model.root;
        if (record && record.data.state === 'done') {
            // Refresh the record to get latest data
            await this.model.load();
        }
        
        return result;
    }
}

/**
 * Enhanced List Controller for real-time updates
 */
export class CrmActivityDashboardListController extends ListController {
    setup() {
        super.setup();
        
        // Auto-refresh every 5 minutes for data consistency
        this.autoRefreshInterval = setInterval(() => {
            this.refreshData();
        }, 300000); // 5 minutes
    }

    /**
     * Refresh data and show subtle notification
     */
    async refreshData() {
        try {
            await this.model.load();
            
            // Show subtle refresh indicator
            this.showRefreshIndicator();
        } catch (error) {
            console.warn('Failed to refresh dashboard data:', error);
        }
    }

    /**
     * Show subtle refresh indicator
     */
    showRefreshIndicator() {
        const indicator = document.createElement('div');
        indicator.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: #4CAF50;
            color: white;
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 12px;
            z-index: 1000;
            opacity: 0;
            animation: slideInFadeOut 2s ease forwards;
        `;
        indicator.textContent = '✓ Dashboard updated';

        // Add animation if not exists
        if (!document.getElementById('refresh-animations')) {
            const style = document.createElement('style');
            style.id = 'refresh-animations';
            style.textContent = `
                @keyframes slideInFadeOut {
                    0% { opacity: 0; transform: translateX(100px); }
                    15% { opacity: 1; transform: translateX(0); }
                    85% { opacity: 1; transform: translateX(0); }
                    100% { opacity: 0; transform: translateX(100px); }
                }
            `;
            document.head.appendChild(style);
        }

        document.body.appendChild(indicator);

        setTimeout(() => {
            if (indicator.parentNode) {
                indicator.parentNode.removeChild(indicator);
            }
        }, 2000);
    }

    /**
     * Clean up intervals on unmount
     */
    onWillUnmount() {
        if (this.autoRefreshInterval) {
            clearInterval(this.autoRefreshInterval);
        }
        super.onWillUnmount();
    }
}

// Register the enhanced components
registry.category("actions").add("activity_done_success", ActivityDoneSuccessAction);
registry.category("controllers").add("crm_activity_dashboard_form", CrmActivityDashboardFormController);
registry.category("controllers").add("crm_activity_dashboard_list", CrmActivityDashboardListController);