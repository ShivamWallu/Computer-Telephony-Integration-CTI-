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

    },

    async loadAdminData() {
        await Promise.all([
            this.loadTeamTable(),
            this.loadAuditLogs(),
            this.populateEmployeeDropdown(),
            this.refreshSidebarStats(),
            app.loadSmartfloTokenTable ? app.loadSmartfloTokenTable() : Promise.resolve()
        ]);
    },

    async refreshSidebarStats() {
        try {
            const stats = await api.get('/employees/assignment-stats');
            const totalBadge = document.getElementById('admin-sidebar-total-badge');
            if (totalBadge) totalBadge.textContent = `${(stats.total_customers || 0).toLocaleString()} Total`;

            const unassignedCount = document.getElementById('admin-sidebar-unassigned-count');
            if (unassignedCount) unassignedCount.textContent = (stats.unassigned_customers || 0).toLocaleString();

            const assignedTotal = (stats.total_customers || 0) - (stats.unassigned_customers || 0);
            const assignedCount = document.getElementById('admin-sidebar-assigned-count');
            if (assignedCount) assignedCount.textContent = Math.max(0, assignedTotal).toLocaleString();
        } catch (err) {
            console.error("Failed to load sidebar assignment stats:", err);
        }
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
            const allCustomersCount = stats.kpis?.total_customers ?? 0;
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
                        <div style="display: flex; align-items: center; gap: 0.65rem;">
                            <div class="user-avatar" style="width: 32px; height: 32px; font-size: 0.78rem; font-weight: 700; flex-shrink: 0; background: ${emp.role === 'admin' ? 'linear-gradient(135deg, var(--primary), #818cf8)' : 'var(--bg-surface-elevated)'}; color: ${emp.role === 'admin' ? '#fff' : 'var(--text-primary)'}; border: 1.5px solid var(--border-color);">
                                ${initials}
                            </div>
                            <div style="min-width: 0;">
                                <div style="font-weight: 700; font-size: 0.875rem; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${emp.full_name || 'Unnamed'}</div>
                                <div style="font-size: 0.75rem; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${emp.email}</div>
                            </div>
                        </div>
                    </td>
                    <td>
                        <span style="font-family: monospace; font-size: 0.8125rem; font-weight: 600; color: var(--text-secondary); white-space: nowrap;">${phone}</span>
                    </td>
                    <td>
                        <span class="badge badge-standard" style="font-size: 0.75rem; font-weight: 600; white-space: nowrap;">
                            ${allowedCid}
                        </span>
                    </td>
                    <td>
                        <span class="badge ${desig === 'Director' ? 'badge-vip' : 'badge-standard'}" style="font-size: 0.75rem; font-weight: 600; white-space: nowrap;">
                            ${desig}
                        </span>
                    </td>
                    <td>
                        <span class="badge ${emp.role === 'admin' ? 'badge-vip' : 'badge-standard'}" style="font-size: 0.72rem; font-weight: 700; white-space: nowrap;">${(emp.role || 'employee').toUpperCase()}</span>
                    </td>
                    <td style="font-weight: 700; font-size: 0.875rem; color: var(--primary); text-align: center;">${emp.customers_count ?? 0}</td>
                    <td style="font-weight: 700; font-size: 0.875rem; color: var(--success); text-align: center;">${emp.calls_logged ?? 0}</td>
                    <td style="font-weight: 700; font-size: 0.875rem; color: var(--purple); text-align: center;">${emp.followups_count ?? emp.followups_completed ?? 0}</td>
                    <td style="text-align: center; white-space: nowrap;">
                        ${isAdmin && !isSelf ? `
                            <button class="btn btn-danger btn-xs" onclick="window.admin.openDeleteEmployeeModal(${empId}, '${safeName}')" title="Delete Member" style="font-size: 0.75rem; padding: 0.3rem 0.65rem; border-radius: 6px; display: inline-flex; align-items: center; gap: 4px; font-weight: 600;">
                                ${Icons.get('trash', { size: 12 })}
                                <span>Delete</span>
                            </button>
                        ` : `<span class="badge badge-standard" style="font-size: 0.72rem; color: var(--text-muted); font-weight: 600;">${isSelf ? 'Admin (You)' : 'Active'}</span>`}
                    </td>
                </tr>
            `}).join('');

        } catch (err) {
            console.error("Team table error:", err);
            tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--danger);">Failed to load team data.</td></tr>`;
        }
    },

    escapeHtml(str) {
        if (str === null || str === undefined) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    },

    handleScopeChange(val) {
        const container = document.getElementById('container-reassign-individual');
        const isSelected = val === 'selected' || val === 'individual';
        if (container) {
            container.style.display = isSelected ? 'block' : 'none';
        }
        if (isSelected) {
            this.populateCustomerChecklist();
        }
    },

    async populateEmployeeDropdown() {
        const sel = document.getElementById('reassign-target-employee');
        const matrixTargetSel = document.getElementById('reassign-matrix-target-employee');
        const matrixFilterSel = document.getElementById('reassign-matrix-filter-agent');
        const checklistFilterSel = document.getElementById('reassign-checklist-filter-agent');

        try {
            const rawEmployees = await api.get('/employees');
            const employees = (rawEmployees || []).filter(e => (e.role || '').toLowerCase() === 'employee');
            const empOptions = `
                <option value="0">All Employees (Shared Pool / Universal Access)</option>
                ${employees.map(e => `
                    <option value="${e.id}">${this.escapeHtml(e.full_name)} (${(e.role || 'Staff').toUpperCase()})</option>
                `).join('')}
            `;

            if (sel) sel.innerHTML = empOptions;
            if (matrixTargetSel) matrixTargetSel.innerHTML = empOptions;

            const filterOptions = `
                <option value="">All Allocation Pools</option>
                <option value="0">⚡ Unassigned Only</option>
                ${employees.map(e => `
                    <option value="${e.id}">${this.escapeHtml(e.full_name)} (${(e.role || 'Staff').toUpperCase()})</option>
                `).join('')}
            `;

            if (matrixFilterSel) matrixFilterSel.innerHTML = filterOptions;
            if (checklistFilterSel) checklistFilterSel.innerHTML = `
                <option value="">All Agents</option>
                <option value="0">Unassigned</option>
                ${employees.map(e => `<option value="${e.id}">${this.escapeHtml(e.full_name)}</option>`).join('')}
            `;

        } catch (err) {
            console.error("Could not populate employee dropdown:", err);
        }
    },

    async populateCustomerChecklist() {
        const container = document.getElementById('reassign-customer-checklist');
        if (!container) return;

        try {
            const custRes = await api.get('/customers?limit=300');
            if (custRes && custRes.items) {
                this.cachedChecklistCustomers = custRes.items;
                this.renderInlineChecklist(custRes.items);
            }
        } catch (err) {
            console.error("Could not populate customer checklist:", err);
            container.innerHTML = `<span style="color: var(--danger); font-size: 0.8rem;">Failed to load customers list.</span>`;
        }
    },

    renderInlineChecklist(items) {
        const container = document.getElementById('reassign-customer-checklist');
        if (!container) return;

        if (!items || items.length === 0) {
            container.innerHTML = `<span style="color: var(--text-muted); font-size: 0.75rem; text-align: center; padding: 0.5rem;">No matching customers found.</span>`;
            return;
        }

        container.innerHTML = items.map(c => {
            const assignedName = c.assigned_employee?.full_name || 'Unassigned';
            const name = c.party_name || c.name || 'Customer';
            const phone = c.phone_1 || c.mobile || '';
            const partyCode = c.party_code || '';
            return `
            <label class="reassign-inline-item" data-name="${this.escapeHtml(name).toLowerCase()}" data-code="${this.escapeHtml(partyCode).toLowerCase()}" data-phone="${this.escapeHtml(phone)}" data-agent="${c.assigned_employee_id || 0}" style="display: flex; align-items: center; gap: 0.5rem; font-size: 0.8125rem; cursor: pointer; padding: 0.25rem 0.4rem; border-radius: var(--radius-xs); transition: background 0.15s ease;" onmouseover="this.style.background='var(--bg-surface-hover)'" onmouseout="this.style.background='transparent'">
                <input type="checkbox" class="reassign-cust-check" value="${c.id}" style="width: 15px; height: 15px; accent-color: var(--primary); cursor: pointer;" />
                <span style="font-weight: 600; color: var(--text-primary); font-size: 0.78rem;">${this.escapeHtml(name)}</span>
                <span style="color: var(--text-muted); font-size: 0.7rem;">(${this.escapeHtml(phone)})</span>
                <span style="margin-left: auto; font-size: 0.65rem;" class="badge ${c.assigned_employee_id ? 'badge-standard' : 'badge-lead'}">${this.escapeHtml(assignedName)}</span>
            </label>
            `;
        }).join('');
    },

    filterInlineChecklist() {
        const search = (document.getElementById('reassign-checklist-search')?.value || '').trim().toLowerCase();
        const agent = document.getElementById('reassign-checklist-filter-agent')?.value;
        const items = document.querySelectorAll('.reassign-inline-item');

        items.forEach(el => {
            const name = el.getAttribute('data-name') || '';
            const code = el.getAttribute('data-code') || '';
            const phone = el.getAttribute('data-phone') || '';
            const elAgent = el.getAttribute('data-agent') || '0';

            const matchSearch = !search || name.includes(search) || code.includes(search) || phone.includes(search);
            const matchAgent = !agent || (agent === '0' ? elAgent === '0' : elAgent === agent);

            el.style.display = (matchSearch && matchAgent) ? 'flex' : 'none';
        });
    },

    async executeReassignment() {
        const rawTargetId = document.getElementById('reassign-target-employee')?.value;
        const targetId = parseInt(rawTargetId);
        const scope = document.getElementById('reassign-scope')?.value || 'all';

        let payload = {
            target_employee_id: (isNaN(targetId) || targetId === 0) ? null : targetId,
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

            api.toast(res.message || `Successfully assigned customers to ${res.assigned_to}!`, "success");

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
            api.toast(`Reassignment failed: ${err.message}`, "error");
        }
    },

    // ── LARGE MULTI-SELECT REASSIGNMENT MATRIX SYSTEM ─────────────────────────

    matrixSelectedCustomerIds: new Set(),
    matrixCurrentPage: 1,
    matrixLimit: 50,
    matrixSearchTimer: null,
    matrixCachedStats: null,
    cachedChecklistCustomers: [],

    async openReassignmentMatrixModal() {
        app.openModal('modal-customer-reassignment-matrix');
        await this.populateEmployeeDropdown();
        await this.refreshReassignMatrixStats();
        this.matrixCurrentPage = 1;
        await this.loadReassignCustomersTable();
    },

    async refreshReassignMatrixStats() {
        try {
            const stats = await api.get('/employees/assignment-stats');
            this.matrixCachedStats = stats;
            this.renderReassignEmployeePills(stats);

            const totalBadge = document.getElementById('reassign-matrix-badge-total');
            if (totalBadge) totalBadge.textContent = `${(stats.total_customers || 0).toLocaleString()} Total`;

            const unassignedBadge = document.getElementById('reassign-matrix-badge-unassigned');
            if (unassignedBadge) unassignedBadge.textContent = `Unassigned: ${(stats.unassigned_customers || 0).toLocaleString()}`;

        } catch (err) {
            console.error("Failed to load assignment stats:", err);
        }
    },

    renderReassignEmployeePills(stats) {
        const container = document.getElementById('reassign-matrix-emp-pills');
        if (!container || !stats) return;

        const currentAgentFilter = document.getElementById('reassign-matrix-filter-agent')?.value || '';
        const isAllActive = currentAgentFilter === '';
        const isUnassignedActive = currentAgentFilter === '0';

        const pills = [];

        // All Customers pill
        pills.push(`
            <button type="button" class="btn btn-xs ${isAllActive ? 'btn-primary' : 'btn-secondary'}" onclick="admin.filterMatrixByAgent('')" style="display: inline-flex; align-items: center; gap: 6px; border-radius: var(--radius-full); font-weight: 600; padding: 0.3rem 0.75rem;">
                <span style="display: inline-flex; align-items: center; gap: 4px;">${Icons.get('users', { size: 12 })} All Customers</span>
                <span class="badge" style="background: rgba(255,255,255,0.25); color: inherit; padding: 1px 6px; font-size: 0.7rem;">${stats.total_customers || 0}</span>
            </button>
        `);

        // Unassigned pill
        pills.push(`
            <button type="button" class="btn btn-xs ${isUnassignedActive ? 'btn-warning' : 'btn-secondary'}" onclick="admin.filterMatrixByAgent('0')" style="display: inline-flex; align-items: center; gap: 6px; border-radius: var(--radius-full); font-weight: 600; padding: 0.3rem 0.75rem; border-color: rgba(245,158,11,0.4);">
                <span style="display: inline-flex; align-items: center; gap: 4px;">${Icons.get('inbox', { size: 12 })} Unassigned / Shared</span>
                <span class="badge" style="background: rgba(245,158,11,0.25); color: #D97706; padding: 1px 6px; font-size: 0.7rem;">${stats.unassigned_customers || 0}</span>
            </button>
        `);

        // Each Employee pill
        (stats.employees || []).forEach(emp => {
            const isEmpActive = String(currentAgentFilter) === String(emp.employee_id);
            const initials = (emp.full_name || 'U').split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
            pills.push(`
                <button type="button" class="btn btn-xs ${isEmpActive ? 'btn-primary' : 'btn-secondary'}" onclick="admin.filterMatrixByAgent('${emp.employee_id}')" style="display: inline-flex; align-items: center; gap: 5px; border-radius: var(--radius-full); padding: 0.25rem 0.65rem;">
                    <span style="width: 18px; height: 18px; border-radius: 50%; background: var(--primary-subtle); color: var(--primary); font-size: 0.65rem; display: inline-flex; align-items: center; justify-content: center; font-weight: 700;">${initials}</span>
                    <span style="font-weight: 600;">${this.escapeHtml(emp.full_name)}</span>
                    <span class="badge badge-standard" style="padding: 1px 6px; font-size: 0.7rem; font-weight: 700; color: var(--primary);">${emp.assigned_count || 0}</span>
                </button>
            `);
        });

        container.innerHTML = pills.join('');
    },

    filterMatrixByAgent(agentId) {
        const select = document.getElementById('reassign-matrix-filter-agent');
        if (select) select.value = agentId;
        this.handleMatrixFilterChange();
    },

    handleMatrixSearchDebounced() {
        clearTimeout(this.matrixSearchTimer);
        this.matrixSearchTimer = setTimeout(() => {
            this.matrixCurrentPage = 1;
            this.loadReassignCustomersTable();
        }, 250);
    },

    handleMatrixFilterChange() {
        this.matrixCurrentPage = 1;
        if (this.matrixCachedStats) {
            this.renderReassignEmployeePills(this.matrixCachedStats);
        }
        this.loadReassignCustomersTable();
    },

    resetMatrixFilters() {
        const searchInput = document.getElementById('reassign-matrix-search');
        if (searchInput) searchInput.value = '';
        const agentSel = document.getElementById('reassign-matrix-filter-agent');
        if (agentSel) agentSel.value = '';
        const statusSel = document.getElementById('reassign-matrix-filter-status');
        if (statusSel) statusSel.value = '';
        const catSel = document.getElementById('reassign-matrix-filter-category');
        if (catSel) catSel.value = '';

        this.matrixCurrentPage = 1;
        if (this.matrixCachedStats) {
            this.renderReassignEmployeePills(this.matrixCachedStats);
        }
        this.loadReassignCustomersTable();
    },

    handleMatrixLimitChange(val) {
        this.matrixLimit = parseInt(val, 10) || 50;
        this.matrixCurrentPage = 1;
        this.loadReassignCustomersTable();
    },

    handleMatrixPrevPage() {
        if (this.matrixCurrentPage > 1) {
            this.matrixCurrentPage--;
            this.loadReassignCustomersTable();
        }
    },

    handleMatrixNextPage() {
        this.matrixCurrentPage++;
        this.loadReassignCustomersTable();
    },

    async loadReassignCustomersTable() {
        const tbody = document.getElementById('reassign-matrix-table-body');
        if (!tbody) return;

        tbody.innerHTML = Array.from({ length: 6 }).map(() => `
            <tr class="skeleton-row">
                <td style="text-align: center;"><div class="skeleton" style="width: 16px; height: 16px; margin: 0 auto;"></div></td>
                <td><div class="skeleton" style="width: 80px; height: 14px;"></div></td>
                <td><div class="skeleton" style="width: 140px; height: 14px;"></div></td>
                <td><div class="skeleton" style="width: 110px; height: 14px;"></div></td>
                <td><div class="skeleton" style="width: 100px; height: 14px;"></div></td>
                <td><div class="skeleton" style="width: 90px; height: 14px;"></div></td>
                <td><div class="skeleton" style="width: 60px; height: 18px; border-radius: 10px;"></div></td>
                <td><div class="skeleton" style="width: 120px; height: 14px;"></div></td>
            </tr>
        `).join('');

        const search = (document.getElementById('reassign-matrix-search')?.value || '').trim();
        const agentId = document.getElementById('reassign-matrix-filter-agent')?.value;
        const status = document.getElementById('reassign-matrix-filter-status')?.value;
        const category = document.getElementById('reassign-matrix-filter-category')?.value;

        try {
            let url = `/customers?page=${this.matrixCurrentPage}&limit=${this.matrixLimit}`;
            if (search) url += `&search=${encodeURIComponent(search)}`;
            if (status) url += `&status=${encodeURIComponent(status)}`;
            if (agentId !== undefined && agentId !== null && agentId !== '') {
                url += `&assigned_employee_id=${encodeURIComponent(agentId)}`;
            }

            const data = await api.get(url);

            // Filter by category in client if present
            let items = data.items || [];
            if (category) {
                items = items.filter(c => (c.category || 'Regular') === category);
            }

            const total = data.total || 0;
            const totalPages = data.total_pages || 1;
            const startNum = items.length > 0 ? ((this.matrixCurrentPage - 1) * this.matrixLimit + 1) : 0;
            const endNum = Math.min(this.matrixCurrentPage * this.matrixLimit, total);

            const paginationInfo = document.getElementById('reassign-matrix-pagination-info');
            if (paginationInfo) {
                paginationInfo.textContent = `Showing ${startNum} to ${endNum} of ${total.toLocaleString()} customers (Page ${this.matrixCurrentPage} of ${totalPages})`;
            }

            const pageIndicator = document.getElementById('reassign-matrix-page-indicator');
            if (pageIndicator) pageIndicator.textContent = `Page ${this.matrixCurrentPage} / ${totalPages}`;

            const btnPrev = document.getElementById('reassign-matrix-btn-prev');
            if (btnPrev) btnPrev.disabled = this.matrixCurrentPage <= 1;

            const btnNext = document.getElementById('reassign-matrix-btn-next');
            if (btnNext) btnNext.disabled = this.matrixCurrentPage >= totalPages;

            if (items.length === 0) {
                tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-muted); padding: 3rem;">No customers match the selected matrix filters.</td></tr>`;
                this.updateMatrixSelectionCounters();
                return;
            }

            tbody.innerHTML = items.map(c => {
                const isSelected = this.matrixSelectedCustomerIds.has(c.id);
                const isStaffAssigned = c.assigned_employee && (c.assigned_employee.role || '').toLowerCase() === 'employee';
                const assignedName = isStaffAssigned ? c.assigned_employee.full_name : 'Unassigned / Shared Pool';
                const assignedClass = isStaffAssigned ? 'badge-standard' : 'badge-lead';
                const statusClass = c.status === 'Active' ? 'badge-active' : (c.status === 'Lead' ? 'badge-lead' : 'badge-standard');
                const location = [c.city, c.state].filter(Boolean).join(', ') || '—';
                const partyCode = c.party_code || c.customer_id || '—';
                const partyName = c.party_name || c.name || '—';
                const phone = c.phone_1 || c.mobile || '—';
                const contactPerson = c.contact_person_1 || '—';

                return `
                <tr style="cursor: pointer; background: ${isSelected ? 'rgba(99,102,241,0.08)' : 'transparent'};" onclick="admin.handleMatrixRowClick(event, ${c.id})">
                    <td style="text-align: center;" onclick="event.stopPropagation();">
                        <input type="checkbox" class="matrix-row-checkbox" value="${c.id}" ${isSelected ? 'checked' : ''} onchange="admin.handleMatrixRowCheck(${c.id}, this.checked)" style="width: 16px; height: 16px; accent-color: var(--primary); cursor: pointer;" />
                    </td>
                    <td><span class="badge badge-standard">${this.escapeHtml(partyCode)}</span></td>
                    <td>
                        <div style="font-weight: 600; color: var(--text-primary);">${this.escapeHtml(partyName)}</div>
                    </td>
                    <td><span style="color: var(--text-secondary); font-size: 0.8125rem;">${this.escapeHtml(contactPerson)}</span></td>
                    <td><span style="font-weight: 600; color: var(--primary); font-variant-numeric: tabular-nums;">${this.escapeHtml(phone)}</span></td>
                    <td><span style="font-size: 0.78rem; color: var(--text-secondary);">${this.escapeHtml(location)}</span></td>
                    <td><span class="badge ${statusClass}">${this.escapeHtml(c.status)}</span></td>
                    <td>
                        <span class="badge ${assignedClass}" style="font-size: 0.75rem; font-weight: 600;">
                            ${this.escapeHtml(assignedName)}
                        </span>
                    </td>
                </tr>
                `;
            }).join('');

            this.updateMatrixSelectionCounters();

        } catch (err) {
            console.error("Matrix load table error:", err);
            tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--danger); padding: 2rem;">Failed to load customers for assignment matrix: ${err.message}</td></tr>`;
        }
    },

    handleMatrixRowClick(event, id) {
        // Toggle selection on row click if user didn't click on an interactive element
        const checkbox = document.querySelector(`.matrix-row-checkbox[value="${id}"]`);
        if (checkbox) {
            checkbox.checked = !checkbox.checked;
            this.handleMatrixRowCheck(id, checkbox.checked);
        }
    },

    handleMatrixRowCheck(id, checked) {
        if (checked) {
            this.matrixSelectedCustomerIds.add(id);
        } else {
            this.matrixSelectedCustomerIds.delete(id);
        }

        // Highlight row styling
        const checkbox = document.querySelector(`.matrix-row-checkbox[value="${id}"]`);
        if (checkbox && checkbox.closest('tr')) {
            checkbox.closest('tr').style.background = checked ? 'rgba(99,102,241,0.08)' : 'transparent';
        }

        this.updateMatrixSelectionCounters();
    },

    handleMatrixMasterCheck(checked) {
        const checkboxes = document.querySelectorAll('.matrix-row-checkbox');
        checkboxes.forEach(cb => {
            cb.checked = checked;
            const id = parseInt(cb.value, 10);
            if (checked) {
                this.matrixSelectedCustomerIds.add(id);
            } else {
                this.matrixSelectedCustomerIds.delete(id);
            }
            if (cb.closest('tr')) {
                cb.closest('tr').style.background = checked ? 'rgba(99,102,241,0.08)' : 'transparent';
            }
        });
        this.updateMatrixSelectionCounters();
    },

    toggleMatrixSelectCurrentPage(select) {
        const masterCheck = document.getElementById('reassign-matrix-master-check');
        if (masterCheck) masterCheck.checked = select;
        this.handleMatrixMasterCheck(select);
    },

    clearAllMatrixSelections() {
        this.matrixSelectedCustomerIds.clear();
        const checkboxes = document.querySelectorAll('.matrix-row-checkbox');
        checkboxes.forEach(cb => {
            cb.checked = false;
            if (cb.closest('tr')) cb.closest('tr').style.background = 'transparent';
        });
        const masterCheck = document.getElementById('reassign-matrix-master-check');
        if (masterCheck) masterCheck.checked = false;
        this.updateMatrixSelectionCounters();
    },

    updateMatrixSelectionCounters() {
        const count = this.matrixSelectedCustomerIds.size;

        const badgeSelected = document.getElementById('reassign-matrix-badge-selected');
        if (badgeSelected) badgeSelected.textContent = `Selected: ${count.toLocaleString()}`;

        const footerCount = document.getElementById('reassign-matrix-footer-selected-count');
        if (footerCount) footerCount.textContent = count.toLocaleString();

        // Master check state
        const checkboxes = document.querySelectorAll('.matrix-row-checkbox');
        const masterCheck = document.getElementById('reassign-matrix-master-check');
        if (masterCheck && checkboxes.length > 0) {
            const checkedCount = [...checkboxes].filter(cb => cb.checked).length;
            masterCheck.checked = checkedCount === checkboxes.length;
            masterCheck.indeterminate = checkedCount > 0 && checkedCount < checkboxes.length;
        }
    },

    async executeMatrixReassignment() {
        const selectedIds = Array.from(this.matrixSelectedCustomerIds);
        if (selectedIds.length === 0) {
            api.toast("Please select at least one customer from the matrix to assign.", "error");
            return;
        }

        const rawTargetId = document.getElementById('reassign-matrix-target-employee')?.value;
        const targetId = parseInt(rawTargetId, 10);
        const targetEmployeeId = (isNaN(targetId) || targetId === 0) ? null : targetId;

        const btn = document.getElementById('btn-execute-matrix-reassign');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = `<span class="spinner-sm"></span> Assigning ${selectedIds.length} Customers...`;
        }

        try {
            const payload = {
                customer_ids: selectedIds,
                target_employee_id: targetEmployeeId,
                reassign_scope: 'selected'
            };

            const res = await api.post('/employees/reassign-customers', payload);

            api.toast(res.message || `Successfully assigned ${selectedIds.length} customers to ${res.assigned_to}!`, "success");

            // Clear selection and refresh matrix & team data
            this.matrixSelectedCustomerIds.clear();
            await this.refreshReassignMatrixStats();
            await this.refreshSidebarStats();
            await this.loadReassignCustomersTable();
            await this.loadTeamTable();
            if (typeof customer !== 'undefined') {
                customer.loadCustomers();
            }
            app.refreshDashboard();

        } catch (err) {
            api.toast(`Assignment failed: ${err.message}`, "error");
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = `<svg class="icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg><span>Execute Reassignment</span>`;
            }
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
                <tr class="audit-row" data-user="${userName.toLowerCase()}" data-email="${userEmail.toLowerCase()}" data-action="${actionLabel.toLowerCase()}" data-entity="${(l.entity_type || '').toLowerCase()}" data-details="${detailsText.toLowerCase()}">
                    <td>
                        <span style="font-size: 0.75rem; color: var(--text-secondary); font-variant-numeric: tabular-nums; white-space: nowrap;">
                            ${app.formatDateTime(l.created_at)}
                        </span>
                    </td>
                    <td>
                        <div style="display: flex; align-items: center; gap: 0.5rem;">
                            <div style="width: 26px; height: 26px; border-radius: 50%; background: var(--primary-subtle); color: var(--primary); display: flex; align-items: center; justify-content: center; font-size: 0.75rem; font-weight: 700; flex-shrink: 0;">
                                ${initials}
                            </div>
                            <div>
                                <strong style="color: var(--text-primary); font-size: 0.875rem;">${userName}</strong>
                                ${userEmail ? `<div style="font-size: 0.75rem; color: var(--text-muted); line-height: 1.2;">${userEmail}</div>` : ''}
                            </div>
                        </div>
                    </td>
                    <td>
                        <span class="badge ${roleBadgeClass}" style="font-size: 0.75rem; font-weight: 600; padding: 0.15rem 0.5rem;">
                            ${userRole}
                        </span>
                    </td>
                    <td>
                        <span class="badge ${badgeClass}" style="font-size: 0.75rem; font-weight: 600;">
                            ${actionLabel}
                        </span>
                    </td>
                    <td>
                        <span style="font-size: 0.8125rem; font-weight: 500; color: var(--text-primary);">
                            ${(l.entity_type || '').toUpperCase()} ${l.entity_id ? `(#${l.entity_id})` : ''}
                        </span>
                    </td>
                    <td>
                        <span class="badge badge-active" style="font-size: 0.75rem; font-weight: 600;">
                            ${status}
                        </span>
                    </td>
                    <td style="font-size: 0.78rem; color: var(--text-muted); max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${detailsText}">
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
            const details = row.getAttribute('data-details') || '';
            if (user.includes(query) || email.includes(query) || action.includes(query) || entity.includes(query) || details.includes(query)) {
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

    async openPermissionsModal(empId, empName) {
        try {
            const emp = await api.get(`/employees/${empId}`);
            document.getElementById('modal-perm-emp-id').value = empId;
            document.getElementById('modal-perm-emp-name').textContent = emp.full_name || empName;
            document.getElementById('modal-perm-emp-email').textContent = emp.email || '';
            document.getElementById('modal-perm-emp-subtitle').textContent = `Configuring permissions for ${emp.full_name || empName} (ID: #${empId})`;
            const roleBadge = document.getElementById('modal-perm-emp-role-badge');
            if (roleBadge) {
                roleBadge.textContent = (emp.role || 'employee').toUpperCase();
                roleBadge.className = `badge ${emp.role === 'admin' ? 'badge-vip' : 'badge-standard'}`;
            }

            // Categories checkboxes
            const allowedCats = (emp.allowed_categories || '*').split(',').map(s => s.trim());
            const isAll = allowedCats.includes('*');
            document.querySelectorAll('.chk-emp-cat').forEach(cb => {
                cb.checked = isAll || allowedCats.includes(cb.value);
            });

            // Feature checkboxes
            const setCheck = (id, val) => {
                const el = document.getElementById(id);
                if (el) el.checked = val !== false;
            };

            setCheck('chk-perm-add-customer', emp.can_add_customer);
            setCheck('chk-perm-edit-customer', emp.can_edit_customer);
            setCheck('chk-perm-delete-customer', emp.can_delete_customer);
            setCheck('chk-perm-rate-customer', emp.can_rate_customer);
            setCheck('chk-perm-make-calls', emp.can_make_calls);
            setCheck('chk-perm-listen-recordings', emp.can_listen_recordings);
            setCheck('chk-perm-export-data', emp.can_export_data);
            setCheck('chk-perm-view-unassigned', emp.can_view_unassigned);

            app.openModal('modal-employee-permissions');
        } catch (err) {
            api.toast(`Failed to load employee details: ${err.message}`, "error");
        }
    },

    toggleAllCategoryCheckboxes() {
        const cbs = document.querySelectorAll('.chk-emp-cat');
        const anyUnchecked = Array.from(cbs).some(cb => !cb.checked);
        cbs.forEach(cb => cb.checked = anyUnchecked);
    },

    async saveEmployeePermissions() {
        const empId = document.getElementById('modal-perm-emp-id')?.value;
        if (!empId) return;

        // Collect checked categories
        const checkedCats = [];
        document.querySelectorAll('.chk-emp-cat:checked').forEach(cb => {
            checkedCats.push(cb.value);
        });

        const totalCats = document.querySelectorAll('.chk-emp-cat').length;
        const allowed_categories = (checkedCats.length === totalCats || checkedCats.length === 0)
            ? '*'
            : checkedCats.join(',');

        const payload = {
            allowed_categories: allowed_categories,
            can_add_customer: document.getElementById('chk-perm-add-customer')?.checked ?? true,
            can_edit_customer: document.getElementById('chk-perm-edit-customer')?.checked ?? true,
            can_delete_customer: document.getElementById('chk-perm-delete-customer')?.checked ?? false,
            can_rate_customer: document.getElementById('chk-perm-rate-customer')?.checked ?? true,
            can_make_calls: document.getElementById('chk-perm-make-calls')?.checked ?? true,
            can_listen_recordings: document.getElementById('chk-perm-listen-recordings')?.checked ?? true,
            can_export_data: document.getElementById('chk-perm-export-data')?.checked ?? true,
            can_view_unassigned: document.getElementById('chk-perm-view-unassigned')?.checked ?? true
        };

        try {
            const res = await api.put(`/employees/${empId}/permissions`, payload);
            app.closeModal('modal-employee-permissions');
            api.toast(res.message || "Employee permissions saved successfully!", "success");

            // If editing own permissions, update current user cache
            const currUser = api.getCurrentUser();
            if (currUser && currUser.id == empId) {
                Object.assign(currUser, payload);
                api.setCurrentUser(currUser);
            }

            await this.loadTeamTable();
        } catch (err) {
            api.toast(`Failed to update permissions: ${err.message}`, "error");
        }
    },

    currentPurgeScope: 'ALL',
    currentExpectedPurgeCode: 'DELETE-ALL',

    async openPurgeCustomersModal(initialCategory = 'ALL') {
        const select = document.getElementById('inp-purge-category-scope');
        if (select) {
            select.value = initialCategory || 'ALL';
        }
        const input = document.getElementById('inp-purge-confirm-text');
        if (input) input.value = '';

        await this.handlePurgeScopeChange(initialCategory || 'ALL');
        app.openModal('modal-purge-customers');
    },

    async handlePurgeScopeChange(categoryVal) {
        this.currentPurgeScope = categoryVal || 'ALL';
        const isAll = !categoryVal || categoryVal === 'ALL';
        const normTag = isAll ? 'ALL' : categoryVal.toUpperCase().replace(/\s+/g, '-');
        this.currentExpectedPurgeCode = `DELETE-${normTag}`;

        // Update UI elements
        const codeEl = document.getElementById('purge-expected-code');
        const input = document.getElementById('inp-purge-confirm-text');
        const badge = document.getElementById('purge-target-badge');
        const btnText = document.getElementById('btn-purge-text');
        const countEl = document.getElementById('purge-target-count');

        if (codeEl) codeEl.textContent = this.currentExpectedPurgeCode;
        if (input) {
            input.placeholder = this.currentExpectedPurgeCode;
            input.value = '';
        }
        if (badge) {
            badge.textContent = isAll ? 'ALL CATEGORIES' : `CATEGORY: ${categoryVal}`;
            badge.className = isAll ? 'badge badge-danger' : 'badge badge-warning';
        }
        if (btnText) {
            btnText.textContent = isAll ? 'Purge All Customers' : `Purge ${categoryVal} Data`;
        }
        if (countEl) countEl.textContent = '...';

        try {
            const param = isAll ? '' : `?category=${encodeURIComponent(categoryVal)}`;
            const preview = await api.get(`/customers/purge-preview${param}`);
            if (countEl) {
                const total = preview?.customer_count ?? 0;
                countEl.textContent = (window.app && typeof app.formatFullNumber === 'function') ? app.formatFullNumber(total) : total;
            }
        } catch (err) {
            console.error("Purge preview error:", err);
            if (countEl) countEl.textContent = '—';
        }
    },

    validatePurgeInput(val) {
        const btn = document.getElementById('btn-execute-purge-customers');
        if (!btn) return;
        const isMatch = (val || '').trim().toUpperCase() === this.currentExpectedPurgeCode.toUpperCase();
        btn.style.opacity = isMatch ? '1' : '0.7';
    },

    async executePurgeScopedCustomers() {
        const input = document.getElementById('inp-purge-confirm-text');
        const confirmPhrase = (input?.value || '').trim().toUpperCase();

        if (confirmPhrase !== this.currentExpectedPurgeCode.toUpperCase()) {
            api.toast(`Please type '${this.currentExpectedPurgeCode}' exactly to confirm deletion.`, "warning");
            return;
        }

        const isAll = this.currentPurgeScope === 'ALL';
        const btn = document.getElementById('btn-execute-purge-customers');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = `<span class="spinner-sm" style="border-top-color:#fff;"></span><span>Purging records...</span>`;
        }

        try {
            const catParam = isAll ? '' : `&category=${encodeURIComponent(this.currentPurgeScope)}`;
            const res = await api.delete(`/customers/purge-all?confirmation=${encodeURIComponent(confirmPhrase)}${catParam}`);

            app.closeModal('modal-purge-customers');
            if (input) input.value = '';

            const deletedCount = res?.purged_customers ?? res?.deleted_customers ?? 0;
            const successMsg = res?.message || `Successfully deleted ${deletedCount} customer accounts. Demo account preserved.`;
            api.toast(successMsg, "success", 5000);

            // Refresh UI tables & dashboards
            if (typeof customer !== 'undefined' && typeof customer.loadCustomers === 'function') {
                await customer.loadCustomers();
            }
            if (typeof intelligence !== 'undefined' && typeof intelligence.loadIntelligence === 'function') {
                await intelligence.loadIntelligence();
            }
            if (window.app && typeof app.refreshDashboard === 'function') {
                app.refreshDashboard();
            }
            if (typeof this.refreshSidebarStats === 'function') {
                await this.refreshSidebarStats();
            }
            if (typeof this.loadAuditLogs === 'function') {
                await this.loadAuditLogs();
            }
        } catch (err) {
            api.toast(`Failed to purge customer data: ${err.message}`, "error");
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg><span id="btn-purge-text">${isAll ? 'Purge All Customers' : `Purge ${this.currentPurgeScope} Data`}</span>`;
            }
        }
    }
};

window.admin = admin;
