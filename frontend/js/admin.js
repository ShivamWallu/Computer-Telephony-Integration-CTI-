/**
 * Admin Panel: Team Management, Add/Delete Employee, Multi-Customer Reassignment & System Audit Logs
 */
const admin = {
    selectedDeleteEmployeeId: null,

    init() {
        // Open Add Employee Modal
        document.getElementById('btn-open-add-employee')?.addEventListener('click', () => {
            this.openAddEmployeeModal();
        });

        // Submit Add Employee Form
        document.getElementById('btn-submit-add-employee')?.addEventListener('click', (e) => {
            e.preventDefault();
            this.submitAddEmployee();
        });

        // Reassign Scope Mode Change (All / Unassigned / Selected)
        document.getElementById('reassign-scope')?.addEventListener('change', (e) => {
            const container = document.getElementById('container-reassign-individual');
            const isSelected = e.target.value === 'selected' || e.target.value === 'individual';
            if (container) {
                container.style.display = isSelected ? 'block' : 'none';
            }
            if (isSelected) {
                this.populateCustomerChecklist();
            }
        });

        // Select All / Clear Checkboxes
        document.getElementById('btn-reassign-select-all')?.addEventListener('click', () => {
            document.querySelectorAll('.reassign-cust-check').forEach(cb => cb.checked = true);
        });
        document.getElementById('btn-reassign-clear-all')?.addEventListener('click', () => {
            document.querySelectorAll('.reassign-cust-check').forEach(cb => cb.checked = false);
        });

        // Customer Reassignment Trigger
        document.getElementById('btn-trigger-reassign')?.addEventListener('click', () => {
            this.executeReassignment();
        });

        // Confirm Delete Employee Action in Modal
        document.getElementById('btn-confirm-delete-emp')?.addEventListener('click', () => {
            this.executeDeleteEmployee();
        });

        // Audit Trail Clear Handlers
        document.getElementById('btn-clear-audit-logs')?.addEventListener('click', () => {
            app.openModal('modal-clear-audit-logs');
        });
        document.getElementById('btn-confirm-clear-audit-logs')?.addEventListener('click', () => {
            this.executeClearAuditLogs();
        });

        // Production Data Cleanup Handlers
        document.getElementById('btn-admin-clean-prod-data')?.addEventListener('click', () => {
            app.openModal('modal-clean-prod-data');
        });
        document.getElementById('btn-confirm-clean-prod-data')?.addEventListener('click', () => {
            this.executeCleanProductionData();
        });
    },

    async loadAdminData() {
        await Promise.all([
            this.loadTeamTable(),
            this.loadAuditLogs(),
            this.populateEmployeeDropdown(),
            this.populateCustomerChecklist(),
            app.loadSmartfloTokenTable ? app.loadSmartfloTokenTable() : Promise.resolve()
        ]);
    },

    openAddEmployeeModal() {
        const form = document.getElementById('form-add-employee');
        if (form) form.reset();
        app.openModal('modal-add-employee');
    },

    async submitAddEmployee() {
        const name = document.getElementById('inp-emp-name')?.value.trim();
        const email = document.getElementById('inp-emp-email')?.value.trim();
        const password = document.getElementById('inp-emp-password')?.value.trim();
        const phone = document.getElementById('inp-emp-phone')?.value.trim() || null;
        const allowedCallerId = document.getElementById('inp-emp-allowed-caller-id')?.value.trim() || null;
        const designation = document.getElementById('inp-emp-designation')?.value.trim() || 'Employee';
        const role = document.getElementById('inp-emp-role')?.value || 'employee';

        if (!name || !email || !password) {
            api.toast("Please fill in Name, Email, and Password", "error");
            return;
        }

        try {
            const newEmp = await api.post('/employees', {
                full_name: name,
                email: email,
                password: password,
                phone: phone,
                allowed_caller_id: allowedCallerId,
                vid: allowedCallerId,
                designation: designation,
                role: role
            });

            api.toast(`Team member ${newEmp.full_name} (${newEmp.role.toUpperCase()}) created successfully!`, "success");
            app.closeModal('modal-add-employee');

            await this.loadTeamTable();
            await this.populateEmployeeDropdown();
            if (typeof customer !== 'undefined' && customer.populateAgentDropdown) {
                await customer.populateAgentDropdown();
            }
            if (typeof app !== 'undefined' && app.populateUserQuickSwitcher) {
                await app.populateUserQuickSwitcher();
            }
        } catch (err) {
            api.toast(`Failed to add employee: ${err.message}`, "error");
        }
    },

    openDeleteEmployeeModal(empId, empName) {
        if (!empId) {
            api.toast("Invalid employee ID selected", "error");
            return;
        }
        const currentUserId = api.getCurrentUser()?.id;
        if (empId === currentUserId) {
            api.toast("You cannot delete your own active administrator account.", "warning");
            return;
        }

        this.selectedDeleteEmployeeId = empId;
        const nameEl = document.getElementById('modal-delete-emp-name');
        if (nameEl) nameEl.textContent = `${empName} (ID: #${empId})`;
        app.openModal('modal-delete-employee');
    },

    async executeDeleteEmployee() {
        if (!this.selectedDeleteEmployeeId) {
            api.toast("No employee selected for deletion", "error");
            return;
        }

        try {
            const res = await api.delete(`/employees/${this.selectedDeleteEmployeeId}`);
            app.closeModal('modal-delete-employee');
            api.toast(res.message || "Employee removed successfully. Assigned customer data is safe.", "success");
            this.selectedDeleteEmployeeId = null;

            await this.loadTeamTable();
            await this.populateEmployeeDropdown();
            if (typeof customer !== 'undefined') {
                customer.loadCustomers();
            }
            if (typeof app !== 'undefined' && app.populateUserQuickSwitcher) {
                await app.populateUserQuickSwitcher();
            }
            app.refreshDashboard();
        } catch (err) {
            api.toast(`Failed to delete employee: ${err.message}`, "error");
        }
    },

    async loadTeamTable() {
        const tbody = document.getElementById('admin-team-table-body');
        if (!tbody) return;

        // Render circular loader bar + shimmering skeleton rows
        tbody.innerHTML = `
            <tr>
                <td colspan="9" style="text-align: center; padding: 1rem 0; border-bottom: none;">
                    <div style="display: inline-flex; align-items: center; gap: 8px; font-size: 0.8125rem; color: var(--text-secondary); background: var(--bg-surface); padding: 0.4rem 1rem; border-radius: var(--radius-full); border: 1px solid var(--border-color); box-shadow: var(--shadow-xs);">
                        <span class="spinner-sm" style="border-top-color: var(--primary);"></span>
                        <span>Loading team performance metrics...</span>
                    </div>
                </td>
            </tr>
        ` + Array.from({ length: 4 }).map(() => `
            <tr class="skeleton-row">
                <td>
                    <div style="display: flex; align-items: center; gap: 0.5rem;">
                        <div class="skeleton skeleton-circle" style="width: 28px; height: 28px;"></div>
                        <div>
                            <div class="skeleton" style="width: 120px; height: 13px; margin-bottom: 4px;"></div>
                            <div class="skeleton" style="width: 80px; height: 10px;"></div>
                        </div>
                    </div>
                </td>
                <td><div class="skeleton" style="width: 90px; height: 13px;"></div></td>
                <td><div class="skeleton" style="width: 80px; height: 16px; border-radius: 4px;"></div></td>
                <td><div class="skeleton" style="width: 70px; height: 16px; border-radius: 4px;"></div></td>
                <td><div class="skeleton" style="width: 60px; height: 16px; border-radius: 4px;"></div></td>
                <td><div class="skeleton" style="width: 35px; height: 14px;"></div></td>
                <td><div class="skeleton" style="width: 35px; height: 14px;"></div></td>
                <td><div class="skeleton" style="width: 35px; height: 14px;"></div></td>
                <td><div class="skeleton" style="width: 60px; height: 24px; border-radius: 4px;"></div></td>
            </tr>
        `).join('');

        try {
            const stats = await api.get('/dashboard/stats');
            const team = stats.team_activity || [];
            const currentUser = api.getCurrentUser();
            const isAdmin = currentUser && currentUser.role === 'admin';

            if (team.length === 0) {
                tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">No team metrics available.</td></tr>`;
                return;
            }

            tbody.innerHTML = team.map(emp => {
                const empId = emp.user_id || emp.id;
                const isSelf = currentUser && (currentUser.email === emp.email || currentUser.id === empId);
                const safeName = (emp.full_name || '').replace(/'/g, "\\'");
                const phone = emp.phone || '—';
                const allowedCid = emp.allowed_caller_id || emp.vid || '—';
                const desig = (emp.designation && emp.designation !== 'NA' && String(emp.designation).trim() !== '') ? emp.designation : 'Employee';
                const initials = (emp.full_name || 'U').split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();

                return `
                <tr>
                    <td>
                        <div style="display: flex; align-items: center; gap: 0.5rem;">
                            <div class="user-avatar" style="width: 28px; height: 28px; font-size: 0.6875rem;">
                                ${initials}
                            </div>
                            <div>
                                <div style="font-weight: 600; color: var(--text-primary);">${emp.full_name}</div>
                                <div style="font-size: 0.72rem; color: var(--text-muted);">${emp.email}</div>
                            </div>
                        </div>
                    </td>
                    <td>
                        <span style="font-family: monospace; font-size: 0.75rem; font-weight: 500; color: var(--text-secondary);">${phone}</span>
                    </td>
                    <td>
                        <span class="badge badge-standard" style="font-size: 0.6875rem;">
                            ${allowedCid}
                        </span>
                    </td>
                    <td>
                        <span class="badge ${desig === 'Director' ? 'badge-vip' : 'badge-standard'}">
                            ${desig}
                        </span>
                    </td>
                    <td>
                        <span class="badge ${emp.role === 'admin' ? 'badge-vip' : 'badge-standard'}">${(emp.role || 'employee').toUpperCase()}</span>
                    </td>
                    <td style="font-weight: 600; color: var(--primary); text-align: center;">${emp.assigned_customers_count ?? 0}</td>
                    <td style="font-weight: 600; color: var(--success); text-align: center;">${emp.calls_logged ?? 0}</td>
                    <td style="font-weight: 600; color: var(--purple); text-align: center;">${emp.followups_completed ?? 0}</td>
                    <td>
                        ${isAdmin && !isSelf ? `
                            <button class="btn btn-danger btn-xs" onclick="window.admin.openDeleteEmployeeModal(${empId}, '${safeName}')" title="Delete Member">
                                ${Icons.get('trash', { size: 12 })}
                                <span>Delete</span>
                            </button>
                        ` : `<span style="font-size: 0.72rem; color: var(--text-muted);">${isSelf ? 'Active (You)' : '—'}</span>`}
                    </td>
                </tr>
            `}).join('');

        } catch (err) {
            console.error("Team table error:", err);
            tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--danger);">Failed to load team data.</td></tr>`;
        }
    },

    async populateEmployeeDropdown() {
        const sel = document.getElementById('reassign-target-employee');
        if (!sel) return;

        try {
            const employees = await api.get('/employees');
            sel.innerHTML = employees.map(e => `
                <option value="${e.id}">${e.full_name} (${e.role.toUpperCase()})</option>
            `).join('');
        } catch (err) {
            console.error("Could not populate employee dropdown:", err);
        }
    },

    async populateCustomerChecklist() {
        const container = document.getElementById('reassign-customer-checklist');
        if (!container) return;

        try {
            const custRes = await api.get('/customers?limit=100');
            if (custRes && custRes.items) {
                container.innerHTML = custRes.items.map(c => {
                    const assignedName = c.assigned_employee?.full_name || 'Unassigned';
                    const name = c.party_name || c.name || 'Customer';
                    const phone = c.phone_1 || c.mobile || '';
                    return `
                    <label style="display: flex; align-items: center; gap: 0.5rem; font-size: 0.8125rem; cursor: pointer; padding: 0.25rem 0.4rem; border-radius: var(--radius-xs); transition: background 0.15s ease;" onmouseover="this.style.background='var(--bg-surface-hover)'" onmouseout="this.style.background='transparent'">
                        <input type="checkbox" class="reassign-cust-check" value="${c.id}" style="width: 15px; height: 15px; accent-color: var(--primary); cursor: pointer;" />
                        <span style="font-weight: 600; color: var(--text-primary);">${name}</span>
                        <span style="color: var(--text-muted); font-size: 0.72rem;">(${phone})</span>
                        <span style="margin-left: auto; font-size: 0.6875rem;" class="badge badge-standard">Assigned: ${assignedName}</span>
                    </label>
                    `;
                }).join('');
            }
        } catch (err) {
            console.error("Could not populate customer checklist:", err);
            container.innerHTML = `<span style="color: var(--danger); font-size: 0.8rem;">Failed to load customers list.</span>`;
        }
    },

    async executeReassignment() {
        const targetId = parseInt(document.getElementById('reassign-target-employee')?.value);
        const scope = document.getElementById('reassign-scope')?.value || 'all';

        if (!targetId) {
            api.toast("Please select a target employee", "error");
            return;
        }

        let payload = {
            target_employee_id: targetId,
            reassign_scope: scope
        };

        if (scope === 'selected' || scope === 'individual') {
            const checkedBoxes = [...document.querySelectorAll('.reassign-cust-check:checked')];
            if (checkedBoxes.length === 0) {
                api.toast("Please select at least one customer checkbox to assign", "error");
                return;
            }
            payload.customer_ids = checkedBoxes.map(cb => parseInt(cb.value));
        }

        try {
            const res = await api.post('/employees/reassign-customers', payload);

            api.toast(res.message || `Successfully reassigned customers to ${res.assigned_to}! Email sent.`, "success");
            
            // Auto-reset all reassignment selection fields & dropdowns to clean default state
            const scopeSelect = document.getElementById('reassign-scope');
            if (scopeSelect) scopeSelect.value = 'all';

            const container = document.getElementById('container-reassign-individual');
            if (container) container.style.display = 'none';

            document.querySelectorAll('.reassign-cust-check').forEach(cb => cb.checked = false);

            const targetSelect = document.getElementById('reassign-target-employee');
            if (targetSelect && targetSelect.options.length > 0) {
                targetSelect.selectedIndex = 0;
            }

            await this.loadTeamTable();
            await this.populateCustomerChecklist();
            if (typeof customer !== 'undefined') {
                customer.loadCustomers();
            }
            app.refreshDashboard();
        } catch (err) {
            // On failure, keep user selections intact for easy retry
            api.toast(`Reassignment failed: ${err.message}`, "error");
        }
    },

    async loadAuditLogs() {
        const tbody = document.getElementById('admin-audit-table-body');
        if (!tbody) return;

        try {
            const logs = await api.get('/audit?limit=50');
            if (!logs || logs.length === 0) {
                tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">No audit logs recorded yet.</td></tr>`;
                return;
            }

            this.cachedAuditLogs = logs;
            this.renderAuditLogsTable(logs);
        } catch (err) {
            console.error("Audit log error:", err);
            tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--danger);">Failed to load audit logs.</td></tr>`;
        }
    },

    renderAuditLogsTable(logs) {
        const tbody = document.getElementById('admin-audit-table-body');
        if (!tbody) return;

        if (!logs || logs.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">No matching audit records found.</td></tr>`;
            return;
        }

        tbody.innerHTML = logs.map(l => {
            const userName = l.user_name || "System";
            const userEmail = l.user_email || "";
            const userRole = (l.user_role || "system").toUpperCase();
            const roleBadgeClass = userRole === 'ADMIN' ? 'badge-lead' : (userRole === 'EMPLOYEE' ? 'badge-active' : 'badge-standard');

            let badgeClass = "badge-standard";
            let actionLabel = l.action;
            if (l.action === "USER_LOGIN") {
                badgeClass = "badge-active";
                actionLabel = "User Login";
            } else if (l.action === "USER_SWITCHED_ACCOUNT") {
                badgeClass = "badge-lead";
                actionLabel = "Account Switch";
            } else if (l.action.includes("CLEARED") || l.action.includes("DELETED") || l.action.includes("ARCHIVED")) {
                badgeClass = "badge-overdue";
                actionLabel = l.action.replace(/_/g, ' ');
            } else if (l.action.includes("CREATED") || l.action.includes("ADDED")) {
                badgeClass = "badge-active";
                actionLabel = l.action.replace(/_/g, ' ');
            } else if (l.action.includes("UPDATED") || l.action.includes("REASSIGNED")) {
                badgeClass = "badge-standard";
                actionLabel = l.action.replace(/_/g, ' ');
            }

            let detailsText = "—";
            if (l.changes && Object.keys(l.changes).length > 0) {
                detailsText = Object.entries(l.changes)
                    .map(([k, v]) => `${k.replace(/_/g, ' ')}: ${typeof v === 'object' ? JSON.stringify(v) : v}`)
                    .join(' • ');
            }

            const initials = userName.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase() || 'SYS';
            const status = l.status || "Success";

            return `
                <tr class="audit-row" data-user="${userName.toLowerCase()}" data-email="${userEmail.toLowerCase()}" data-action="${actionLabel.toLowerCase()}" data-entity="${(l.entity_type || '').toLowerCase()}">
                    <td>
                        <span style="font-size: 0.75rem; color: var(--text-secondary); font-variant-numeric: tabular-nums; white-space: nowrap;">
                            ${app.formatDateTime(l.created_at)}
                        </span>
                    </td>
                    <td>
                        <div style="display: flex; align-items: center; gap: 0.5rem;">
                            <div style="width: 26px; height: 26px; border-radius: 50%; background: var(--primary-subtle); color: var(--primary); display: flex; align-items: center; justify-content: center; font-size: 0.68rem; font-weight: 700; flex-shrink: 0;">
                                ${initials}
                            </div>
                            <div>
                                <strong style="color: var(--text-primary); font-size: 0.8125rem;">${userName}</strong>
                                ${userEmail ? `<div style="font-size: 0.6875rem; color: var(--text-muted); line-height: 1.2;">${userEmail}</div>` : ''}
                            </div>
                        </div>
                    </td>
                    <td>
                        <span class="badge ${roleBadgeClass}" style="font-size: 0.6875rem; font-weight: 600; padding: 0.15rem 0.45rem;">
                            ${userRole}
                        </span>
                    </td>
                    <td>
                        <span class="badge ${badgeClass}" style="font-size: 0.72rem; font-weight: 600;">
                            ${actionLabel}
                        </span>
                    </td>
                    <td>
                        <span style="font-size: 0.78rem; font-weight: 500; color: var(--text-primary);">
                            ${(l.entity_type || '').toUpperCase()} ${l.entity_id ? `(#${l.entity_id})` : ''}
                        </span>
                    </td>
                    <td>
                        <span class="badge badge-active" style="font-size: 0.6875rem; font-weight: 600;">
                            ${status}
                        </span>
                    </td>
                    <td style="font-size: 0.72rem; color: var(--text-muted); max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${detailsText}">
                        ${detailsText}
                    </td>
                </tr>
            `;
        }).join('');
    },

    filterAuditLogs() {
        const input = document.getElementById('admin-audit-search');
        if (!input) return;
        const query = (input.value || '').trim().toLowerCase();
        const rows = document.querySelectorAll('.audit-row');
        rows.forEach(row => {
            const user = row.getAttribute('data-user') || '';
            const email = row.getAttribute('data-email') || '';
            const action = row.getAttribute('data-action') || '';
            const entity = row.getAttribute('data-entity') || '';
            if (user.includes(query) || email.includes(query) || action.includes(query) || entity.includes(query)) {
                row.style.display = '';
            } else {
                row.style.display = 'none';
            }
        });
    },

    async executeClearAuditLogs() {
        try {
            const res = await api.delete('/audit');
            app.closeModal('modal-clear-audit-logs');
            api.toast(res.message || "Audit trail logs cleared successfully!", "success");
            this.loadAuditLogs();
        } catch (err) {
            api.toast(`Failed to clear audit trail: ${err.message}`, "error");
        }
    },

    async executeCleanProductionData() {
        const btn = document.getElementById('btn-confirm-clean-prod-data');
        if (btn) {
            btn.disabled = true;
            btn.textContent = "Cleaning...";
        }

        try {
            const res = await api.post('/employees/clean-production-data', {});
            app.closeModal('modal-clean-prod-data');
            api.toast(res.message || "Production cleanup complete! Customer 7814749816 is preserved.", "success");
            
            await this.loadAdminData();
            if (typeof customer !== 'undefined') {
                customer.loadCustomers();
            }
            app.refreshDashboard();
            app.loadCallsView();
        } catch (err) {
            api.toast(`Cleanup failed: ${err.message}`, "error");
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.textContent = "Yes, Clean Test Data";
            }
        }
    }
};

window.admin = admin;
