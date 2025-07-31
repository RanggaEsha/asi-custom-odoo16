/** @odoo-module **/

import { ProjectDashboard } from "@project/static/src/components/project_dashboard/project_dashboard";
import { patch } from "@web/core/utils/patch";

// Patch the ProjectDashboard component if it exists
if (ProjectDashboard) {
    patch(ProjectDashboard.prototype, "peepl_sale.ProjectDashboard", {
        
        setup() {
            this._super(...arguments);
            // Filter out sales-related sections from the dashboard
        },

        // Override data loading to exclude sales data
        async loadData() {
            const result = await this._super(...arguments);
            
            // Remove sales-related data
            if (result && result.data) {
                delete result.data.sales;
                delete result.data.profitability;
                delete result.data.sale_orders;
            }
            
            return result;
        },

        // Override sections rendering
        get sections() {
            const originalSections = this._super(...arguments) || [];
            
            // Filter out sales-related sections
            return originalSections.filter(section => {
                const sectionName = section.name || section.key || '';
                return !['sales', 'profitability', 'sale_orders', 'sales_orders'].includes(sectionName.toLowerCase());
            });
        }
    });
}

// Also patch any project-related controllers or views
import { ProjectProjectFormController } from "@project/static/src/views/project_form/project_form_controller";

if (ProjectProjectFormController) {
    patch(ProjectProjectFormController.prototype, "peepl_sale.ProjectFormController", {
        
        async onWillStart() {
            await this._super(...arguments);
            // Remove sales data from form controller
            this._hideSalesSections();
        },

        _hideSalesSections() {
            // Hide sales-related sections in the DOM
            const salesSections = document.querySelectorAll(
                '.o_project_overview_sales, .o_project_overview_profitability, [data-section="sales"], [data-section="profitability"]'
            );
            
            salesSections.forEach(section => {
                section.style.display = 'none';
            });
        }
    });
}