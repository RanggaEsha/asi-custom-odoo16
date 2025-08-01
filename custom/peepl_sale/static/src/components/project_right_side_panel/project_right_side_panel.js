/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

// Pending changes tracker
let pendingChanges = {
    participants: new Map(),
    hasChanges: false
};

// Get RPC service - try multiple approaches
function getRpcService() {
    // Try to get from window.odoo
    if (window.odoo?.env?.services?.rpc) {
        return window.odoo.env.services.rpc;
    }
    
    // Try to get from the registry
    try {
        const services = registry.category("services");
        const rpcService = services.get("rpc");
        if (rpcService) {
            return rpcService;
        }
    } catch (e) {
        // Service not available
    }
    
    return null;
}

// Get notification service
function getNotificationService() {
    if (window.odoo?.env?.services?.notification) {
        return window.odoo.env.services.notification;
    }
    
    try {
        const services = registry.category("services");
        const notificationService = services.get("notification");
        if (notificationService) {
            return notificationService;
        }
    } catch (e) {
        // Service not available
    }
    
    return null;
}

// Simple RPC call function
async function callRpc(model, method, args = [], kwargs = {}) {
    console.log(`Making RPC call: ${model}.${method}`, { args, kwargs });
    
    const rpcService = getRpcService();
    
    if (rpcService && typeof rpcService.query === 'function') {
        try {
            const result = await rpcService.query("/web/dataset/call_kw", {
                model: model,
                method: method,
                args: args,
                kwargs: kwargs
            });
            console.log(`RPC call successful: ${model}.${method}`, result);
            return result;
        } catch (error) {
            console.error(`RPC call failed: ${model}.${method}`, error);
            throw error;
        }
    } else {
        // Fallback using fetch
        console.log('Using fallback fetch method for RPC');
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
        
        try {
            const response = await fetch('/web/dataset/call_kw', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken || '',
                },
                body: JSON.stringify({
                    jsonrpc: "2.0",
                    method: "call",
                    params: {
                        model: model,
                        method: method,
                        args: args,
                        kwargs: kwargs
                    }
                })
            });
            
            const data = await response.json();
            console.log('Fetch response:', data);
            
            if (data.error) {
                console.error('RPC Error:', data.error);
                throw new Error(data.error.message || 'RPC Error');
            }
            return data.result;
        } catch (error) {
            console.error('Fetch error:', error);
            throw error;
        }
    }
}

// Simple notification function
function notify(message, type = 'info', title = '') {
    const notificationService = getNotificationService();
    if (notificationService) {
        if (typeof notificationService === 'function') {
            notificationService(message, { title, type });
        } else if (typeof notificationService.add === 'function') {
            notificationService.add(message, { title, type });
        } else {
            showCustomToast(message, type, title);
        }
    } else {
        showCustomToast(message, type, title);
    }
}

// === GLOBAL FUNCTIONS (These are called by the XML template) ===

window.setParticipantConfirmed = async function(ev) {
    ev.preventDefault();
    const button = ev.currentTarget;
    const participantId = parseInt(button.dataset.id);
    const participantRow = button.closest('tr');
    
    addPendingChange(participantId, participantRow, 'confirmed');
    updateParticipantUI(participantRow, 'confirmed');
    showSubmitCancelButtons();
};

window.setParticipantRescheduled = async function(ev) {
    ev.preventDefault();
    const button = ev.currentTarget;
    const participantId = parseInt(button.dataset.id);
    const participantRow = button.closest('tr');
    
    addPendingChange(participantId, participantRow, 'rescheduled');
    updateParticipantUI(participantRow, 'rescheduled');
    showSubmitCancelButtons();
};

window.setParticipantCancelled = async function(ev) {
    ev.preventDefault();
    const button = ev.currentTarget;
    const participantId = parseInt(button.dataset.id);
    const participantRow = button.closest('tr');
    
    addPendingChange(participantId, participantRow, 'cancelled');
    updateParticipantUI(participantRow, 'cancelled');
    showSubmitCancelButtons();
};

