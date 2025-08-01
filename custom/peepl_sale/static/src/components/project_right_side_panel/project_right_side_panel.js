/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import rpc from 'web.rpc';

// Pending changes tracker
let pendingChanges = {
    participants: new Map(), // participantId -> {originalState, newState, element}
    hasChanges: false
};

// Simple global functions approach
window.setParticipantConfirmed = async function(ev) {
    ev.preventDefault();
    const button = ev.currentTarget;
    const participantId = parseInt(button.dataset.id);
    const participantRow = button.closest('tr');
    
    // Add to pending changes instead of immediate backend call
    addPendingChange(participantId, participantRow, 'confirmed');
    updateParticipantUI(participantRow, 'confirmed');
    showSubmitCancelButtons();
};

window.setParticipantRescheduled = async function(ev) {
    ev.preventDefault();
    const button = ev.currentTarget;
    const participantId = parseInt(button.dataset.id);
    const participantRow = button.closest('tr');
    
    // Add to pending changes instead of immediate backend call
    addPendingChange(participantId, participantRow, 'rescheduled');
    updateParticipantUI(participantRow, 'rescheduled');
    showSubmitCancelButtons();
};

window.setParticipantCancelled = async function(ev) {
    ev.preventDefault();
    const button = ev.currentTarget;
    const participantId = parseInt(button.dataset.id);
    const participantRow = button.closest('tr');
    
    // Add to pending changes instead of immediate backend call
    addPendingChange(participantId, participantRow, 'cancelled');
    updateParticipantUI(participantRow, 'cancelled');
    showSubmitCancelButtons();
};

window.setParticipantReset = async function(ev) {
    ev.preventDefault();
    const button = ev.currentTarget;
    const participantId = parseInt(button.dataset.id);
    const participantRow = button.closest('tr');
    
    // Add to pending changes instead of immediate backend call
    addPendingChange(participantId, participantRow, 'not_yet_confirmed');
    updateParticipantUI(participantRow, 'not_yet_confirmed');
    showSubmitCancelButtons();
};

window.markAllParticipantsCompleted = async function(ev) {
    ev.preventDefault();
    const button = ev.currentTarget;
    
    // Find all pending participants and add them to pending changes
    const participantRows = document.querySelectorAll('table tbody tr');
    let changedCount = 0;
    
    participantRows.forEach(row => {
        const stateCell = row.querySelector('td:nth-child(4)');
        if (stateCell && stateCell.textContent.trim() === 'not_yet_confirmed') {
            const participantId = getParticipantIdFromRow(row);
            if (participantId) {
                addPendingChange(participantId, row, 'confirmed');
                updateParticipantUI(row, 'confirmed');
                changedCount++;
            }
        }
    });
    
    if (changedCount > 0) {
        updateParticipantCounters();
        showSubmitCancelButtons();
        showNotification(`${changedCount} participants marked as completed. Click Submit to save changes.`, 'info', 'Pending Changes');
    }
};

// New functions for the confirmation flow
window.submitChanges = async function() {
    const submitButton = document.getElementById('submit-changes-btn');
    const cancelButton = document.getElementById('cancel-changes-btn');
    
    if (!pendingChanges.hasChanges) return;
    
    // Show loading state
    setButtonLoading(submitButton, true);
    setButtonLoading(cancelButton, true);
    
    try {
        let successCount = 0;
        let errorCount = 0;
        
        // Process all pending changes
        for (const [participantId, change] of pendingChanges.participants) {
            try {
                let result;
                
                if (change.newState === 'confirmed') {
                    result = await rpc.query({
                        model: 'participant',
                        method: 'action_set_confirmed',
                        args: [participantId],
                    });
                } else if (change.newState === 'rescheduled') {
                    result = await rpc.query({
                        model: 'participant',
                        method: 'action_set_rescheduled',
                        args: [participantId],
                    });
                } else if (change.newState === 'cancelled') {
                    result = await rpc.query({
                        model: 'participant',
                        method: 'action_set_cancelled',
                        args: [participantId],
                    });
                } else if (change.newState === 'not_yet_confirmed') {
                    // For reset, we need to update the participant state back to not_yet_confirmed
                    result = await rpc.query({
                        model: 'participant',
                        method: 'write',
                        args: [participantId, {
                            'state': 'not_yet_confirmed',
                            'completion_date': false
                        }],
                    });
                }
                
                successCount++;
            } catch (error) {
                console.error(`Error updating participant ${participantId}:`, error);
                errorCount++;
            }
        }
        
        // Clear pending changes
        clearPendingChanges();
        hideSubmitCancelButtons();
        
        // Show result notification
        if (errorCount === 0) {
            showNotification(`Successfully updated ${successCount} participants!`, 'success', 'Changes Saved');
        } else {
            showNotification(`Updated ${successCount} participants, ${errorCount} failed.`, 'warning', 'Partial Success');
        }
        
    } catch (error) {
        console.error('Error submitting changes:', error);
        showNotification('Error saving changes. Please try again.', 'danger', 'Save Failed');
    } finally {
        setButtonLoading(submitButton, false);
        setButtonLoading(cancelButton, false);
    }
};

