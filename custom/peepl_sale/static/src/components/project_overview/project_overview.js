/** @odoo-module **/

import { ProjectOverview } from "@project_enterprise/components/project_overview/project_overview";
import { patch } from "@web/core/utils/patch";

// Patch the ProjectOverview component to hide sales-related sections
patch(ProjectOverview.prototype, "peepl_sale.ProjectOverview", {
    
    setup() {
        this._super(...arguments);
        // Override setup to modify data loading if needed
    },

    // Override the method that determines which sections to show
    get showSalesSection() {
        // Always return false to hide sales section
        return false;
    },

    get showProfitabilitySection() {
        // Always return false to hide profitability section
        return false;
    },

    get showSalesOrdersSection() {
        // Always return false to hide sales orders section
        return false;
    },

    // If the component uses a different method to control visibility
    _getSectionsToDisplay() {
        const sections = this._super(...arguments) || [];
        // Filter out sales-related sections
        return sections.filter(section => 
            !['sales', 'profitability', 'sales_orders', 'sale'].includes(section.toLowerCase())
        );
    }
});

// Alternative approach: Patch the component's willStart method to filter data
patch(ProjectOverview.prototype, "peepl_sale.ProjectOverviewData", {
    
    async willStart() {
        await this._super(...arguments);
        
        // Remove sales-related data from the component's state
        if (this.state && this.state.data) {
            // Remove sales sections from data
            delete this.state.data.sales;
            delete this.state.data.profitability;
            delete this.state.data.sales_orders;
            delete this.state.data.sale_orders;
        }
        
        // If data is stored differently, adjust accordingly
        if (this.data) {
            delete this.data.sales;
            delete this.data.profitability;
            delete this.data.sales_orders;
            delete this.data.sale_orders;
        }
    }
});