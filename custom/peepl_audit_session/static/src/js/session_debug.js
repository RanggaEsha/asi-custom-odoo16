// Session debug helper
odoo.define('peepl_audit_session.debug', function (require) {
    "use strict";

    var ajax = require('web.ajax');
    
    // Add debug functions to window for console access
    window.debugAuditSession = function() {
        return ajax.jsonRpc('/audit/debug/session', 'call', {})
            .then(function(result) {
                console.log('=== AUDIT SESSION DEBUG ===');
                console.log('Session SID:', result.session_sid);
                console.log('User ID:', result.user_id);
                console.log('Current Session:', result.current_session);
                console.log('User Sessions Count:', result.user_sessions_count);
                console.log('Recent Sessions:', result.user_sessions);
                return result;
            });
    };
    
    window.forceCreateAuditSession = function() {
        return ajax.jsonRpc('/audit/debug/create_session', 'call', {})
            .then(function(result) {
                console.log('=== FORCE CREATE SESSION ===');
                console.log('Result:', result);
                return result;
            });
    };
    
    // Auto-debug on login (optional)
    $(document).ready(function() {
        // Uncomment this to auto-debug on page load
        // setTimeout(window.debugAuditSession, 2000);
    });
});