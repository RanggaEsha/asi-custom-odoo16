// File: static/src/js/audit_session_tracker.js
// This handles browser close, tab close, and user inactivity

odoo.define('peepl_audit_session.session_tracker', function (require) {
    "use strict";

    var ajax = require('web.ajax');
    var core = require('web.core');
    var session = require('web.session');
    
    var _t = core._t;
    var _logger = console;

    /**
     * Audit Session Tracker
     * Handles browser close, tab close, and inactivity detection
     */
    var AuditSessionTracker = {
        
        // Configuration
        INACTIVITY_TIMEOUT: 30 * 60 * 1000, // 30 minutes in milliseconds
        inactivityTimer: null,
        isTracking: false,
        
        /**
         * Initialize the session tracker
         */
        init: function() {
            if (this.isTracking) {
                return; // Already initialized
            }
            
            this.isTracking = true;
            this.setupBrowserCloseDetection();
            this.setupInactivityDetection();
            
            _logger.log('Audit session tracker initialized');
        },
        
        /**
         * Setup browser/tab close detection
         */
        setupBrowserCloseDetection: function() {
            var self = this;
            
            // Handle browser/tab close
            window.addEventListener('beforeunload', function(event) {
                self.handleSessionEnd('browser_close');
            });
            
            // Fallback for some browsers
            window.addEventListener('unload', function(event) {
                // Use sendBeacon for better reliability
                if (navigator.sendBeacon) {
                    var data = JSON.stringify({
                        action: 'session_end',
                        reason: 'browser_close'
                    });
                    navigator.sendBeacon('/audit/session/end', data);
                }
            });
            
            // Handle page visibility changes (tab switching, minimizing)
            document.addEventListener('visibilitychange', function() {
                if (document.hidden) {
                    // User switched away from tab
                    self.pauseInactivityTimer();
                } else {
                    // User returned to tab
                    self.resetInactivityTimer();
                }
            });
        },
        
        /**
         * Setup user inactivity detection
         */
        setupInactivityDetection: function() {
            var self = this;
            
            // Events that indicate user activity
            var activityEvents = ['click', 'keypress', 'scroll', 'mousemove', 'touchstart'];
            
            activityEvents.forEach(function(eventType) {
                document.addEventListener(eventType, function() {
                    self.resetInactivityTimer();
                }, true); // Use capture phase for better coverage
            });
            
            // Start the inactivity timer
            this.resetInactivityTimer();
        },
        
        /**
         * Reset the inactivity timer
         */
        resetInactivityTimer: function() {
            var self = this;
            
            // Clear existing timer
            if (this.inactivityTimer) {
                clearTimeout(this.inactivityTimer);
            }
            
            // Set new timer
            this.inactivityTimer = setTimeout(function() {
                self.handleInactivity();
            }, this.INACTIVITY_TIMEOUT);
        },
        
        /**
         * Pause the inactivity timer (when tab is hidden)
         */
        pauseInactivityTimer: function() {
            if (this.inactivityTimer) {
                clearTimeout(this.inactivityTimer);
                this.inactivityTimer = null;
            }
        },
        
        /**
         * Handle user inactivity
         */
        handleInactivity: function() {
            _logger.log('User inactivity detected, closing audit session');
            this.handleSessionEnd('inactivity');
        },
        
        /**
         * Handle session end (browser close, inactivity, etc.)
         */
        handleSessionEnd: function(reason) {
            ajax.jsonRpc('/audit/session/close', 'call', {
                reason: reason,
                timestamp: new Date().toISOString()
            }).then(function(result) {
                _logger.log('Audit session closed:', result);
            }).catch(function(error) {
                _logger.warn('Failed to close audit session:', error);
            });
        },
        
        /**
         * Get current session info
         */
        getSessionInfo: function() {
            return ajax.jsonRpc('/audit/session/info', 'call', {});
        },
        
        /**
         * Manual session close (for explicit logout)
         */
        closeSession: function() {
            return this.handleSessionEnd('manual_logout');
        }
    };
    
    // Auto-initialize when DOM is ready
    $(document).ready(function() {
        // Only initialize if user is logged in
        if (session.uid && session.uid !== false) {
            AuditSessionTracker.init();
        }
    });
    
    // Export for manual use
    return AuditSessionTracker;
});