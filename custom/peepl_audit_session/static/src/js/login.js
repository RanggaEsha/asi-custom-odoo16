// Enhanced login session checker and creator

odoo.define('peepl_audit_session.login_session_checker', function (require) {
    "use strict";

    var ajax = require('web.ajax');
    var core = require('web.core');
    var session = require('web.session');
    var WebClient = require('web.WebClient');
    
    var _t = core._t;
    var _logger = console;

    /**
     * Login Session Checker - Ensures audit sessions are created after login
     */
    var LoginSessionChecker = {
        
        // Configuration
        CHECK_INTERVAL: 10000,  // 10 seconds
        MAX_RETRIES: 5,
        RETRY_DELAY: 5000,      // 5 seconds
        
        // State
        isChecking: false,
        checkAttempts: 0,
        checkTimer: null,
        isInitialized: false,
        
        /**
         * Initialize the login session checker
         */
        init: function() {
            if (this.isInitialized) {
                return;
            }
            
            this.isInitialized = true;
            
            // Start checking immediately if user is logged in
            if (session.uid && session.uid !== false) {
                _logger.log('LOGIN_CHECKER - User logged in, starting session check');
                this.startSessionCheck();
            }
            
            // Monitor for login events
            this.setupLoginMonitoring();
            
            _logger.log('LOGIN_CHECKER - Initialized');
        },
        
        /**
         * Setup monitoring for login events
         */
        setupLoginMonitoring: function() {
            var self = this;
            
            // Monitor session changes
            var originalSetCookie = session.set_cookie;
            session.set_cookie = function() {
                var result = originalSetCookie.apply(this, arguments);
                
                // If user just logged in, check session
                if (this.uid && this.uid !== false && !self.isChecking) {
                    _logger.log('LOGIN_CHECKER - Login detected via session change');
                    setTimeout(function() {
                        self.startSessionCheck();
                    }, 2000); // Small delay to let login complete
                }
                
                return result;
            };
            
            // Monitor hash changes that might indicate navigation after login
            $(window).on('hashchange', function() {
                if (session.uid && session.uid !== false && !self.isChecking) {
                    // Check if we're on the main app (not login page)
                    if (window.location.hash && !window.location.hash.includes('login')) {
                        _logger.log('LOGIN_CHECKER - App navigation detected, checking session');
                        self.checkSessionOnce();
                    }
                }
            });
        },
        
        /**
         * Start periodic session checking
         */
        startSessionCheck: function() {
            if (this.isChecking) {
                return;
            }
            
            this.isChecking = true;
            this.checkAttempts = 0;
            
            _logger.log('LOGIN_CHECKER - Starting session check');
            
            // Check immediately
            this.performSessionCheck();
            
            // Set up periodic checking
            var self = this;
            this.checkTimer = setInterval(function() {
                self.performSessionCheck();
            }, this.CHECK_INTERVAL);
        },
        
        /**
         * Stop session checking
         */
        stopSessionCheck: function() {
            if (this.checkTimer) {
                clearInterval(this.checkTimer);
                this.checkTimer = null;
            }
            
            this.isChecking = false;
            _logger.log('LOGIN_CHECKER - Stopped session check');
        },
        
        /**
         * Perform a single session check
         */
        checkSessionOnce: function() {
            if (!session.uid || session.uid === false) {
                return;
            }
            
            var self = this;
            this.performSessionCheck().then(function(result) {
                if (result && result.session_exists) {
                    _logger.log('LOGIN_CHECKER - Single check: Session exists');
                } else {
                    _logger.log('LOGIN_CHECKER - Single check: Session missing, attempting creation');
                }
            });
        },
        
        /**
         * Perform session check and creation if needed
         */
        performSessionCheck: function() {
            var self = this;
            
            if (!session.uid || session.uid === false) {
                this.stopSessionCheck();
                return Promise.resolve({ session_exists: false, reason: 'not_logged_in' });
            }
            
            this.checkAttempts++;
            
            _logger.log('LOGIN_CHECKER - Check attempt', this.checkAttempts);
            
            return ajax.jsonRpc('/audit/session/check', 'call', {})
                .then(function(result) {
                    if (result.exists) {
                        _logger.log('LOGIN_CHECKER - Session exists:', result.session_id);
                        
                        // Check if SID matches
                        if (!result.sid_match) {
                            _logger.warn('LOGIN_CHECKER - SID mismatch detected, repairing session');
                            return self.repairSession();
                        }
                        
                        // Session is good, stop checking
                        self.stopSessionCheck();
                        return { session_exists: true, session_id: result.session_id };
                        
                    } else {
                        _logger.warn('LOGIN_CHECKER - No audit session found, creating one');
                        return self.createSession();
                    }
                })
                .catch(function(error) {
                    _logger.error('LOGIN_CHECKER - Check failed:', error);
                    
                    if (self.checkAttempts >= self.MAX_RETRIES) {
                        _logger.error('LOGIN_CHECKER - Max retries reached, stopping check');
                        self.stopSessionCheck();
                        return { session_exists: false, reason: 'max_retries' };
                    }
                    
                    // Continue checking
                    return { session_exists: false, reason: 'check_error' };
                });
        },
        
        /**
         * Create audit session
         */
        createSession: function() {
            var self = this;
            
            _logger.log('LOGIN_CHECKER - Creating audit session');
            
            return ajax.jsonRpc('/audit/session/create', 'call', {})
                .then(function(result) {
                    if (result.success) {
                        _logger.log('LOGIN_CHECKER - Session created successfully:', result.session_id);
                        self.stopSessionCheck();
                        
                        // Show success notification
                        self.showNotification('success', 'Audit session created successfully');
                        
                        return { session_exists: true, session_id: result.session_id, created: true };
                    } else {
                        _logger.error('LOGIN_CHECKER - Session creation failed:', result.message);
                        
                        // Try repair as fallback
                        return self.repairSession();
                    }
                })
                .catch(function(error) {
                    _logger.error('LOGIN_CHECKER - Session creation error:', error);
                    
                    // Try repair as fallback
                    return self.repairSession();
                });
        },
        
        /**
         * Repair audit session
         */
        repairSession: function() {
            var self = this;
            
            _logger.log('LOGIN_CHECKER - Repairing audit session');
            
            return ajax.jsonRpc('/audit/session/repair', 'call', {})
                .then(function(result) {
                    if (result.success) {
                        _logger.log('LOGIN_CHECKER - Session repaired successfully:', result.session_id);
                        self.stopSessionCheck();
                        
                        // Show notification based on action
                        if (result.action === 'session_created') {
                            self.showNotification('warning', 'Audit session was missing and has been repaired');
                        }
                        
                        return { session_exists: true, session_id: result.session_id, repaired: true };
                    } else {
                        _logger.error('LOGIN_CHECKER - Session repair failed:', result.message);
                        
                        if (self.checkAttempts >= self.MAX_RETRIES) {
                            self.stopSessionCheck();
                            self.showNotification('danger', 'Failed to create audit session after multiple attempts');
                        }
                        
                        return { session_exists: false, reason: 'repair_failed' };
                    }
                })
                .catch(function(error) {
                    _logger.error('LOGIN_CHECKER - Session repair error:', error);
                    
                    if (self.checkAttempts >= self.MAX_RETRIES) {
                        self.stopSessionCheck();
                        self.showNotification('danger', 'Audit session creation failed');
                    }
                    
                    return { session_exists: false, reason: 'repair_error' };
                });
        },
        
        /**
         * Show notification to user
         */
        showNotification: function(type, message) {
            try {
                // Try to use Odoo's notification system
                if (core.bus) {
                    core.bus.trigger('notification', {
                        type: type,
                        title: 'Audit Session',
                        message: message,
                        sticky: false
                    });
                } else {
                    // Fallback to console
                    _logger.log('NOTIFICATION:', type, message);
                }
            } catch (e) {
                _logger.log('NOTIFICATION (fallback):', type, message);
            }
        },
        
        /**
         * Get session status for debugging
         */
        getStatus: function() {
            return {
                isChecking: this.isChecking,
                checkAttempts: this.checkAttempts,
                isInitialized: this.isInitialized,
                userLoggedIn: !!(session.uid && session.uid !== false)
            };
        },
        
        /**
         * Manual trigger for session check
         */
        manualCheck: function() {
            _logger.log('LOGIN_CHECKER - Manual check triggered');
            this.checkSessionOnce();
        },
        
        /**
         * Force session creation
         */
        forceCreate: function() {
            _logger.log('LOGIN_CHECKER - Force creation triggered');
            return this.createSession();
        }
    };
    
    // Auto-initialize when DOM is ready
    $(document).ready(function() {
        LoginSessionChecker.init();
    });
    
    // Also initialize on WebClient start
    WebClient.include({
        start: function() {
            var result = this._super.apply(this, arguments);
            
            // Check session after WebClient starts
            if (session.uid && session.uid !== false) {
                setTimeout(function() {
                    LoginSessionChecker.checkSessionOnce();
                }, 3000); // Give some time for everything to load
            }
            
            return result;
        }
    });
    
    // Expose for debugging
    window.LoginSessionChecker = LoginSessionChecker;
    
    return LoginSessionChecker;
});