window.cancelChanges = function() {
    // Revert all UI changes
    for (const [participantId, change] of pendingChanges.participants) {
        revertParticipantUI(change.element, change.originalState);
    }
    
    // Clear pending changes and hide buttons
    clearPendingChanges();
    hideSubmitCancelButtons();
    updateParticipantCounters();
    
    showNotification('All changes have been cancelled.', 'info', 'Changes Cancelled');
};

// Helper functions for pending changes management
function addPendingChange(participantId, element, newState) {
    // Store original state if not already stored
    if (!pendingChanges.participants.has(participantId)) {
        const originalState = getOriginalParticipantState(element);
        pendingChanges.participants.set(participantId, {
            originalState: originalState,
            newState: newState,
            element: element
        });
    } else {
        // Update the new state but keep original state
        const existing = pendingChanges.participants.get(participantId);
        existing.newState = newState;
    }
    
    pendingChanges.hasChanges = true;
}

function getOriginalParticipantState(element) {
    const stateCell = element.querySelector('td:nth-child(4)');
    return stateCell ? stateCell.textContent.trim() : 'not_yet_confirmed';
}

function getParticipantIdFromRow(row) {
    // Try to get participant ID from action buttons
    const buttons = row.querySelectorAll('button[data-id]');
    if (buttons.length > 0) {
        return parseInt(buttons[0].dataset.id);
    }
    return null;
}

function clearPendingChanges() {
    pendingChanges.participants.clear();
    pendingChanges.hasChanges = false;
}

function revertParticipantUI(element, originalState) {
    // Revert state column
    const stateCell = element.querySelector('td:nth-child(4)');
    if (stateCell) {
        stateCell.textContent = originalState;
    }
    
    // Revert actions column - restore appropriate buttons based on original state
    const actionsCell = element.querySelector('td:nth-child(5)');
    const participantId = getParticipantIdFromRow(element);
    
    if (actionsCell && participantId) {
        if (originalState === 'not_yet_confirmed') {
            // Show the action buttons for pending participants
            actionsCell.innerHTML = `
                <button onclick="setParticipantConfirmed(event)" data-id="${participantId}" class="btn btn-success btn-sm" title="Complete">
                    <i class="fa fa-check"></i>
                </button>
                <button onclick="setParticipantRescheduled(event)" data-id="${participantId}" class="btn btn-warning btn-sm" title="Reschedule">
                    <i class="fa fa-clock-o"></i>
                </button>
                <button onclick="setParticipantCancelled(event)" data-id="${participantId}" class="btn btn-danger btn-sm" title="Cancel">
                    <i class="fa fa-times"></i>
                </button>
            `;
        } else {
            // Show reset button for completed/cancelled/rescheduled participants
            const stateBadges = {
                'confirmed': '<span class="badge badge-success">✅ Completed</span>',
                'rescheduled': '<span class="badge badge-warning">⟳ Rescheduled</span>',
                'cancelled': '<span class="badge badge-danger">❌ Cancelled</span>'
            };
            actionsCell.innerHTML = `
                <div style="display: flex; align-items: center; gap: 8px;">
                    ${stateBadges[originalState] || ''}
                    <button onclick="setParticipantReset(event)" data-id="${participantId}" class="btn btn-info btn-sm" title="Reset to Pending">
                        <i class="fa fa-undo"></i>
                    </button>
                </div>
            `;
        }
    }
    
    // Remove row styling and pending border
    element.className = element.className.replace(/table-\w+/g, '');
    element.style.border = '';
}

