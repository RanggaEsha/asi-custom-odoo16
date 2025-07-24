odoo.define('peepl_audit_session.simple_tracker', function (require) {
    "use strict";

    var ajax = require('web.ajax');
    var session = require('web.session');
    
    var SimpleSessionTracker = {
        isTracking: false,
        
        init: function() {
            if (this.isTracking || !session.uid) {
                return;
            }
            
            this.isTracking = true;
            this.setupLogoutDetection();
            console.log('Simple session tracker initialized');
        },
        
        setupLogoutDetection: function() {
            var self = this;
            
            // Method 1: Browser close detection
            window.addEventListener('beforeunload', function(event) {
                self.closeSession('browser_close');
            });
            
            // Method 2: Fallback with sendBeacon
            window.addEventListener('unload', function(event) {
                if (navigator.sendBeacon) {
                    navigator.sendBeacon('/audit/session/end', 'browser_close');
                }
            });
            
            // Method 3: Logout button detection
            $(document).on('click', 'a[href*="/web/session/logout"], .o_user_menu a[data-menu="logout"]', function(event) {
                console.log('Logout button clicked');
                self.closeSession('logout_button');
            });
            
            // Method 4: Monitor for navigation to login page
            var currentUrl = window.location.href;
            setInterval(function() {
                if (window.location.href !== currentUrl) {
                    if (window.location.href.includes('/web/login')) {
                        self.closeSession('navigation_logout');
                    }
                    currentUrl = window.location.href;
                }
            }, 2000);
        },
        
        closeSession: function(reason) {
            try {
                ajax.jsonRpc('/audit/session/close', 'call', {
                    reason: reason
                }).then(function(result) {
                    console.log('Session closed:', result);
                }).catch(function(error) {
                    console.warn('Failed to close session:', error);
                });
            } catch (error) {
                console.warn('Error closing session:', error);
            }
        }
    };
    
    // Initialize when DOM is ready
    $(document).ready(function() {
        if (session.uid && session.uid !== false) {
            SimpleSessionTracker.init();
        }
    });
    
    return SimpleSessionTracker;
});