// Enhanced audit_session_tracker.js with heartbeat and better detection

odoo.define('peepl_audit_session.enhanced_session_tracker', function (require) {
    "use strict";

    var ajax = require('web.ajax');
    var core = require('web.core');
    var session = require('web.session');
    
    var _t = core._t;
    var _logger = console;

    /**
     * Enhanced Audit Session Tracker with Heartbeat
     */
    var EnhancedSessionTracker = {
        
        // Configuration
        INACTIVITY_TIMEOUT: 30 * 60 * 1000, // 30 minutes
        HEARTBEAT_INTERVAL: 5 * 60 * 1000,  // 5 minutes
        MAX_RETRY_ATTEMPTS: 3,
        
        // State
        inactivityTimer: null,
        heartbeatTimer: null,
        isTracking: false,
        lastActivityTime: Date.now(),
        heartbeatFailures: 0,
        isWindowClosing: false,
        
        /**
         * Initialize the enhanced session tracker
         */
        init: function() {
            if (this.isTracking) {
                return;
            }
            
            this.isTracking = true;
            this.setupBrowserCloseDetection();
            this.setupInactivityDetection();
            this.setupHeartbeat();
            this.setupVisibilityDetection();
            
            _logger.log('Enhanced audit session tracker initialized');
        },
        
        /**
         * Setup enhanced browser/tab close detection
         */
        setupBrowserCloseDetection: function() {
            var self = this;
            
            // Primary beforeunload handler
            window.addEventListener('beforeunload', function(event) {
                self.isWindowClosing = true;
                self.handleSessionEnd('browser_close_beforeunload');
                
                // For some browsers, return a string to show confirmation dialog
                // Comment out if you don't want confirmation dialog
                // return 'Are you sure you want to leave? Your session will be closed.';
            });
            
            // Fallback unload handler with sendBeacon
            window.addEventListener('unload', function(event) {
                self.isWindowClosing = true;
                
                // Use sendBeacon for better reliability
                if (navigator.sendBeacon && !self.isWindowClosing) {
                    var data = JSON.stringify({
                        action: 'session_end',
                        reason: 'browser_close_unload',
                        timestamp: new Date().toISOString()
                    });
                    
                    var success = navigator.sendBeacon('/audit/session/end', data);
                    _logger.log('SendBeacon result:', success);
                }
            });
            
            // Enhanced: Detect tab close vs browser close
            window.addEventListener('pagehide', function(event) {
                if (event.persisted) {
                    // Page is being cached (back/forward navigation)
                    self.pauseHeartbeat();
                } else {
                    // Page is being unloaded (tab/browser close)
                    self.handleSessionEnd('browser_close_pagehide');
                }
            });
            
            // Detect when page becomes visible again (back from cache)
            window.addEventListener('pageshow', function(event) {
                if (event.persisted) {
                    // Page restored from cache
                    self.resumeHeartbeat();
                    self.resetInactivityTimer();
                }
            });
        },
        
        /**
         * Setup enhanced inactivity detection
         */
        setupInactivityDetection: function() {
            var self = this;
            
            // Events that indicate user activity
            var activityEvents = [
                'click', 'keypress', 'keydown', 'keyup', 
                'scroll', 'mousemove', 'mousedown', 'mouseup',
                'touchstart', 'touchmove', 'touchend',
                'wheel', 'focus', 'blur'
            ];
            
            // Throttled activity handler to avoid excessive calls
            var activityHandler = this.throttle(function() {
                self.onUserActivity();
            }, 1000); // Max once per second
            
            activityEvents.forEach(function(eventType) {
                document.addEventListener(eventType, activityHandler, {
                    passive: true,
                    capture: true
                });
            });
            
            // Start the inactivity timer
            this.resetInactivityTimer();
        },
        
        /**
         * Setup session heartbeat to server
         */
        setupHeartbeat: function() {
            var self = this;
            
            this.heartbeatTimer = setInterval(function() {
                if (!self.isWindowClosing) {
                    self.sendHeartbeat();
                }
            }, this.HEARTBEAT_INTERVAL);
            
            // Send initial heartbeat
            this.sendHeartbeat();
        },
        
        /**
         * Setup page visibility detection
         */
        setupVisibilityDetection: function() {
            var self = this;
            
            document.addEventListener('visibilitychange', function() {
                if (document.hidden) {
                    // User switched away from tab
                    self.pauseInactivityTimer();
                    self.pauseHeartbeat();
                } else {
                    // User returned to tab
                    self.resetInactivityTimer();
                    self.resumeHeartbeat();
                }
            });
        },
        
        /**
         * Handle user activity
         */
        onUserActivity: function() {
            this.lastActivityTime = Date.now();
            this.resetInactivityTimer();
        },
        
        /**
         * Send heartbeat to server
         */
        sendHeartbeat: function() {
            var self = this;
            
            ajax.jsonRpc('/audit/session/heartbeat', 'call', {
                timestamp: new Date().toISOString(),
                last_activity: this.lastActivityTime
            }).then(function(result) {
                if (result && result.success) {
                    self.heartbeatFailures = 0;
                    _logger.debug('Session heartbeat sent successfully');
                } else {
                    self.heartbeatFailures++;
                    _logger.warn('Session heartbeat failed:', result);
                    
                    if (self.heartbeatFailures >= self.MAX_RETRY_ATTEMPTS) {
                        _logger.error('Max heartbeat failures reached, session may be invalid');
                        self.handleSessionEnd('heartbeat_failure');
                    }
                }
            }).catch(function(error) {
                self.heartbeatFailures++;
                _logger.warn('Session heartbeat error:', error);
                
                if (self.heartbeatFailures >= self.MAX_RETRY_ATTEMPTS) {
                    _logger.error('Max heartbeat failures reached');
                    self.handleSessionEnd('heartbeat_failure');
                }
            });
        },
        
        /**
         * Reset the inactivity timer
         */
        resetInactivityTimer: function() {
            var self = this;
            
            if (this.inactivityTimer) {
                clearTimeout(this.inactivityTimer);
            }
            
            this.inactivityTimer = setTimeout(function() {
                self.handleInactivity();
            }, this.INACTIVITY_TIMEOUT);
        },
        
        /**
         * Pause the inactivity timer
         */
        pauseInactivityTimer: function() {
            if (this.inactivityTimer) {
                clearTimeout(this.inactivityTimer);
                this.inactivityTimer = null;
            }
        },
        
        /**
         * Pause heartbeat
         */
        pauseHeartbeat: function() {
            if (this.heartbeatTimer) {
                clearInterval(this.heartbeatTimer);
                this.heartbeatTimer = null;
            }
        },
        
        /**
         * Resume heartbeat
         */
        resumeHeartbeat: function() {
            if (!this.heartbeatTimer && !this.isWindowClosing) {
                this.setupHeartbeat();
            }
        },
        
        /**
         * Handle user inactivity
         */
        handleInactivity: function() {
            _logger.warn('User inactivity detected, closing audit session');
            this.handleSessionEnd('inactivity');
        },
        
        /**
         * Handle session end with retry logic
         */
        handleSessionEnd: function(reason) {
            var self = this;
            var attempts = 0;
            var maxAttempts = 3;
            
            function attemptClose() {
                attempts++;
                
                ajax.jsonRpc('/audit/session/close', 'call', {
                    reason: reason,
                    timestamp: new Date().toISOString(),
                    last_activity: self.lastActivityTime
                }).then(function(result) {
                    _logger.log('Audit session closed:', result);
                    self.cleanup();
                }).catch(function(error) {
                    _logger.warn('Failed to close audit session (attempt ' + attempts + '):', error);
                    
                    if (attempts < maxAttempts) {
                        // Retry with exponential backoff
                        setTimeout(attemptClose, attempts * 1000);
                    } else {
                        _logger.error('Max attempts reached, session close failed');
                        self.cleanup();
                    }
                });
            }
            
            attemptClose();
        },
        
        /**
         * Cleanup timers and event listeners
         */
        cleanup: function() {
            this.pauseInactivityTimer();
            this.pauseHeartbeat();
            this.isTracking = false;
        },
        
        /**
         * Throttle function to limit function calls
         */
        throttle: function(func, limit) {
            var inThrottle;
            return function() {
                var args = arguments;
                var context = this;
                if (!inThrottle) {
                    func.apply(context, args);
                    inThrottle = true;
                    setTimeout(function() {
                        inThrottle = false;
                    }, limit);
                }
            };
        },
        
        /**
         * Get current session info
         */
        getSessionInfo: function() {
            return ajax.jsonRpc('/audit/session/info', 'call', {});
        },
        
        /**
         * Manual session close
         */
        closeSession: function() {
            return this.handleSessionEnd('manual_logout');
        }
    };
    
    // Auto-initialize when DOM is ready
    $(document).ready(function() {
        if (session.uid && session.uid !== false) {
            EnhancedSessionTracker.init();
        }
    });
    
    return EnhancedSessionTracker;
});