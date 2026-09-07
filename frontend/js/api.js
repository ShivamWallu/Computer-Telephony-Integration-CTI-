/**
 * Enterprise CRM API Client with JWT Authorization, Cookie Session Manager & Toast Manager
 * 
 * Session Priority:  Cookie (crm_session) → localStorage → unauthenticated
 * Cookie Lifetime:   30 days when "Remember Me" is checked; session-only otherwise
 */
const api = {
    baseUrl: '/api',
    tokenKey: 'crm_access_token',
    userKey: 'crm_user_info',
    SESSION_COOKIE: 'crm_session',
    USER_COOKIE: 'crm_user',

    // ── Cookie Helpers ────────────────────────────────────────────────────────

    _getCookie(name) {
        try {
            const match = document.cookie.match(
                new RegExp('(?:^|; )' + name.replace(/([.$?*|{}()[\]\\/+^])/g, '\\$1') + '=([^;]*)')
            );
            return match ? decodeURIComponent(match[1]) : null;
        } catch (e) { return null; }
    },

    _setCookie(name, value, days) {
        try {
            let cookie = `${name}=${encodeURIComponent(value)};path=/;SameSite=Lax`;
            if (days) {
                const d = new Date();
                d.setTime(d.getTime() + days * 864e5);
                cookie += `;expires=${d.toUTCString()}`;
            }
            document.cookie = cookie;
        } catch (e) { console.warn('Cookie write failed:', e); }
    },

    _deleteCookie(name) {
        document.cookie = `${name}=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/;SameSite=Lax`;
    },

    // ── Token / Session API ───────────────────────────────────────────────────

    getToken() {
        // Priority: persistent cookie → localStorage (fallback)
        return this._getCookie(this.SESSION_COOKIE) || localStorage.getItem(this.tokenKey) || null;
    },

    setSession(token, user, rememberMe = true) {
        const days = rememberMe ? 30 : null; // null = session-only cookie
        this._setCookie(this.SESSION_COOKIE, token, days);
        try {
            this._setCookie(this.USER_COOKIE, JSON.stringify(user), days);
            localStorage.setItem(this.tokenKey, token);
            localStorage.setItem(this.userKey, JSON.stringify(user));
        } catch (e) { console.warn('Storage write failed:', e); }
    },

    getCurrentUser() {
        try {
            const cookieUser = this._getCookie(this.USER_COOKIE);
            if (cookieUser) return JSON.parse(cookieUser);
            const lsUser = localStorage.getItem(this.userKey);
            return lsUser ? JSON.parse(lsUser) : null;
        } catch (e) { return null; }
    },

    setCurrentUser(user) {
        try {
            if (!user) return;
            const userStr = JSON.stringify(user);
            this._setCookie(this.USER_COOKIE, userStr, 30);
            localStorage.setItem(this.userKey, userStr);
            localStorage.setItem('user', userStr);
        } catch (e) { console.warn('Failed to update user in storage:', e); }
    },

    getUser() { return this.getCurrentUser(); },

    clearSession() {
        this._deleteCookie(this.SESSION_COOKIE);
        this._deleteCookie(this.USER_COOKIE);
        try {
            localStorage.removeItem(this.tokenKey);
            localStorage.removeItem(this.userKey);
            localStorage.removeItem('access_token');
            localStorage.removeItem('user');
        } catch (e) {}
    },

    logout() {
        if (window.app && typeof app.logout === 'function') {
            app.logout();
        } else {
            this.clearSession();
            try { localStorage.clear(); sessionStorage.clear(); } catch (e) {}
            window.location.reload();
        }
    },

    async request(endpoint, options = {}) {
        const url = `${this.baseUrl}${endpoint}`;
        const headers = options.headers || {};

        const isAuthRoute = endpoint.startsWith('/auth/') || endpoint === '/calls/active' || endpoint === '/health';
        const token = this.getToken();

        // If not an auth route and no token exists, do not send unauthenticated request
        if (!token && !isAuthRoute) {
            if (window.app && typeof app.showLoginView === 'function') {
                app.showLoginView();
            }
            throw new Error("Authentication required. Please sign in.");
        }

        if (token && !headers['Authorization']) {
            headers['Authorization'] = `Bearer ${token}`;
        }

        if (!(options.body instanceof FormData) && !headers['Content-Type']) {
            headers['Content-Type'] = 'application/json';
        }

        options.headers = headers;

        try {
            const res = await fetch(url, options);
            if (res.status === 401 && !isAuthRoute) {
                console.warn(`Unauthorized access on ${endpoint}. Redirecting to login.`);
                this.clearSession();
                if (window.app && typeof app.showLoginView === 'function') {
                    app.showLoginView();
                }
            }

            const contentType = res.headers.get("content-type");
            let data;
            if (contentType && contentType.includes("application/json")) {
                data = await res.json();
            } else if (contentType && contentType.includes("text/csv")) {
                data = await res.text();
            } else {
                data = await res.text();
            }

            if (!res.ok) {
                const errorMsg = data?.detail || data?.message || res.statusText || "Request failed";
                throw new Error(errorMsg);
            }
            return data;
        } catch (err) {
            console.error(`API Error on ${endpoint}:`, err);
            throw err;
        }
    },

    get(endpoint) {
        return this.request(endpoint, { method: 'GET' });
    },

    post(endpoint, body) {
        const isFormData = body instanceof FormData;
        return this.request(endpoint, {
            method: 'POST',
            body: isFormData ? body : JSON.stringify(body)
        });
    },

    put(endpoint, body) {
        return this.request(endpoint, {
            method: 'PUT',
            body: JSON.stringify(body)
        });
    },

    delete(endpoint, body) {
        const options = { method: 'DELETE' };
        if (body) {
            options.body = typeof body === 'string' ? body : JSON.stringify(body);
        }
        return this.request(endpoint, options);
    },

    // Simple & Professional Toast Notification System
    toast(message, type = 'info', duration = 3000) {
        const container = document.getElementById('toast-container');
        if (!container) return;

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        
        let iconSvg = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>`;
        
        if (type === 'success') {
            iconSvg = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2.5"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>`;
        } else if (type === 'error' || type === 'danger' || type === 'delete') {
            iconSvg = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#EF4444" stroke-width="2.5"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>`;
        } else if (type === 'warning') {
            iconSvg = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#F59E0B" stroke-width="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>`;
        }

        toast.innerHTML = `<span style="display: inline-flex; align-items: center; flex-shrink: 0;">${iconSvg}</span><span style="flex: 1; word-break: break-word;">${message}</span>`;
        container.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(-16px)';
            toast.style.transition = 'opacity 0.2s ease, transform 0.2s ease';
            setTimeout(() => toast.remove(), 200);
        }, duration);
    }
};

window.api = api;
window.logout = () => api.logout();
