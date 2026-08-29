/**
 * Conversation Notes, Transactional Emails, and Interaction Modals
 */
const interactions = {
    templates: {},

    init() {
        if (api.getToken()) {
            this.loadTemplates();
        }

        // Follow-up toggle in Add Note modal
        const chkFu = document.getElementById('chk-inter-create-fu');
        const fuFields = document.getElementById('inter-fu-fields');
        chkFu?.addEventListener('change', () => {
            fuFields.style.display = chkFu.checked ? 'block' : 'none';
        });

        // Email Template Selector change
        const tplSelect = document.getElementById('inp-email-template-select');
        tplSelect?.addEventListener('change', () => {
            const key = tplSelect.value;
            if (key && this.templates[key]) {
                const name = document.getElementById('drawer-cust-name')?.textContent || "Customer";
                const company = document.getElementById('drawer-cust-company')?.textContent || name;
                const agent = api.getCurrentUser()?.full_name || "Support Team";

                let subj = this.templates[key].subject.replace('{company_or_name}', company).replace('{name}', name);
                let body = this.templates[key].body.replace('{name}', name).replace('{company_or_name}', company).replace('{agent_name}', agent);

                document.getElementById('inp-email-subject').value = subj;
                document.getElementById('inp-email-body').value = body;
            }
        });

        // Submit Interaction Note
        document.getElementById('btn-submit-add-interaction')?.addEventListener('click', (e) => {
            e.preventDefault();
            this.submitAddInteraction();
        });

        // Submit Send Email
        document.getElementById('btn-submit-send-email')?.addEventListener('click', (e) => {
            e.preventDefault();
            this.submitSendEmail();
        });
    },

    async loadTemplates() {
        try {
            this.templates = await api.get('/emails/templates');
        } catch (err) {
            console.error("Could not load email templates:", err);
        }
    },

    openAddNoteModal(customerId, defaultType = 'note', defaultDirection = 'internal', scheduleFollowUp = false) {
        document.getElementById('form-add-interaction').reset();
        document.getElementById('inp-inter-cust-id').value = customerId;
        document.getElementById('inp-inter-type').value = defaultType;
        document.getElementById('inp-inter-direction').value = defaultDirection;

        const chkFu = document.getElementById('chk-inter-create-fu');
        const fuFields = document.getElementById('inter-fu-fields');
        chkFu.checked = scheduleFollowUp;
        fuFields.style.display = scheduleFollowUp ? 'block' : 'none';

        if (scheduleFollowUp) {
            // Default due date to tomorrow 11:00 AM
            const tmrw = new Date();
            tmrw.setDate(tmrw.getDate() + 1);
            tmrw.setHours(11, 0, 0, 0);
            document.getElementById('inp-inter-fu-date').value = tmrw.toISOString().slice(0, 16);
        }

        app.openModal('modal-add-interaction');
    },

    async submitAddInteraction() {
        const customerId = parseInt(document.getElementById('inp-inter-cust-id').value);
        const chkFu = document.getElementById('chk-inter-create-fu').checked;
        const fuDateVal = document.getElementById('inp-inter-fu-date').value;

        const payload = {
            customer_id: customerId,
            interaction_type: document.getElementById('inp-inter-type').value,
            direction: document.getElementById('inp-inter-direction').value,
            subject: document.getElementById('inp-inter-subject').value.trim(),
            content: document.getElementById('inp-inter-content').value.trim(),
            create_follow_up: chkFu,
            follow_up_due_date: chkFu && fuDateVal ? new Date(fuDateVal).toISOString() : null,
            follow_up_priority: document.getElementById('inp-inter-fu-priority').value,
            follow_up_title: `Follow-up: ${document.getElementById('inp-inter-subject').value.trim()}`
        };

        if (!payload.subject || !payload.content) {
            api.toast("Subject and Notes content are required", "error");
            return;
        }

        try {
            await api.post('/interactions', payload);
            api.toast("Interaction note recorded successfully!", "success");
            app.closeModal('modal-add-interaction');
            customer.loadTimeline(customerId);
            app.refreshDashboard();
        } catch (err) {
            api.toast(`Failed to save interaction: ${err.message}`, "error");
        }
    },

    openSendEmailModal(customerId, customerEmail, customerName) {
        document.getElementById('form-send-email').reset();
        document.getElementById('inp-email-cust-id').value = customerId;
        document.getElementById('inp-email-to').value = customerEmail || '';
        
        // Trigger template default (Call follow-up)
        document.getElementById('inp-email-template-select').value = "call_followup";
        document.getElementById('inp-email-template-select').dispatchEvent(new Event('change'));

        app.openModal('modal-send-email');
    },

    async submitSendEmail() {
        const customerId = parseInt(document.getElementById('inp-email-cust-id').value);
        const payload = {
            to_email: document.getElementById('inp-email-to').value.trim(),
            subject: document.getElementById('inp-email-subject').value.trim(),
            body: document.getElementById('inp-email-body').value.trim(),
            template_name: document.getElementById('inp-email-template-select').value || null
        };

        if (!payload.to_email || !payload.subject || !payload.body) {
            api.toast("Recipient, Subject, and Email body are required", "error");
            return;
        }

        try {
            api.toast("Sending email...", "info");
            const res = await api.post(`/emails/send/${customerId}`, payload);
            api.toast(`Email successfully sent to ${payload.to_email}!`, "success");
            app.closeModal('modal-send-email');
            customer.loadTimeline(customerId);
            app.refreshDashboard();
        } catch (err) {
            api.toast(`Failed to send email: ${err.message}`, "error");
        }
    }
};
