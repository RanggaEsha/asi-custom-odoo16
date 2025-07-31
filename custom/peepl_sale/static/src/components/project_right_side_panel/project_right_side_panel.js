/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import rpc from 'web.rpc';

// Simple global functions approach
window.setParticipantConfirmed = async function(ev) {
    ev.preventDefault();
    const button = ev.currentTarget;
    const participantId = parseInt(button.dataset.id);
    const participantRow = button.closest('tr');
    
    // Add loading state
    setButtonLoading(button, true);
    
    try {
        const result = await rpc.query({
            model: 'participant',
            method: 'action_set_confirmed',
            args: [participantId],
        });
        
        handleParticipantActionResult(result, participantRow, 'confirmed');
    } catch (error) {
        console.error('Error setting participant confirmed:', error);
        showNotification('Error updating participant status', 'danger');
    } finally {
        setButtonLoading(button, false);
    }
};

window.setParticipantRescheduled = async function(ev) {
    ev.preventDefault();
    const button = ev.currentTarget;
    const participantId = parseInt(button.dataset.id);
    const participantRow = button.closest('tr');
    
    // Add loading state
    setButtonLoading(button, true);
    
    try {
        const result = await rpc.query({
            model: 'participant',
            method: 'action_set_rescheduled',
            args: [participantId],
        });
        
        handleParticipantActionResult(result, participantRow, 'rescheduled');
    } catch (error) {
        console.error('Error setting participant rescheduled:', error);
        showNotification('Error updating participant status', 'danger');
    } finally {
        setButtonLoading(button, false);
    }
};

window.setParticipantCancelled = async function(ev) {
    ev.preventDefault();
    const button = ev.currentTarget;
    const participantId = parseInt(button.dataset.id);
    const participantRow = button.closest('tr');
    
    // Add loading state
    setButtonLoading(button, true);
    
    try {
        const result = await rpc.query({
            model: 'participant',
            method: 'action_set_cancelled',
            args: [participantId],
        });
        
        handleParticipantActionResult(result, participantRow, 'cancelled');
    } catch (error) {
        console.error('Error setting participant cancelled:', error);
        showNotification('Error updating participant status', 'danger');
    } finally {
        setButtonLoading(button, false);
    }
};

window.markAllParticipantsCompleted = async function(ev) {
    ev.preventDefault();
    const button = ev.currentTarget;
    const projectId = getProjectIdFromURL() || button.dataset.projectId;
    
    if (!projectId) {
        showNotification('Project ID not found', 'danger');
        return;
    }
    
    // Add loading state
    setButtonLoading(button, true);
    
    try {
        const result = await rpc.query({
            model: 'project.project',
            method: 'action_mark_all_participants_completed',
            args: [parseInt(projectId)],
        });
        
        // For mark all, update all pending participants
        markAllParticipantsAsCompleted();
        handleParticipantActionResult(result, null, null);
    } catch (error) {
        console.error('Error marking all participants completed:', error);
        showNotification('Error updating participants', 'danger');
    } finally {
        setButtonLoading(button, false);
    }
};

function markAllParticipantsAsCompleted() {
    // Find all rows with pending participants and update them
    const participantRows = document.querySelectorAll('table tbody tr');
    participantRows.forEach(row => {
        const stateCell = row.querySelector('td:nth-child(4)');
        if (stateCell && stateCell.textContent.trim() === 'not_yet_confirmed') {
            updateParticipantUI(row, 'confirmed');
        }
    });
    updateParticipantCounters();
}

function handleParticipantActionResult(result, participantElement = null, newState = null) {
    if (result && Array.isArray(result)) {
        for (const action of result) {
            if (action.type === 'ir.actions.client' && action.tag === 'display_notification') {
                showNotification(action.params.message, action.params.type, action.params.title);
            } else if (action.type === 'ir.actions.client' && action.tag === 'reload') {
                // Instead of reloading, just update the UI seamlessly
                updateParticipantUI(participantElement, newState);
                updateParticipantCounters();
            }
        }
    }
}