window.setParticipantReset = async function(ev) {
    ev.preventDefault();
    const button = ev.currentTarget;
    const participantId = parseInt(button.dataset.id);
    const participantRow = button.closest('tr');
    
    addPendingChange(participantId, participantRow, 'not_yet_confirmed');
    updateParticipantUI(participantRow, 'not_yet_confirmed');
    showSubmitCancelButtons();
};

window.markAllParticipantsCompleted = async function(ev) {
    ev.preventDefault();
    
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
        notify(`${changedCount} participants marked as completed. Click Submit to save changes.`, 'info', 'Pending Changes');
    }
};

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
        const errors = [];
        
        console.log(`Starting to process ${pendingChanges.participants.size} participant changes`);
        
        // Process all pending changes
        for (const [participantId, change] of pendingChanges.participants) {
            try {
                console.log(`Processing participant ${participantId} - changing from ${change.originalState} to ${change.newState}`);
                
                // Prepare write data based on new state
                let writeData = { 'state': change.newState };
                
                // Set completion_date based on state
                if (change.newState === 'confirmed') {
                    writeData['completion_date'] = new Date().toISOString().split('T')[0];
                } else {
                    writeData['completion_date'] = false;
                }
                
                console.log(`Write data for participant ${participantId}:`, writeData);
                
                // Try the write operation with multiple fallback strategies
                let writeSuccess = false;
                let lastError = null;
                
                // Strategy 1: Direct write with all fields
                try {
                    const result = await callRpc('participant', 'write', [[participantId], writeData]);
                    console.log(`✅ Direct write successful for participant ${participantId}:`, result);
                    writeSuccess = true;
                } catch (error) {
                    console.log(`❌ Direct write failed for participant ${participantId}:`, error);
                    lastError = error;
                }
                
                // Strategy 2: Write only state field if full write failed
                if (!writeSuccess) {
                    try {
                        console.log(`Trying state-only write for participant ${participantId}`);
                        const result = await callRpc('participant', 'write', [[participantId], { 'state': change.newState }]);
                        console.log(`✅ State-only write successful for participant ${participantId}:`, result);
                        writeSuccess = true;
                        
                        // Try to update completion_date separately if state write worked
                        if (writeData.completion_date !== undefined) {
                            try {
                                await callRpc('participant', 'write', [[participantId], { 'completion_date': writeData.completion_date }]);
                                console.log(`✅ Completion date updated separately for participant ${participantId}`);
                            } catch (dateError) {
                                console.log(`⚠️ State updated but completion date failed for participant ${participantId}:`, dateError);
                            }
                        }
                    } catch (error) {
                        console.log(`❌ State-only write also failed for participant ${participantId}:`, error);
                        lastError = error;
                    }
                }
                
                // Strategy 3: Try using action methods as fallback
                if (!writeSuccess && change.newState !== 'not_yet_confirmed') {
                    try {
                        let actionMethod = '';
                        if (change.newState === 'confirmed') {
                            actionMethod = 'action_set_confirmed';
                        } else if (change.newState === 'rescheduled') {
                            actionMethod = 'action_set_rescheduled';
                        } else if (change.newState === 'cancelled') {
                            actionMethod = 'action_set_cancelled';
                        } else if (change.newState === 'not_yet_confirmed') {
                            actionMethod = 'action_set_not_yet_confirmed';
                        }
                        
                        if (actionMethod) {
                            console.log(`Trying action method ${actionMethod} for participant ${participantId}`);
                            const result = await callRpc('participant', actionMethod, [[participantId]]);
                            console.log(`✅ Action method successful for participant ${participantId}:`, result);
                            writeSuccess = true;
                        }
                    } catch (error) {
                        console.log(`❌ Action method also failed for participant ${participantId}:`, error);
                        lastError = error;
                    }
                }
                
                if (writeSuccess) {
                    console.log(`✅ Successfully updated participant ${participantId}`);
                    successCount++;
                } else {
                    console.error(`❌ All strategies failed for participant ${participantId}. Last error:`, lastError);
                    errorCount++;
                    errors.push({
                        participantId,
                        error: lastError?.message || 'Unknown error',
                        originalState: change.originalState,
                        targetState: change.newState
                    });
                }
                
            } catch (error) {
                console.error(`❌ Unexpected error updating participant ${participantId}:`, error);
                errorCount++;
                errors.push({
                    participantId,
                    error: error.message || 'Unexpected error',
                    originalState: change.originalState,
                    targetState: change.newState
                });
            }
        }
        
        // Clear pending changes
        clearPendingChanges();
        hideSubmitCancelButtons();
        
        // Show detailed result notification
        if (errorCount === 0) {
            notify(`Successfully updated ${successCount} participants!`, 'success', 'Changes Saved');
        } else if (successCount > 0) {
            console.log('Errors encountered:', errors);
            notify(`Updated ${successCount} participants successfully, ${errorCount} failed. Check console for details.`, 'warning', 'Partial Success');
        } else {
            console.log('All operations failed. Errors:', errors);
            notify(`Failed to update any participants. Check console for details.`, 'danger', 'Save Failed');
        }
        
        // Refresh the page after a longer delay to show updated data
        setTimeout(() => {
            window.location.reload();
        }, 1000); // Increased delay from 2s to 7s

        // To disable reload, comment out the above lines:
        // setTimeout(() => {
        //     window.location.reload();
        // }, 7000);
        
    } catch (error) {
        console.error('❌ Critical error in submitChanges:', error);
        notify('Critical error saving changes. Please try again.', 'danger', 'Save Failed');
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
    
    notify('All changes have been cancelled.', 'info', 'Changes Cancelled');
};