// Additional: Hook into authentication flow
odoo.define('peepl_audit_session.auth_session_hook', function (require) {
    "use strict";
    
    var session = require('web.session');
    var LoginSessionChecker = require('peepl_audit_session.login_session_checker');
    
    // Monitor authentication events more directly
    var originalRPC = session.rpc;
    session.rpc = function(url, params, options) {
        var result = originalRPC.apply(this, arguments);
        
        // Check if this is an authentication call
        if (url === '/web/session/authenticate' || url.includes('authenticate')) {
            result.then(function(response) {
                if (response && response.uid) {
                    console.log('AUTH_HOOK - Authentication successful, checking session');
                    setTimeout(function() {
                        LoginSessionChecker.manualCheck();
                    }, 2000);
                }
            }).catch(function(error) {
                console.log('AUTH_HOOK - Authentication failed');
            });
        }
        
        return result;
    };
});

// Debug helper functions
window.debugAuditLogin = function() {
    console.log('=== AUDIT LOGIN DEBUG ===');
    
    if (window.LoginSessionChecker) {
        console.log('Checker Status:', window.LoginSessionChecker.getStatus());
        
        // Check session
        window.LoginSessionChecker.manualCheck();
        
        // Also check via direct API call
        fetch('/audit/session/check', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                jsonrpc: '2.0',
                method: 'call',
                params: {}
            })
        }).then(response => response.json())
          .then(data => {
              console.log('Direct session check result:', data);
          });
    } else {
        console.log('LoginSessionChecker not available');
    }
    
    console.log('Session UID:', session.uid);
    console.log('Current URL:', window.location.href);
};

window.forceCreateAuditSession = function() {
    if (window.LoginSessionChecker) {
        return window.LoginSessionChecker.forceCreate();
    } else {
        console.log('LoginSessionChecker not available');
        return Promise.reject('LoginSessionChecker not available');
    }
};