function updateParticipantUI(participantRow, newState) {
    if (!participantRow || !newState) return;
    
    // Update the state column
    const stateCell = participantRow.querySelector('td:nth-child(4)'); // Status column
    if (stateCell) {
        stateCell.textContent = newState;
    }
    
    // Update the actions column - hide buttons for completed/cancelled/rescheduled
    const actionsCell = participantRow.querySelector('td:nth-child(5)'); // Actions column
    if (actionsCell && newState !== 'not_yet_confirmed') {
        // Clear all buttons and show state badge
        const stateBadges = {
            'confirmed': '<span class="badge badge-success">✅ Completed</span>',
            'rescheduled': '<span class="badge badge-warning">⟳ Rescheduled</span>',
            'cancelled': '<span class="badge badge-danger">❌ Cancelled</span>'
        };
        actionsCell.innerHTML = stateBadges[newState] || '';
    }
    
    // Add row styling based on state
    participantRow.className = participantRow.className.replace(/table-\w+/g, '');
    const rowStyles = {
        'confirmed': 'table-success',
        'rescheduled': 'table-warning', 
        'cancelled': 'table-danger'
    };
    if (rowStyles[newState]) {
        participantRow.classList.add(rowStyles[newState]);
    }
}

function updateParticipantCounters() {
    // Update the "Mark All Test Completed" button visibility
    const markAllButton = document.querySelector('button[onclick*="markAllParticipantsCompleted"]');
    const participantRows = document.querySelectorAll('table tbody tr');
    
    let pendingCount = 0;
    let completedCount = 0;
    let totalCount = participantRows.length;
    
    participantRows.forEach(row => {
        const stateCell = row.querySelector('td:nth-child(4)');
        if (stateCell) {
            const state = stateCell.textContent.trim();
            if (state === 'not_yet_confirmed') {
                pendingCount++;
            } else if (state === 'confirmed') {
                completedCount++;
            }
        }
    });
    
    // Hide "Mark All" button if no pending participants
    if (markAllButton) {
        markAllButton.style.display = pendingCount > 0 ? 'block' : 'none';
    }
    
    // Update any counter displays
    updateCounterDisplays(totalCount, completedCount, pendingCount);
}

function updateCounterDisplays(total, completed, pending) {
    // Update any stat buttons or counters in the UI
    const statButtons = document.querySelectorAll('.oe_stat_button, .o_stat_button');
    statButtons.forEach(button => {
        const statText = button.querySelector('.o_stat_text');
        if (statText && statText.textContent.includes('Participants')) {
            const statValue = button.querySelector('.o_stat_value');
            if (statValue) {
                statValue.textContent = `${completed}/${total}`;
            }
        }
    });
}

