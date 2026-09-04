/**
 * Customer Directory, Profile 360° Drawer, Edit Manager, and Unified Timeline (15 Columns Schema)
 */
const customer = {
    currentPage: 1,
    limit: 15,
    currentCustomerId: null,
    editingCustomerId: null,
    currentTimelineFilter: 'all',

    init() {
        // Customer Filter inputs
        const searchInput = document.getElementById('customers-filter-search');
        const statusSelect = document.getElementById('customers-filter-status');

        if (searchInput) {
            let timer;
            searchInput.addEventListener('input', () => {
                clearTimeout(timer);
                timer = setTimeout(() => {
                    this.currentPage = 1;
                    this.loadCustomers();
                }, 200);
            });
        }
        if (statusSelect) statusSelect.addEventListener('change', () => { this.currentPage = 1; this.loadCustomers(); });

        // Pagination buttons
        document.getElementById('btn-cust-prev')?.addEventListener('click', () => {
            if (this.currentPage > 1) {
                this.currentPage--;
                this.loadCustomers();
            }
        });
        document.getElementById('btn-cust-next')?.addEventListener('click', () => {
            this.currentPage++;
            this.loadCustomers();
        });

        // Drawer Sub-Tabs switching
        document.querySelectorAll('[data-drawer-tab]').forEach(btn => {
            btn.addEventListener('click', () => {
                const tab = btn.dataset.drawerTab;
                this.switchDrawerTab(tab);
            });
        });

        // Drawer Close Buttons (Known & New)
        document.getElementById('btn-close-drawer')?.addEventListener('click', () => {
            this.closeDrawer();
        });
        document.getElementById('btn-close-drawer-new')?.addEventListener('click', () => {
            this.closeDrawer();
        });
        document.getElementById('drawer-overlay')?.addEventListener('click', (e) => {
            if (e.target.id === 'drawer-overlay') this.closeDrawer();
        });

        // New / Unknown Customer Quick Register button
        document.getElementById('btn-drawer-quick-register')?.addEventListener('click', () => {
            const phone = this.currentUnregisteredPhone || '';
            this.openAddModal(phone);
        });

        // Timeline Filter Chips
        document.querySelectorAll('[data-timeline-filter]').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('[data-timeline-filter]').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this.currentTimelineFilter = btn.dataset.timelineFilter;
                if (this.currentCustomerId) {
                    this.loadTimeline(this.currentCustomerId, this.currentTimelineFilter);
                }
            });
        });

        // Add / Edit Customer Form Submit (Modal)
        document.getElementById('btn-submit-add-customer')?.addEventListener('click', (e) => {
            e.preventDefault();
            this.submitCustomerForm();
        });

        // Drawer Delete Customer Button (Admin Only)
        document.getElementById('btn-drawer-delete-customer')?.addEventListener('click', () => {
            if (this.currentCustomerId) this.openDeleteCustomerModal();
        });

        // Modal Confirm Delete Customer Action
        document.getElementById('btn-confirm-delete-cust')?.addEventListener('click', () => {
            if (this.currentCustomerId) this.executeDeleteCustomer();
        });
    },

    async switchDrawerTab(tabName) {
        // Toggle tab buttons
        document.querySelectorAll('.drawer-tab-btn').forEach(b => {
            if (b.dataset.drawerTab === tabName) b.classList.add('active');
            else b.classList.remove('active');
        });

        // Toggle tab panes
        document.querySelectorAll('.drawer-tab-pane').forEach(p => {
            p.classList.remove('active');
        });
        const targetPane = document.getElementById(`dtab-${tabName}`);
        if (targetPane) targetPane.classList.add('active');

        // Pre-fill fields depending on active tab
        if (tabName === 'edit' && this.currentCustomerData) {
            await this.populateAgentDropdown('dinp-assigned-agent');
            const c = this.currentCustomerData;
            document.getElementById('dinp-party-code').value = c.party_code || c.customer_id || '';
            document.getElementById('dinp-party-name').value = c.party_name || c.name || '';
            document.getElementById('dinp-address-date').value = c.address_date || '';
            document.getElementById('dinp-addr1').value = c.address_line_1 || c.address || '';
            document.getElementById('dinp-addr2').value = c.address_line_2 || '';
            document.getElementById('dinp-addr3').value = c.address_line_3 || '';
            document.getElementById('dinp-contact-person').value = c.contact_person_1 || '';
            document.getElementById('dinp-email').value = c.email_id_1 || c.email || '';
            document.getElementById('dinp-country').value = c.country || 'India';
            document.getElementById('dinp-state').value = c.state || '';
            document.getElementById('dinp-city').value = c.city || '';
            document.getElementById('dinp-pincode').value = c.pincode || '';
            document.getElementById('dinp-phone-type').value = c.phone_type_1 || 'Mobile';
            document.getElementById('dinp-phone1').value = c.phone_1 || c.mobile || '';
            document.getElementById('dinp-status').value = c.status || 'Active';
            if (c.assigned_employee_id) {
                document.getElementById('dinp-assigned-agent').value = c.assigned_employee_id;
            }
        } else if (tabName === 'email') {
            const emailInput = document.getElementById('dinp-email-to');
            if (emailInput && this.currentCustomerData) {
                emailInput.value = this.currentCustomerData.email_id_1 || this.currentCustomerData.email || '';
            }
        } else if (tabName === 'followup') {
            const dateInput = document.getElementById('dinp-fu-date');
            if (dateInput && !dateInput.value) {
                dateInput.value = new Date().toISOString().split('T')[0];
            }
            const timeInput = document.getElementById('dinp-fu-time');
            if (timeInput && !timeInput.value) {
                timeInput.value = "11:00";
            }
        } else if (tabName === 'note') {
            const noteInput = document.getElementById('dinp-note-content');
            if (noteInput) noteInput.value = '';
        } else if (tabName === 'docs' && this.currentCustomerId) {
            this.loadDocuments(this.currentCustomerId, this.currentDocFilter || 'all');
        }
    },

    currentDocFilter: 'all',

    filterDocuments(category, btnElement) {
        if (btnElement) {
            document.querySelectorAll('[data-doc-filter]').forEach(b => b.classList.remove('active'));
            btnElement.classList.add('active');
        }
        this.currentDocFilter = category;
        if (this.currentCustomerId) {
            this.loadDocuments(this.currentCustomerId, category);
        }
    },

    async loadDocuments(customerId, categoryFilter = 'all') {
        const listEl = document.getElementById('drawer-documents-list');
        const badgeCount = document.getElementById('drawer-docs-badge-count');
        const tabCount = document.getElementById('drawer-docs-count');
        if (!listEl) return;

        try {
            const docs = await api.get(`/customers/${customerId}/documents`);
            if (tabCount) tabCount.textContent = docs.length;
            if (badgeCount) badgeCount.textContent = `${docs.length} Files`;

            let displayDocs = docs;
            if (categoryFilter && categoryFilter !== 'all') {
                displayDocs = docs.filter(d => d.category === categoryFilter);
            }

            if (displayDocs.length === 0) {
                listEl.innerHTML = `
                    <div style="text-align: center; padding: 1.5rem 1rem; color: var(--text-muted); font-size: 0.8125rem; border: 1px dashed var(--border-color); border-radius: var(--radius-md);">
                        <div style="margin-bottom: 0.35rem; color: var(--text-muted);">${Icons.get('folder', { size: 24 })}</div>
                        <div>No documents found in this category.</div>
                        <div style="font-size: 0.75rem; margin-top: 0.25rem;">Use the upload box above to attach GST, PAN, Contracts, or Invoices.</div>
                    </div>
                `;
                return;
            }

            listEl.innerHTML = displayDocs.map(doc => {
                const sizeKb = (doc.file_size_bytes / 1024).toFixed(1);
                const sizeStr = doc.file_size_bytes >= 1024 * 1024 
                    ? `${(doc.file_size_bytes / (1024 * 1024)).toFixed(2)} MB` 
                    : `${sizeKb} KB`;

                const uploadDateStr = app.formatDateTime(doc.created_at);
                const uploadedByStr = doc.uploaded_by?.full_name || 'Staff';

                return `
                    <div class="compact-tl-item" style="padding: 0.65rem 0.75rem; border-left: 3px solid var(--primary); background: var(--bg-surface-elevated);">
                        <div style="display: flex; align-items: flex-start; justify-content: space-between; gap: 0.5rem;">
                            <div style="display: flex; gap: 0.5rem; align-items: flex-start; min-width: 0;">
                                <span style="color: var(--primary); margin-top: 2px;">${Icons.get('file-text', { size: 16 })}</span>
                                <div style="min-width: 0;">
                                    <div style="font-weight: 600; font-size: 0.8125rem; color: var(--text-primary); word-break: break-all;">
                                        ${this.escapeHtml(doc.filename)}
                                    </div>
                                    <div style="display: flex; gap: 0.35rem; align-items: center; flex-wrap: wrap; margin-top: 0.2rem;">
                                        <span class="badge badge-standard" style="font-size: 0.6875rem;">${this.escapeHtml(doc.category)}</span>
                                        <span style="font-size: 0.6875rem; color: var(--text-muted);">${sizeStr}</span>
                                        <span style="font-size: 0.6875rem; color: var(--text-muted);">${uploadDateStr}</span>
                                        <span style="font-size: 0.6875rem; color: var(--text-muted);">${this.escapeHtml(uploadedByStr)}</span>
                                    </div>
                                    ${doc.description ? `
                                        <div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.25rem; font-style: italic;">
                                            “${this.escapeHtml(doc.description)}”
                                        </div>
                                    ` : ''}
                                </div>
                            </div>
                            <div style="display: flex; gap: 0.25rem; flex-shrink: 0;">
                                <button class="btn btn-secondary btn-xs" onclick="customer.previewDocument(${doc.id}, '${this.escapeHtml(doc.filename)}')" title="View / Preview">
                                    ${Icons.get('eye', { size: 12 })}
                                    <span>View</span>
                                </button>
                                <button class="btn btn-secondary btn-xs" onclick="customer.downloadDocument(${doc.id}, '${this.escapeHtml(doc.filename)}')" title="Download">
                                    ${Icons.get('download', { size: 12 })}
                                    <span>Download</span>
                                </button>
                                <button class="btn btn-secondary btn-xs" onclick="customer.deleteDocument(${doc.id}, '${this.escapeHtml(doc.filename)}')" title="Delete Document" style="color: var(--danger);">
                                    ${Icons.get('trash', { size: 12 })}
                                </button>
                            </div>
                        </div>
                    </div>
                `;
            }).join('');

        } catch (err) {
            console.error("Error loading customer documents:", err);
            listEl.innerHTML = `<p class="text-danger" style="font-size: 0.8125rem; padding: 1rem 0; text-align: center;">Failed to load documents.</p>`;
        }
    },

    async submitDocumentUpload() {
        if (!this.currentCustomerId) return;
        const fileInput = document.getElementById('dinp-doc-file');
        const categorySelect = document.getElementById('dinp-doc-category');
        const descInput = document.getElementById('dinp-doc-desc');
        const btn = document.getElementById('btn-submit-doc-upload');

        if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
            api.toast("Please select a file to upload", "error");
            return;
        }

        const file = fileInput.files[0];
        const category = categorySelect?.value || 'General';
        const description = descInput?.value.trim() || '';

        const formData = new FormData();
        formData.append('file', file);
        formData.append('category', category);
        if (description) formData.append('description', description);

        if (btn) {
            btn.disabled = true;
            btn.textContent = "Uploading...";
        }

        try {
            api.toast(`Uploading ${file.name}...`, "info");
            await api.post(`/customers/${this.currentCustomerId}/documents`, formData);
            api.toast(`Document '${file.name}' uploaded successfully!`, "success");

            fileInput.value = '';
            if (descInput) descInput.value = '';
            await this.loadDocuments(this.currentCustomerId, this.currentDocFilter || 'all');
        } catch (err) {
            api.toast(`Upload failed: ${err.message}`, "error");
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.textContent = "Upload";
            }
        }
    },

    async previewDocument(docId, filename = 'document') {
        if (!this.currentCustomerId || !docId) return;
        const token = api.getToken() || localStorage.getItem('crm_access_token') || localStorage.getItem('access_token');
        
        try {
            api.toast(`Opening preview for '${filename}'...`, "info");
            const url = `/api/customers/${this.currentCustomerId}/documents/${docId}/preview` + (token ? `?token=${encodeURIComponent(token)}` : '');
            const response = await fetch(url, {
                headers: token ? { 'Authorization': `Bearer ${token}` } : {}
            });

            if (!response.ok) {
                const errJson = await response.json().catch(() => ({}));
                throw new Error(errJson.detail || `HTTP ${response.status}: Failed to preview file`);
            }

            const blob = await response.blob();
            const blobUrl = window.URL.createObjectURL(blob);
            window.open(blobUrl, '_blank');
            setTimeout(() => window.URL.revokeObjectURL(blobUrl), 120000);
        } catch (err) {
            console.error("Preview failed:", err);
            api.toast(`Preview failed: ${err.message}`, "error");
        }
    },

    async downloadDocument(docId, filename = 'document') {
        if (!this.currentCustomerId || !docId) return;
        const token = api.getToken() || localStorage.getItem('crm_access_token') || localStorage.getItem('access_token');
        
        try {
            api.toast(`Downloading '${filename}'...`, "info");
            const url = `/api/customers/${this.currentCustomerId}/documents/${docId}/download` + (token ? `?token=${encodeURIComponent(token)}` : '');
            const response = await fetch(url, {
                headers: token ? { 'Authorization': `Bearer ${token}` } : {}
            });

            if (!response.ok) {
                const errJson = await response.json().catch(() => ({}));
                throw new Error(errJson.detail || `HTTP ${response.status}: Failed to download file`);
            }

            let downloadFilename = filename;
            const disposition = response.headers.get('Content-Disposition');
            if (disposition && disposition.includes('filename=')) {
                const match = disposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
                if (match && match[1]) {
                    downloadFilename = match[1].replace(/['"]/g, '');
                }
            }

            const blob = await response.blob();
            const blobUrl = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = blobUrl;
            a.download = downloadFilename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(blobUrl);
            api.toast(`Downloaded '${downloadFilename}'`, "success");
        } catch (err) {
            console.error("Download failed:", err);
            api.toast(`Download failed: ${err.message}`, "error");
        }
    },

    async deleteDocument(docId, filename = 'document') {
        if (!this.currentCustomerId || !docId) return;
        if (!confirm(`Are you sure you want to delete document '${filename}'?`)) return;

        try {
            await api.delete(`/customers/${this.currentCustomerId}/documents/${docId}`);
            api.toast(`Document '${filename}' deleted`, "success");
            await this.loadDocuments(this.currentCustomerId, this.currentDocFilter || 'all');
        } catch (err) {
            api.toast(`Delete failed: ${err.message}`, "error");
        }
    },

    async submitDrawerEditForm() {
        if (!this.currentCustomerId) return;
        const payload = {
            party_code: document.getElementById('dinp-party-code').value.trim() || null,
            party_name: document.getElementById('dinp-party-name').value.trim(),
            address_date: document.getElementById('dinp-address-date').value.trim() || null,
            address_line_1: document.getElementById('dinp-addr1').value.trim() || null,
            address_line_2: document.getElementById('dinp-addr2').value.trim() || null,
            address_line_3: document.getElementById('dinp-addr3').value.trim() || null,
            contact_person_1: document.getElementById('dinp-contact-person').value.trim() || null,
            email_id_1: document.getElementById('dinp-email').value.trim() || null,
            country: document.getElementById('dinp-country').value.trim() || 'India',
            state: document.getElementById('dinp-state').value.trim() || null,
            city: document.getElementById('dinp-city').value.trim() || null,
            pincode: document.getElementById('dinp-pincode').value.trim() || null,
            phone_type_1: document.getElementById('dinp-phone-type').value,
            phone_1: document.getElementById('dinp-phone1').value.trim(),
            status: document.getElementById('dinp-status').value,
            assigned_employee_id: parseInt(document.getElementById('dinp-assigned-agent').value) || null
        };

        if (!payload.party_name || !payload.phone_1) {
            api.toast("Party Name and Phone 1 are required", "error");
            return;
        }

        try {
            const updated = await api.put(`/customers/${this.currentCustomerId}`, payload);
            api.toast(`Customer ${updated.party_name} updated successfully!`, "success");
            this.populateDrawerFields(updated);
            this.switchDrawerTab('profile');
            this.loadCustomers();
            app.refreshDashboard();
        } catch (err) {
            api.toast(`Save failed: ${err.message}`, "error");
        }
    },

    async submitDrawerNote() {
        if (!this.currentCustomerId) return;
        const noteContent = document.getElementById('dinp-note-content').value.trim();
        const noteType = document.getElementById('dinp-note-type').value;
        const notePriority = document.getElementById('dinp-note-priority').value;

        if (!noteContent) {
            api.toast("Please enter note details", "error");
            return;
        }

        try {
            await api.post('/interactions', {
                customer_id: this.currentCustomerId,
                type: noteType,
                direction: 'internal',
                subject: `${noteType.toUpperCase()} Note (${notePriority} Priority)`,
                content: noteContent
            });

            api.toast("Interaction note saved and added to timeline!", "success");
            document.getElementById('dinp-note-content').value = '';
            await this.loadTimeline(this.currentCustomerId, this.currentTimelineFilter);
            this.switchDrawerTab('profile');
            app.refreshDashboard();
        } catch (err) {
            api.toast(`Failed to save note: ${err.message}`, "error");
        }
    },

    applyEmailTemplate(tmpl) {
        const bodyEl = document.getElementById('dinp-email-body');
        const subjEl = document.getElementById('dinp-email-subject');
        if (!bodyEl) return;

        const custName = this.currentCustomerData?.party_name || this.currentCustomerData?.name || 'Valued Customer';
        const contactName = this.currentCustomerData?.contact_person_1 || custName;

        if (tmpl === 'followup') {
            subjEl.value = `Follow-up Regarding Our Recent Conversation - ${custName}`;
            bodyEl.value = `Dear ${contactName},\n\nThank you for speaking with our team today. Following up on our discussion regarding your requirements, please find the summary below...\n\nBest Regards,\nKOGM Client Support`;
        } else if (tmpl === 'order') {
            subjEl.value = `Order Confirmation & Dispatch Update - ${custName}`;
            bodyEl.value = `Dear ${contactName},\n\nWe are pleased to confirm that your order is processed. Our dispatch team is preparing the consignment.\n\nBest Regards,\nKOGM Enterprise Operations`;
        } else if (tmpl === 'support') {
            subjEl.value = `Support Ticket Resolution Update - ${custName}`;
            bodyEl.value = `Dear ${contactName},\n\nThis is to inform you that the inquiry raised during your call has been reviewed and resolved by our technical team.\n\nBest Regards,\nKOGM Customer Success Team`;
        }
    },

    async submitDrawerEmail() {
        if (!this.currentCustomerId) return;
        const to = document.getElementById('dinp-email-to').value.trim();
        const subject = document.getElementById('dinp-email-subject').value.trim();
        const body = document.getElementById('dinp-email-body').value.trim();
        const btn = document.getElementById('btn-submit-drawer-email');

        if (!to || !subject || !body) {
            api.toast("Please fill in recipient email, subject, and message", "error");
            return;
        }

        if (btn) {
            btn.disabled = true;
            btn.textContent = "Sending Email...";
        }

        try {
            await api.post('/emails/send', {
                customer_id: this.currentCustomerId,
                to_email: to,
                subject: subject,
                body: body
            });

            api.toast(`Email dispatched to ${to} and logged to timeline!`, "success");
            document.getElementById('dinp-email-subject').value = '';
            document.getElementById('dinp-email-body').value = '';
            await this.loadTimeline(this.currentCustomerId, this.currentTimelineFilter);
            this.switchDrawerTab('profile');
            app.refreshDashboard();
        } catch (err) {
            api.toast(`Email error: ${err.message}`, "error");
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.textContent = "Send Email";
            }
        }
    },

    async submitDrawerFollowup() {
        if (!this.currentCustomerId) return;
        const title = document.getElementById('dinp-fu-title').value.trim();
        const dueDate = document.getElementById('dinp-fu-date').value;
        const dueTime = document.getElementById('dinp-fu-time')?.value || '11:00';
        const priority = document.getElementById('dinp-fu-priority').value;
        const notes = document.getElementById('dinp-fu-notes').value.trim();

        if (!title || !dueDate) {
            api.toast("Please enter follow-up reason and due date", "error");
            return;
        }

        const dueDateTimeStr = `${dueDate}T${dueTime}:00`;
        const scheduledDate = new Date(dueDateTimeStr);
        const isoDueDate = isNaN(scheduledDate.getTime()) ? new Date().toISOString() : scheduledDate.toISOString();

        try {
            await api.post('/followups', {
                customer_id: this.currentCustomerId,
                title: title,
                due_date: isoDueDate,
                priority: priority,
                description: notes || `Follow-up task scheduled for ${title}`,
                notes: notes || null
            });

            api.toast("Follow-up task scheduled and added to timeline!", "success");
            document.getElementById('dinp-fu-title').value = '';
            document.getElementById('dinp-fu-notes').value = '';
            await this.loadTimeline(this.currentCustomerId, this.currentTimelineFilter);
            this.switchDrawerTab('profile');
            app.refreshDashboard();
        } catch (err) {
            api.toast(`Follow-up error: ${err.message}`, "error");
        }
    },

    escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    },

    async loadCustomers() {
        const tbody = document.getElementById('customers-table-body');
        if (!tbody) return;

        // Render shimmering skeleton rows while loading
        tbody.innerHTML = Array.from({ length: 8 }).map(() => `
            <tr class="skeleton-row">
                <td><div class="skeleton" style="width: 75px; height: 14px;"></div></td>
                <td>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <div class="skeleton skeleton-circle" style="width: 26px; height: 26px;"></div>
                        <div>
                            <div class="skeleton" style="width: 130px; height: 13px; margin-bottom: 4px;"></div>
                            <div class="skeleton" style="width: 85px; height: 10px;"></div>
                        </div>
                    </div>
                </td>
                <td><div class="skeleton" style="width: 95px; height: 13px;"></div></td>
                <td><div class="skeleton" style="width: 120px; height: 13px;"></div></td>
                <td><div class="skeleton" style="width: 85px; height: 13px;"></div></td>
                <td><div class="skeleton" style="width: 60px; height: 18px; border-radius: 10px;"></div></td>
                <td><div class="skeleton" style="width: 80px; height: 13px;"></div></td>
                <td><div class="skeleton" style="width: 80px; height: 13px;"></div></td>
                <td><div class="skeleton" style="width: 70px; height: 26px; border-radius: 4px;"></div></td>
            </tr>
        `).join('');

        const search = document.getElementById('customers-filter-search')?.value.trim() || '';
        const status = document.getElementById('customers-filter-status')?.value || '';

        try {
            let url = `/customers?page=${this.currentPage}&limit=${this.limit}`;
            if (search) url += `&search=${encodeURIComponent(search)}`;
            if (status) url += `&status=${encodeURIComponent(status)}`;

            const data = await api.get(url);
            
            const totalFormatted = (window.app && typeof app.formatFullNumber === 'function') ? app.formatFullNumber(data.total) : data.total;
            const startNum = data.items.length > 0 ? ((data.page - 1) * this.limit + 1) : 0;
            const endNum = Math.min(data.page * this.limit, data.total);
            document.getElementById('customers-pagination-info').textContent = 
                `Showing ${startNum} to ${endNum} of ${totalFormatted} customers (Page ${data.page} of ${data.total_pages})`;
            
            const badge = document.getElementById('nav-badge-customers');
            if (badge) {
                badge.textContent = (window.app && typeof app.formatNumberDisplay === 'function') ? app.formatNumberDisplay(data.total) : data.total;
                badge.title = `${totalFormatted} Total Customers`;
            }

            if (data.items.length === 0) {
                tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--text-muted); padding: 2rem;">No customers match current filter.</td></tr>`;
                return;
            }

            tbody.innerHTML = data.items.map(c => {
                const statusClass = c.status === 'Active' ? 'badge-active' : (c.status === 'Lead' ? 'badge-lead' : 'badge-standard');
                const location = [c.city, c.state].filter(Boolean).join(', ') || '—';
                const partyCode = c.party_code || c.customer_id;
                const partyName = c.party_name || c.name;
                const phone1 = c.phone_1 || c.mobile;
                const emailId = c.email_id_1 || c.email || '—';
                const contactPerson = c.contact_person_1 || '—';
                
                return `
                    <tr style="cursor: pointer;" onclick="customer.openDrawer(${c.id})">
                        <td><span class="badge badge-standard">${partyCode}</span></td>
                        <td>
                            <div style="font-weight: 600; color: var(--text-primary);">${partyName}</div>
                        </td>
                        <td>
                            <div style="font-weight: 500; color: var(--text-secondary);">${contactPerson}</div>
                        </td>
                        <td>
                            <div style="font-weight: 600; color: var(--primary); font-variant-numeric: tabular-nums;">${phone1}</div>
                        </td>
                        <td><span style="font-size: 0.75rem; color: var(--text-muted);">${emailId}</span></td>
                        <td><span style="font-size: 0.75rem;">${location}</span></td>
                        <td><span class="badge ${statusClass}">${c.status}</span></td>
                        <td><span style="font-size: 0.75rem;">${c.assigned_employee?.full_name || 'Unassigned'}</span></td>
                        <td>
                            <div style="display: flex; gap: 0.25rem;" onclick="event.stopPropagation();">
                                <button class="btn btn-secondary btn-xs" onclick="cti.makeOutgoingCall('${this.escapeHtml(phone1)}', ${c.id})" title="Initiate Outgoing Call" style="color: var(--primary); font-weight: 600;">
                                    ${Icons.get('phone', { size: 12 })}
                                    <span>Call</span>
                                </button>
                                <button class="btn btn-secondary btn-xs" onclick="customer.openDrawer(${c.id})" title="View Profile">
                                    ${Icons.get('eye', { size: 12 })}
                                    <span>View</span>
                                </button>
                                <button class="btn btn-secondary btn-xs" onclick="customer.openEditModal(${c.id})" title="Edit Details">
                                    ${Icons.get('edit', { size: 12 })}
                                    <span>Edit</span>
                                </button>
                            </div>
                        </td>
                    </tr>
                `;
            }).join('');

        } catch (err) {
            console.error("Error loading customers:", err);
            tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--danger);">Failed to load customers</td></tr>`;
        }
    },

    populateDrawerFields(cust) {
        if (!cust) return;
        this.currentCustomerData = cust;
        const setVal = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = val !== null && val !== undefined && val !== '' ? val : '—';
        };

        const partyCode = cust.party_code || cust.customer_id || '—';
        const partyName = cust.party_name || cust.name || '—';
        const phone1 = cust.phone_1 || cust.mobile || '—';
        const contactPerson = cust.contact_person_1 || cust.name || '—';
        const emailId = cust.email_id_1 || cust.email || '—';
        const location = [cust.city, cust.state, cust.country, cust.pincode ? `(${cust.pincode})` : ''].filter(Boolean).join(', ') || 'Location N/A';

        setVal('drawer-cust-id', partyCode);
        setVal('drawer-cust-name', partyName);
        setVal('drawer-cust-contact', `Contact: ${contactPerson}`);
        setVal('drawer-cust-location', location);
        
        // 15 Standardized Fields
        setVal('drawer-cust-party-code', partyCode);
        setVal('drawer-cust-party-name', partyName);
        setVal('drawer-cust-address-date', cust.address_date);
        setVal('drawer-cust-addr1', cust.address_line_1 || cust.address);
        setVal('drawer-cust-addr2', cust.address_line_2);
        setVal('drawer-cust-addr3', cust.address_line_3);
        setVal('drawer-cust-contact-person', contactPerson);
        setVal('drawer-cust-email-id', emailId);
        setVal('drawer-cust-country', cust.country || 'India');
        setVal('drawer-cust-state', cust.state);
        setVal('drawer-cust-city', cust.city);
        setVal('drawer-cust-pincode', cust.pincode);
        setVal('drawer-cust-phone-type', cust.phone_type_1 || 'Mobile');
        setVal('drawer-cust-phone-1', phone1);
        setVal('drawer-cust-status', cust.status || 'Active');

        const statusBadge = document.getElementById('drawer-cust-status-badge');
        if (statusBadge) {
            statusBadge.innerHTML = `<span class="badge ${cust.status === 'Active' ? 'badge-active' : 'badge-lead'}">${cust.status || 'Active'}</span>`;
        }

        // Render Multiple Phone Numbers List
        if (cust.phone_numbers && Array.isArray(cust.phone_numbers)) {
            this.renderCustomerPhoneList(cust.phone_numbers);
        } else {
            api.get(`/customers/${cust.id}/phones`).then(phones => {
                this.renderCustomerPhoneList(phones);
            }).catch(() => {
                this.renderCustomerPhoneList([
                    { id: 0, phone_number: phone1, phone_type: cust.phone_type_1 || 'Mobile', label: 'Primary Contact', is_primary: true }
                ]);
            });
        }

        const user = api.getCurrentUser();
        const delBtn = document.getElementById('btn-drawer-delete-customer');
        if (delBtn) {
            delBtn.style.display = (user && user.role === 'admin') ? 'inline-flex' : 'none';
        }

        // Update TCS iON Sync Button State (Enabled if party_name exists, disabled if missing)
        this.updateTcsSyncState(cust);
    },

    toggleAddPhoneForm(show = null) {
        const box = document.getElementById('drawer-add-phone-box');
        if (!box) return;
        if (show === null) {
            box.style.display = box.style.display === 'none' ? 'block' : 'none';
        } else {
            box.style.display = show ? 'block' : 'none';
        }
        if (box.style.display === 'block') {
            document.getElementById('dinp-newphone-number')?.focus();
        }
    },

    async submitAddPhone() {
        if (!this.currentCustomerId) return;
        const phoneNum = document.getElementById('dinp-newphone-number')?.value.trim();
        const phoneType = document.getElementById('dinp-newphone-type')?.value || 'Mobile';
        const phoneLabel = document.getElementById('dinp-newphone-label')?.value.trim() || null;
        const btn = document.getElementById('btn-submit-save-phone');

        if (!phoneNum) {
            api.toast("Please enter a phone number", "error");
            return;
        }

        try {
            if (btn) btn.disabled = true;
            const updatedPhones = await api.post(`/customers/${this.currentCustomerId}/phones`, {
                phone_number: phoneNum,
                phone_type: phoneType,
                label: phoneLabel,
                is_primary: false
            });
            api.toast(`Phone number '${phoneNum}' added to customer profile!`, "success");
            this.renderCustomerPhoneList(updatedPhones);
            this.toggleAddPhoneForm(false);
            document.getElementById('dinp-newphone-number').value = "";
            document.getElementById('dinp-newphone-label').value = "";
            this.loadCustomers();
        } catch (err) {
            api.toast(`Failed to add phone: ${err.message}`, "error");
        } finally {
            if (btn) btn.disabled = false;
        }
    },

    async setPrimaryPhone(phoneId) {
        if (!this.currentCustomerId) return;
        try {
            const updatedPhones = await api.put(`/customers/${this.currentCustomerId}/phones/${phoneId}/primary`, {});
            api.toast("Primary phone number updated successfully!", "success");
            const freshCust = await api.get(`/customers/${this.currentCustomerId}`);
            this.populateDrawerFields(freshCust);
            this.loadCustomers();
        } catch (err) {
            api.toast(`Failed to set primary phone: ${err.message}`, "error");
        }
    },

    async deletePhone(phoneId, phoneNumber) {
        if (!this.currentCustomerId || !phoneId) return;
        if (!confirm(`Are you sure you want to remove '${phoneNumber}' from this customer?`)) return;

        try {
            const updatedPhones = await api.delete(`/customers/${this.currentCustomerId}/phones/${phoneId}`);
            api.toast(`Phone number '${phoneNumber}' removed.`, "success");
            this.renderCustomerPhoneList(updatedPhones);
            this.loadCustomers();
        } catch (err) {
            api.toast(`Failed to delete phone: ${err.message}`, "error");
        }
    },

    renderCustomerPhoneList(phones) {
        const listEl = document.getElementById('drawer-phones-list');
        const countEl = document.getElementById('drawer-phones-count');
        if (!listEl) return;

        if (!phones || phones.length === 0) {
            listEl.innerHTML = `
                <div style="font-size: 0.75rem; color: var(--text-muted); padding: 0.35rem 0;">
                    No additional numbers saved.
                </div>
            `;
            if (countEl) countEl.textContent = "1 Number";
            return;
        }

        if (countEl) countEl.textContent = `${phones.length} ${phones.length === 1 ? 'Number' : 'Numbers'}`;

        listEl.innerHTML = phones.map(p => {
            const isPrimary = Boolean(p.is_primary);
            const type = p.phone_type || 'Mobile';
            const rawDigits = p.phone_normalized || p.phone_number.replace(/\D/g, '');
            const cleanDigits = rawDigits.slice(-10);

            return `
                <div style="display: flex; align-items: center; justify-content: space-between; background: var(--bg-surface); padding: 0.4rem 0.6rem; border-radius: var(--radius-sm); border: 1px solid ${isPrimary ? 'var(--primary)' : 'var(--border-color)'};">
                    <div style="display: flex; align-items: center; gap: 0.45rem; min-width: 0;">
                        <span style="color: var(--text-muted);">${Icons.get('phone', { size: 14 })}</span>
                        <div style="min-width: 0;">
                            <div style="display: flex; align-items: center; gap: 0.35rem;">
                                <span style="font-weight: 600; font-size: 0.8125rem; color: ${isPrimary ? 'var(--primary)' : 'var(--text-primary)'}; font-variant-numeric: tabular-nums;">
                                    ${this.escapeHtml(p.phone_number)}
                                </span>
                                ${isPrimary ? `
                                    <span class="badge badge-active" style="font-size: 0.625rem; padding: 0.05rem 0.3rem;">
                                        PRIMARY
                                    </span>
                                ` : ''}
                            </div>
                            <div style="font-size: 0.6875rem; color: var(--text-muted);">
                                ${this.escapeHtml(p.label || type)}
                            </div>
                        </div>
                    </div>
                    <div style="display: flex; gap: 0.25rem; align-items: center; flex-shrink: 0;">
                        <button class="btn btn-secondary btn-xs" onclick="cti.makeOutgoingCall('${this.escapeHtml(p.phone_number)}', ${this.currentCustomerId})" title="Initiate Call">
                            ${Icons.get('phone', { size: 11 })}
                            <span>Call</span>
                        </button>
                        ${type === 'WhatsApp' ? `
                            <a href="https://wa.me/91${cleanDigits}" target="_blank" class="btn btn-secondary btn-xs" style="color: var(--success);" title="Open WhatsApp Chat">
                                ${Icons.get('message-square', { size: 11 })}
                                <span>WA</span>
                            </a>
                        ` : ''}
                        ${!isPrimary && p.id !== 0 ? `
                            <button class="btn btn-secondary btn-xs" onclick="customer.setPrimaryPhone(${p.id})" title="Set as Primary Contact Number">
                                Make Primary
                            </button>
                            <button class="btn btn-secondary btn-xs" style="color: var(--danger);" onclick="customer.deletePhone(${p.id}, '${this.escapeHtml(p.phone_number)}')" title="Delete Phone Number">
                                ${Icons.get('trash', { size: 11 })}
                            </button>
                        ` : ''}
                    </div>
                </div>
            `;
        }).join('');
    },

    async openDrawer(customerId, prefetchedCustomer = null) {
        if (!customerId) return;
        this.currentCustomerId = customerId;

        // Close any blocking modal if open
        document.querySelectorAll('.modal-overlay.open').forEach(m => m.classList.remove('open'));

        // Switch to Known Customer View & default to Profile Tab
        const knownView = document.getElementById('drawer-view-known');
        const newView = document.getElementById('drawer-view-new');
        if (knownView) knownView.style.display = 'flex';
        if (newView) newView.style.display = 'none';
        this.switchDrawerTab('profile');

        const overlay = document.getElementById('drawer-overlay');
        if (overlay) {
            overlay.style.removeProperty('display');
            overlay.classList.add('open');
        }

        if (prefetchedCustomer) {
            this.populateDrawerFields(prefetchedCustomer);
            if (prefetchedCustomer.recent_interactions && prefetchedCustomer.recent_interactions.length > 0) {
                this.renderTimelineItems(prefetchedCustomer.recent_interactions);
            }
        }

        try {
            const cust = await api.get(`/customers/${customerId}`);
            this.populateDrawerFields(cust);
            this.loadTimeline(customerId, this.currentTimelineFilter);
            
            api.get(`/customers/${customerId}/documents`).then(docs => {
                const tabCount = document.getElementById('drawer-docs-count');
                const badgeCount = document.getElementById('drawer-docs-badge-count');
                if (tabCount) tabCount.textContent = docs.length;
                if (badgeCount) badgeCount.textContent = `${docs.length} Files`;
            }).catch(() => {});
        } catch (err) {
            console.warn("Could not fetch customer details from /customers/" + customerId, err);
            this.loadTimeline(customerId, this.currentTimelineFilter);
        }
    },

    openNewCustomerDrawer(phoneNumber, callData = null) {
        this.currentCustomerId = null;
        this.currentUnregisteredPhone = phoneNumber;

        // Close any blocking modal if open
        document.querySelectorAll('.modal-overlay.open').forEach(m => m.classList.remove('open'));

        // Switch to New / Unregistered Caller View
        const knownView = document.getElementById('drawer-view-known');
        const newView = document.getElementById('drawer-view-new');
        if (knownView) knownView.style.display = 'none';
        if (newView) newView.style.display = 'flex';

        // Populate unregistered caller information
        const phoneEl = document.getElementById('drawer-new-cust-phone');
        const callPhoneEl = document.getElementById('drawer-new-call-phone');
        const callIdEl = document.getElementById('drawer-new-call-id');
        const callTimeEl = document.getElementById('drawer-new-call-time');

        if (phoneEl) phoneEl.textContent = phoneNumber;
        if (callPhoneEl) callPhoneEl.textContent = phoneNumber;
        if (callIdEl) callIdEl.textContent = callData?.call_id || `CALL-LIVE`;
        if (callTimeEl) callTimeEl.textContent = new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true });

        const overlay = document.getElementById('drawer-overlay');
        if (overlay) {
            overlay.style.removeProperty('display');
            overlay.classList.add('open');
        }
    },

    closeDrawer() {
        const overlay = document.getElementById('drawer-overlay');
        if (overlay) {
            overlay.style.removeProperty('display');
            overlay.classList.remove('open');
        }
        this.currentCustomerId = null;
    },

    renderTimelineItems(items) {
        const listEl = document.getElementById('drawer-timeline-list');
        const countEl = document.getElementById('drawer-tl-count');
        if (countEl) countEl.textContent = `${items.length} ${items.length === 1 ? 'Event' : 'Events'}`;
        if (!listEl) return;

        if (items.length === 0) {
            listEl.innerHTML = `
                <div style="text-align: center; padding: 1.25rem 0.5rem; color: var(--text-muted); font-size: 0.8125rem; border: 1px dashed var(--border-color); border-radius: var(--radius-md);">
                    <div style="margin-bottom: 0.25rem; color: var(--text-muted);">${Icons.get('clock', { size: 20 })}</div>
                    <div>No timeline interactions recorded in this channel.</div>
                </div>
            `;
            return;
        }

        listEl.innerHTML = items.map((item, idx) => {
            let badgeClass = "badge-standard";
            let channelLabel = "Note";
            let iconName = "file-text";

            if (item.type === 'call') {
                badgeClass = "badge-active";
                channelLabel = item.direction === 'outgoing' ? "Outbound Call" : "Inbound Call";
                iconName = item.direction === 'outgoing' ? "phone-outgoing" : "phone-incoming";
            } else if (item.type === 'email') {
                badgeClass = "badge-vip";
                channelLabel = "Email";
                iconName = "mail";
            } else if (item.type === 'followup') {
                badgeClass = "badge-lead";
                channelLabel = "Follow-up";
                iconName = "clock";
            } else if (item.type === 'whatsapp') {
                badgeClass = "badge-active";
                channelLabel = "WhatsApp";
                iconName = "message-square";
            } else if (item.type === 'meeting') {
                badgeClass = "badge-vip";
                channelLabel = "Meeting";
                iconName = "users";
            } else {
                badgeClass = "badge-standard";
                channelLabel = "Note";
                iconName = "file-text";
            }

            const formattedTime = app.formatDateTime(item.timestamp || item.time);
            const title = item.title || `${channelLabel} Logged`;
            const content = (item.description || item.content || '').trim();
            const preview = content ? (content.length > 70 ? content.substring(0, 70) + '...' : content) : 'No additional details logged.';
            const userName = item.user_name || 'System';
            const itemId = `tl-${item.id || idx}`;

            return `
                <div class="compact-tl-item" data-tl-id="${itemId}" onclick="customer.toggleTimelineExpand('${itemId}')">
                    <div class="compact-tl-header">
                        <div class="compact-tl-left">
                            <span class="compact-tl-icon" style="color: var(--primary);">${Icons.get(iconName, { size: 14 })}</span>
                            <span class="badge ${badgeClass}">${channelLabel}</span>
                            <span class="compact-tl-title" title="${this.escapeHtml(title)}">${this.escapeHtml(title)}</span>
                        </div>
                        <div class="compact-tl-right">
                            <span class="compact-tl-time">${formattedTime}</span>
                            <span class="compact-tl-arrow" id="arrow-${itemId}" style="display: inline-flex; transition: transform 0.2s ease;">${Icons.get('chevron-down', { size: 12 })}</span>
                        </div>
                    </div>
                    
                    <div class="compact-tl-preview" id="prev-${itemId}">
                        ${this.escapeHtml(preview)}
                    </div>

                    <div class="compact-tl-details" id="details-${itemId}" style="display: none;">
                        <div class="compact-tl-meta-bar">
                            <span><strong>By:</strong> ${this.escapeHtml(userName)}</span>
                            ${item.meta?.duration ? `<span><strong>Duration:</strong> ${item.meta.duration}</span>` : ''}
                            ${item.meta?.due_date ? `<span><strong>Due:</strong> ${app.formatDateTime(item.meta.due_date)}</span>` : ''}
                            ${item.meta?.priority ? `<span><strong>Priority:</strong> ${item.meta.priority}</span>` : ''}
                            ${item.meta?.status ? `<span><strong>Status:</strong> ${item.meta.status}</span>` : ''}
                        </div>
                        <div class="compact-tl-full-text">
                            ${this.escapeHtml(content || 'No detailed message.')}
                        </div>
                        ${item.meta?.recording_url ? `
                            <div style="margin-top: 0.4rem; padding-top: 0.4rem; border-top: 1px dashed var(--border-color);">
                                <button type="button" class="btn btn-primary btn-xs" onclick="event.stopPropagation(); cti.playRecording('${this.escapeHtml(item.meta.recording_url)}', '${this.escapeHtml(title)}');">
                                    ${Icons.get('play', { size: 11 })}
                                    <span>Play Call Recording (Fast Stream)</span>
                                </button>
                            </div>
                        ` : ''}
                    </div>
                </div>
            `;
        }).join('');
    },

    toggleTimelineExpand(id) {
        const details = document.getElementById(`details-${id}`);
        const preview = document.getElementById(`prev-${id}`);
        const arrow = document.getElementById(`arrow-${id}`);
        if (!details) return;

        const isExpanded = details.style.display === 'block';
        if (isExpanded) {
            details.style.display = 'none';
            if (preview) preview.style.display = 'block';
            if (arrow) arrow.style.transform = 'rotate(0deg)';
        } else {
            details.style.display = 'block';
            if (preview) preview.style.display = 'none';
            if (arrow) arrow.style.transform = 'rotate(180deg)';
        }
    },

    async loadTimeline(customerId, filter = 'all') {
        const listEl = document.getElementById('drawer-timeline-list');
        if (!listEl) return;

        try {
            const data = await api.get(`/customers/${customerId}/timeline`);
            let items = data.timeline || [];

            if (filter !== 'all') {
                if (filter === 'note') {
                    items = items.filter(i => ['note', 'internal', 'meeting', 'whatsapp', 'system'].includes(i.type));
                } else if (filter === 'followup') {
                    items = items.filter(i => i.type === 'followup');
                } else if (filter === 'call') {
                    items = items.filter(i => i.type === 'call');
                } else if (filter === 'email') {
                    items = items.filter(i => i.type === 'email');
                } else {
                    items = items.filter(i => i.type === filter);
                }
            }

            this.renderTimelineItems(items);

        } catch (err) {
            console.error("Error loading customer timeline:", err);
            listEl.innerHTML = `<p class="text-danger" style="font-size: 0.8125rem; padding: 1rem 0; text-align: center;">Failed to load interaction timeline.</p>`;
        }
    },

    async openAddModal(prefilledPhone = '') {
        this.editingCustomerId = null;
        const form = document.getElementById('form-add-customer');
        if (form) form.reset();

        const titleEl = document.getElementById('modal-cust-title');
        if (titleEl) titleEl.textContent = "Create New Customer (15 Columns Schema)";

        const submitBtn = document.getElementById('btn-submit-add-customer');
        if (submitBtn) {
            submitBtn.innerHTML = `
                <svg class="icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"></path><polyline points="17 21 17 13 7 13 7 21"></polyline><polyline points="7 3 7 8 15 8"></polyline></svg>
                <span>Save Customer Record</span>
            `;
        }

        const editIdEl = document.getElementById('inp-cust-edit-id');
        if (editIdEl) editIdEl.value = "";

        const countryEl = document.getElementById('inp-cust-country');
        if (countryEl) countryEl.value = "India";

        const ptypeEl = document.getElementById('inp-cust-phone-type');
        if (ptypeEl) ptypeEl.value = "Mobile";

        const statusEl = document.getElementById('inp-cust-status');
        if (statusEl) statusEl.value = "Active";

        if (prefilledPhone) {
            const phoneInput = document.getElementById('inp-cust-phone1');
            if (phoneInput) phoneInput.value = prefilledPhone;
        }

        // Populate agents dropdown safely
        await this.populateAgentDropdown();

        // Close right-side drawer if open so modal is 100% unobstructed
        if (this.isDrawerOpen) {
            this.closeDrawer();
        }

        app.openModal('modal-add-customer');
    },

    async openEditModal(customerId) {
        this.editingCustomerId = customerId;
        const form = document.getElementById('form-add-customer');
        if (form) form.reset();

        document.getElementById('modal-cust-title').textContent = "Edit Customer Profile (15 Columns)";
        document.getElementById('btn-submit-add-customer').textContent = "Update Customer";
        document.getElementById('inp-cust-edit-id').value = customerId;

        // Populate agents dropdown
        await this.populateAgentDropdown();

        try {
            const cust = await api.get(`/customers/${customerId}`);

            document.getElementById('inp-cust-party-code').value = cust.party_code || cust.customer_id || '';
            document.getElementById('inp-cust-party-name').value = cust.party_name || cust.name || '';
            document.getElementById('inp-cust-address-date').value = cust.address_date || '';
            document.getElementById('inp-cust-addr1').value = cust.address_line_1 || cust.address || '';
            document.getElementById('inp-cust-addr2').value = cust.address_line_2 || '';
            document.getElementById('inp-cust-addr3').value = cust.address_line_3 || '';
            document.getElementById('inp-cust-contact-person').value = cust.contact_person_1 || '';
            document.getElementById('inp-cust-email-id').value = cust.email_id_1 || cust.email || '';
            document.getElementById('inp-cust-country').value = cust.country || 'India';
            document.getElementById('inp-cust-state').value = cust.state || '';
            document.getElementById('inp-cust-city').value = cust.city || '';
            document.getElementById('inp-cust-pincode').value = cust.pincode || '';
            document.getElementById('inp-cust-phone-type').value = cust.phone_type_1 || 'Mobile';
            
            // Handle Phone 1 & Country Code
            let phone1 = (cust.phone_1 || cust.mobile || '').trim();
            let cc = "+91";
            if (phone1.startsWith("+")) {
                const parts = phone1.split(' ');
                if (parts.length > 1) {
                    cc = parts[0];
                    phone1 = parts.slice(1).join('');
                }
            }
            const ccSelect = document.getElementById('inp-cust-country-code');
            if ([...ccSelect.options].some(o => o.value === cc)) {
                ccSelect.value = cc;
            } else {
                ccSelect.value = "+91";
            }
            document.getElementById('inp-cust-phone1').value = phone1;

            document.getElementById('inp-cust-status').value = cust.status || 'Active';
            if (cust.assigned_employee_id) {
                document.getElementById('inp-cust-agent').value = cust.assigned_employee_id;
            }
            document.getElementById('inp-cust-notes').value = cust.notes || '';

            app.openModal('modal-add-customer');
        } catch (err) {
            api.toast(`Error fetching customer details: ${err.message}`, "error");
        }
    },

    async populateAgentDropdown() {
        const agentSel = document.getElementById('inp-cust-agent');
        if (!agentSel) return;
        try {
            const employees = await api.get('/employees');
            agentSel.innerHTML = employees.map(e => `
                <option value="${e.id}">${e.full_name} (${e.role.toUpperCase()})</option>
            `).join('');
        } catch (err) {
            console.error("Error loading employees for dropdown:", err);
        }
    },

    async submitCustomerForm() {
        const cc = document.getElementById('inp-cust-country-code').value.trim();
        const rawPhone = document.getElementById('inp-cust-phone1').value.trim();
        const fullPhone = cc && !rawPhone.startsWith("+") ? `${cc} ${rawPhone}` : rawPhone;

        const payload = {
            party_code: document.getElementById('inp-cust-party-code').value.trim() || null,
            party_name: document.getElementById('inp-cust-party-name').value.trim(),
            address_date: document.getElementById('inp-cust-address-date').value.trim() || null,
            address_line_1: document.getElementById('inp-cust-addr1').value.trim() || null,
            address_line_2: document.getElementById('inp-cust-addr2').value.trim() || null,
            address_line_3: document.getElementById('inp-cust-addr3').value.trim() || null,
            contact_person_1: document.getElementById('inp-cust-contact-person').value.trim() || null,
            email_id_1: document.getElementById('inp-cust-email-id').value.trim() || null,
            country: document.getElementById('inp-cust-country').value.trim() || 'India',
            state: document.getElementById('inp-cust-state').value.trim() || null,
            city: document.getElementById('inp-cust-city').value.trim() || null,
            pincode: document.getElementById('inp-cust-pincode').value.trim() || null,
            phone_type_1: document.getElementById('inp-cust-phone-type').value,
            phone_1: fullPhone,
            status: document.getElementById('inp-cust-status').value,
            assigned_employee_id: parseInt(document.getElementById('inp-cust-agent').value) || null,
            notes: document.getElementById('inp-cust-notes').value.trim() || null
        };

        if (!payload.party_name || !rawPhone) {
            api.toast("Party Name and Phone 1 are required", "error");
            return;
        }

        try {
            if (this.editingCustomerId) {
                // Update Existing Customer
                const updated = await api.put(`/customers/${this.editingCustomerId}`, payload);
                api.toast(`Customer ${updated.party_name} updated successfully!`, "success");
                app.closeModal('modal-add-customer');
                this.loadCustomers();
                app.refreshDashboard();
                if (this.currentCustomerId === this.editingCustomerId) {
                    this.openDrawer(this.editingCustomerId);
                }
            } else {
                // Create New Customer
                const newCust = await api.post('/customers', payload);
                api.toast(`Customer ${newCust.party_name} created successfully!`, "success");
                app.closeModal('modal-add-customer');
                this.loadCustomers();
                app.refreshDashboard();
                this.openDrawer(newCust.id);
            }
        } catch (err) {
            api.toast(`Failed to save customer: ${err.message}`, "error");
        }
    },

    openDeleteCustomerModal() {
        app.openModal('modal-delete-customer');
    },

    async executeDeleteCustomer() {
        if (!this.currentCustomerId) return;
        try {
            const res = await api.delete(`/customers/${this.currentCustomerId}`);
            app.closeModal('modal-delete-customer');
            this.closeDrawer();
            api.toast(res.message || "Customer archived successfully", "success");
            this.loadCustomers();
            app.refreshDashboard();
        } catch (err) {
            api.toast(`Failed to delete customer: ${err.message}`, "error");
        }
    },

    openTcsIonPortal() {
        const email = "trng_infotech@khandelia.com";
        const password = "Pass!@#32132";
        const url = "https://training.tcsion.com/Login/Login.html";
        const cust = this.currentCustomerData;
        const partyName = (cust?.party_name || cust?.name || '').trim();

        // Auto copy credentials to clipboard
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(email).then(() => {
                api.toast(`🚀 Opening TCS iON... User: ${email} | Pass: ${password}${partyName ? ` | Party: "${partyName}"` : ''}`, "info", 7000);
            }).catch(() => {
                api.toast(`🚀 Opening TCS iON Portal... User: ${email} | Pass: ${password}`, "info", 5000);
            });
        } else {
            api.toast(`🚀 Opening TCS iON Portal... User: ${email} | Pass: ${password}`, "info", 5000);
        }

        // Open in new tab
        window.open(url, "_blank", "noopener,noreferrer");
    },

    copyTcsCredentials(type) {
        const text = type === 'user' ? 'trng_infotech@khandelia.com' : 'Pass!@#32132';
        const label = type === 'user' ? 'Username / Email' : 'Password';
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(() => {
                api.toast(`✅ TCS iON ${label} copied to clipboard!`, "success");
            }).catch(() => {
                prompt(`Copy ${label}:`, text);
            });
        } else {
            prompt(`Copy ${label}:`, text);
        }
    },

    copyCurrentPartyName() {
        const cust = this.currentCustomerData;
        const partyName = (cust?.party_name || cust?.name || '').trim();
        if (!partyName || partyName === '—') {
            api.toast("No Party Name available to copy.", "warning");
            return;
        }
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(partyName).then(() => {
                api.toast(`📋 Party Name "${partyName}" copied! Paste directly into TCS iON search box.`, "success", 5000);
            }).catch(() => {
                prompt("Copy Party Name:", partyName);
            });
        } else {
            prompt("Copy Party Name:", partyName);
        }
    },

    currentTcsLedgerData: null,
    isTcsSyncing: false,

    updateTcsSyncState(cust) {
        this.currentCustomerData = cust;
        const partyName = (cust?.party_name || cust?.name || '').trim();
        const syncBtn = document.getElementById('btn-drawer-sync-tcs');
        const visualBtn = document.getElementById('btn-drawer-launch-visual');
        const tabSyncBtn = document.getElementById('btn-tab-sync-tcs');
        const noPartyAlert = document.getElementById('tcs-ledger-no-party-alert');
        const partyBadge = document.getElementById('tcs-ledger-party-badge');

        if (partyBadge) {
            partyBadge.textContent = partyName ? `${partyName} (ARSC0010)` : 'Party Ledger Detail (ARSC0010)';
        }

        if (!partyName || partyName === '—') {
            // Disabled state when Party Name is missing
            if (syncBtn) {
                syncBtn.disabled = true;
                syncBtn.style.opacity = '0.55';
                syncBtn.style.cursor = 'not-allowed';
                syncBtn.title = "⚠️ Party Name is missing. Please edit customer profile to add a Party Name.";
            }
            if (visualBtn) {
                visualBtn.disabled = true;
                visualBtn.style.opacity = '0.55';
                visualBtn.style.cursor = 'not-allowed';
            }
            if (tabSyncBtn) {
                tabSyncBtn.disabled = true;
                tabSyncBtn.style.opacity = '0.55';
                tabSyncBtn.style.cursor = 'not-allowed';
            }
            if (noPartyAlert) noPartyAlert.style.display = 'block';
        } else {
            // Enabled state
            if (syncBtn && !this.isTcsSyncing) {
                syncBtn.disabled = false;
                syncBtn.style.opacity = '1';
                syncBtn.style.cursor = 'pointer';
                syncBtn.title = `Scrape Party Ledger Detail Report for "${partyName}" directly from TCS iON`;
            }
            if (visualBtn) {
                visualBtn.disabled = false;
                visualBtn.style.opacity = '1';
                visualBtn.style.cursor = 'pointer';
            }
            if (tabSyncBtn && !this.isTcsSyncing) {
                tabSyncBtn.disabled = false;
                tabSyncBtn.style.opacity = '1';
                tabSyncBtn.style.cursor = 'pointer';
            }
            if (noPartyAlert) noPartyAlert.style.display = 'none';
        }
    },

    async launchVisualTcsLedger() {
        const cust = this.currentCustomerData;
        const partyName = (cust?.party_name || cust?.name || document.getElementById('drawer-cust-party-name')?.textContent || '').trim();

        if (!partyName || partyName === '—') {
            api.toast("Party Name is required to open TCS iON Party Ledger screen.", "warning");
            return;
        }

        const monthsSelect = document.getElementById('sel-tcs-months-back');
        const monthsBack = monthsSelect ? parseInt(monthsSelect.value) || 3 : 3;

        const launchBtn = document.getElementById('btn-drawer-launch-visual');
        const textSpan = document.getElementById('text-launch-visual-btn');

        if (launchBtn) {
            launchBtn.disabled = true;
            launchBtn.style.opacity = '0.75';
        }
        if (textSpan) textSpan.textContent = "Launching Screen...";

        api.toast(`🖥️ Opening real Chrome browser to navigate to Party Ledger for "${partyName}"...`, "info", 6000);

        try {
            const res = await api.post('/integrations/tcsion/launch-visual', {
                customer_id: this.currentCustomerId || null,
                party_name: partyName,
                months_back: monthsBack
            });

            if (res.cooldown) {
                api.toast("⏳ TCS iON Active Session Cooldown: Another session is active. Please wait 2 minutes.", "warning", 8000);
            } else if (res.success) {
                api.toast(`🚀 Live Party Ledger Detail Report screen opened on your desktop!`, "success", 7000);
            } else {
                api.toast(res.message || "Visual Launcher completed.", "info");
            }
        } catch (err) {
            console.error("Visual Launcher Error:", err);
            api.toast(`Visual Launcher Error: ${err.message}`, "error");
        } finally {
            if (launchBtn) {
                launchBtn.disabled = false;
                launchBtn.style.opacity = '1';
            }
            if (textSpan) textSpan.textContent = "🖥️ Auto-Open TCS Screen";
        }
    },

    async syncTcsIonLedger() {
        if (this.isTcsSyncing) return; // Prevent multiple simultaneous clicks

        const cust = this.currentCustomerData;
        const partyName = (cust?.party_name || cust?.name || document.getElementById('drawer-cust-party-name')?.textContent || '').trim();

        if (!partyName || partyName === '—' || partyName === 'Location N/A') {
            api.toast("Party Name is required to sync TCS iON Ledger. Please update Customer Profile first.", "warning");
            return;
        }

        const monthsSelect = document.getElementById('sel-tcs-months-back');
        const monthsBack = monthsSelect ? parseInt(monthsSelect.value) || 3 : 3;

        // Switch to TCS Ledger tab automatically
        this.switchDrawerTab('ledger');

        // Set Loading UI States
        this.isTcsSyncing = true;
        const syncBtn = document.getElementById('btn-drawer-sync-tcs');
        const tabSyncBtn = document.getElementById('btn-tab-sync-tcs');
        const idleIcon = document.getElementById('icon-sync-tcs-idle');
        const spinIcon = document.getElementById('icon-sync-tcs-spinning');
        const btnText = document.getElementById('text-sync-tcs-btn');
        const progressBox = document.getElementById('tcs-ledger-progress-box');
        const stepText = document.getElementById('tcs-progress-step-text');

        if (syncBtn) {
            syncBtn.disabled = true;
            syncBtn.style.opacity = '0.75';
            syncBtn.style.cursor = 'wait';
        }
        if (tabSyncBtn) {
            tabSyncBtn.disabled = true;
            tabSyncBtn.style.opacity = '0.75';
            tabSyncBtn.style.cursor = 'wait';
        }
        if (idleIcon) idleIcon.style.display = 'none';
        if (spinIcon) spinIcon.style.display = 'inline-block';
        if (btnText) btnText.textContent = "Scraping TCS...";
        if (progressBox) progressBox.style.display = 'block';

        const updateStep = (msg) => {
            if (stepText) stepText.textContent = msg;
        };

        updateStep("1/4: Initializing Browser & Authenticating with TCS iON...");
        const stepTimer1 = setTimeout(() => updateStep("2/4: Accessing Finance & Accounting -> Accounts Receivable..."), 3500);
        const stepTimer2 = setTimeout(() => updateStep(`3/4: Opening Party Ledger Report (ARSC0010) & Searching "${partyName}"...`), 8000);
        const stepTimer3 = setTimeout(() => updateStep("4/4: Applying Site Filters & Extracting Ledger Vouchers..."), 13000);

        try {
            const res = await api.post('/integrations/tcsion/ledger', {
                customer_id: this.currentCustomerId || null,
                party_name: partyName,
                months_back: monthsBack
            });

            clearTimeout(stepTimer1);
            clearTimeout(stepTimer2);
            clearTimeout(stepTimer3);

            if (!res || res.success === false) {
                throw new Error(res?.error || "Failed to extract ledger from TCS iON.");
            }

            this.currentTcsLedgerData = res;
            this.renderTcsLedgerTable(res);
            
            if (res.total_records === 0) {
                api.toast(res.message || `No ledger vouchers found for "${partyName}".`, "info", 5000);
            } else {
                api.toast(`✅ TCS iON Ledger for "${partyName}" synced successfully! (${res.total_records} vouchers)`, "success");
            }

        } catch (err) {
            clearTimeout(stepTimer1);
            clearTimeout(stepTimer2);
            clearTimeout(stepTimer3);
            console.error("TCS iON Sync Error:", err);
            
            const errMsg = err.message || "Failed to sync TCS iON ledger";
            this.showTcsLedgerError(errMsg);
            api.toast(`❌ TCS iON Sync Failed: ${errMsg}`, "error", 9000);
        } finally {
            this.isTcsSyncing = false;
            if (syncBtn) {
                syncBtn.disabled = false;
                syncBtn.style.opacity = '1';
                syncBtn.style.cursor = 'pointer';
            }
            if (tabSyncBtn) {
                tabSyncBtn.disabled = false;
                tabSyncBtn.style.opacity = '1';
                tabSyncBtn.style.cursor = 'pointer';
            }
            if (idleIcon) idleIcon.style.display = 'inline-block';
            if (spinIcon) spinIcon.style.display = 'none';
            if (btnText) btnText.textContent = "📥 Scrape from TCS";
            if (progressBox) progressBox.style.display = 'none';
        }
    },

    showTcsLedgerError(errMsg) {
        const tbody = document.getElementById('tbody-tcs-ledger');
        const countEl = document.getElementById('tcs-ledger-count');
        const subtitleEl = document.getElementById('tcs-ledger-subtitle');
        const kpiOpening = document.getElementById('kpi-tcs-opening');
        const kpiDebit = document.getElementById('kpi-tcs-debit');
        const kpiCredit = document.getElementById('kpi-tcs-credit');
        const kpiClosing = document.getElementById('kpi-tcs-closing');

        if (countEl) countEl.textContent = '0 vouchers';
        if (kpiOpening) kpiOpening.textContent = '₹0.00';
        if (kpiDebit) kpiDebit.textContent = '₹0.00';
        if (kpiCredit) kpiCredit.textContent = '₹0.00';
        if (kpiClosing) kpiClosing.textContent = '₹0.00';

        if (subtitleEl) {
            subtitleEl.innerHTML = `<span style="color: #ef4444; font-weight: 700;">⚠️ Sync Error: ${errMsg}</span>`;
        }

        if (tbody) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="7" style="text-align: center; padding: 3rem 1.5rem;">
                        <div style="font-size: 2rem; margin-bottom: 0.75rem;">⚠️</div>
                        <div style="font-size: 1rem; font-weight: 800; color: #ef4444; margin-bottom: 0.5rem;">
                            TCS iON Live Sync Error
                        </div>
                        <div style="font-size: 0.85rem; color: #cbd5e1; max-width: 540px; margin: 0 auto; background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); padding: 0.85rem 1.25rem; border-radius: 8px; line-height: 1.5;">
                            ${errMsg}
                        </div>
                        <div style="margin-top: 1rem; font-size: 0.8rem; color: var(--text-muted, #94a3b8);">
                            Tip: You can use <strong>[🖥️ Auto-Open TCS Screen]</strong> to navigate visually on your desktop or upload an export file.
                        </div>
                    </td>
                </tr>
            `;
        }
    },

    renderTcsLedgerTable(data) {
        const tbody = document.getElementById('tbody-tcs-ledger');
        const countEl = document.getElementById('tcs-ledger-count');
        const subtitleEl = document.getElementById('tcs-ledger-subtitle');
        const kpiOpening = document.getElementById('kpi-tcs-opening');
        const kpiDebit = document.getElementById('kpi-tcs-debit');
        const kpiCredit = document.getElementById('kpi-tcs-credit');
        const kpiClosing = document.getElementById('kpi-tcs-closing');

        if (!data || !tbody) return;

        const summary = data.summary || {};
        const records = data.records || [];

        if (countEl) countEl.textContent = records.length;
        if (subtitleEl && data.from_date && data.to_date) {
            subtitleEl.textContent = `Period: ${data.from_date} to ${data.to_date} | Synced: ${new Date().toLocaleTimeString()} (${data.source || 'TCS iON'})`;
        }

        // Format currency numbers with Indian commas
        const fmtCur = (val) => {
            const num = parseFloat(val) || 0;
            return '₹' + num.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        };

        if (kpiOpening) kpiOpening.textContent = fmtCur(summary.opening_balance || 0);
        if (kpiDebit) kpiDebit.textContent = fmtCur(summary.total_debit || 0);
        if (kpiCredit) kpiCredit.textContent = fmtCur(summary.total_credit || 0);
        if (kpiClosing) {
            kpiClosing.textContent = fmtCur(summary.closing_balance || 0);
            kpiClosing.style.color = (summary.closing_balance || 0) > 0 ? 'var(--danger)' : 'var(--success)';
        }

        if (records.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="7" style="text-align: center; color: var(--text-muted); padding: 2rem;">
                        No voucher records found in TCS iON for party <strong>"${data.party_name}"</strong> in the selected period.
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = records.map(r => `
            <tr>
                <td style="font-weight: 700; font-family: monospace; color: var(--primary);">${this.escapeHtml(r.voucher_number || '—')}</td>
                <td style="white-space: nowrap; font-size: 0.8125rem;">${this.escapeHtml(r.voucher_date || '—')}</td>
                <td><span class="badge badge-standard" style="font-size: 0.75rem;">${this.escapeHtml(r.voucher_sub_type || 'General')}</span></td>
                <td style="font-size: 0.8125rem; max-width: 240px; word-break: break-word;">${this.escapeHtml(r.particulars || '—')}</td>
                <td style="text-align: right; font-weight: 600; color: ${r.debit_amount > 0 ? 'var(--danger)' : 'var(--text-muted)'};">${r.debit_amount > 0 ? fmtCur(r.debit_amount) : '—'}</td>
                <td style="text-align: right; font-weight: 600; color: ${r.credit_amount > 0 ? 'var(--success)' : 'var(--text-muted)'};">${r.credit_amount > 0 ? fmtCur(r.credit_amount) : '—'}</td>
                <td style="text-align: right; font-weight: 700; color: var(--text-primary);">${fmtCur(r.balance_amount || 0)}</td>
            </tr>
        `).join('');
    },

    exportTcsLedgerCSV() {
        if (!this.currentTcsLedgerData || !this.currentTcsLedgerData.records || this.currentTcsLedgerData.records.length === 0) {
            api.toast("No ledger records available to export", "warning");
            return;
        }

        const data = this.currentTcsLedgerData;
        const rows = [
            ["Voucher No", "Voucher Date", "Voucher Type", "Particulars", "Debit (INR)", "Credit (INR)", "Balance (INR)"]
        ];

        data.records.forEach(r => {
            rows.push([
                `"${r.voucher_number || ''}"`,
                `"${r.voucher_date || ''}"`,
                `"${r.voucher_sub_type || ''}"`,
                `"${(r.particulars || '').replace(/"/g, '""')}"`,
                r.debit_amount || 0,
                r.credit_amount || 0,
                r.balance_amount || 0
            ]);
        });

        const csvContent = "data:text/csv;charset=utf-8," + rows.map(e => e.join(",")).join("\n");
        const encodedUri = encodeURI(csvContent);
        const link = document.createElement("a");
        link.setAttribute("href", encodedUri);
        link.setAttribute("download", `TCS_Ledger_${(data.party_name || 'Customer').replace(/\s+/g, '_')}_${new Date().toISOString().slice(0, 10)}.csv`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        api.toast("✅ TCS Ledger CSV downloaded successfully!", "success");
    },

    exportTcsLedgerExcel() {
        this.exportTcsLedgerCSV();
    },

    async handleTcsFileUpload(inputEl) {
        if (!inputEl || !inputEl.files || inputEl.files.length === 0) return;
        const file = inputEl.files[0];

        const cust = this.currentCustomerData;
        const partyName = (cust?.party_name || cust?.name || document.getElementById('drawer-cust-party-name')?.textContent || '').trim();

        const formData = new FormData();
        formData.append('file', file);
        if (this.currentCustomerId) formData.append('customer_id', this.currentCustomerId);
        if (partyName) formData.append('party_name', partyName);

        try {
            api.toast(`⏳ Parsing TCS iON export (${file.name})...`, "info");
            const res = await api.post('/integrations/tcsion/upload-ledger', formData);
            
            this.currentTcsLedgerData = res;
            this.renderTcsLedgerTable(res);
            api.toast(`✅ Successfully imported ${res.total_records || 0} vouchers from ${file.name}!`, "success");
        } catch (err) {
            console.error("TCS File Upload Error:", err);
            api.toast(`Failed to parse TCS iON file: ${err.message}`, "error");
        } finally {
            inputEl.value = "";
        }
    }
};

window.customer = customer;
