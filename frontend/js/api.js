/**
 * Enterprise CRM API Client with JWT Authorization & Toast Manager
 */
const api = {
    baseUrl: '/api',
    tokenKey: 'crm_access_token',
    userKey: 'crm_user_info',

    getToken() {
        return localStorage.getItem(this.tokenKey);
    },

    setSession(token, user) {
        localStorage.setItem(this.tokenKey, token);
        localStorage.setItem(this.userKey, JSON.stringify(user));
    },

    getCurrentUser() {
        const u = localStorage.getItem(this.userKey);
        return u ? JSON.parse(u) : null;
    },

    getUser() {
        return this.getCurrentUser();
    },

    clearSession() {
        localStorage.removeItem(this.tokenKey);
        localStorage.removeItem(this.userKey);
        localStorage.removeItem('access_token');
        localStorage.removeItem('user');
    },

    logout() {
        if (window.app && typeof app.logout === 'function') {
            app.logout();
        } else {
            this.clearSession();
            localStorage.clear();
            sessionStorage.clear();
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
