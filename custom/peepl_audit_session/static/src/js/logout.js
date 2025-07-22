// Add this to a JavaScript file in your static/src/js folder
// This will detect when users close browser tabs/windows

odoo.define('peepl_audit_session.logout_detection', function (require) {
    "use strict";

    var ajax = require('web.ajax');
    var core = require('web.core');

    // Track when user closes browser tab/window
    window.addEventListener('beforeunload', function(event) {
        // Send logout signal to server
        ajax.jsonRpc('/audit/session/logout', 'call', {})
            .then(function(result) {
                console.log('Logout tracked:', result);
            })
            .catch(function(error) {
                console.error('Failed to track logout:', error);
            });
    });

    // Track when user navigates away from Odoo
    window.addEventListener('unload', function(event) {
        // Send logout signal to server (fallback)
        navigator.sendBeacon('/audit/session/logout', JSON.stringify({}));
    });

    // Track user inactivity (optional)
    var inactivityTimer;
    var INACTIVITY_TIMEOUT = 30 * 60 * 1000; // 30 minutes

    function resetInactivityTimer() {
        clearTimeout(inactivityTimer);
        inactivityTimer = setTimeout(function() {
            // User inactive for 30 minutes - close session
            ajax.jsonRpc('/audit/session/close', 'call', {})
                .then(function(result) {
                    console.log('Session closed due to inactivity:', result);
                });
        }, INACTIVITY_TIMEOUT);
    }

    // Reset timer on user activity
    document.addEventListener('click', resetInactivityTimer);
    document.addEventListener('keypress', resetInactivityTimer);
    document.addEventListener('scroll', resetInactivityTimer);
    
    // Start the timer
    resetInactivityTimer();
});