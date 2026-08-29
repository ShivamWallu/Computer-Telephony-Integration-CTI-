/**
 * Follow-up Tasks and Pipeline Manager with Individual Deletion Support
 */
const followups = {
    currentTab: 'all',
    pendingDeleteId: null,

    init() {
        // Tab switching
        document.querySelectorAll('[data-fu-tab]').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('[data-fu-tab]').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this.currentTab = btn.dataset.fuTab;
                this.loadFollowups();
            });
        });

        // Confirm Delete Button in Modal
        document.getElementById('btn-confirm-delete-fu')?.addEventListener('click', async () => {
            if (this.pendingDeleteId) {
                await this.executeDeleteFollowup(this.pendingDeleteId);
            }
        });
    },

    async loadFollowups() {
        const container = document.getElementById('followups-container');
        if (!container) return;

        container.innerHTML = `<p class="text-muted" style="padding: 1rem 0;">Loading follow-ups...</p>`;

        try {
            const data = await api.get(`/followups?filter_type=${this.currentTab}`);
            
            if (data.length === 0) {
                container.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 2rem;">No follow-up tasks in this queue.</div>`;
                return;
            }

            container.innerHTML = data.map(f => {
                const isOverdue = new Date(f.due_date) < new Date() && f.status !== 'Completed';
                const priorityColor = f.priority === 'Urgent' ? 'badge-danger' : (f.priority === 'High' ? 'badge-vip' : 'badge-standard');
                const dueStr = app.formatDateTime(f.due_date);
                const custName = f.customer?.party_name || f.customer?.name || 'Customer';
                const custCode = f.customer?.party_code || f.customer?.customer_id || '';
                const phone = f.customer?.phone_1 || f.customer?.mobile || '';
                
                return `
                    <div class="kpi-card" style="align-items: center; ${isOverdue ? 'border-left: 4px solid var(--danger);' : ''}">
                        <div style="display: flex; align-items: center; gap: 0.75rem; flex: 1;">
                            <input type="checkbox" ${f.status === 'Completed' ? 'checked' : ''} onchange="followups.toggleComplete(${f.id}, this.checked)" style="width: 16px; height: 16px; cursor: pointer; accent-color: var(--primary);" title="Toggle Complete" />
                            <div>
                                <div style="font-weight: 600; font-size: 0.875rem; color: var(--text-primary); text-decoration: ${f.status === 'Completed' ? 'line-through' : 'none'};">
                                    ${f.title}
                                </div>
                                <div style="font-size: 0.75rem; color: var(--text-muted); display: flex; gap: 0.75rem; margin-top: 0.2rem; flex-wrap: wrap;">
                                    <span>${custName} ${custCode ? `(${custCode})` : ''}</span>
                                    <span>Due: <strong>${dueStr}</strong></span>
                                    ${isOverdue ? '<span class="badge badge-overdue">OVERDUE</span>' : ''}
                                </div>
                            </div>
                        </div>

                        <div style="display: flex; align-items: center; gap: 0.35rem; flex-wrap: wrap;">
                            <span class="badge ${priorityColor}">${f.priority}</span>
                            <span class="badge ${f.status === 'Completed' ? 'badge-active' : 'badge-standard'}">${f.status}</span>
                            ${f.customer ? `
                                <button class="btn btn-secondary btn-xs" onclick="customer.openDrawer(${f.customer_id})">
                                    ${Icons.get('user', { size: 12 })}
                                    <span>Profile</span>
                                </button>
                                ${phone ? `
                                    <button class="btn btn-secondary btn-xs" onclick="cti.makeOutgoingCall('${phone}', ${f.customer_id})" style="color: var(--primary); font-weight: 600;">
                                        ${Icons.get('phone', { size: 12 })}
                                        <span>Call</span>
                                    </button>
                                ` : ''}
                            ` : ''}
                            <button class="btn btn-secondary btn-xs" onclick="followups.openDeleteModal(${f.id}, '${f.title.replace(/'/g, "\\'")}')" title="Delete Follow-up" style="color: var(--danger);">
                                ${Icons.get('trash', { size: 12 })}
                            </button>
                        </div>
                    </div>
                `;
            }).join('');

        } catch (err) {
            console.error("Error loading follow-ups:", err);
            container.innerHTML = `<p style="color: var(--danger);">Failed to load follow-ups.</p>`;
        }
    },

    openDeleteModal(followupId, title) {
        this.pendingDeleteId = followupId;
        const titleEl = document.getElementById('modal-delete-fu-title');
        if (titleEl) titleEl.textContent = `"${title}"`;
        app.openModal('modal-delete-followup');
    },

    async executeDeleteFollowup(followupId) {
        try {
            const res = await api.delete(`/followups/${followupId}`);
            app.closeModal('modal-delete-followup');
            api.toast(res.message || "Follow-up task deleted successfully!", "success");
            this.pendingDeleteId = null;
            this.loadFollowups();
            app.refreshDashboard();
            if (customer.currentCustomerId) {
                customer.loadTimeline(customer.currentCustomerId, customer.currentTimelineFilter);
            }
        } catch (err) {
            api.toast(`Error deleting follow-up: ${err.message}`, "error");
        }
    },

    async toggleComplete(followupId, isCompleted) {
        try {
            await api.put(`/followups/${followupId}`, {
                status: isCompleted ? 'Completed' : 'Pending'
            });
            api.toast(isCompleted ? "Follow-up marked completed!" : "Follow-up reopened", "success");
            this.loadFollowups();
            app.refreshDashboard();
        } catch (err) {
            api.toast(`Error updating task: ${err.message}`, "error");
        }
    }
};

window.followups = followups;
