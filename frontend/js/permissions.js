/**
 * Employee Permissions & Business Category Access Center
 * Manages 10 category scoping (By Product, HUSK, SAS, MRO, MCK, DOC, MSD, MOL, MOMT, General) and granular action permissions.
 * Strict Security: Only System Administrators can configure or modify permissions.
 */
const permissionsManager = {
    cachedEmployees: [],
    selectedEmpId: null,

    allCategories: [
        { code: 'By Product', name: 'By Product (All Lines)' },
        { code: 'HUSK', name: 'Rice Husk & Biomass' },
        { code: 'SAS', name: 'Automation & Power Corp' },
        { code: 'MRO', name: 'Industrial Supplies' },
        { code: 'MCK', name: 'Precision Machinery' },
        { code: 'DOC', name: 'Global Logistics' },
        { code: 'MSD', name: 'Steels & Fasteners' },
        { code: 'MOL', name: 'Oils & Agro Extracts' },
        { code: 'MOMT', name: 'Heavy Tools & Dies' },
        { code: 'General', name: 'General Accounts' }
    ],

    isAdminUser() {
        const user = (typeof api !== 'undefined' && api.getCurrentUser) ? api.getCurrentUser() : null;
        return Boolean(user && (user.role === 'admin' || user.role === 'ADMIN'));
    },

    handleNonAdminClick() {
        if (typeof api !== 'undefined' && api.toast) {
            api.toast("🔒 Security Alert: Only system administrators are authorized to configure employee permissions.", "warning");
        }
    },

    init() {
        // Bind search & filter inputs in the Permissions View
        const searchInput = document.getElementById('inp-permissions-search');
        if (searchInput) {
            searchInput.addEventListener('input', () => {
                this.applyFilters();
            });
        }

        const catFilter = document.getElementById('select-permissions-cat-filter');
        if (catFilter) {
            catFilter.addEventListener('change', () => {
                this.applyFilters();
            });
        }

        const roleFilter = document.getElementById('select-permissions-role-filter');
        if (roleFilter) {
            roleFilter.addEventListener('change', () => {
                this.applyFilters();
            });
        }

        // Modal Save Button listener
        const btnSaveModal = document.getElementById('btn-save-modal-perms');
        if (btnSaveModal) {
            btnSaveModal.addEventListener('click', () => {
                this.saveModalPermissions();
            });
        }

        // Allow clicking anywhere on the switch card to toggle smoothly
        document.querySelectorAll('.perm-switch-card').forEach(card => {
            card.addEventListener('click', (e) => {
                if (e.target.closest('.perm-switch-toggle') || e.target.tagName === 'INPUT') {
                    return;
                }
                const input = card.querySelector('input[type="checkbox"]');
                if (input && !input.disabled) {
                    input.checked = !input.checked;
                    input.dispatchEvent(new Event('change'));
                }
            });
        });

        // Allow clicking anywhere on category view cards to toggle smoothly
        document.querySelectorAll('.perm-cat-card').forEach(card => {
            card.addEventListener('click', (e) => {
                if (e.target.tagName === 'INPUT') return;
                const chk = card.querySelector('input[type="checkbox"]');
                if (chk) {
                    chk.checked = !chk.checked;
                    this.syncCategoryCardUI(chk);
                }
            });
        });

        // Allow clicking anywhere on upload cards to toggle smoothly
        document.querySelectorAll('.perm-upload-card').forEach(card => {
            card.addEventListener('click', (e) => {
                if (e.target.tagName === 'INPUT') return;
                const chk = card.querySelector('input[type="checkbox"]');
                if (chk) {
                    chk.checked = !chk.checked;
                    this.syncUploadCategoryCardUI(chk);
                }
            });
        });
    },

    async loadPermissionsView() {
        const tbody = document.getElementById('permissions-matrix-tbody');
        if (tbody) {
            tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding: 2.5rem; color: var(--text-muted);">
                <div style="display: flex; align-items: center; justify-content: center; gap: 0.6rem;">
                    <svg class="icon animate-spin" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--primary)" stroke-width="2.5"><path d="M21 12a9 9 0 1 1-6.219-8.56"></path></svg>
                    <span style="font-weight: 600; font-size: 0.875rem;">Loading team access control and permissions matrix...</span>
                </div>
            </td></tr>`;
        }

        try {
            const employees = await api.get('/employees');
            this.cachedEmployees = employees || [];
            this.renderKPIs(this.cachedEmployees);
            this.applyFilters();
        } catch (err) {
            console.error("Failed to load permissions matrix:", err);
            if (tbody) {
                tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding: 2rem; color: var(--danger);">
                    Failed to load permissions: ${err.message}
                </td></tr>`;
            }
        }
    },

    renderKPIs(employees) {
        const totalEl = document.getElementById('perm-kpi-total-members');
        const allAccessEl = document.getElementById('perm-kpi-all-access');
        const scopedEl = document.getElementById('perm-kpi-scoped');
        const callsEl = document.getElementById('perm-kpi-calls-enabled');

        if (!totalEl) return;

        const total = employees.length;
        let allAccessCount = 0;
        let scopedCount = 0;
        let callsEnabledCount = 0;

        employees.forEach(emp => {
            const cats = this.parseEmployeeCategories(emp);
            if (cats.length === 0 || cats.includes('ALL') || cats.includes('*') || cats.length >= 10) {
                allAccessCount++;
            } else {
                scopedCount++;
            }

            if (emp.can_make_calls !== false) {
                callsEnabledCount++;
            }
        });

        if (totalEl) totalEl.textContent = total;
        if (allAccessEl) allAccessEl.textContent = allAccessCount;
        if (scopedEl) scopedEl.textContent = scopedCount;
        if (callsEl) callsEl.textContent = callsEnabledCount;
    },

    parseEmployeeCategories(emp) {
        if (!emp) return [];
        let raw = emp.allowed_categories;
        if (!raw) return [];
        if (Array.isArray(raw)) {
            return raw.map(c => String(c).trim()).filter(c => c && c !== '***' && c !== "['***']");
        }
        if (typeof raw === 'string') {
            let s = raw.replace(/[\[\]\'\"]/g, '').trim();
            if (!s || s === '***') return [];
            return s.split(',').map(c => c.trim()).filter(c => c && c !== '***');
        }
        return [];
    },

    parseEmployeeUploadCategories(emp) {
        if (!emp) return [];
        let raw = emp.allowed_upload_categories;
        if (!raw) return [];
        if (Array.isArray(raw)) {
            return raw.map(c => String(c).trim()).filter(c => c && c !== '***' && c !== "['***']");
        }
        if (typeof raw === 'string') {
            let s = raw.replace(/[\[\]\'\"]/g, '').trim();
            if (!s || s === '***') return [];
            return s.split(',').map(c => c.trim()).filter(c => c && c !== '***');
        }
        return [];
    },

    applyFilters() {
        const searchVal = (document.getElementById('inp-permissions-search')?.value || '').toLowerCase().trim();
        const catVal = (document.getElementById('select-permissions-cat-filter')?.value || 'ALL').toUpperCase();
        const roleVal = (document.getElementById('select-permissions-role-filter')?.value || 'ALL').toLowerCase();

        let filtered = this.cachedEmployees.filter(emp => {
            // Text Search
            const nameMatch = (emp.full_name || '').toLowerCase().includes(searchVal);
            const emailMatch = (emp.email || '').toLowerCase().includes(searchVal);
            const desigMatch = (emp.designation || '').toLowerCase().includes(searchVal);
            const matchesSearch = !searchVal || nameMatch || emailMatch || desigMatch;

            // Role Filter
            const matchesRole = roleVal === 'all' || (emp.role || 'employee').toLowerCase() === roleVal;

            // Category Filter
            let matchesCat = true;
            if (catVal !== 'ALL') {
                const cats = this.parseEmployeeCategories(emp).map(c => c.toUpperCase());
                matchesCat = cats.length === 0 || cats.includes('ALL') || cats.includes('*') || cats.includes(catVal);
            }

            return matchesSearch && matchesRole && matchesCat;
        });

        this.renderMatrixTable(filtered);
    },

    async togglePermissionDirect(empId, fieldName) {
        if (!this.isAdminUser()) {
            this.handleNonAdminClick();
            return;
        }

        const emp = this.cachedEmployees.find(e => Number(e.id) === Number(empId));
        if (!emp) {
            if (typeof api !== 'undefined' && api.toast) api.toast("Employee record not found", "error");
            return;
        }

        // Determine current and next state
        const currentVal = emp[fieldName] !== undefined && emp[fieldName] !== null 
            ? Boolean(emp[fieldName]) 
            : (fieldName === 'can_delete_customer' ? false : true);
        const newVal = !currentVal;

        // Optimistically update employee object in cache
        emp[fieldName] = newVal;

        // Update DOM element immediately
        const toggleEl = document.getElementById(`toggle-row-${emp.id}-${fieldName}`);
        if (toggleEl) {
            if (newVal) {
                toggleEl.classList.remove('off');
                toggleEl.classList.add('on');
            } else {
                toggleEl.classList.remove('on');
                toggleEl.classList.add('off');
            }
            toggleEl.setAttribute('title', `Click to toggle (Currently: ${newVal ? 'Allowed' : 'Restricted'})`);
        }

        const fieldLabels = {
            'can_add_customer': 'Add Customer',
            'can_edit_customer': 'Edit Customer',
            'can_delete_customer': 'Delete Customer',
            'can_rate_customer': '1-5★ Rating',
            'can_make_calls': 'Outbound Calls',
            'can_listen_recordings': 'Audio Recordings',
            'can_export_data': 'Data Export',
            'can_view_unassigned': 'Unassigned Visibility'
        };
        const label = fieldLabels[fieldName] || fieldName;

        try {
            const payload = { [fieldName]: newVal };
            const updated = await api.put(`/employees/${emp.id}/permissions`, payload);

            // Update cached object with server response
            const idx = this.cachedEmployees.findIndex(e => Number(e.id) === Number(emp.id));
            if (idx !== -1) {
                this.cachedEmployees[idx] = { ...this.cachedEmployees[idx], ...updated };
            }

            // Sync with current logged in user session if self
            const currUser = (typeof api !== 'undefined' && api.getCurrentUser) ? api.getCurrentUser() : null;
            if (currUser && Number(currUser.id) === Number(emp.id)) {
                Object.assign(currUser, payload);
                if (typeof api.setCurrentUser === 'function') {
                    api.setCurrentUser(currUser);
                } else {
                    localStorage.setItem('crm_user_info', JSON.stringify(currUser));
                }
            }

            this.renderKPIs(this.cachedEmployees);
            if (typeof api !== 'undefined' && api.toast) {
                api.toast(`${label} set to ${newVal ? 'ALLOWED ✓' : 'RESTRICTED ✕'} for ${emp.full_name || emp.email}`, "success");
            }
        } catch (err) {
            console.error(`Failed to toggle ${fieldName}:`, err);
            emp[fieldName] = currentVal;
            if (toggleEl) {
                if (currentVal) {
                    toggleEl.classList.remove('off');
                    toggleEl.classList.add('on');
                } else {
                    toggleEl.classList.remove('on');
                    toggleEl.classList.add('off');
                }
            }
            if (typeof api !== 'undefined' && api.toast) {
                api.toast(`Failed to update permission: ${err.message}`, "error");
            }
        }
    },

    renderMatrixTable(employees) {
        const tbody = document.getElementById('permissions-matrix-tbody');
        const countBadge = document.getElementById('perm-filtered-count-badge');

        if (countBadge) {
            countBadge.textContent = `${employees.length} Members`;
        }

        if (!tbody) return;

        if (employees.length === 0) {
            tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding: 2.5rem; color: var(--text-muted);">
                <div style="font-weight: 600; font-size: 0.95rem; margin-bottom: 0.25rem;">No employees found matching criteria</div>
                <div style="font-size: 0.8125rem;">Try adjusting the search query or category filters.</div>
            </td></tr>`;
            return;
        }

        const isCurrentAdmin = this.isAdminUser();

        tbody.innerHTML = employees.map((emp, idx) => {
            const isEmpAdmin = emp.role === 'admin' || emp.role === 'ADMIN';
            const initials = (emp.full_name || emp.email).split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();

            // View Categories parsing
            const viewCats = this.parseEmployeeCategories(emp);
            let viewCatsHtml = '';
            const catClickAttr = isCurrentAdmin
                ? `onclick="permissionsManager.openEditPermissionsModal(${emp.id})" style="cursor: pointer;" title="Click to configure business category access"`
                : `onclick="permissionsManager.handleNonAdminClick()" style="cursor: not-allowed;" title="🔒 Category Access (Admin Controlled)"`;

            if (isEmpAdmin || viewCats.length === 0 || viewCats.includes('ALL') || viewCats.includes('*') || viewCats.length >= 10) {
                viewCatsHtml = `<div ${catClickAttr}><span class="badge badge-active" style="background: rgba(16,185,129,0.14); color: #059669; font-weight: 700; border: 1px solid rgba(16,185,129,0.3); display: inline-flex; align-items: center; gap: 4px; padding: 3px 8px;">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"></polyline></svg>
                    <span>ALL CATEGORIES (10)</span>
                </span></div>`;
            } else {
                viewCatsHtml = `<div ${catClickAttr} style="display: flex; gap: 4px; flex-wrap: wrap; max-width: 220px;">` +
                    viewCats.map(c => `<span class="perm-cat-tag">${c}</span>`).join('') +
                    `</div>`;
            }

            // Upload Categories parsing
            const uploadCats = this.parseEmployeeUploadCategories(emp);
            let uploadCatsHtml = '';
            if (isEmpAdmin || uploadCats.includes('*') || uploadCats.includes('ALL') || uploadCats.length >= 10) {
                uploadCatsHtml = `<div ${catClickAttr}><span class="badge" style="background: rgba(79, 70, 229, 0.12); color: var(--primary); font-weight: 700; border: 1px solid rgba(79, 70, 229, 0.3); display: inline-flex; align-items: center; gap: 4px; padding: 3px 8px;">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>
                    <span>${isEmpAdmin ? 'ADMIN FULL UPLOAD' : 'ALL 10 UPLOAD'}</span>
                </span></div>`;
            } else if (uploadCats.length === 0) {
                uploadCatsHtml = `<div ${catClickAttr}><span class="badge badge-standard" style="color: var(--text-muted); border: 1px dashed var(--border-color); display: inline-flex; align-items: center; gap: 4px; padding: 3px 8px; font-size: 0.72rem;">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                    <span>No Upload (Admin Only)</span>
                </span></div>`;
            } else {
                uploadCatsHtml = `<div ${catClickAttr} style="display: flex; gap: 4px; flex-wrap: wrap; max-width: 220px;">` +
                    uploadCats.map(c => `<span class="perm-cat-tag" style="background: rgba(79,70,229,0.1); color: var(--primary); border-color: rgba(79,70,229,0.3); display: inline-flex; align-items: center; gap: 3px;">${c} <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg></span>`).join('') +
                    `</div>`;
            }

            // High-clarity Matrix Mini-Toggle helper with 1-click toggle support
            const renderToggle = (val, fieldName, label, defaultVal = true) => {
                const isAllowed = val !== undefined && val !== null ? Boolean(val) : defaultVal;
                const stateClass = isAllowed ? 'on' : 'off';

                let tooltip = '';
                let clickAttr = '';

                if (isCurrentAdmin) {
                    tooltip = `${label}: ${isAllowed ? 'Allowed' : 'Restricted'} (Click to toggle)`;
                    clickAttr = `onclick="event.stopPropagation(); permissionsManager.togglePermissionDirect(${emp.id}, '${fieldName}')" style="cursor: pointer;"`;
                } else {
                    tooltip = `🔒 ${label}: ${isAllowed ? 'Allowed' : 'Restricted'} (Admin authorization required to change)`;
                    clickAttr = `onclick="permissionsManager.handleNonAdminClick()" style="cursor: not-allowed; opacity: 0.85;"`;
                }

                return `<div class="perm-table-toggle ${stateClass}" id="toggle-row-${emp.id}-${fieldName}" title="${tooltip}" ${clickAttr}>
                    <div class="perm-mini-switch">
                        <div class="perm-mini-knob"></div>
                    </div>
                    <span>${label}</span>
                </div>`;
            };

            const dataPermsHtml = `
                <div style="display: flex; gap: 5px; flex-wrap: wrap; max-width: 240px;">
                    ${renderToggle(emp.can_add_customer, 'can_add_customer', 'Add', true)}
                    ${renderToggle(emp.can_edit_customer, 'can_edit_customer', 'Edit', true)}
                    ${renderToggle(emp.can_delete_customer, 'can_delete_customer', 'Delete', false)}
                    ${renderToggle(emp.can_rate_customer, 'can_rate_customer', '1-5★', true)}
                </div>
            `;

            const commsPermsHtml = `
                <div style="display: flex; gap: 5px; flex-wrap: wrap;">
                    ${renderToggle(emp.can_make_calls, 'can_make_calls', 'Calls', true)}
                    ${renderToggle(emp.can_listen_recordings, 'can_listen_recordings', 'Audio', true)}
                </div>
            `;

            const exportPermsHtml = `
                <div style="display: flex; gap: 5px; flex-wrap: wrap;">
                    ${renderToggle(emp.can_export_data, 'can_export_data', 'Export', true)}
                    ${renderToggle(emp.can_view_unassigned, 'can_view_unassigned', 'Unassigned', true)}
                </div>
            `;

            const actionBtnHtml = isCurrentAdmin
                ? `<button type="button" class="btn btn-primary btn-xs" onclick="permissionsManager.openEditPermissionsModal(${emp.id})" style="font-weight: 600; gap: 5px; padding: 0.35rem 0.75rem; border-radius: 6px; box-shadow: 0 1px 3px rgba(79,70,229,0.2);">
                    <svg class="icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
                    <span>Configure</span>
                </button>`
                : `<span class="badge badge-standard" onclick="permissionsManager.handleNonAdminClick()" style="font-size: 0.72rem; color: var(--text-muted); cursor: not-allowed; display: inline-flex; align-items: center; gap: 4px; padding: 4px 8px;">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                    <span>View Only</span>
                </span>`;

            return `
                <tr>
                    <td style="font-weight: 700; color: var(--text-muted); width: 40px; text-align: center;">${idx + 1}</td>
                    <td>
                        <div style="display: flex; align-items: center; gap: 0.75rem; ${isCurrentAdmin ? 'cursor: pointer;' : ''}" ${isCurrentAdmin ? `onclick="permissionsManager.openEditPermissionsModal(${emp.id})"` : ''}>
                            <div style="width: 36px; height: 36px; border-radius: 50%; background: ${isEmpAdmin ? 'linear-gradient(135deg, var(--primary), #818cf8)' : 'var(--bg-surface-elevated)'}; color: ${isEmpAdmin ? '#fff' : 'var(--text-primary)'}; font-weight: 800; font-size: 0.78rem; display: flex; align-items: center; justify-content: center; border: 1.5px solid var(--border-color);">
                                ${initials}
                            </div>
                            <div>
                                <div style="font-weight: 700; font-size: 0.875rem; color: var(--text-primary); display: flex; align-items: center; gap: 6px;">
                                    <span>${emp.full_name || 'Unnamed Employee'}</span>
                                    <span class="${isEmpAdmin ? 'badge badge-vip' : 'badge badge-standard'}" style="font-size: 0.6875rem;">
                                        ${(emp.role || 'employee').toUpperCase()}
                                    </span>
                                </div>
                                <div style="font-size: 0.72rem; color: var(--text-muted); margin-top: 1px;">
                                    ${emp.email} • <span style="color: var(--text-secondary); font-weight: 600;">${emp.designation || 'Staff'}</span>
                                </div>
                            </div>
                        </div>
                    </td>
                    <td>${viewCatsHtml}</td>
                    <td>${uploadCatsHtml}</td>
                    <td>${dataPermsHtml}</td>
                    <td>${commsPermsHtml}</td>
                    <td>${exportPermsHtml}</td>
                    <td style="text-align: right; white-space: nowrap;">
                        ${actionBtnHtml}
                    </td>
                </tr>
            `;
        }).join('');
    },

    openEditPermissionsModal(empId) {
        if (!this.isAdminUser()) {
            this.handleNonAdminClick();
            return;
        }

        const emp = this.cachedEmployees.find(e => Number(e.id) === Number(empId));
        if (!emp) {
            api.toast("Employee record not found in system cache", "error");
            return;
        }

        this.selectedEmpId = emp.id;

        // Set Profile Details in Modal Header
        const nameEl = document.getElementById('modal-perm-emp-name');
        const emailEl = document.getElementById('modal-perm-emp-email');
        const desigEl = document.getElementById('modal-perm-emp-desig');
        const roleEl = document.getElementById('modal-perm-emp-role');
        const avatarEl = document.getElementById('modal-perm-emp-avatar');

        const initials = (emp.full_name || emp.email).split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();

        if (nameEl) nameEl.textContent = emp.full_name || 'Unnamed Employee';
        if (emailEl) emailEl.textContent = emp.email || '—';
        if (desigEl) desigEl.textContent = emp.designation || 'Staff Member';
        if (avatarEl) avatarEl.textContent = initials;

        if (roleEl) {
            roleEl.textContent = (emp.role || 'EMPLOYEE').toUpperCase();
            roleEl.className = emp.role === 'admin' ? 'badge badge-vip' : 'badge badge-standard';
        }

        // Parse View Categories
        const viewCats = this.parseEmployeeCategories(emp);
        const isAllView = viewCats.length === 0 || viewCats.includes('ALL') || viewCats.includes('*') || viewCats.length >= 10;
        const normalizedView = viewCats.map(c => c.toUpperCase());

        document.querySelectorAll('.chk-modal-cat').forEach(chk => {
            const shouldCheck = isAllView || normalizedView.includes(chk.value.toUpperCase());
            chk.checked = shouldCheck;
            this.syncCategoryCardUI(chk);
        });

        // Parse Upload Categories
        const uploadCats = this.parseEmployeeUploadCategories(emp);
        const isAllUpload = emp.role === 'admin' || uploadCats.includes('ALL') || uploadCats.includes('*') || uploadCats.length >= 10;
        const normalizedUpload = uploadCats.map(c => c.toUpperCase());

        document.querySelectorAll('.chk-modal-upload-cat').forEach(chk => {
            const shouldCheck = isAllUpload || normalizedUpload.includes(chk.value.toUpperCase());
            chk.checked = shouldCheck;
            this.syncUploadCategoryCardUI(chk);
        });

        // Sync Feature Switches
        const setSwitch = (type, val) => {
            const chk = document.getElementById(`chk-modal-perm-${type}`);
            if (chk) {
                chk.checked = Boolean(val);
                this.syncSwitchCardUI(type, chk.checked);
            }
        };

        setSwitch('add', emp.can_add_customer !== false);
        setSwitch('edit', emp.can_edit_customer !== false);
        setSwitch('delete', Boolean(emp.can_delete_customer));
        setSwitch('rate', emp.can_rate_customer !== false);
        setSwitch('calls', emp.can_make_calls !== false);
        setSwitch('recordings', emp.can_listen_recordings !== false);
        setSwitch('export', emp.can_export_data !== false);
        setSwitch('unassigned', emp.can_view_unassigned !== false);

        if (window.app && typeof app.openModal === 'function') {
            app.openModal('modal-edit-employee-permissions');
        } else {
            const modal = document.getElementById('modal-edit-employee-permissions');
            if (modal) modal.classList.add('active');
        }
    },

    syncCategoryCardUI(chk) {
        if (!chk) return;
        const safeVal = String(chk.value || '').replace(/\s+/g, '-');
        const card = document.getElementById(`card-cat-${safeVal}`) || document.getElementById(`card-cat-${chk.value}`) || chk.closest('.perm-cat-card');
        if (!card) return;
        const checkIcon = card.querySelector('.perm-cat-check');

        if (chk.checked) {
            card.classList.add('active');
            if (checkIcon) checkIcon.style.opacity = '1';
        } else {
            card.classList.remove('active');
            if (checkIcon) checkIcon.style.opacity = '0';
        }
    },

    setModalCategories(isSelectAll) {
        document.querySelectorAll('.chk-modal-cat').forEach(chk => {
            chk.checked = isSelectAll;
            this.syncCategoryCardUI(chk);
        });
    },

    syncUploadCategoryCardUI(chk) {
        if (!chk) return;
        const safeVal = String(chk.value || '').replace(/\s+/g, '-');
        const card = document.getElementById(`card-upload-cat-${safeVal}`) || document.getElementById(`card-upload-cat-${chk.value}`) || chk.closest('.perm-upload-card') || chk.closest('.perm-cat-card');
        if (!card) return;
        const checkIcon = card.querySelector('.perm-upload-check') || card.querySelector('.perm-cat-check');

        if (chk.checked) {
            card.classList.add('active');
            if (checkIcon) checkIcon.style.opacity = '1';
        } else {
            card.classList.remove('active');
            if (checkIcon) checkIcon.style.opacity = '0';
        }
    },

    setModalUploadCategories(isSelectAll) {
        document.querySelectorAll('.chk-modal-upload-cat').forEach(chk => {
            chk.checked = isSelectAll;
            this.syncUploadCategoryCardUI(chk);
        });
    },

    syncSwitchCardUI(type, isChecked) {
        const card = document.getElementById(`switch-card-${type}`);
        const badge = document.getElementById(`badge-perm-${type}`);

        if (card) {
            if (isChecked) {
                card.classList.add('allowed');
                card.classList.remove('restricted');
            } else {
                card.classList.remove('allowed');
                card.classList.add('restricted');
            }
        }

        if (badge) {
            if (isChecked) {
                badge.className = 'perm-status-badge allowed';
                badge.textContent = '✓ ALLOWED';
            } else {
                badge.className = 'perm-status-badge restricted';
                badge.textContent = '✕ RESTRICTED';
            }
        }
    },

    async saveModalPermissions() {
        if (!this.isAdminUser()) {
            this.handleNonAdminClick();
            return;
        }

        if (!this.selectedEmpId) {
            api.toast("No employee selected", "error");
            return;
        }

        const btn = document.getElementById('btn-save-modal-perms');
        const origHtml = btn ? btn.innerHTML : "Save Employee Permissions";

        // Collect selected view categories
        const checkedViewCats = [];
        document.querySelectorAll('.chk-modal-cat:checked').forEach(c => {
            checkedViewCats.push(c.value);
        });

        // Collect selected upload categories
        const checkedUploadCats = [];
        document.querySelectorAll('.chk-modal-upload-cat:checked').forEach(c => {
            checkedUploadCats.push(c.value);
        });

        const getCheck = (id) => {
            const el = document.getElementById(id);
            return el ? el.checked : false;
        };

        const payload = {
            allowed_categories: checkedViewCats.length > 0 ? checkedViewCats : ['*'],
            allowed_upload_categories: checkedUploadCats,
            can_add_customer: getCheck('chk-modal-perm-add'),
            can_edit_customer: getCheck('chk-modal-perm-edit'),
            can_delete_customer: getCheck('chk-modal-perm-delete'),
            can_rate_customer: getCheck('chk-modal-perm-rate'),
            can_make_calls: getCheck('chk-modal-perm-calls'),
            can_listen_recordings: getCheck('chk-modal-perm-recordings'),
            can_export_data: getCheck('chk-modal-perm-export'),
            can_view_unassigned: getCheck('chk-modal-perm-unassigned')
        };

        if (btn) {
            btn.disabled = true;
            btn.innerHTML = `<span style="display: inline-flex; align-items: center; gap: 0.5rem;"><svg class="icon animate-spin" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 12a9 9 0 1 1-6.219-8.56"></path></svg><span>Updating Permissions...</span></span>`;
        }

        try {
            const updated = await api.put(`/employees/${this.selectedEmpId}/permissions`, payload);

            // Update local cache
            const idx = this.cachedEmployees.findIndex(e => Number(e.id) === Number(this.selectedEmpId));
            if (idx !== -1) {
                this.cachedEmployees[idx] = { ...this.cachedEmployees[idx], ...updated };
            }

            // Sync with current user cache if updating own admin account
            const currUser = (typeof api !== 'undefined' && api.getCurrentUser) ? api.getCurrentUser() : null;
            if (currUser && Number(currUser.id) === Number(this.selectedEmpId)) {
                Object.assign(currUser, payload);
                if (typeof api.setCurrentUser === 'function') {
                    api.setCurrentUser(currUser);
                } else {
                    localStorage.setItem('crm_user_info', JSON.stringify(currUser));
                }
            }

            // Sync with excelImport quick permit if present
            if (typeof excelImport !== 'undefined' && excelImport.quickPermEmployees) {
                const qIdx = excelImport.quickPermEmployees.findIndex(e => Number(e.id) === Number(this.selectedEmpId));
                if (qIdx !== -1) {
                    excelImport.quickPermEmployees[qIdx] = { ...excelImport.quickPermEmployees[qIdx], ...updated };
                    if (typeof excelImport.handleQuickPermEmployeeChange === 'function') {
                        excelImport.handleQuickPermEmployeeChange(this.selectedEmpId);
                    }
                }
            }

            if (window.app && typeof app.closeModal === 'function') {
                app.closeModal('modal-edit-employee-permissions');
            } else {
                const modal = document.getElementById('modal-edit-employee-permissions');
                if (modal) modal.classList.remove('active');
            }

            this.applyFilters();
            this.renderKPIs(this.cachedEmployees);
            api.toast(`Permissions successfully updated for ${updated.full_name || 'Employee'}!`, "success");
        } catch (err) {
            console.error("Failed to save permissions:", err);
            api.toast(`Failed to save permissions: ${err.message}`, "error");
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = origHtml;
            }
        }
    }
};

window.permissionsManager = permissionsManager;
