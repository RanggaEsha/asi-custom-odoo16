/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onMounted, onPatched } from "@odoo/owl";

// Service to hide sales sections across all project views
class ProjectSalesHiderService {
    
    hideSalesSections() {
        // CSS selectors for sales-related sections
        const selectors = [
            '.o_project_overview_sales',
            '.o_project_overview_profitability', 
            '.o_project_overview_sale_orders',
            '[data-section="sales"]',
            '[data-section="profitability"]',
            '[data-section="sale_orders"]',
            // Add more specific selectors based on actual DOM structure
            '.o_project_sales_section',
            '.o_project_profitability_section',
            // Generic selectors for text content
            '.o_stat_text:contains("Sales")',
            '.o_stat_text:contains("Profitability")'
        ];

        selectors.forEach(selector => {
            const elements = document.querySelectorAll(selector);
            elements.forEach(element => {
                // Hide the element and its parent container if needed
                element.style.display = 'none';
                
                // Also hide parent row/container if it becomes empty
                const parent = element.closest('.row, .col, .o_stat_button, .card');
                if (parent && this._isContainerEmpty(parent)) {
                    parent.style.display = 'none';
                }
            });
        });

        // Hide sections by text content (fallback method)
        this._hideByTextContent();
    }

    _hideByTextContent() {
        // Find and hide elements containing sales-related text
        const textPatterns = ['Sales Orders', 'Profitability', /Sales.*Orders?/i, /Profit/i];
        
        textPatterns.forEach(pattern => {
            const xpath = `//text()[contains(., "${pattern}")]`;
            const textNodes = document.evaluate(xpath, document, null, XPathResult.UNORDERED_NODE_SNAPSHOT_TYPE, null);
            
            for (let i = 0; i < textNodes.snapshotLength; i++) {
                const textNode = textNodes.snapshotItem(i);
                const element = textNode.parentElement;
                
                // Hide the containing section/card/row
                const container = element.closest('.card, .row, .col, .o_stat_button, .section');
                if (container) {
                    container.style.display = 'none';
                }
            }
        });
    }

    _isContainerEmpty(container) {
        // Check if container has any visible children
        const visibleChildren = container.querySelectorAll('*:not([style*="display: none"])');
        return visibleChildren.length === 0;
    }
}

// Register the service
registry.category("services").add("projectSalesHider", {
    start() {
        return new ProjectSalesHiderService();
    },
});

// Component mixin to automatically hide sales sections
export const ProjectSalesHiderMixin = {
    setup() {
        this.projectSalesHider = this.env.services.projectSalesHider;
        
        onMounted(() => {
            this.projectSalesHider.hideSalesSections();
        });
        
        onPatched(() => {
            this.projectSalesHider.hideSalesSections();
        });
    }
};

// Auto-hide sales sections when DOM changes (global approach)
if (typeof MutationObserver !== 'undefined') {
    const observer = new MutationObserver((mutations) => {
        let shouldHide = false;
        
        mutations.forEach((mutation) => {
            if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
                // Check if any added nodes contain project overview elements
                mutation.addedNodes.forEach((node) => {
                    if (node.nodeType === 1 && ( // Element node
                        node.classList?.contains('o_project_overview') ||
                        node.querySelector?.('.o_project_overview') ||
                        node.classList?.contains('o_form_view') ||
                        node.querySelector?.('.o_form_view')
                    )) {
                        shouldHide = true;
                    }
                });
            }
        });

        if (shouldHide) {
            // Delay hiding to ensure DOM is fully rendered
            setTimeout(() => {
                const service = new ProjectSalesHiderService();
                service.hideSalesSections();
            }, 100);
        }
    });

    // Start observing
    observer.observe(document.body, {
        childList: true,
        subtree: true
    });
}