// === HELPER FUNCTIONS ===

function addPendingChange(participantId, element, newState) {
    if (!pendingChanges.participants.has(participantId)) {
        const originalState = getOriginalParticipantState(element);
        pendingChanges.participants.set(participantId, {
            originalState: originalState,
            newState: newState,
            element: element
        });
    } else {
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
    const stateCell = element.querySelector('td:nth-child(4)');
    if (stateCell) {
        stateCell.textContent = originalState;
    }
    
    const actionsCell = element.querySelector('td:nth-child(5)');
    const participantId = getParticipantIdFromRow(element);
    
    if (actionsCell && participantId) {
        if (originalState === 'not_yet_confirmed') {
            actionsCell.innerHTML = `
                <div class="btn-group btn-group-sm" role="group">
                    <button onclick="setParticipantConfirmed(event)" data-id="${participantId}" class="btn btn-success btn-sm" title="Complete" type="button">
                        <i class="fa fa-check"></i>
                    </button>
                    <button onclick="setParticipantRescheduled(event)" data-id="${participantId}" class="btn btn-warning btn-sm" title="Reschedule" type="button">
                        <i class="fa fa-clock-o"></i>
                    </button>
                    <button onclick="setParticipantCancelled(event)" data-id="${participantId}" class="btn btn-danger btn-sm" title="Cancel" type="button">
                        <i class="fa fa-times"></i>
                    </button>
                </div>
            `;
        } else {
            const stateBadges = {
                'confirmed': '<span class="badge bg-success"><i class="fa fa-check me-1"></i>Completed</span>',
                'rescheduled': '<span class="badge bg-warning text-dark"><i class="fa fa-clock-o me-1"></i>Rescheduled</span>',
                'cancelled': '<span class="badge bg-danger"><i class="fa fa-times me-1"></i>Cancelled</span>'
            };
            actionsCell.innerHTML = `
                <div class="d-flex align-items-center justify-content-between">
                    <div>${stateBadges[originalState] || ''}</div>
                    <button onclick="setParticipantReset(event)" data-id="${participantId}" class="btn btn-info btn-sm ms-2" title="Reset to Pending" type="button">
                        <i class="fa fa-undo"></i>
                    </button>
                </div>
            `;
        }
    }
    
    element.className = element.className.replace(/table-\w+/g, '');
    element.style.border = '';
}

function showSubmitCancelButtons() {
    hideSubmitCancelButtons();
    
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
    
    const submitBtn = document.createElement('button');
    submitBtn.id = 'submit-changes-btn';
    submitBtn.innerHTML = '<i class="fa fa-check"></i> Submit Changes';
    submitBtn.className = 'btn btn-primary';
    submitBtn.style.cssText = 'min-width: 120px;';
    submitBtn.onclick = window.submitChanges;
    
    const cancelBtn = document.createElement('button');
    cancelBtn.id = 'cancel-changes-btn';
    cancelBtn.innerHTML = '<i class="fa fa-times"></i> Cancel';
    cancelBtn.className = 'btn btn-secondary';
    cancelBtn.style.cssText = 'min-width: 120px;';
    cancelBtn.onclick = window.cancelChanges;
    
    const counter = document.createElement('div');
    counter.style.cssText = 'display: flex; align-items: center; margin-right: 10px; color: #666; font-size: 14px;';
    counter.innerHTML = `<i class="fa fa-edit" style="margin-right: 5px;"></i> ${pendingChanges.participants.size} changes`;
    
    buttonsContainer.appendChild(counter);
    buttonsContainer.appendChild(submitBtn);
    buttonsContainer.appendChild(cancelBtn);
    
    document.body.appendChild(buttonsContainer);
    
    setTimeout(() => {
        buttonsContainer.style.animation = 'slideInUp 0.3s ease-out';
    }, 10);
    
    addAnimationStyles();
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
    
    const stateCell = participantRow.querySelector('td:nth-child(4)');
    if (stateCell) {
        stateCell.textContent = newState;
    }
    
    const actionsCell = participantRow.querySelector('td:nth-child(5)');
    const participantId = getParticipantIdFromRow(participantRow);
    
    if (actionsCell && participantId) {
        if (newState === 'not_yet_confirmed') {
            actionsCell.innerHTML = `
                <div class="btn-group btn-group-sm" role="group">
                    <button onclick="setParticipantConfirmed(event)" data-id="${participantId}" class="btn btn-success btn-sm" title="Complete" type="button">
                        <i class="fa fa-check"></i>
                    </button>
                    <button onclick="setParticipantRescheduled(event)" data-id="${participantId}" class="btn btn-warning btn-sm" title="Reschedule" type="button">
                        <i class="fa fa-clock-o"></i>
                    </button>
                    <button onclick="setParticipantCancelled(event)" data-id="${participantId}" class="btn btn-danger btn-sm" title="Cancel" type="button">
                        <i class="fa fa-times"></i>
                    </button>
                </div>
                <small class="text-info d-block mt-1">(pending reset)</small>
            `;
        } else {
            const stateBadges = {
                'confirmed': '<span class="badge bg-success"><i class="fa fa-check me-1"></i>Completed <small>(pending)</small></span>',
                'rescheduled': '<span class="badge bg-warning text-dark"><i class="fa fa-clock-o me-1"></i>Rescheduled <small>(pending)</small></span>',
                'cancelled': '<span class="badge bg-danger"><i class="fa fa-times me-1"></i>Cancelled <small>(pending)</small></span>'
            };
            actionsCell.innerHTML = `
                <div class="d-flex align-items-center justify-content-between">
                    <div>${stateBadges[newState] || ''}</div>
                    <button onclick="setParticipantReset(event)" data-id="${participantId}" class="btn btn-info btn-sm ms-2" title="Reset to Pending" type="button">
                        <i class="fa fa-undo"></i>
                    </button>
                </div>
            `;
        }
    }
    
    participantRow.className = participantRow.className.replace(/table-\w+/g, '');
    
    if (newState === 'not_yet_confirmed') {
        participantRow.style.border = '2px dashed rgba(0,123,255,0.5)';
    } else {
        const rowStyles = {
            'confirmed': 'table-success',
            'rescheduled': 'table-warning', 
            'cancelled': 'table-danger'
        };
        if (rowStyles[newState]) {
            participantRow.classList.add(rowStyles[newState]);
            participantRow.style.border = '2px dashed rgba(0,0,0,0.3)';
        }
    }
}

function updateParticipantCounters() {
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
    
    if (markAllButton) {
        markAllButton.style.display = pendingCount > 0 ? 'block' : 'none';
    }
    
    updateCounterDisplays(totalCount, completedCount, pendingCount);
}

function updateCounterDisplays(total, completed, pending) {
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

function showCustomToast(message, type = 'info', title = '') {
    const toast = document.createElement('div');
    
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
    
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'slideOutRight 0.3s ease-in';
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 300);
    }, 4000);
    
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
    if (!button) return;
    
    if (isLoading) {
        button.dataset.originalHtml = button.innerHTML;
        button.disabled = true;
        button.style.opacity = '0.7';
        button.style.cursor = 'not-allowed';
        button.innerHTML = '<i class="fa fa-spinner fa-spin"></i>';
    } else {
        button.disabled = false;
        button.style.opacity = '1';
        button.style.cursor = 'pointer';
        button.innerHTML = button.dataset.originalHtml || button.innerHTML;
    }
}