function showLoadingOverlay() {
    const overlay = document.createElement('div');
    overlay.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(255,255,255,0.9);
        z-index: 99999;
        display: flex;
        align-items: center;
        justify-content: center;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    `;
    
    overlay.innerHTML = `
        <div style="text-align: center;">
            <div style="
                width: 40px;
                height: 40px;
                border: 4px solid #f3f3f3;
                border-top: 4px solid #007bff;
                border-radius: 50%;
                animation: spin 1s linear infinite;
                margin: 0 auto 15px;
            "></div>
            <div style="color: #666; font-size: 16px;">Refreshing...</div>
        </div>
    `;
    
    // Add CSS animation for spinner
    if (!document.getElementById('loading-animations')) {
        const style = document.createElement('style');
        style.id = 'loading-animations';
        style.textContent = `
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
        `;
        document.head.appendChild(style);
    }
    
    document.body.appendChild(overlay);
}

function showNotification(message, type = 'info', title = '') {
    // Try multiple approaches for better notifications
    
    // Method 1: Try Odoo's modern notification service
    if (window.odoo?.env?.services?.notification) {
        window.odoo.env.services.notification.add(message, {
            title: title,
            type: type,
        });
        return;
    }
    
    // Method 2: Try accessing via registry
    try {
        const { registry } = owl.core;
        const notificationService = registry.category("services").get("notification");
        if (notificationService) {
            notificationService.add(message, {
                title: title,
                type: type,
            });
            return;
        }
    } catch (e) {
        // Continue to next method
    }
    
    // Method 3: Custom toast notification
    showCustomToast(message, type, title);
}

function showCustomToast(message, type = 'info', title = '') {
    // Create custom toast notification
    const toast = document.createElement('div');
    
    // Toast styling based on type
    const typeStyles = {
        'success': 'background: #28a745; color: white; border-left: 4px solid #1e7e34;',
        'danger': 'background: #dc3545; color: white; border-left: 4px solid #bd2130;',
        'warning': 'background: #ffc107; color: #212529; border-left: 4px solid #e0a800;',
        'info': 'background: #17a2b8; color: white; border-left: 4px solid #138496;'
    };
    
    const baseStyle = `
        position: fixed;
        top: 20px;
        right: 20px;
        min-width: 300px;
        max-width: 500px;
        padding: 15px 20px;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        z-index: 10000;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        font-size: 14px;
        line-height: 1.4;
        animation: slideInRight 0.3s ease-out;
        cursor: pointer;
    `;
    
    toast.style.cssText = baseStyle + (typeStyles[type] || typeStyles['info']);
    
    // Toast content
    const titleHtml = title ? `<div style="font-weight: bold; margin-bottom: 5px; font-size: 15px;">${title}</div>` : '';
    const iconMap = {
        'success': '✅',
        'danger': '❌', 
        'warning': '⚠️',
        'info': 'ℹ️'
    };
    
    toast.innerHTML = `
        <div style="display: flex; align-items: flex-start; gap: 10px;">
            <span style="font-size: 18px; flex-shrink: 0;">${iconMap[type] || iconMap['info']}</span>
            <div style="flex: 1;">
                ${titleHtml}
                <div>${message}</div>
            </div>
            <span style="font-size: 18px; opacity: 0.7; margin-left: 10px; cursor: pointer;" onclick="this.parentElement.parentElement.remove()">×</span>
        </div>
    `;
    
    // Add CSS animation
    if (!document.getElementById('toast-animations')) {
        const style = document.createElement('style');
        style.id = 'toast-animations';
        style.textContent = `
            @keyframes slideInRight {
                from { transform: translateX(100%); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
            @keyframes slideOutRight {
                from { transform: translateX(0); opacity: 1; }
                to { transform: translateX(100%); opacity: 0; }
            }
        `;
        document.head.appendChild(style);
    }
    
    // Add to DOM
    document.body.appendChild(toast);
    
    // Auto remove after 4 seconds with slide out animation
    setTimeout(() => {
        toast.style.animation = 'slideOutRight 0.3s ease-in';
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 300);
    }, 4000);
    
    // Click to dismiss
    toast.addEventListener('click', () => {
        toast.style.animation = 'slideOutRight 0.3s ease-in';
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 300);
    });
}

function setButtonLoading(button, isLoading) {
    if (isLoading) {
        // Store original content
        button.dataset.originalHtml = button.innerHTML;
        button.disabled = true;
        button.style.opacity = '0.7';
        button.style.cursor = 'not-allowed';
        
        // Add loading spinner
        button.innerHTML = '<i class="fa fa-spinner fa-spin"></i>';
    } else {
        // Restore original content
        button.disabled = false;
        button.style.opacity = '1';
        button.style.cursor = 'pointer';
        button.innerHTML = button.dataset.originalHtml || button.innerHTML;
    }
}

function getProjectIdFromURL() {
    // Extract project ID from current URL
    const urlParams = new URLSearchParams(window.location.search);
    const activeId = urlParams.get('id');
    if (activeId && window.location.href.includes('project.project')) {
        return parseInt(activeId);
    }
    
    // Try to get from the URL path
    const pathMatch = window.location.pathname.match(/\/web.*?\/(\d+)/);
    if (pathMatch) {
        return parseInt(pathMatch[1]);
    }
    
    return null;
}

console.log('Participant button handlers loaded successfully');