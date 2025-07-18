/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";

export class ActivityDoneSuccessAction extends Component {
    setup() {
        const { params } = this.props.action;
        
        // Show success notification
        this.env.services.notification.add(params.message, {
            title: params.title,
            type: "success",
        });
        
        // Close current dialog/wizard
        this.env.services.action.doAction({
            type: 'ir.actions.act_window_close'
        });
        
        // Reload the current view after a short delay
        setTimeout(() => {
            this.env.services.action.doAction({
                type: 'ir.actions.client',
                tag: 'reload'
            });
        }, 500);
    }
}

ActivityDoneSuccessAction.template = "crm_activity_dashboard.ActivityDoneSuccess";

registry.category("actions").add("activity_done_success", ActivityDoneSuccessAction);
