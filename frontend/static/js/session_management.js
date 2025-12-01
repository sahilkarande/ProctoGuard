/**
 * Session Management & Back Button Handler
 * Prevents cached page display after logout
 * Production-ready navigation behavior
 */

(function() {
    'use strict';

    // ============= SESSION MANAGEMENT =============

    /**
     * Prevent back button after logout
     */
    function preventBackButtonAfterLogout() {
        // Check if user just logged out
        if (window.performance && window.performance.navigation.type === 2) {
            // User came back using back button
            if (document.body.classList.contains('logged-out')) {
                // Redirect to login if trying to access protected page after logout
                window.location.replace('/login');
            }
        }
    }

    /**
     * Clear history on logout
     */
    function clearHistoryOnLogout() {
        const logoutButtons = document.querySelectorAll('a[href*="logout"]');
        
        logoutButtons.forEach(button => {
            button.addEventListener('click', function(e) {
                e.preventDefault();
                
                // Mark as logged out
                sessionStorage.setItem('logged_out', 'true');
                
                // Redirect to logout
                window.location.replace(this.href);
            });
        });
    }

    /**
     * Check if session is valid
     */
    function checkSessionValidity() {
        // If logged_out flag is set, redirect to login
        if (sessionStorage.getItem('logged_out') === 'true') {
            const protectedPages = [
                '/student/dashboard',
                '/faculty/dashboard',
                '/exam/',
                '/profile',
                '/admin'
            ];
            
            const currentPath = window.location.pathname;
            const isProtectedPage = protectedPages.some(page => currentPath.includes(page));
            
            if (isProtectedPage) {
                sessionStorage.removeItem('logged_out');
                window.location.replace('/login');
            }
        }
    }

    /**
     * Handle successful login
     */
    function handleSuccessfulLogin() {
        const loginForm = document.querySelector('form[action*="login"]');
        
        if (loginForm) {
            loginForm.addEventListener('submit', function() {
                // Clear logout flag on successful login
                sessionStorage.removeItem('logged_out');
            });
        }
    }

    /**
     * Disable browser cache for authenticated pages
     */
    function disableBrowserCache() {
        // Add meta tags to prevent caching
        if (!document.querySelector('meta[http-equiv="Cache-Control"]')) {
            const metaTags = [
                { httpEquiv: 'Cache-Control', content: 'no-cache, no-store, must-revalidate' },
                { httpEquiv: 'Pragma', content: 'no-cache' },
                { httpEquiv: 'Expires', content: '0' }
            ];
            
            metaTags.forEach(tag => {
                const meta = document.createElement('meta');
                meta.httpEquiv = tag.httpEquiv;
                meta.content = tag.content;
                document.head.appendChild(meta);
            });
        }
    }

    // ============= HISTORY MANAGEMENT =============

    /**
     * Prevent back navigation to sensitive pages
     */
    function preventSensitivePageBackNav() {
        const sensitivePages = [
            '/exam/',
            '/student/exam/',
            '/faculty/exam/',
            '/verify-otp',
            '/logout'
        ];
        
        const currentPath = window.location.pathname;
        const isSensitivePage = sensitivePages.some(page => currentPath.includes(page));
        
        if (isSensitivePage) {
            // Replace current history entry
            history.pushState(null, document.title, location.href);
            
            window.addEventListener('popstate', function(event) {
                history.pushState(null, document.title, location.href);
            });
        }
    }

    /**
     * Smart back button handling
     */
    function handleSmartBackButton() {
        // Add custom back buttons if needed
        const customBackButtons = document.querySelectorAll('[data-smart-back]');
        
        customBackButtons.forEach(button => {
            button.addEventListener('click', function(e) {
                e.preventDefault();
                
                const destination = this.dataset.smartBack;
                
                if (destination) {
                    window.location.href = destination;
                } else {
                    // Smart navigation based on user role
                    const userRole = document.body.dataset.userRole;
                    
                    if (userRole === 'student') {
                        window.location.href = '/student/dashboard';
                    } else if (userRole === 'faculty') {
                        window.location.href = '/faculty/dashboard';
                    } else {
                        window.location.href = '/';
                    }
                }
            });
        });
    }

    // ============= SESSION TIMEOUT =============

    /**
     * Handle session timeout gracefully
     */
    function handleSessionTimeout() {
        let sessionTimeout;
        const SESSION_DURATION = 3600000; // 1 hour in milliseconds
        const WARNING_TIME = 300000; // 5 minutes warning

        function resetSessionTimer() {
            clearTimeout(sessionTimeout);
            
            sessionTimeout = setTimeout(function() {
                showSessionWarning();
            }, SESSION_DURATION - WARNING_TIME);
        }

        function showSessionWarning() {
            const warning = confirm(
                'Your session will expire in 5 minutes due to inactivity. ' +
                'Click OK to stay logged in, or Cancel to logout now.'
            );
            
            if (warning) {
                // Refresh session by making a lightweight request
                fetch('/api/refresh-session', { method: 'POST' })
                    .then(() => resetSessionTimer())
                    .catch(() => {
                        alert('Session refresh failed. Please log in again.');
                        window.location.href = '/logout';
                    });
            } else {
                window.location.href = '/logout';
            }
        }

        // Reset timer on user activity
        const activityEvents = ['mousedown', 'keypress', 'scroll', 'touchstart'];
        
        activityEvents.forEach(event => {
            document.addEventListener(event, resetSessionTimer, { passive: true });
        });

        // Initial timer
        resetSessionTimer();
    }

    // ============= PAGE REFRESH WARNING =============

    /**
     * Warn user before leaving exam page
     */
    function warnBeforeExamLeave() {
        if (window.location.pathname.includes('/exam/') && 
            window.location.pathname.includes('/take')) {
            
            window.addEventListener('beforeunload', function(e) {
                const message = 'Are you sure you want to leave? Your exam progress may be lost.';
                e.returnValue = message;
                return message;
            });
        }
    }

    // ============= INITIALIZATION =============

    /**
     * Initialize all session management features
     */
    function init() {
        // Core session management
        preventBackButtonAfterLogout();
        clearHistoryOnLogout();
        checkSessionValidity();
        handleSuccessfulLogin();
        disableBrowserCache();
        
        // History management
        preventSensitivePageBackNav();
        handleSmartBackButton();
        
        // Session timeout (only for authenticated users)
        if (document.body.classList.contains('authenticated')) {
            handleSessionTimeout();
        }
        
        // Exam-specific warnings
        warnBeforeExamLeave();
        
        console.log('✅ Session management initialized');
    }

    // Run on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();

// ============= UTILITY FUNCTIONS =============

/**
 * Check if user is authenticated (can be called from other scripts)
 */
function isUserAuthenticated() {
    return document.body.classList.contains('authenticated') || 
           sessionStorage.getItem('logged_out') !== 'true';
}

/**
 * Redirect to dashboard based on role
 */
function redirectToDashboard() {
    const userRole = document.body.dataset.userRole;
    
    if (userRole === 'student') {
        window.location.href = '/student/dashboard';
    } else if (userRole === 'faculty') {
        window.location.href = '/faculty/dashboard';
    } else {
        window.location.href = '/';
    }
}

/**
 * Safe logout with proper cleanup
 */
function safeLogout() {
    sessionStorage.setItem('logged_out', 'true');
    sessionStorage.clear();
    localStorage.clear();
    window.location.replace('/logout');
}

console.log('✅ Session management utilities loaded');