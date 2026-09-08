/**
 * Customer Directory, Profile 360° Drawer, Edit Manager, and Unified Timeline (15 Columns Schema)
 */
const customer = {
    currentPage: 1,
    limit: 15,
    currentCustomerTab: 'all',
    assignedFocusPage: 1,
    assignedFocusLimit: 15,
    assignedFocusTotal: 0,
    assignedFocusTotalPages: 1,
    assignedSearchTimer: null,
    currentCustomerId: null,
    editingCustomerId: null,
    selectedCategory: 'ALL',
    businessCategories: [
        { code: 'ALL', name: 'All Categories' },
        { code: 'By Product', name: 'By Product' },
        { code: 'HUSK', name: 'HUSK' },
        { code: 'SAS', name: 'SAS' },
        { code: 'MRO', name: 'MRO' },
        { code: 'MCK', name: 'MCK' },
        { code: 'DOC', name: 'DOC' },
        { code: 'MSD', name: 'MSD' },
        { code: 'MOL', name: 'MOL' },
        { code: 'MOMT', name: 'MOMT' },
        { code: 'General', name: 'General' }
    ],

    escapeHtml(str) {
        if (str === null || str === undefined) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    },

    init() {
        this.initCategoryTabs();

        const searchInput = document.getElementById('customers-filter-search');
        const statusSelect = document.getElementById('customers-filter-status');
        const categorySelect = document.getElementById('customers-filter-category');
        const agentSelect = document.getElementById('customers-filter-agent');

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
        if (categorySelect) categorySelect.addEventListener('change', () => { this.currentPage = 1; this.loadCustomers(); });
        if (agentSelect) agentSelect.addEventListener('change', () => { this.currentPage = 1; this.loadCustomers(); });

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
            if (document.getElementById('dinp-category')) {
                document.getElementById('dinp-category').value = c.category || 'General';
            }
            document.getElementById('dinp-address-date').value = c.address_date || '';
            document.getElementById('dinp-addr1').value = c.address_line_1 || c.address || '';
            document.getElementById('dinp-addr2').value = c.address_line_2 || '';
            document.getElementById('dinp-addr3').value = c.address_line_3 || '';
            document.getElementById('dinp-country').value = c.country || 'India';
            document.getElementById('dinp-state').value = c.state || '';
            if (document.getElementById('dinp-district')) {
                document.getElementById('dinp-district').value = c.district || '';
            }
            document.getElementById('dinp-city').value = c.city || '';
            document.getElementById('dinp-pincode').value = c.pincode || '';
            if (document.getElementById('dinp-zone')) {
                document.getElementById('dinp-zone').value = c.zone || '';
            }
            if (document.getElementById('dinp-website')) {
                document.getElementById('dinp-website').value = c.company_website || '';
            }
            if (document.getElementById('dinp-sales-region')) {
                document.getElementById('dinp-sales-region').value = c.sales_region_code || '';
            }
            document.getElementById('dinp-contact-person').value = c.contact_person_1 || '';
            document.getElementById('dinp-email').value = c.email_id_1 || c.email || '';
            document.getElementById('dinp-phone-type').value = c.phone_type_1 || 'Mobile';
            document.getElementById('dinp-phone1').value = c.phone_1 || c.mobile || '';
            if (document.getElementById('dinp-contact-person-2')) {
                document.getElementById('dinp-contact-person-2').value = c.contact_person_2 || '';
            }
            if (document.getElementById('dinp-email-2')) {
                document.getElementById('dinp-email-2').value = c.email_id_2 || '';
            }
            if (document.getElementById('dinp-phone-2')) {
                document.getElementById('dinp-phone-2').value = c.phone_2 || '';
            }
            if (document.getElementById('dinp-contact-person-3')) {
                document.getElementById('dinp-contact-person-3').value = c.contact_person_3 || '';
            }
            if (document.getElementById('dinp-email-3')) {
                document.getElementById('dinp-email-3').value = c.email_id_3 || '';
            }
            if (document.getElementById('dinp-phone-3')) {
                document.getElementById('dinp-phone-3').value = c.phone_3 || '';
            }
            if (document.getElementById('dinp-notes')) {
                document.getElementById('dinp-notes').value = c.notes || '';
            }
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
                                        <span class="badge badge-standard">${this.escapeHtml(doc.category)}</span>
                                        <span style="font-size: 0.75rem; color: var(--text-muted);">${sizeStr}</span>
                                        <span style="font-size: 0.75rem; color: var(--text-muted);">${uploadDateStr}</span>
                                        <span style="font-size: 0.75rem; color: var(--text-muted);">${this.escapeHtml(uploadedByStr)}</span>
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
            category: document.getElementById('dinp-category') ? document.getElementById('dinp-category').value.trim() : 'General',
            address_date: document.getElementById('dinp-address-date').value.trim() || null,
            address_line_1: document.getElementById('dinp-addr1').value.trim() || null,
            address_line_2: document.getElementById('dinp-addr2').value.trim() || null,
            address_line_3: document.getElementById('dinp-addr3').value.trim() || null,
            country: document.getElementById('dinp-country').value.trim() || 'India',
            state: document.getElementById('dinp-state').value.trim() || null,
            district: document.getElementById('dinp-district') ? document.getElementById('dinp-district').value.trim() || null : null,
            city: document.getElementById('dinp-city').value.trim() || null,
            pincode: document.getElementById('dinp-pincode').value.trim() || null,
            zone: document.getElementById('dinp-zone') ? document.getElementById('dinp-zone').value.trim() || null : null,
            company_website: document.getElementById('dinp-website') ? document.getElementById('dinp-website').value.trim() || null : null,
            sales_region_code: document.getElementById('dinp-sales-region') ? document.getElementById('dinp-sales-region').value.trim() || null : null,
            contact_person_1: document.getElementById('dinp-contact-person').value.trim() || null,
            email_id_1: document.getElementById('dinp-email').value.trim() || null,
            phone_type_1: document.getElementById('dinp-phone-type').value,
            phone_1: document.getElementById('dinp-phone1').value.trim(),
            contact_person_2: document.getElementById('dinp-contact-person-2') ? document.getElementById('dinp-contact-person-2').value.trim() || null : null,
            email_id_2: document.getElementById('dinp-email-2') ? document.getElementById('dinp-email-2').value.trim() || null : null,
            phone_2: document.getElementById('dinp-phone-2') ? document.getElementById('dinp-phone-2').value.trim() || null : null,
            contact_person_3: document.getElementById('dinp-contact-person-3') ? document.getElementById('dinp-contact-person-3').value.trim() || null : null,
            email_id_3: document.getElementById('dinp-email-3') ? document.getElementById('dinp-email-3').value.trim() || null : null,
            phone_3: document.getElementById('dinp-phone-3') ? document.getElementById('dinp-phone-3').value.trim() || null : null,
            notes: document.getElementById('dinp-notes') ? document.getElementById('dinp-notes').value.trim() || null : null,
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

    switchCustomerViewTab(tabName) {
        this.currentCustomerTab = tabName;
        const btnAll = document.getElementById('tab-cust-all');
        const btnAssigned = document.getElementById('tab-cust-assigned');
        const paneAll = document.getElementById('pane-cust-all');
        const paneAssigned = document.getElementById('pane-cust-assigned');

        if (tabName === 'assigned') {
            btnAll?.classList.remove('active');
            btnAssigned?.classList.add('active');
            if (paneAll) paneAll.style.display = 'none';
            if (paneAssigned) paneAssigned.style.display = 'block';
            this.assignedFocusPage = 1;
            this.loadAssignedFocusCustomers();
        } else {
            btnAssigned?.classList.remove('active');
            btnAll?.classList.add('active');
            if (paneAssigned) paneAssigned.style.display = 'none';
            if (paneAll) paneAll.style.display = 'block';
            this.currentPage = 1;
            this.loadCustomers();
        }
    },

    debounceAssignedSearch() {
        clearTimeout(this.assignedSearchTimer);
        this.assignedSearchTimer = setTimeout(() => {
            this.assignedFocusPage = 1;
            this.loadAssignedFocusCustomers();
        }, 200);
    },

    assignedPrevPage() {
        if (this.assignedFocusPage > 1) {
            this.assignedFocusPage--;
            this.loadAssignedFocusCustomers();
        }
    },

    assignedNextPage() {
        if (this.assignedFocusPage < this.assignedFocusTotalPages) {
            this.assignedFocusPage++;
            this.loadAssignedFocusCustomers();
        }
    },

    async loadAssignedFocusCustomers() {
        const tbody = document.getElementById('assigned-focus-table-body');
        if (!tbody) return;

        // Render skeleton rows
        tbody.innerHTML = Array.from({ length: 6 }).map(() => `
            <tr class="skeleton-row">
                <td><div class="skeleton" style="width: 85px; height: 18px; border-radius: 12px;"></div></td>
                <td><div class="skeleton" style="width: 70px; height: 14px;"></div></td>
                <td><div class="skeleton" style="width: 140px; height: 14px;"></div></td>
                <td><div class="skeleton" style="width: 100px; height: 13px;"></div></td>
                <td><div class="skeleton" style="width: 110px; height: 14px;"></div></td>
                <td><div class="skeleton" style="width: 90px; height: 16px;"></div></td>
                <td><div class="skeleton" style="width: 90px; height: 13px;"></div></td>
                <td><div class="skeleton" style="width: 180px; height: 13px;"></div></td>
                <td><div class="skeleton" style="width: 120px; height: 26px; border-radius: 4px;"></div></td>
            </tr>
        `).join('');

        const currentUser = api.getCurrentUser();
        const isAdmin = currentUser && (currentUser.role === 'admin' || currentUser.email === 'infotech@khandelia.com' || currentUser.email === 'itchd.kogm@gmail.com');
        const adminFilterBox = document.getElementById('assigned-focus-admin-filter');
        const employeeSelect = document.getElementById('assigned-focus-employee-select');
        const agentLabel = document.getElementById('assigned-focus-agent-label');

        let targetEmployeeId = null;

        if (isAdmin) {
            if (adminFilterBox) adminFilterBox.style.display = 'flex';
            if (agentLabel) agentLabel.textContent = 'Team Priority Focus Accounts';

            // Populate employee select if empty
            if (employeeSelect && employeeSelect.options.length === 0) {
                try {
                    const employees = await api.get('/employees');
                    const teamEmployees = employees.filter(e => e.role !== 'admin');
                    employeeSelect.innerHTML = `
                        <option value="all">Entire Team (All Assigned Employees)</option>
                        ${teamEmployees.map(e => `<option value="${e.id}">${this.escapeHtml(e.full_name)} (${(e.designation || e.role).toUpperCase()})</option>`).join('')}
                    `;
                    employeeSelect.value = "all";
                } catch (e) {
                    console.error("Error populating assigned focus employee select:", e);
                }
            }

            if (employeeSelect && employeeSelect.value && employeeSelect.value !== 'all') {
                targetEmployeeId = parseInt(employeeSelect.value, 10);
            }
        } else {
            if (adminFilterBox) adminFilterBox.style.display = 'none';
            if (agentLabel) agentLabel.textContent = `My Assigned Accounts (${currentUser?.full_name || 'My Focus'})`;
            targetEmployeeId = currentUser?.id || null;
        }

        const search = document.getElementById('assigned-focus-filter-search')?.value.trim() || '';

        try {
            let url = `/customers?page=${this.assignedFocusPage}&limit=${this.assignedFocusLimit}`;
            if (targetEmployeeId) {
                url += `&assigned_employee_id=${targetEmployeeId}`;
            } else if (isAdmin) {
                url += `&assigned_role=employee`;
            }
            if (search) {
                url += `&search=${encodeURIComponent(search)}`;
            }

            const data = await api.get(url);
            this.assignedFocusTotal = data.total;
            this.assignedFocusTotalPages = data.total_pages;

            const totalFormatted = (window.app && typeof app.formatFullNumber === 'function') ? app.formatFullNumber(data.total) : data.total;
            const startNum = data.items.length > 0 ? ((data.page - 1) * this.assignedFocusLimit + 1) : 0;
            const endNum = Math.min(data.page * this.assignedFocusLimit, data.total);
            
            const pageInfo = document.getElementById('assigned-focus-pagination-info');
            if (pageInfo) {
                pageInfo.textContent = `Showing ${startNum} to ${endNum} of ${totalFormatted} assigned focus accounts (Page ${data.page} of ${data.total_pages})`;
            }

            const badge = document.getElementById('nav-badge-assigned-focus');
            if (badge) {
                badge.textContent = (window.app && typeof app.formatNumberDisplay === 'function') ? app.formatNumberDisplay(data.total) : data.total;
            }

            if (data.items.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="9" style="text-align: center; color: var(--text-muted); padding: 2.5rem 1rem;">
                            <div style="margin-bottom: 0.5rem; color: var(--primary);">${Icons.get('user-check', { size: 28 })}</div>
                            <div style="font-weight: 600; color: var(--text-primary); margin-bottom: 0.25rem;">No assigned focus customers found</div>
                            <div style="font-size: 0.8125rem;">Customers assigned to team members by admin will appear here for high-priority handling.</div>
                        </td>
                    </tr>
                `;
                return;
            }

            tbody.innerHTML = data.items.map(c => {
                const partyCode = c.party_code || c.customer_id || '—';
                const partyName = c.party_name || c.name || '—';
                const phone1 = c.phone_1 || c.mobile || '—';
                const contactPerson = c.contact_person_1 || '—';
                const assignedEmpName = c.assigned_employee?.full_name || 'Unassigned';

                // Rating & Tier
                const r = Math.max(0, Math.min(5, parseInt(c.rating, 10) || 0));
                let starsHtml = '';
                for (let i = 1; i <= 5; i++) {
                    if (i <= r) {
                        starsHtml += `<svg width="12" height="12" viewBox="0 0 24 24" style="fill: #F59E0B; stroke: #F59E0B; stroke-width: 1px;"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>`;
                    } else {
                        starsHtml += `<svg width="12" height="12" viewBox="0 0 24 24" style="fill: rgba(245, 158, 11, 0.04); stroke: #F59E0B; stroke-width: 1.5px; opacity: 0.85;"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>`;
                    }
                }

                // Determine priority from notes
                let priorityLabel = "High Attention";
                let priorityClass = "badge-warning";
                if (c.notes && c.notes.includes("[Urgent Priority]")) {
                    priorityLabel = "Urgent Priority";
                    priorityClass = "badge-danger";
                } else if (c.notes && c.notes.includes("[VIP Client]")) {
                    priorityLabel = "VIP Account";
                    priorityClass = "badge-vip";
                } else if (c.notes && c.notes.includes("[Standard Follow-up]")) {
                    priorityLabel = "Special Focus";
                    priorityClass = "badge-standard";
                }

                // Clean display note
                let cleanNote = c.notes || 'Special priority account assigned for proactive follow-up.';
                if (cleanNote.length > 90) cleanNote = cleanNote.substring(0, 87) + '...';

                return `
                    <tr style="cursor: pointer; background: rgba(245, 158, 11, 0.02);" onclick="customer.openDrawer(${c.id})">
                        <td>
                            <span class="badge ${priorityClass}" style="font-size: 0.72rem; font-weight: 700;">${priorityLabel}</span>
                        </td>
                        <td><span class="badge badge-standard">${partyCode}</span></td>
                        <td>
                            <div style="font-weight: 700; color: var(--text-primary); font-size: 0.875rem;">${this.escapeHtml(partyName)}</div>
                            <div style="font-size: 0.72rem; color: var(--text-muted);">${c.city || ''} ${c.state ? '• ' + c.state : ''}</div>
                        </td>
                        <td><div style="font-weight: 600; color: var(--text-secondary);">${this.escapeHtml(contactPerson)}</div></td>
                        <td>
                            <div style="font-weight: 700; color: var(--primary); font-variant-numeric: tabular-nums;">${this.escapeHtml(phone1)}</div>
                        </td>
                        <td>
                            <div style="display: flex; align-items: center; gap: 4px;">
                                <div style="display: flex; gap: 1px;">${starsHtml}</div>
                                <span style="font-size: 0.72rem; font-weight: 700; color: var(--text-secondary);">${r > 0 ? r + '.0' : '—'}</span>
                            </div>
                            <div style="font-size: 0.68rem; color: var(--text-muted); margin-top: 1px;">${this.escapeHtml(c.category || 'Regular')}</div>
                        </td>
                        <td>
                            <div style="display: flex; align-items: center; gap: 5px;">
                                <div style="width: 22px; height: 22px; border-radius: 50%; background: var(--primary-subtle); color: var(--primary); font-size: 0.65rem; font-weight: 700; display: flex; align-items: center; justify-content: center;">
                                    ${assignedEmpName.substring(0, 2).toUpperCase()}
                                </div>
                                <span style="font-weight: 600; font-size: 0.78rem;">${this.escapeHtml(assignedEmpName)}</span>
                            </div>
                        </td>
                        <td>
                            <div style="font-size: 0.75rem; color: var(--text-secondary); max-width: 260px; line-height: 1.35;" title="${this.escapeHtml(c.notes || '')}">
                                ${this.escapeHtml(cleanNote)}
                            </div>
                        </td>
                        <td>
                            <div style="display: flex; gap: 0.25rem; align-items: center;" onclick="event.stopPropagation();">
                                <button class="btn btn-success btn-xs" onclick="cti.makeOutgoingCall('${this.escapeHtml(phone1)}', ${c.id})" title="Direct Call" style="font-weight: 700; height: 26px; padding: 0 7px;">
                                    ${Icons.get('phone', { size: 12 })}
                                    <span>Call</span>
                                </button>
                                <button class="btn btn-warning btn-xs" onclick="customer.openAssignModal(${c.id})" title="Re-Assign / Update Priority" style="height: 26px; padding: 0 7px; background: rgba(245,158,11,0.15); color: #D97706; border: 1px solid rgba(245,158,11,0.35);">
                                    ${Icons.get('user-plus', { size: 12 })} <span>Assign</span>
                                </button>
                                <button class="btn btn-secondary btn-xs" onclick="customer.openDrawer(${c.id})" title="View 360° Profile" style="height: 26px; padding: 0 7px;">
                                    ${Icons.get('eye', { size: 12 })}
                                </button>
                            </div>
                        </td>
                    </tr>
                `;
            }).join('');

        } catch (err) {
            console.error("Error loading assigned focus customers:", err);
            tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--danger);">Failed to load assigned focus customers</td></tr>`;
        }
    },

    async openAssignModal(customerId) {
        if (!customerId) return;
        try {
            const cust = await api.get(`/customers/${customerId}`);
            document.getElementById('inp-assign-cust-id').value = cust.id;
            document.getElementById('modal-assign-cust-name').textContent = cust.party_name || cust.name || 'Customer';
            document.getElementById('modal-assign-cust-phone').textContent = cust.phone_1 || cust.mobile || '—';
            
            const currentAgentBadge = document.getElementById('modal-assign-current-agent');
            if (currentAgentBadge) {
                currentAgentBadge.textContent = cust.assigned_employee ? `Currently: ${cust.assigned_employee.full_name}` : 'Currently: Unassigned';
            }

            const employeeSelect = document.getElementById('inp-assign-employee-select');
            if (employeeSelect) {
                const employees = await api.get('/employees');
                employeeSelect.innerHTML = employees.map(e => `
                    <option value="${e.id}">${this.escapeHtml(e.full_name)} (${e.role.toUpperCase()}) — ${this.escapeHtml(e.email)}</option>
                `).join('');

                if (cust.assigned_employee_id) {
                    employeeSelect.value = cust.assigned_employee_id;
                }
            }

            document.getElementById('inp-assign-instructions').value = '';
            document.getElementById('inp-assign-priority').value = 'High Attention';

            app.openModal('modal-assign-customer');
        } catch (err) {
            api.toast(`Error preparing assignment modal: ${err.message}`, "error");
        }
    },

    async submitAssignCustomer() {
        const custId = document.getElementById('inp-assign-cust-id')?.value;
        const employeeId = document.getElementById('inp-assign-employee-select')?.value;
        const priority = document.getElementById('inp-assign-priority')?.value || 'High Attention';
        const instructions = document.getElementById('inp-assign-instructions')?.value.trim() || '';
        const btn = document.getElementById('btn-submit-assign-customer');

        if (!custId || !employeeId) {
            api.toast("Please select an employee to assign this customer", "error");
            return;
        }

        if (btn) {
            btn.disabled = true;
            btn.textContent = "Assigning & Dispatching Email...";
        }

        try {
            const updated = await api.post(`/customers/${custId}/assign`, {
                employee_id: parseInt(employeeId, 10),
                priority_level: priority,
                instruction_notes: instructions
            });

            api.toast(`Assigned to ${updated.assigned_employee?.full_name || 'Employee'}! Priority notification email sent.`, "success");
            app.closeModal('modal-assign-customer');

            // Refresh UI tables
            this.loadAssignedFocusCustomers();
            this.loadCustomers();
            if (this.currentCustomerId === parseInt(custId, 10)) {
                this.populateDrawerFields(updated);
                this.loadTimeline(custId, this.currentTimelineFilter);
            }
            app.refreshDashboard();
        } catch (err) {
            api.toast(`Assignment failed: ${err.message}`, "error");
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = `<svg class="icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg><span>Assign &amp; Send Email</span>`;
            }
        }
    },

    getCategoryIconSvg(code) {
        const icons = {
            'ALL': `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>`,
            'By Product': `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/></svg>`,
            'HUSK': `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M7 20h10"/><path d="M10 20c0-4.5 3-7 5-11"/><path d="M15 9c2 0 4-1 4-4-3 0-5 2-5 4z"/><path d="M13 13c-2 0-4-1-4-4 3 0 5 2 5 4z"/></svg>`,
            'SAS': `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>`,
            'MRO': `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>`,
            'MCK': `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>`,
            'DOC': `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="1" y="3" width="15" height="13"/><polygon points="16 8 20 8 23 11 23 16 16 16 16 8"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/></svg>`,
            'MSD': `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>`,
            'MOL': `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z"/></svg>`,
            'MOMT': `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 12l-8.5 8.5a2.12 2.12 0 0 1-3-3L12 9"/><path d="M17.64 4.36a9 9 0 0 0-1.92-1.28L14 4.5l3.5 3.5 1.42-1.72c-.4-.7-.84-1.35-1.28-1.92z"/></svg>`,
            'General': `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="2" width="16" height="20" rx="2" ry="2"/><line x1="9" y1="22" x2="9" y2="22.01"/><line x1="15" y1="22" x2="15" y2="22.01"/><line x1="9" y1="6" x2="9" y2="6.01"/><line x1="15" y1="6" x2="15" y2="6.01"/><line x1="9" y1="10" x2="9" y2="10.01"/><line x1="15" y1="10" x2="15" y2="10.01"/><line x1="9" y1="14" x2="9" y2="14.01"/><line x1="15" y1="14" x2="15" y2="14.01"/></svg>`
        };
        return icons[code] || icons['General'];
    },

    getCategoryStyle(code) {
        const styles = {
            'DOC': { bg: 'rgba(59, 130, 246, 0.12)', color: '#2563EB', border: 'rgba(59, 130, 246, 0.35)' },
            'HUSK': { bg: 'rgba(16, 185, 129, 0.12)', color: '#059669', border: 'rgba(16, 185, 129, 0.35)' },
            'SAS': { bg: 'rgba(139, 92, 246, 0.12)', color: '#7C3AED', border: 'rgba(139, 92, 246, 0.35)' },
            'MRO': { bg: 'rgba(6, 182, 212, 0.12)', color: '#0891B2', border: 'rgba(6, 182, 212, 0.35)' },
            'MCK': { bg: 'rgba(249, 115, 22, 0.12)', color: '#EA580C', border: 'rgba(249, 115, 22, 0.35)' },
            'MSD': { bg: 'rgba(100, 116, 139, 0.12)', color: '#475569', border: 'rgba(100, 116, 139, 0.35)' },
            'MOL': { bg: 'rgba(234, 179, 8, 0.15)', color: '#CA8A04', border: 'rgba(234, 179, 8, 0.35)' },
            'MOMT': { bg: 'rgba(225, 29, 72, 0.12)', color: '#E11D48', border: 'rgba(225, 29, 72, 0.35)' },
            'General': { bg: 'rgba(99, 102, 241, 0.12)', color: '#4F46E5', border: 'rgba(99, 102, 241, 0.35)' },
            'By Product': { bg: 'rgba(20, 184, 166, 0.12)', color: '#0D9488', border: 'rgba(20, 184, 166, 0.35)' }
        };
        return styles[code] || styles['General'];
    },

    getCategoryBadgeHtml(catCode) {
        return this.renderCategoryBadgeHtml(catCode);
    },

    renderCategoryBadgeHtml(catCode) {
        if (!catCode) return '';
        const style = this.getCategoryStyle(catCode);
        const iconSvg = this.getCategoryIconSvg(catCode);
        return `
            <span class="badge" style="background: ${style.bg}; color: ${style.color}; border: 1px solid ${style.border}; font-weight: 700; display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 6px; letter-spacing: 0.02em;">
                <span style="display: inline-flex; align-items: center;">${iconSvg}</span>
                <span>${this.escapeHtml(catCode)}</span>
            </span>
        `;
    },

    initCategoryTabs() {
        const bar = document.getElementById('customer-category-tabs-bar');
        if (!bar) return;

        const user = (typeof api !== 'undefined' && api.getCurrentUser) ? api.getCurrentUser() : null;
        let allowedCats = [];
        if (user) {
            let raw = user.allowed_categories;
            if (Array.isArray(raw)) {
                allowedCats = raw.map(c => String(c).trim().toUpperCase());
            } else if (typeof raw === 'string') {
                let s = raw.replace(/[\[\]\'\"]/g, '').trim();
                if (s) allowedCats = s.split(',').map(c => c.trim().toUpperCase());
            }
        }
        const hasAllAccess = !user || user.role === 'admin' || user.role === 'ADMIN' || allowedCats.length === 0 || allowedCats.includes('*') || allowedCats.includes('ALL') || allowedCats.length >= 10;

        const visibleCategories = this.businessCategories.filter(cat => {
            if (cat.code === 'ALL') return true;
            if (hasAllAccess) return true;
            return allowedCats.includes(cat.code.toUpperCase());
        });

        bar.innerHTML = visibleCategories.map(cat => {
            const isActive = this.selectedCategory === cat.code;
            const svgIcon = this.getCategoryIconSvg(cat.code);
            return `
                <button type="button" class="btn btn-sm ${isActive ? 'btn-primary' : 'btn-secondary'}" 
                    id="btn-cust-cat-${cat.code.replace(/\s+/g, '-')}"
                    onclick="customer.switchCategoryTab('${cat.code}')"
                    style="display: inline-flex; align-items: center; gap: 6px; font-weight: 600; font-size: 0.78rem; padding: 0.35rem 0.8rem; border-radius: 20px; white-space: nowrap; flex-shrink: 0;">
                    <span style="display: inline-flex; align-items: center;">${svgIcon}</span>
                    <span>${cat.name}</span>
                </button>
            `;
        }).join('');

        this.updateCategoryIndicator();
    },

    switchCategoryTab(catCode) {
        this.selectedCategory = catCode;
        this.currentPage = 1;

        // Update active tab buttons
        const bar = document.getElementById('customer-category-tabs-bar');
        if (bar) {
            bar.querySelectorAll('button').forEach(btn => {
                btn.className = 'btn btn-sm btn-secondary';
            });
            const activeBtn = document.getElementById(`btn-cust-cat-${catCode.replace(/\s+/g, '-')}`);
            if (activeBtn) {
                activeBtn.className = 'btn btn-sm btn-primary';
            }
        }

        this.updateCategoryIndicator();
        this.loadCustomers();
    },

    updateCategoryIndicator() {
        const indicator = document.getElementById('cust-active-category-indicator');
        const purgeBtn = document.getElementById('btn-purge-active-cat');
        const purgeLabel = document.getElementById('btn-purge-active-cat-label');
        const user = (typeof api !== 'undefined' && api.getCurrentUser) ? api.getCurrentUser() : null;
        const isAdmin = user && (user.role === 'admin' || user.role === 'ADMIN');

        if (indicator) {
            if (this.selectedCategory === 'ALL') {
                indicator.textContent = 'Showing All Categories';
                indicator.className = 'badge badge-standard';
            } else {
                indicator.textContent = `Showing: ${this.selectedCategory}`;
                indicator.className = 'badge badge-active';
            }
        }

        if (purgeBtn) {
            if (isAdmin && this.selectedCategory && this.selectedCategory !== 'ALL') {
                purgeBtn.style.display = 'inline-flex';
                if (purgeLabel) purgeLabel.textContent = `Reset ${this.selectedCategory} Data`;
            } else {
                purgeBtn.style.display = 'none';
            }
        }
    },

    openPurgeForActiveCategory() {
        if (typeof admin !== 'undefined' && admin.openPurgeCustomersModal) {
            admin.openPurgeCustomersModal(this.selectedCategory || 'ALL');
        }
    },

    _customerCache: {},

    async loadCustomers() {
        const tbody = document.getElementById('customers-table-body');
        if (!tbody) return;

        const search = document.getElementById('customers-filter-search')?.value.trim() || '';
        const status = document.getElementById('customers-filter-status')?.value || '';
        const categorySelectVal = document.getElementById('customers-filter-category')?.value || '';
        const category = (this.selectedCategory && this.selectedCategory !== 'ALL') ? this.selectedCategory : categorySelectVal;
        const agentId = document.getElementById('customers-filter-agent')?.value;

        let url = `/customers?page=${this.currentPage}&limit=${this.limit}`;
        if (search) url += `&search=${encodeURIComponent(search)}`;
        if (status) url += `&status=${encodeURIComponent(status)}`;
        if (category) url += `&category=${encodeURIComponent(category)}`;
        if (agentId !== undefined && agentId !== null && agentId !== '') {
            url += `&assigned_employee_id=${encodeURIComponent(agentId)}`;
        }

        // Instant SWR: If cached data exists for this exact filter/page, render in 0ms!
        if (this._customerCache[url]) {
            this.renderCustomerTable(this._customerCache[url]);
        } else {
            // Render shimmering skeleton rows only on initial fetch
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
        }

        try {
            const data = await api.get(url);
            this._customerCache[url] = data;
            this.renderCustomerTable(data);

            // Background refresh assigned badge
            const curUser = api.getCurrentUser();
            const isAdm = curUser && (curUser.role === 'admin' || curUser.email === 'infotech@khandelia.com' || curUser.email === 'itchd.kogm@gmail.com');
            const empParam = isAdm ? '&assigned_role=employee' : (curUser ? `&assigned_employee_id=${curUser.id}` : '');
            api.get(`/customers?page=1&limit=1${empParam}`).then(res => {
                const assignedBadge = document.getElementById('nav-badge-assigned-focus');
                if (assignedBadge) {
                    assignedBadge.textContent = (window.app && typeof app.formatNumberDisplay === 'function') ? app.formatNumberDisplay(res.total) : res.total;
                }
            }).catch(() => {});

        } catch (err) {
            console.error("Error loading customers:", err);
            if (!this._customerCache[url]) {
                tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--danger);">Failed to load customers</td></tr>`;
            }
        }
    },

    renderCustomerTable(data) {
        const tbody = document.getElementById('customers-table-body');
        if (!tbody || !data) return;

        const totalFormatted = (window.app && typeof app.formatFullNumber === 'function') ? app.formatFullNumber(data.total) : data.total;
        const startNum = data.items.length > 0 ? ((data.page - 1) * this.limit + 1) : 0;
        const endNum = Math.min(data.page * this.limit, data.total);
        const pageInfo = document.getElementById('customers-pagination-info');
        if (pageInfo) {
            pageInfo.textContent = `Showing ${startNum} to ${endNum} of ${totalFormatted} customers (Page ${data.page} of ${data.total_pages})`;
        }

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

            const isStaff = c.assigned_employee && (c.assigned_employee.role || '').toLowerCase() === 'employee';
            const assignedName = isStaff ? c.assigned_employee.full_name : 'Unassigned';
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
                    <td><span style="font-size: 0.75rem;">${assignedName}</span></td>
                    <td>
                        <div style="display: flex; gap: 0.25rem; align-items: center;" onclick="event.stopPropagation();">
                            <button class="btn btn-secondary btn-xs" onclick="cti.makeOutgoingCall('${this.escapeHtml(phone1)}', ${c.id})" title="Initiate Outgoing Call" style="color: var(--primary); font-weight: 600;">
                                ${Icons.get('phone', { size: 12 })}
                                <span>Call</span>
                            </button>
                            <button class="btn btn-warning btn-xs" onclick="customer.openAssignModal(${c.id})" title="Assign to Employee / Priority Focus" style="height: 24px; padding: 0 5px; background: rgba(245,158,11,0.15); color: #D97706; border: 1px solid rgba(245,158,11,0.35); display: inline-flex; align-items: center; justify-content: center;">
                                ${Icons.get('user-plus', { size: 12 })}
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

        // Render Business Category Badges in Header & Metadata Grid
        const bizCatBadgeEl = document.getElementById('drawer-cust-biz-cat-badge');
        const gridCatBoxEl = document.getElementById('drawer-cust-grid-cat-box');
        const custCat = cust.category || 'General';
        
        if (bizCatBadgeEl) {
            const style = this.getCategoryStyle(custCat);
            const iconSvg = this.getCategoryIconSvg(custCat);
            bizCatBadgeEl.style.display = 'inline-flex';
            bizCatBadgeEl.style.background = style.bg;
            bizCatBadgeEl.style.color = style.color;
            bizCatBadgeEl.style.border = `1px solid ${style.border}`;
            bizCatBadgeEl.innerHTML = `<span style="display: inline-flex; align-items: center;">${iconSvg}</span><span>${this.escapeHtml(custCat)}</span>`;
        }

        if (gridCatBoxEl) {
            gridCatBoxEl.innerHTML = this.renderCategoryBadgeHtml(custCat);
        }

        // Render Customer Rating Badge in Drawer Header
        const ratingBadgeEl = document.getElementById('drawer-cust-rating-badge');
        if (ratingBadgeEl) {
            const r = Math.max(0, Math.min(5, parseInt(cust.rating, 10) || 0));
            const ratingLabels = { 0: 'Unrated Account', 1: 'Needs Attention', 2: 'Growth Potential', 3: 'Good Standing', 4: 'Premium Account', 5: 'Top Tier Customer' };
            const ratingColors = { 0: '#94A3B8', 1: '#EF4444', 2: '#F97316', 3: '#EAB308', 4: '#3B82F6', 5: '#10B981' };
            const ratingBgColors = { 0: 'rgba(148,163,184,0.1)', 1: 'rgba(239,68,68,0.08)', 2: 'rgba(249,115,22,0.08)', 3: 'rgba(234,179,8,0.1)', 4: 'rgba(59,130,246,0.08)', 5: 'rgba(16,185,129,0.1)' };
            const color = ratingColors[r] || '#94A3B8';
            const bg = ratingBgColors[r] || 'rgba(148,163,184,0.1)';
            const label = ratingLabels[r] || 'Unrated';
            let starsHtml = '';
            for (let i = 1; i <= 5; i++) {
                if (i <= r) {
                    starsHtml += `<svg width="15" height="15" viewBox="0 0 24 24" style="fill: #F59E0B; stroke: #F59E0B; stroke-width: 1px; filter: drop-shadow(0 0 4px rgba(245,158,11,0.45)); flex-shrink: 0;"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>`;
                } else {
                    starsHtml += `<svg width="15" height="15" viewBox="0 0 24 24" style="fill: rgba(245, 158, 11, 0.04); stroke: #F59E0B; stroke-width: 1.8px; opacity: 0.85; flex-shrink: 0;"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>`;
                }
            }
            ratingBadgeEl.innerHTML = `
                <div style="display: inline-flex; align-items: center; gap: 0.45rem; background: ${bg}; border: 1.5px solid ${color}25; border-radius: 8px; padding: 4px 10px;">
                    <div style="display: flex; align-items: center; gap: 2px;">${starsHtml}</div>
                    <div style="width: 1px; height: 14px; background: ${color}30; margin: 0 1px;"></div>
                    <span style="font-size: 0.78rem; font-weight: 800; color: ${color};">${r > 0 ? r + '.0' : '—'}</span>
                    <span style="font-size: 0.7rem; font-weight: 700; color: ${color}; background: ${color}18; border-radius: 4px; padding: 1px 5px; letter-spacing: 0.02em;">${label.toUpperCase()}</span>
                </div>
            `;
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
        const isAdmin = user && (user.role === 'admin' || user.role === 'ADMIN');
        const canDelete = isAdmin || (user && user.can_delete_customer === true);
        const delBtn = document.getElementById('btn-drawer-delete-customer');
        if (delBtn) {
            delBtn.style.display = canDelete ? 'inline-flex' : 'none';
        }

        const canEdit = isAdmin || (user && user.can_edit_customer !== false);
        const editTab = document.querySelector('[data-drawer-tab="edit"]');
        if (editTab) {
            editTab.style.display = canEdit ? 'inline-flex' : 'none';
        }

        this.updateTcsCredentialsUI();
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
                                <span style="font-weight: 600; font-size: 0.875rem; color: ${isPrimary ? 'var(--primary)' : 'var(--text-primary)'}; font-variant-numeric: tabular-nums;">
                                    ${this.escapeHtml(p.phone_number)}
                                </span>
                                ${isPrimary ? `
                                    <span class="badge badge-active" style="font-size: 0.72rem; padding: 0.08rem 0.35rem;">
                                        PRIMARY
                                    </span>
                                ` : ''}
                            </div>
                            <div style="font-size: 0.75rem; color: var(--text-muted);">
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
            }).catch(() => { });
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
        if (titleEl) titleEl.textContent = "Create New Customer (25 Master Columns Schema)";

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

        const ccSelect = document.getElementById('inp-cust-country-code');
        if (ccSelect) ccSelect.value = "+91";

        const statusEl = document.getElementById('inp-cust-status');
        if (statusEl) statusEl.value = "Active";

        if (prefilledPhone) {
            const phoneInput = document.getElementById('inp-cust-phone1');
            if (phoneInput) phoneInput.value = prefilledPhone;
        }

        const catSelect = document.getElementById('inp-cust-category');
        if (catSelect) {
            if (this.selectedCategory && this.selectedCategory !== 'ALL') {
                catSelect.value = this.selectedCategory;
            } else {
                catSelect.value = 'General';
            }
        }

        // Close right-side drawer if open so modal is 100% unobstructed
        if (this.isDrawerOpen) {
            this.closeDrawer();
        }

        // Open modal immediately for instant feedback
        app.openModal('modal-add-customer');

        // Populate agents dropdown safely in background
        this.populateAgentDropdown();
    },

    async openEditModal(customerId) {
        this.editingCustomerId = customerId;
        const form = document.getElementById('form-add-customer');
        if (form) form.reset();

        document.getElementById('modal-cust-title').textContent = "Edit Customer Profile (25 Master Columns)";
        document.getElementById('btn-submit-add-customer').textContent = "Update Customer";
        document.getElementById('inp-cust-edit-id').value = customerId;

        // Populate agents dropdown
        await this.populateAgentDropdown();

        try {
            const cust = await api.get(`/customers/${customerId}`);

            const setField = (id, val) => {
                const el = document.getElementById(id);
                if (el) el.value = val !== null && val !== undefined ? val : '';
            };

            setField('inp-cust-party-code', cust.party_code || cust.customer_id);
            setField('inp-cust-party-name', cust.party_name || cust.name);
            setField('inp-cust-category', cust.category || 'General');
            setField('inp-cust-address-date', cust.address_date);
            setField('inp-cust-addr1', cust.address_line_1 || cust.address);
            setField('inp-cust-addr2', cust.address_line_2);
            setField('inp-cust-addr3', cust.address_line_3);
            setField('inp-cust-country', cust.country || 'India');
            setField('inp-cust-state', cust.state);
            setField('inp-cust-district', cust.district);
            setField('inp-cust-city', cust.city);
            setField('inp-cust-pincode', cust.pincode);
            setField('inp-cust-zone', cust.zone);
            setField('inp-cust-website', cust.company_website);
            setField('inp-cust-sales-region', cust.sales_region_code);
            setField('inp-cust-contact-person', cust.contact_person_1);
            setField('inp-cust-email-id', cust.email_id_1 || cust.email);
            setField('inp-cust-phone-type', cust.phone_type_1 || 'Mobile');

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
            if (ccSelect) {
                if ([...ccSelect.options].some(o => o.value === cc)) {
                    ccSelect.value = cc;
                } else {
                    ccSelect.value = "+91";
                }
            }
            setField('inp-cust-phone1', phone1);

            // Contact 2 & Contact 3
            setField('inp-cust-contact-person-2', cust.contact_person_2);
            setField('inp-cust-email-id-2', cust.email_id_2);
            setField('inp-cust-phone-2', cust.phone_2);
            setField('inp-cust-contact-person-3', cust.contact_person_3);
            setField('inp-cust-email-id-3', cust.email_id_3);
            setField('inp-cust-phone-3', cust.phone_3);

            setField('inp-cust-status', cust.status || 'Active');
            if (cust.assigned_employee_id) {
                setField('inp-cust-agent', cust.assigned_employee_id);
            }
            setField('inp-cust-notes', cust.notes);

            app.openModal('modal-add-customer');
        } catch (err) {
            api.toast(`Error fetching customer details: ${err.message}`, "error");
        }
    },

    async populateAgentDropdown() {
        try {
            const rawEmployees = await api.get('/employees');
            const employees = (rawEmployees || []).filter(e => (e.role || '').toLowerCase() === 'employee');
            const agentSel = document.getElementById('inp-cust-agent');
            if (agentSel) {
                agentSel.innerHTML = `
                    <option value="">Unassigned / Shared</option>
                    ${employees.map(e => `
                        <option value="${e.id}">${this.escapeHtml(e.full_name)} (${(e.role || 'Staff').toUpperCase()})</option>
                    `).join('')}
                `;
            }

            const filterAgentSel = document.getElementById('customers-filter-agent');
            if (filterAgentSel) {
                const curVal = filterAgentSel.value;
                filterAgentSel.innerHTML = `
                    <option value="">All Assigned Agents</option>
                    <option value="0">⚡ Unassigned Only</option>
                    ${employees.map(e => `
                        <option value="${e.id}">${this.escapeHtml(e.full_name)} (${(e.role || 'Staff').toUpperCase()})</option>
                    `).join('')}
                `;
                if (curVal) filterAgentSel.value = curVal;
            }
        } catch (err) {
            console.error("Error loading employees for dropdown:", err);
        }
    },

    async submitCustomerForm() {
        const cc = document.getElementById('inp-cust-country-code')?.value.trim() || '';
        const rawPhone = document.getElementById('inp-cust-phone1')?.value.trim() || '';
        const fullPhone = cc && !rawPhone.startsWith("+") ? `${cc} ${rawPhone}` : rawPhone;

        const getVal = (id) => {
            const el = document.getElementById(id);
            return el ? el.value.trim() || null : null;
        };

        const payload = {
            party_code: getVal('inp-cust-party-code'),
            party_name: getVal('inp-cust-party-name'),
            category: getVal('inp-cust-category') || 'General',
            address_date: getVal('inp-cust-address-date'),
            address_line_1: getVal('inp-cust-addr1'),
            address_line_2: getVal('inp-cust-addr2'),
            address_line_3: getVal('inp-cust-addr3'),
            country: getVal('inp-cust-country') || 'India',
            state: getVal('inp-cust-state'),
            district: getVal('inp-cust-district'),
            city: getVal('inp-cust-city'),
            pincode: getVal('inp-cust-pincode'),
            zone: getVal('inp-cust-zone'),
            company_website: getVal('inp-cust-website'),
            sales_region_code: getVal('inp-cust-sales-region'),
            contact_person_1: getVal('inp-cust-contact-person'),
            email_id_1: getVal('inp-cust-email-id'),
            phone_type_1: document.getElementById('inp-cust-phone-type')?.value || 'Mobile',
            phone_1: fullPhone,
            contact_person_2: getVal('inp-cust-contact-person-2'),
            email_id_2: getVal('inp-cust-email-id-2'),
            phone_2: getVal('inp-cust-phone-2'),
            contact_person_3: getVal('inp-cust-contact-person-3'),
            email_id_3: getVal('inp-cust-email-id-3'),
            phone_3: getVal('inp-cust-phone-3'),
            status: document.getElementById('inp-cust-status')?.value || 'Active',
            assigned_employee_id: parseInt(document.getElementById('inp-cust-agent')?.value) || null,
            notes: getVal('inp-cust-notes')
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

    isTcsPassVisible: false,

    getTcsCredentials() {
        const MASTER_ADMIN_USER = "trng_infotech@khandelia.com";
        const MASTER_ADMIN_PASS = "Pass!@#32132";

        // Predefined fallback map for all 9 employees' dedicated TCS credentials
        const EMPLOYEE_TCS_MAP = {
            "kogm.sahildogra@gmail.com": { email: "trng_sahildogra@khandelia.com", pass: "Sahil@Tcs2026!" },
            "sahil.dogra@khandelia.com": { email: "trng_sahildogra@khandelia.com", pass: "Sahil@Tcs2026!" },
            "bmjagga@khandelia.com": { email: "trng_bmjagga@khandelia.com", pass: "Jagga@Tcs2026!" },
            "jagga@khandelia.com": { email: "trng_bmjagga@khandelia.com", pass: "Jagga@Tcs2026!" },
            "sales.kol@khandelia.com": { email: "trng_utpalpal@khandelia.com", pass: "Utpal@Tcs2026!" },
            "utpal@khandelia.com": { email: "trng_utpalpal@khandelia.com", pass: "Utpal@Tcs2026!" },
            "sales.gm@khandelia.com": { email: "trng_suniljain@khandelia.com", pass: "Sunil@Tcs2026!" },
            "sunil@khandelia.com": { email: "trng_suniljain@khandelia.com", pass: "Sunil@Tcs2026!" },
            "customercare@khandelia.com": { email: "trng_customercare@khandelia.com", pass: "Ravi@Tcs2026!" },
            "account.unit6@khandelia.com": { email: "trng_ankushdingra@khandelia.com", pass: "Ankush@Tcs2026!" },
            "ankush@khandelia.com": { email: "trng_ankushdingra@khandelia.com", pass: "Ankush@Tcs2026!" },
            "kogm.sonukumar@gmail.com": { email: "trng_sonukumar@khandelia.com", pass: "Sonu@Tcs2026!" },
            "sonu@khandelia.com": { email: "trng_sonukumar@khandelia.com", pass: "Sonu@Tcs2026!" },
            "storepurchase@khandelia.com": { email: "trng_ankushkapila@khandelia.com", pass: "Store@Tcs2026!" },
            "kogm.pankaj@gmail.com": { email: "trng_pankaj@khandelia.com", pass: "Pankaj@Tcs2026!" },
            "pankaj@khandelia.com": { email: "trng_pankaj@khandelia.com", pass: "Pankaj@Tcs2026!" }
        };

        const user = api.getCurrentUser();
        if (!user) {
            return {
                email: MASTER_ADMIN_USER,
                password: MASTER_ADMIN_PASS,
                role: 'admin',
                name: 'Administrator'
            };
        }

        const userEmail = (user.email || '').toLowerCase().trim();
        const isAdmin = user.role === 'admin' ||
            userEmail === 'infotech@khandelia.com' ||
            userEmail === 'itchd.kogm@gmail.com';

        if (isAdmin) {
            return {
                email: user.tcs_username || MASTER_ADMIN_USER,
                password: user.tcs_password || MASTER_ADMIN_PASS,
                role: 'admin',
                name: user.full_name || 'Admin'
            };
        }

        const empCreds = EMPLOYEE_TCS_MAP[userEmail] || {};
        return {
            email: user.tcs_username || empCreds.email || MASTER_ADMIN_USER,
            password: user.tcs_password || empCreds.pass || MASTER_ADMIN_PASS,
            role: user.role || 'employee',
            name: user.full_name || 'Employee'
        };
    },

    updateTcsCredentialsUI() {
        const creds = this.getTcsCredentials();
        const userEl = document.getElementById('tcs-creds-user-text');
        const passEl = document.getElementById('tcs-creds-pass-text');
        const badgeEl = document.getElementById('tcs-creds-badge');
        const toggleBtn = document.getElementById('btn-toggle-tcs-pass');

        if (userEl) userEl.textContent = creds.email;
        if (passEl) {
            passEl.textContent = this.isTcsPassVisible ? creds.password : '••••••••';
            passEl.title = this.isTcsPassVisible ? creds.password : 'Password masked';
        }
        if (badgeEl) {
            const isAdm = creds.role === 'admin';
            badgeEl.textContent = isAdm ? 'Admin Master' : `${creds.name} (Employee)`;
            badgeEl.className = isAdm ? 'badge' : 'badge';
            badgeEl.style.cssText = isAdm
                ? 'background: #eff6ff; color: #1e40af; border: 1px solid #bfdbfe; font-size: 0.75rem; font-weight: 700;'
                : 'background: #f0fdf4; color: #166534; border: 1px solid #bbf7d0; font-size: 0.75rem; font-weight: 700;';
        }
        if (toggleBtn) {
            toggleBtn.textContent = this.isTcsPassVisible ? 'Hide Pass' : 'Show Pass';
            toggleBtn.title = this.isTcsPassVisible ? 'Hide Password' : 'Show Password';
        }
    },

    toggleTcsPasswordVisibility() {
        this.isTcsPassVisible = !this.isTcsPassVisible;
        const creds = this.getTcsCredentials();
        const passEl = document.getElementById('tcs-creds-pass-text');
        const toggleBtn = document.getElementById('btn-toggle-tcs-pass');

        if (passEl) {
            passEl.textContent = this.isTcsPassVisible ? creds.password : '••••••••';
            passEl.title = this.isTcsPassVisible ? creds.password : 'Password masked';
        }
        if (toggleBtn) {
            toggleBtn.textContent = this.isTcsPassVisible ? 'Hide Pass' : 'Show Pass';
            toggleBtn.title = this.isTcsPassVisible ? 'Hide Password' : 'Show Password';
        }
    },

    openTcsIonPortal() {
        const creds = this.getTcsCredentials();
        const email = creds.email;
        const password = creds.password;
        const url = "https://training.tcsion.com/Login/Login.html";
        const cust = this.currentCustomerData;
        const partyName = (cust?.party_name || cust?.name || '').trim();

        // Auto copy credentials to clipboard
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(email).then(() => {
                api.toast(`Opening TCS iON... User: ${email} | Pass: ${password}${partyName ? ` | Party: "${partyName}"` : ''}`, "info", 7000);
            }).catch(() => {
                api.toast(`Opening TCS iON Portal... User: ${email} | Pass: ${password}`, "info", 5000);
            });
        } else {
            api.toast(`Opening TCS iON Portal... User: ${email} | Pass: ${password}`, "info", 5000);
        }

        // Open in new tab
        window.open(url, "_blank", "noopener,noreferrer");
    },

    copyTcsCredentials(type) {
        const creds = this.getTcsCredentials();
        const text = type === 'user' ? creds.email : creds.password;
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

    toggleExportMenu(event) {
        if (event) {
            event.stopPropagation();
        }
        const dropdown = document.getElementById('cust-export-dropdown');
        if (dropdown) {
            const isShown = dropdown.style.display === 'block';
            dropdown.style.display = isShown ? 'none' : 'block';
        }
    },

    async downloadExport(format = 'xlsx') {
        const dropdown = document.getElementById('cust-export-dropdown');
        if (dropdown) dropdown.style.display = 'none';

        const search = document.getElementById('customers-filter-search')?.value.trim() || '';
        const status = document.getElementById('customers-filter-status')?.value || '';
        const category = document.getElementById('customers-filter-category')?.value || '';
        const agentId = document.getElementById('customers-filter-agent')?.value || '';

        let url = `${api.baseUrl || '/api'}/customers/export?format=${encodeURIComponent(format)}`;
        if (search) url += `&search=${encodeURIComponent(search)}`;
        if (status) url += `&status=${encodeURIComponent(status)}`;
        if (category) url += `&category=${encodeURIComponent(category)}`;
        if (agentId) url += `&assigned_employee_id=${encodeURIComponent(agentId)}`;

        api.toast(`Preparing ${format.toUpperCase()} export...`, "info");

        try {
            const token = api.getToken();
            const headers = {};
            if (token) {
                headers['Authorization'] = `Bearer ${token}`;
            }

            const res = await fetch(url, { headers });
            if (!res.ok) {
                const errData = await res.json().catch(() => ({ detail: 'Failed to download file' }));
                throw new Error(errData.detail || 'Download failed');
            }

            const blob = await res.blob();
            const downloadUrl = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = downloadUrl;
            const dateStr = new Date().toISOString().slice(0, 10);
            a.download = `customers_export_${dateStr}.${format}`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(downloadUrl);

            api.toast(`✅ Successfully downloaded ${format.toUpperCase()} export!`, "success");
        } catch (err) {
            api.toast(`Export error: ${err.message}`, "error");
        }
    },

    /**
     * Apply active employee permissions to customer UI elements
     */
    applyUserPermissions(user) {
        if (!user) return;
        const isAdmin = user.role === 'admin' || user.role === 'ADMIN';

        // Re-initialize category tabs according to employee's allowed categories
        this.initCategoryTabs();

        // Add Customer Permission
        const canAdd = isAdmin || user.can_add_customer !== false;
        const quickRegBtn = document.getElementById('btn-drawer-quick-register');
        if (quickRegBtn) quickRegBtn.style.display = canAdd ? 'inline-flex' : 'none';

        // Delete Customer Permission
        const canDelete = isAdmin || Boolean(user.can_delete_customer);
        const delBtn = document.getElementById('btn-drawer-delete-customer');
        if (delBtn) delBtn.style.display = canDelete ? 'inline-flex' : 'none';

        // Edit Customer Permission
        const canEdit = isAdmin || user.can_edit_customer !== false;
        const editTab = document.querySelector('[data-drawer-tab="edit"]');
        if (editTab) editTab.style.display = canEdit ? 'inline-flex' : 'none';

        // Export Customers Permission
        const canExport = isAdmin || user.can_export_data !== false;
        const exportBtn = document.getElementById('btn-export-customers');
        if (exportBtn) exportBtn.style.display = canExport ? 'inline-flex' : 'none';

        // Unassigned Tab Visibility
        const canUnassigned = isAdmin || user.can_view_unassigned !== false;
        const unassignedTab = document.querySelector('[data-customer-tab="unassigned"]');
        if (unassignedTab) unassignedTab.style.display = canUnassigned ? 'inline-flex' : 'none';
    }
};

// Global click listener to close export dropdown when clicking outside
document.addEventListener('click', (e) => {
    const dropdown = document.getElementById('cust-export-dropdown');
    const toggleBtn = document.getElementById('btn-export-dropdown-toggle');
    if (dropdown && dropdown.style.display === 'block') {
        if (!dropdown.contains(e.target) && !toggleBtn?.contains(e.target)) {
            dropdown.style.display = 'none';
        }
    }
});

window.customer = customer;