function addAnimationStyles() {
    if (!document.getElementById('participant-animations')) {
        const style = document.createElement('style');
        style.id = 'participant-animations';
        style.textContent = `
            @keyframes slideInUp {
                from { transform: translateY(100%); opacity: 0; }
                to { transform: translateY(0); opacity: 1; }
            }
            @keyframes slideOutDown {
                from { transform: translateY(0); opacity: 1; }
                to { transform: translateY(100%); opacity: 0; }
            }
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
}

// Initialize when the module loads
console.log('Project Right Side Panel participant handlers loaded successfully');

// Debug function to test if functions are available
window.testParticipantFunctions = function() {
    console.log('Testing participant functions...');
    console.log('setParticipantConfirmed:', typeof window.setParticipantConfirmed);
    console.log('setParticipantRescheduled:', typeof window.setParticipantRescheduled);
    console.log('setParticipantCancelled:', typeof window.setParticipantCancelled);
    console.log('setParticipantReset:', typeof window.setParticipantReset);
    console.log('markAllParticipantsCompleted:', typeof window.markAllParticipantsCompleted);
    console.log('submitChanges:', typeof window.submitChanges);
    console.log('cancelChanges:', typeof window.cancelChanges);
    
    notify('Function test completed - check console', 'info', 'Debug');
};

// Debug function to test RPC connection
window.testRpcConnection = async function() {
    console.log('Testing RPC connection...');
    
    try {
        // Test with a simple read call first
        const result = await callRpc('participant', 'search_read', [[], ['id', 'first_name', 'last_name', 'state']], { limit: 1 });
        console.log('RPC test successful:', result);
        notify('RPC connection test successful!', 'success', 'Debug');
        return result;
    } catch (error) {
        console.error('RPC test failed:', error);
        notify(`RPC test failed: ${error.message}`, 'danger', 'Debug');
        throw error;
    }
};

// Debug function to test specific participant method
window.testParticipantMethod = async function(participantId) {
    if (!participantId) {
        // Try to get the first participant ID from the table
        const firstButton = document.querySelector('button[data-id]');
        if (firstButton) {
            participantId = parseInt(firstButton.dataset.id);
        } else {
            notify('No participant ID found. Please provide one.', 'warning', 'Debug');
            return;
        }
    }
    
    console.log(`Testing participant method with ID: ${participantId}`);
    
    try {
        // Test reading the participant first
        const participant = await callRpc('participant', 'read', [[participantId], ['id', 'first_name', 'last_name', 'state']]);
        console.log('Participant read successful:', participant);
        
        // Test if the action methods exist
        try {
            const result = await callRpc('participant', 'action_set_confirmed', [[participantId]]);
            console.log('action_set_confirmed test successful:', result);
            notify('Participant method test successful!', 'success', 'Debug');
        } catch (methodError) {
            console.error('Method test failed:', methodError);
            notify(`Method test failed: ${methodError.message}`, 'danger', 'Debug');
        }
        
    } catch (error) {
        console.error('Participant test failed:', error);
        notify(`Participant test failed: ${error.message}`, 'danger', 'Debug');
        throw error;
    }
};