// Enhanced logout detection for all logout scenarios

odoo.define('peepl_audit_session.enhanced_logout_detection', function (require) {
    "use strict";

    var ajax = require('web.ajax');
    var core = require('web.core');
    var session = require('web.session');
    
    var _t = core._t;
    var _logger = console;

    /**
     * Enhanced Logout Detection with Multiple Strategies
     */
    var EnhancedLogoutDetection = {
        
        // Configuration
        MAX_RETRY_ATTEMPTS: 3,
        RETRY_DELAY: 1000,
        isLogoutInProgress: false,
        isWindowClosing: false,
        logoutEndpoints: [
            '/audit/logout/detect',           // Primary audit endpoint
            '/web/session/logout',            // Secondary web session endpoint
            '/audit/session/close/force'     // Emergency force close endpoint
        ],
        
        /**
         * Initialize enhanced logout detection
         */
        init: function() {
            if (this.isInitialized) {
                return;
            }
            
            this.isInitialized = true;
            this.setupMultipleLogoutDetection();
            this.setupNavigationDetection();
            this.setupVisibilityDetection();
            this.setupFormSubmissionDetection();
            
            _logger.log('Enhanced logout detection initialized with multiple strategies');
        },
        
        /**
         * Setup multiple logout detection strategies
         */
        setupMultipleLogoutDetection: function() {
            var self = this;
            
            // Strategy 1: beforeunload (most reliable for browser close)
            window.addEventListener('beforeunload', function(event) {
                _logger.log('LOGOUT_DETECT - beforeunload triggered');
                self.isWindowClosing = true;
                self.handleLogout('beforeunload', true); // synchronous for beforeunload
            });
            
            // Strategy 2: unload with sendBeacon (fallback)
            window.addEventListener('unload', function(event) {
                _logger.log('LOGOUT_DETECT - unload triggered');
                self.isWindowClosing = true;
                self.handleLogoutWithBeacon('unload');
            });
            
            // Strategy 3: pagehide (covers back/forward navigation)
            window.addEventListener('pagehide', function(event) {
                if (!event.persisted) {
                    _logger.log('LOGOUT_DETECT - pagehide (not cached) triggered');
                    self.isWindowClosing = true;
                    self.handleLogout('pagehide', true);
                }
            });
            
            // Strategy 4: Detect actual logout button clicks
            self.setupLogoutButtonDetection();
        },
        
        /**
         * Setup logout button detection
         */
        setupLogoutButtonDetection: function() {
            var self = this;
            
            // Use event delegation to catch logout clicks
            $(document).on('click', 'a[href*="/web/session/logout"], a[data-menu="logout"], .o_user_menu a[href*="logout"]', function(event) {
                _logger.log('LOGOUT_DETECT - Logout button clicked');
                self.handleLogout('logout_button', false);
            });
            
            // Also catch form submissions to logout endpoints
            $(document).on('submit', 'form[action*="/web/session/logout"], form[action*="logout"]', function(event) {
                _logger.log('LOGOUT_DETECT - Logout form submitted');
                self.handleLogout('logout_form', false);
            });
        },
        
        /**
         * Setup navigation detection (URL changes)
         */
        setupNavigationDetection: function() {
            var self = this;
            var currentUrl = window.location.href;
            
            // Monitor for navigation to login page (indicates logout)
            setInterval(function() {
                if (window.location.href !== currentUrl) {
                    if (window.location.href.includes('/web/login') || 
                        window.location.href.includes('/web/session/logout')) {
                        _logger.log('LOGOUT_DETECT - Navigation to login/logout detected');
                        self.handleLogout('navigation', false);
                    }
                    currentUrl = window.location.href;
                }
            }, 1000);
        },
        
        /**
         * Setup visibility detection for session management
         */
        setupVisibilityDetection: function() {
            var self = this;
            
            document.addEventListener('visibilitychange', function() {
                if (document.hidden) {
                    // User switched away - start monitoring for potential logout
                    self.startLogoutMonitoring();
                } else {
                    // User returned - stop monitoring
                    self.stopLogoutMonitoring();
                }
            });
        },
        
        /**
         * Setup form submission detection
         */
        setupFormSubmissionDetection: function() {
            var self = this;
            
            // Monitor for any form submissions that might be logout
            $(document).on('submit', 'form', function(event) {
                var form = $(this);
                var action = form.attr('action') || '';
                
                if (action.includes('logout') || action.includes('/web/session/')) {
                    _logger.log('LOGOUT_DETECT - Potential logout form detected:', action);
                    self.handleLogout('form_submission', false);
                }
            });
        },
        
        /**
         * Start monitoring for logout (when tab is hidden)
         */
        startLogoutMonitoring: function() {
            var self = this;
            
            // Check periodically if session is still valid
            this.monitoringInterval = setInterval(function() {
                if (document.hidden && !self.isLogoutInProgress) {
                    self.checkSessionValidity();
                }
            }, 30000); // Check every 30 seconds when tab is hidden
        },
        
        /**
         * Stop logout monitoring
         */
        stopLogoutMonitoring: function() {
            if (this.monitoringInterval) {
                clearInterval(this.monitoringInterval);
                this.monitoringInterval = null;
            }
        },
        
        /**
         * Check if session is still valid
         */
        checkSessionValidity: function() {
            var self = this;
            
            ajax.jsonRpc('/web/session/get_session_info', 'call', {})
                .then(function(result) {
                    if (!result || !result.uid) {
                        _logger.log('LOGOUT_DETECT - Session invalid, user logged out elsewhere');
                        self.handleLogout('session_invalid', false);
                    }
                })
                .catch(function(error) {
                    _logger.log('LOGOUT_DETECT - Session check failed, assuming logout');
                    self.handleLogout('session_check_failed', false);
                });
        },
        
        /**
         * Handle logout with multiple endpoint attempts
         */
        handleLogout: function(reason, synchronous) {
            if (this.isLogoutInProgress) {
                return;
            }
            
            this.isLogoutInProgress = true;
            _logger.log('LOGOUT_DETECT - Handling logout:', reason);
            
            if (synchronous) {
                // For beforeunload/pagehide, try synchronous request first
                this.attemptSynchronousLogout(reason);
            } else {
                // For other cases, use async with retries
                this.attemptAsyncLogout(reason);
            }
        },
        
        /**
         * Attempt synchronous logout (for beforeunload)
         */
        attemptSynchronousLogout: function(reason) {
            var self = this;
            
            // Try primary endpoint synchronously
            try {
                var xhr = new XMLHttpRequest();
                xhr.open('POST', '/audit/logout/detect', false); // synchronous
                xhr.setRequestHeader('Content-Type', 'application/json');
                xhr.send(JSON.stringify({
                    jsonrpc: '2.0',
                    method: 'call',
                    params: {
                        reason: reason,
                        timestamp: new Date().toISOString()
                    }
                }));
                
                _logger.log('LOGOUT_DETECT - Synchronous logout attempt completed');
            } catch (error) {
                _logger.warn('LOGOUT_DETECT - Synchronous logout failed:', error);
                
                // Fallback to sendBeacon
                this.handleLogoutWithBeacon(reason);
            }
        },
        
        /**
         * Attempt async logout with retries
         */
        attemptAsyncLogout: function(reason) {
            var self = this;
            var attempts = 0;
            
            function tryLogout() {
                attempts++;
                var endpoint = self.logoutEndpoints[(attempts - 1) % self.logoutEndpoints.length];
                
                _logger.log('LOGOUT_DETECT - Async attempt', attempts, 'using endpoint:', endpoint);
                
                ajax.jsonRpc(endpoint, 'call', {
                    reason: reason,
                    timestamp: new Date().toISOString()
                }).then(function(result) {
                    _logger.log('LOGOUT_DETECT - Async logout successful:', result);
                    self.isLogoutInProgress = false;
                }).catch(function(error) {
                    _logger.warn('LOGOUT_DETECT - Async attempt', attempts, 'failed:', error);
                    
                    if (attempts < self.MAX_RETRY_ATTEMPTS) {
                        setTimeout(tryLogout, self.RETRY_DELAY * attempts);
                    } else {
                        _logger.error('LOGOUT_DETECT - All async attempts failed');
                        self.handleLogoutWithBeacon(reason);
                        self.isLogoutInProgress = false;
                    }
                });
            }
            
            tryLogout();
        },
        
        /**
         * Handle logout with sendBeacon (most reliable for browser close)
         */
        handleLogoutWithBeacon: function(reason) {
            if (navigator.sendBeacon) {
                var data = JSON.stringify({
                    action: 'session_end',
                    reason: reason,
                    timestamp: new Date().toISOString()
                });
                
                var success = navigator.sendBeacon('/audit/session/end', data);
                _logger.log('LOGOUT_DETECT - sendBeacon result for', reason, ':', success);
                
                // Also try the force close endpoint
                navigator.sendBeacon('/audit/session/close/force', JSON.stringify({
                    reason: reason + '_beacon'
                }));
            } else {
                _logger.warn('LOGOUT_DETECT - sendBeacon not supported');
            }
        },
        
        /**
         * Manual logout trigger (for logout buttons)
         */
        triggerLogout: function(reason) {
            _logger.log('LOGOUT_DETECT - Manual logout triggered:', reason);
            this.handleLogout(reason || 'manual', false);
        },
        
        /**
         * Force close all sessions for current user
         */
        forceCloseAllSessions: function() {
            return ajax.jsonRpc('/audit/session/close/force', 'call', {
                reason: 'force_close_all'
            });
        }
    };
    
    // Auto-initialize when DOM is ready
    $(document).ready(function() {
        if (session.uid && session.uid !== false) {
            EnhancedLogoutDetection.init();
        }
    });
    
    // Also initialize on hash changes (for SPA navigation)
    $(window).on('hashchange', function() {
        if (session.uid && session.uid !== false && !EnhancedLogoutDetection.isInitialized) {
            EnhancedLogoutDetection.init();
        }
    });
    
    // Expose for manual use
    window.AuditLogoutDetection = EnhancedLogoutDetection;
    
    return EnhancedLogoutDetection;
});

// Additional: Hook into Odoo's core logout mechanisms
odoo.define('peepl_audit_session.core_logout_hook', function (require) {
    "use strict";
    
    var UserMenu = require('web.UserMenu');
    var session = require('web.session');
    
    // Override UserMenu logout method
    UserMenu.include({
        _onMenuLogout: function () {
            console.log('LOGOUT_HOOK - Core logout method called');
            
            // Trigger our logout detection
            if (window.AuditLogoutDetection) {
                window.AuditLogoutDetection.triggerLogout('core_logout_menu');
            }
            
            // Call original method
            return this._super.apply(this, arguments);
        }
    });
    
    // Monitor session changes
    var originalSessionSetCookie = session.set_cookie;
    session.set_cookie = function() {
        var result = originalSessionSetCookie.apply(this, arguments);
        
        // If session is being cleared, trigger logout
        if (!this.uid && window.AuditLogoutDetection) {
            console.log('LOGOUT_HOOK - Session cleared, triggering logout');
            window.AuditLogoutDetection.triggerLogout('session_cleared');
        }
        
        return result;
    };
});