function showSubmitCancelButtons() {
    // Remove existing buttons if any
    hideSubmitCancelButtons();
    
    // Create submit/cancel buttons container
    const buttonsContainer = document.createElement('div');
    buttonsContainer.id = 'submit-cancel-container';
    buttonsContainer.style.cssText = `
        position: fixed;
        bottom: 20px;
        right: 20px;
        z-index: 1000;
        display: flex;
        gap: 10px;
        padding: 15px;
        background: white;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        border: 1px solid #ddd;
    `;
    
    // Submit button
    const submitBtn = document.createElement('button');
    submitBtn.id = 'submit-changes-btn';
    submitBtn.innerHTML = '<i class="fa fa-check"></i> Submit Changes';
    submitBtn.className = 'btn btn-primary';
    submitBtn.style.cssText = 'min-width: 120px;';
    submitBtn.onclick = submitChanges;
    
    // Cancel button  
    const cancelBtn = document.createElement('button');
    cancelBtn.id = 'cancel-changes-btn';
    cancelBtn.innerHTML = '<i class="fa fa-times"></i> Cancel';
    cancelBtn.className = 'btn btn-secondary';
    cancelBtn.style.cssText = 'min-width: 120px;';
    cancelBtn.onclick = cancelChanges;
    
    // Add change counter
    const counter = document.createElement('div');
    counter.style.cssText = 'display: flex; align-items: center; margin-right: 10px; color: #666; font-size: 14px;';
    counter.innerHTML = `<i class="fa fa-edit" style="margin-right: 5px;"></i> ${pendingChanges.participants.size} changes`;
    
    buttonsContainer.appendChild(counter);
    buttonsContainer.appendChild(submitBtn);
    buttonsContainer.appendChild(cancelBtn);
    
    document.body.appendChild(buttonsContainer);
    
    // Add entrance animation
    setTimeout(() => {
        buttonsContainer.style.animation = 'slideInUp 0.3s ease-out';
    }, 10);
    
    // Add CSS animation if not exists
    if (!document.getElementById('submit-cancel-animations')) {
        const style = document.createElement('style');
        style.id = 'submit-cancel-animations';
        style.textContent = `
            @keyframes slideInUp {
                from { transform: translateY(100%); opacity: 0; }
                to { transform: translateY(0); opacity: 1; }
            }
            @keyframes slideOutDown {
                from { transform: translateY(0); opacity: 1; }
                to { transform: translateY(100%); opacity: 0; }
            }
        `;
        document.head.appendChild(style);
    }
}

function hideSubmitCancelButtons() {
    const container = document.getElementById('submit-cancel-container');
    if (container) {
        container.style.animation = 'slideOutDown 0.3s ease-in';
        setTimeout(() => {
            if (container.parentNode) {
                container.parentNode.removeChild(container);
            }
        }, 300);
    }
}

function updateParticipantUI(participantRow, newState) {
    if (!participantRow || !newState) return;
    
    // Update the state column
    const stateCell = participantRow.querySelector('td:nth-child(4)'); // Status column
    if (stateCell) {
        stateCell.textContent = newState;
    }
    
    // Update the actions column based on new state
    const actionsCell = participantRow.querySelector('td:nth-child(5)'); // Actions column
    const participantId = getParticipantIdFromRow(participantRow);
    
    if (actionsCell && participantId) {
        if (newState === 'not_yet_confirmed') {
            // Show action buttons for pending participants (with pending indicator)
            actionsCell.innerHTML = `
                <button onclick="setParticipantConfirmed(event)" data-id="${participantId}" class="btn btn-success btn-sm" title="Complete">
                    <i class="fa fa-check"></i>
                </button>
                <button onclick="setParticipantRescheduled(event)" data-id="${participantId}" class="btn btn-warning btn-sm" title="Reschedule">
                    <i class="fa fa-clock-o"></i>
                </button>
                <button onclick="setParticipantCancelled(event)" data-id="${participantId}" class="btn btn-danger btn-sm" title="Cancel">
                    <i class="fa fa-times"></i>
                </button>
                <small class="text-info d-block mt-1">(pending reset)</small>
            `;
        } else {
            // Show state badge and reset button for completed/cancelled/rescheduled participants
            const stateBadges = {
                'confirmed': '<span class="badge badge-success">✅ Completed <small>(pending)</small></span>',
                'rescheduled': '<span class="badge badge-warning">⟳ Rescheduled <small>(pending)</small></span>',
                'cancelled': '<span class="badge badge-danger">❌ Cancelled <small>(pending)</small></span>'
            };
            actionsCell.innerHTML = `
                <div style="display: flex; align-items: center; gap: 8px;">
                    ${stateBadges[newState] || ''}
                    <button onclick="setParticipantReset(event)" data-id="${participantId}" class="btn btn-info btn-sm" title="Reset to Pending">
                        <i class="fa fa-undo"></i>
                    </button>
                </div>
            `;
        }
    }
    
    // Add row styling based on state with pending indicator
    participantRow.className = participantRow.className.replace(/table-\w+/g, '');
    
    if (newState === 'not_yet_confirmed') {
        // For reset to pending, show neutral styling with pending border
        participantRow.style.border = '2px dashed rgba(0,123,255,0.5)';
    } else {
        const rowStyles = {
            'confirmed': 'table-success',
            'rescheduled': 'table-warning', 
            'cancelled': 'table-danger'
        };
        if (rowStyles[newState]) {
            participantRow.classList.add(rowStyles[newState]);
            // Add subtle border to indicate pending change
            participantRow.style.border = '2px dashed rgba(0,0,0,0.3)';
        }
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