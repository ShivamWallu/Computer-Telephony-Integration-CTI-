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

    delete(endpoint) {
        return this.request(endpoint, { method: 'DELETE' });
    },

    // Toast Manager
    toast(message, type = 'info', duration = 3500) {
        const container = document.getElementById('toast-container');
        if (!container) return;

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        
        let icon = 'ℹ️';
        if (type === 'success') icon = '✅';
        if (type === 'error') icon = '⚠️';

        toast.innerHTML = `<span>${icon}</span><span>${message}</span>`;
        container.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateY(10px)';
            toast.style.transition = 'all 0.25s ease';
            setTimeout(() => toast.remove(), 250);
        }, duration);
    }
};

window.api = api;
window.logout = () => api.logout();
