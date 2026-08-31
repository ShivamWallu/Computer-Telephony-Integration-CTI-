/**
 * Tata Smartflo CTI Softphone, Multi-Call Real-Time Manager & Screen-Pop Engine
 */
const cti = {
    activeCalls: new Map(),
    callTimers: new Map(),
    dismissTimeouts: new Map(),
    processedCallKeys: new Set(),
    selectedCallKey: null,
    eventSource: null,
    pollingInterval: null,

    init() {
        // 1. Bind global telephony buttons
        this.bindEvents();

        // 2. Start Real-time SSE Stream & Polling fallback
        this.startRealtimeCallStream();
        this.startActiveCallPolling();
    },

    bindEvents() {
        // Bind simulator button
        const btnOpenSim = document.getElementById('btn-open-simulate-call');
        if (btnOpenSim) {
            btnOpenSim.addEventListener('click', () => {
                app.openModal('modal-simulate-call');
            });
        }

        // Trigger simulated call
        const btnTriggerSim = document.getElementById('btn-trigger-simulated-call');
        if (btnTriggerSim) {
            btnTriggerSim.addEventListener('click', () => {
                const preset = document.getElementById('sim-preset-number').value;
                const custom = document.getElementById('sim-custom-number').value.trim();
                const phone = custom || preset;
                app.closeModal('modal-simulate-call');
                this.simulateIncomingCall(phone);
            });
        }
    },

    /**
     * Parse and clean operator and circle information
     */
    formatOperatorCircle(op, circle) {
        if (!op && !circle) return 'Tata Smartflo';
        if (typeof op === 'string' && op.trim().startsWith('{')) {
            try {
                const cleanStr = op.replace(/'/g, '"');
                const parsed = JSON.parse(cleanStr);
                op = parsed.operator || '';
                circle = parsed.circle || circle || '';
            } catch (e) {
                op = op.replace(/[{}\']/g, '').replace(/operator\s*:\s*/gi, '').replace(/circle\s*:\s*/gi, '').trim();
            }
        }
        return [op, circle].filter(Boolean).join(' • ') || 'Tata Smartflo';
    },

    /**
     * Connect to Server-Sent Events (SSE) stream for instant Smartflo webhook pushes (< 50ms)
     */
    startRealtimeCallStream() {
        if (typeof EventSource === 'undefined') return;

        try {
            if (this.eventSource) {
                this.eventSource.close();
            }

            this.eventSource = new EventSource('/api/calls/events');

            this.eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    if (data.event === 'incoming_call' || data.event === 'outgoing_call' || (data.call_id && !data.event)) {
                        this.handleIncomingCallEvent(data);
                    } else if (data.event === 'call_ended') {
                        this.handleCallEndedEvent(data);
                    }
                } catch (e) {
                    // Ignore heartbeat comments
                }
            };

            this.eventSource.onerror = () => {
                // Browser auto-reconnects, fallback poller also runs
            };
        } catch (err) {
            console.warn("SSE connection error:", err);
        }
    },

    /**
     * Fallback poller running every 3.5 seconds to guarantee multi-call sync
     */
    startActiveCallPolling() {
        if (this.pollingInterval) clearInterval(this.pollingInterval);

        this.pollingInterval = setInterval(async () => {
            const token = api.getToken();
            if (!token) return;

            try {
                const res = await api.get('/calls/active');
                if (res && res.active_calls && Array.isArray(res.active_calls)) {
                    const serverActiveKeys = new Set();
                    
                    res.active_calls.forEach(call => {
                        const callKey = (call.uuid || call.call_id || '').trim();
                        if (!callKey) return;
                        serverActiveKeys.add(callKey);
                        if (!this.activeCalls.has(callKey)) {
                            this.handleIncomingCallEvent(call);
                        }
                    });

                    // If a call was ringing on frontend but is no longer in server active calls, transition it to ended
                    for (const [key, call] of this.activeCalls.entries()) {
                        if (!serverActiveKeys.has(key) && !call.isEnded && call.status === 'ringing') {
                            this.handleCallEndedEvent({
                                call_id: call.call_id,
                                uuid: call.uuid,
                                phone_number: call.phone_number,
                                status: 'completed'
                            });
                        }
                    }
                }
            } catch (e) {
                // Ignore background polling errors
            }
        }, 3500);
    },

    selectCall(callKey) {
        this.selectedCallKey = callKey;
        const callData = this.activeCalls.get(callKey);
        if (!callData) return;

        // Visual selection indicator on call cards
        document.querySelectorAll('.cti-call-card').forEach(card => {
            if (card.id === `cti-card-${callKey}`) {
                card.classList.add('selected');
            } else {
                card.classList.remove('selected');
            }
        });

        // Instant 360° Profile Drawer
        if (callData.customer_found && callData.customer?.id) {
            customer.openDrawer(callData.customer.id, callData.customer);
        } else {
            customer.openNewCustomerDrawer(callData.phone_number, callData);
        }
    },

    openProfile(callKey, e) {
        if (e) e.stopPropagation();
        this.selectCall(callKey);
    },

    openAddNote(callKey, e) {
        if (e) e.stopPropagation();
        this.selectCall(callKey);
        const callData = this.activeCalls.get(callKey);
        if (callData && callData.customer_found && callData.customer?.id) {
            customer.switchDrawerTab('note');
            setTimeout(() => {
                const noteInput = document.getElementById('dinp-note-content');
                if (noteInput) noteInput.focus();
            }, 100);
        } else if (callData) {
            const tempNotes = document.getElementById('drawer-new-call-notes');
            if (tempNotes) tempNotes.focus();
        }
    },

    openSendEmail(callKey, e) {
        if (e) e.stopPropagation();
        this.selectCall(callKey);
        const callData = this.activeCalls.get(callKey);
        if (callData && callData.customer_found && callData.customer?.id) {
            customer.switchDrawerTab('email');
            setTimeout(() => {
                const subjInput = document.getElementById('dinp-email-subject');
                if (subjInput) subjInput.focus();
            }, 100);
        } else if (callData) {
            api.toast("Please register this customer before composing official email", "info");
            customer.openAddModal(callData.phone_number);
        }
    },

    /**
     * Core handler when an incoming / outgoing call arrives (Smartflo Webhook or Simulator)
     */
    handleIncomingCallEvent(callData) {
        const callKey = (callData.uuid || callData.call_id || '').trim();
        if (!callKey) return;

        const isNewCall = !this.activeCalls.has(callKey);
        const existing = this.activeCalls.get(callKey) || {};
        const merged = { ...existing, ...callData };
        this.activeCalls.set(callKey, merged);

        // Play chime sound strictly once for genuinely new calls
        if (isNewCall && !this.processedCallKeys.has(callKey)) {
            this.processedCallKeys.add(callKey);
            this.playCallChime();
        }

        // Render / Update the live call card in DOM
        this.renderCallCard(callKey, merged);

        // Auto-select and open Customer Profile Drawer for 360° context on new call
        if (isNewCall) {
            this.selectCall(callKey);
            const isOut = merged.direction === 'outgoing';
            if (merged.customer_found && (merged.customer?.id || merged.customer?.party_name)) {
                const callerName = merged.customer.party_name || merged.customer.name || 'Identified Client';
                api.toast(`${isOut ? 'Outgoing' : 'Incoming'} call: Matched ${callerName} (${merged.phone_number})`, "success");
            } else {
                api.toast(`${isOut ? 'Outgoing' : 'Incoming'} call with ${merged.phone_number}`, "info");
            }
        }

        // Refresh dashboard tables
        app.refreshDashboard();
        if (app.currentView === 'calls') {
            app.loadCallsView();
        }
    },

    /**
     * Renders or updates a floating Call Card inside #cti-live-calls-container
     */
    renderCallCard(callKey, callData) {
        const container = document.getElementById('cti-live-calls-container');
        if (!container) return;

        let card = document.getElementById(`cti-card-${callKey}`);
        if (!card) {
            card = document.createElement('div');
            card.id = `cti-card-${callKey}`;
            card.className = 'cti-call-card';
            container.appendChild(card);
        }

        // Set active selection state
        if (this.selectedCallKey === callKey) {
            card.classList.add('selected');
        } else {
            card.classList.remove('selected');
        }

        card.onclick = () => this.selectCall(callKey);

        const isOutgoing = callData.direction === 'outgoing';
        const partyName = callData.customer?.party_name || callData.customer?.name || null;
        const partyCode = callData.customer?.party_code || callData.customer?.customer_id || null;
        const contactPerson = callData.customer?.contact_person_1 || '';
        const city = callData.customer?.city || '';
        const vid = isOutgoing ? (callData.caller_id || callData.caller_phone || callData.vid || 'Smartflo VID') : (callData.call_to_number || 'Smartflo VID');
        const operatorCircle = this.formatOperatorCircle(callData.operator, callData.circle);
        const assignedEmployee = callData.assigned_employee_name || callData.agent_name || 'System';

        const isCustomerFound = Boolean(callData.customer_found && callData.customer);

        // Parse start timestamp for display
        let startEpoch = Date.now();
        const startRaw = callData.start_time || callData.start_stamp || callData.timestamp;
        if (startRaw) {
            const parsed = new Date(startRaw).getTime();
            if (!isNaN(parsed) && parsed > 0) startEpoch = parsed;
        }
        const callTimeDisplay = new Date(startEpoch).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true });

        // Preserve current timer text if already running
        let currentTimerText = "00:00";
        const existingTimerEl = document.getElementById(`cti-timer-${callKey}`);
        if (existingTimerEl && existingTimerEl.textContent.trim()) {
            currentTimerText = existingTimerEl.textContent.trim();
        } else {
            const elapsed = Math.max(0, Math.floor((Date.now() - startEpoch) / 1000));
            const m = String(Math.floor(elapsed / 60)).padStart(2, '0');
            const s = String(elapsed % 60).padStart(2, '0');
            currentTimerText = `${m}:${s}`;
        }

        card.innerHTML = `
            <div class="cti-header">
                <div style="display: flex; align-items: center; gap: 0.4rem;">
                    <div class="cti-status-pill" id="cti-status-pill-${callKey}" style="${isOutgoing ? 'background: var(--primary-subtle); color: var(--primary); border-color: rgba(79, 70, 229, 0.3);' : ''}">
                        <span class="pulse-ring"></span>
                        <span id="cti-status-label-${callKey}">${isOutgoing ? 'OUTGOING CALL' : 'INCOMING CALL'}</span>
                    </div>
                    <span class="badge badge-standard" style="font-size: 0.6875rem;" title="${isOutgoing ? 'Calling via Configured VID' : 'Dialed Virtual Number / VID'}">
                        ${vid}
                    </span>
                </div>
                <div style="display: flex; align-items: center; gap: 0.4rem;">
                    <span style="font-size: 0.72rem; color: var(--text-muted);" title="Call Start Time">${callTimeDisplay}</span>
                    <div id="cti-timer-${callKey}" style="font-size: 0.875rem; font-weight: 700; color: var(--warning); font-variant-numeric: tabular-nums; background: var(--warning-subtle); padding: 0.1rem 0.4rem; border-radius: var(--radius-xs); border: 1px solid rgba(245, 158, 11, 0.25);">
                        ${currentTimerText}
                    </div>
                </div>
            </div>

            <!-- VID / Routing Metadata Banner -->
            <div style="display: flex; justify-content: space-between; align-items: center; background: var(--bg-surface-elevated); padding: 0.3rem 0.55rem; border-radius: var(--radius-xs); font-size: 0.6875rem; color: var(--text-muted); margin-bottom: 0.65rem; border: 1px solid var(--border-color);">
                <span>${operatorCircle}</span>
                <span style="font-weight: 600; color: var(--primary);">Agent: ${assignedEmployee}</span>
            </div>

            <!-- Customer & Caller Info Box -->
            <div class="cti-customer-box">
                <div class="cti-phone-display">
                    ${isOutgoing ? `<span style="font-size: 0.75rem; color: var(--text-muted); font-weight: 500;">To: </span>` : ''}${callData.phone_number}
                </div>
                ${isCustomerFound ? `
                    <div>
                        <div class="cti-cust-name" style="cursor: pointer;">${partyName}</div>
                        <div class="meta-value" style="font-size: 0.75rem; color: var(--text-muted);">
                            ${contactPerson ? `Contact: ${contactPerson} | ` : ''}${city} (${partyCode})
                        </div>
                        ${callData.recent_interactions?.[0]?.content ? `
                            <div class="meta-value" style="margin-top: 0.25rem; font-style: italic; color: var(--text-secondary); font-size: 0.72rem;">
                                "${callData.recent_interactions[0].content.substring(0, 60)}..."
                            </div>
                        ` : ''}
                    </div>
                ` : `
                    <div>
                        <div style="color: var(--danger); font-weight: 600; font-size: 0.8125rem; margin-bottom: 0.15rem;">
                            ${isOutgoing ? 'Unregistered Recipient Number' : 'Unknown Caller (Not in CRM)'}
                        </div>
                    </div>
                `}
            </div>

            <!-- Dynamic Hangup / Recording Result Box -->
            <div id="cti-ended-box-${callKey}" style="display: none; background: var(--bg-surface-elevated); border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: 0.5rem 0.65rem; margin-bottom: 0.65rem; font-size: 0.75rem;">
            </div>

            <!-- Action Buttons -->
            <div class="cti-actions" id="cti-actions-${callKey}">
                ${isCustomerFound ? `
                    <button class="btn btn-secondary btn-xs" onclick="cti.openProfile('${callKey}', event)" title="View Customer 360° Profile">
                        ${Icons.get('user', { size: 12 })}
                        <span>Profile</span>
                    </button>
                    <button class="btn btn-secondary btn-xs" onclick="cti.openAddNote('${callKey}', event)" title="Add Interaction Note">
                        ${Icons.get('edit', { size: 12 })}
                        <span>Note</span>
                    </button>
                    <button class="btn btn-secondary btn-xs" onclick="cti.openSendEmail('${callKey}', event)" title="Compose & Send Email">
                        ${Icons.get('mail', { size: 12 })}
                        <span>Email</span>
                    </button>
                ` : `
                    <button class="btn btn-primary btn-xs" onclick="customer.openAddModal('${callData.phone_number}'); event.stopPropagation();" title="Quick Register Customer (15 Columns Schema)">
                        ${Icons.get('user-plus', { size: 12 })}
                        <span>Quick Register</span>
                    </button>
                    <button class="btn btn-secondary btn-xs" onclick="cti.openAddNote('${callKey}', event)" title="Add Inquiry Note">
                        ${Icons.get('edit', { size: 12 })}
                        <span>Inquiry Note</span>
                    </button>
                `}
                <button class="btn btn-danger btn-xs" onclick="cti.endCall('${callKey}', event)" title="End Active Call & Record CDR">
                    ${Icons.get('phone-off', { size: 12 })}
                    <span>End Call</span>
                </button>
            </div>
        `;

        this.startCardTimer(callKey, startRaw);
    },

    /**
     * Initiate Outgoing Call using configured VID
     */
    async makeOutgoingCall(phoneNumber, customerId = null) {
        if (!phoneNumber) {
            api.toast("Please specify a valid phone number to call", "error");
            return;
        }
        const rawPhone = String(phoneNumber).trim();
        const cleanDigits = rawPhone.replace(/\D/g, '');
        if (cleanDigits.length < 5) {
            api.toast("Please provide a valid phone number (minimum 5 digits)", "error");
            return;
        }

        // Check if an active call already exists for this number
        for (const [key, activeCall] of this.activeCalls.entries()) {
            const activePhoneDigits = String(activeCall.phone_number || '').replace(/\D/g, '');
            if (activePhoneDigits && (activePhoneDigits.endsWith(cleanDigits.slice(-10)) || cleanDigits.endsWith(activePhoneDigits.slice(-10)))) {
                this.selectCall(key);
                api.toast(`Call already active with ${activeCall.phone_number}`, "info");
                return;
            }
        }

        try {
            api.toast(`Initiating outbound call to ${rawPhone}...`, "info");
            const res = await api.post('/calls/outgoing', {
                phone_number: rawPhone,
                customer_id: customerId,
                provider: 'smartflo'
            });
            
            const callKey = res.uuid || res.call_id;
            const callPayload = {
                call_id: res.call_id,
                uuid: res.uuid,
                phone_number: rawPhone,
                call_to_number: rawPhone,
                caller_phone: res.vid,
                caller_id: res.vid,
                vid: res.vid,
                direction: 'outgoing',
                customer_found: res.customer_found,
                customer: res.customer_id ? { id: res.customer_id, party_name: res.customer_name } : null,
                assigned_employee_name: res.agent_name,
                start_time: new Date().toISOString(),
                status: 'ringing',
                provider: 'smartflo'
            };
            this.activeCalls.set(callKey, callPayload);
            this.renderCallCard(callKey, callPayload);
            this.selectCall(callKey);
            
            const provResp = res.provider_response || {};
            const provMsg = provResp.warning || provResp.error || provResp.message || '';
            if (provResp.status === 'failed' || (provMsg && (provMsg.toLowerCase().includes('offline') || provMsg.toLowerCase().includes('error') || provMsg.toLowerCase().includes('failed') || provMsg.toLowerCase().includes('401')))) {
                api.toast(`Smartflo: ${provMsg || 'Could not connect call. Please check agent status/token.'}`, "warning");
            } else {
                api.toast(provResp.message || `Outgoing call placed via VID ${res.vid}! Smartflo is ringing agent phone...`, "success");
            }
        } catch (err) {
            api.toast(`Failed to initiate outgoing call: ${err.message}`, "error");
        }
    },

    /**
     * Action: End Active Call & Record CDR in backend
     */
    async endCall(callKey, e) {
        if (e) e.stopPropagation();
        const call = this.activeCalls.get(callKey);
        const callId = call?.call_id || callKey;
        const callUuid = call?.uuid || callKey;

        let elapsed = 15;
        if (this.callTimers.has(callKey)) {
            const timerInfo = this.callTimers.get(callKey);
            const startMs = timerInfo.startTimeMs || Date.now();
            elapsed = Math.max(1, Math.floor((Date.now() - startMs) / 1000));
        }

        try {
            await api.post('/calls/status', {
                call_id: callId,
                status: 'completed',
                duration_seconds: elapsed,
                notes: 'Call ended from CRM Dashboard Softphone'
            });
        } catch (err) {
            console.warn("Call status update warning:", err);
        }

        this.handleCallEndedEvent({
            call_id: callId,
            uuid: callUuid,
            phone_number: call?.phone_number,
            status: 'completed',
            duration_seconds: elapsed,
            hangup_cause: 'Call Completed / Hangup by Agent'
        });
        api.toast("Active call ended and logged.", "info");
    },

    /**
     * Dismiss and remove call card from DOM (Manual or Auto 5-minute timeout)
     */
    dismissCard(callKey, e) {
        if (e) e.stopPropagation();

        // 1. Clear interval timer if ticking
        if (this.callTimers.has(callKey)) {
            const timerInfo = this.callTimers.get(callKey);
            clearInterval(timerInfo.intervalId || timerInfo);
            this.callTimers.delete(callKey);
        }

        // 2. Clear 5-minute auto-dismiss timeout
        if (this.dismissTimeouts.has(callKey)) {
            clearTimeout(this.dismissTimeouts.get(callKey));
            this.dismissTimeouts.delete(callKey);
        }

        // 3. Remove from active calls map
        this.activeCalls.delete(callKey);

        // 4. Smooth animate out and remove from DOM
        const card = document.getElementById(`cti-card-${callKey}`);
        if (card) {
            card.style.opacity = '0';
            card.style.transform = 'translateY(12px)';
            card.style.transition = 'opacity 0.2s ease, transform 0.2s ease';
            setTimeout(() => {
                if (card.parentNode) card.remove();
            }, 220);
        }
    },

    /**
     * Stop all ticking timers and clear all active call widgets (used on logout/reset)
     */
    stopAllTimers() {
        for (const [key, timerInfo] of this.callTimers.entries()) {
            clearInterval(timerInfo.intervalId || timerInfo);
        }
        this.callTimers.clear();

        for (const [key, timeoutId] of this.dismissTimeouts.entries()) {
            clearTimeout(timeoutId);
        }
        this.dismissTimeouts.clear();

        this.activeCalls.clear();
        this.processedCallKeys.clear();
        const container = document.getElementById('cti-live-calls-container');
        if (container) container.innerHTML = '';
    },

    /**
     * Smooth ticking timer for each call card calculated from start timestamp
     */
    startCardTimer(callKey, startTimeStr) {
        if (this.callTimers.has(callKey)) return;

        let startTimeMs = Date.now();
        if (startTimeStr) {
            const parsed = new Date(startTimeStr).getTime();
            if (!isNaN(parsed) && parsed > 0) {
                startTimeMs = parsed;
            }
        }

        const updateTimerDisplay = () => {
            const elapsedSeconds = Math.max(0, Math.floor((Date.now() - startTimeMs) / 1000));
            const mins = String(Math.floor(elapsedSeconds / 60)).padStart(2, '0');
            const secs = String(elapsedSeconds % 60).padStart(2, '0');
            const timerEl = document.getElementById(`cti-timer-${callKey}`);
            if (timerEl) {
                timerEl.textContent = `${mins}:${secs}`;
            }
        };

        updateTimerDisplay();
        const intervalId = setInterval(updateTimerDisplay, 1000);
        this.callTimers.set(callKey, { intervalId, startTimeMs });
    },

    /**
     * Handler when CDR callback arrives or call disconnects:
     * - Freezes final duration
     * - Displays dismiss state with final status & details
     * - Remains visible for 5 minutes (auto-removes after 5m or manual click)
     */
    handleCallEndedEvent(endData) {
        const callKey = (endData.uuid || endData.call_id || '').trim();
        if (!callKey) return;

        // 1. Stop this specific card's ticking interval timer immediately
        if (this.callTimers.has(callKey)) {
            const timerInfo = this.callTimers.get(callKey);
            clearInterval(timerInfo.intervalId || timerInfo);
            this.callTimers.delete(callKey);
        }

        const existing = this.activeCalls.get(callKey) || {};
        const isCompleted = endData.status === 'completed' || (endData.duration_seconds && endData.duration_seconds > 0);
        const finalStatus = endData.status || (isCompleted ? 'completed' : 'missed');

        // Calculate frozen duration
        let finalDurationSecs = endData.duration_seconds;
        if (finalDurationSecs === undefined || finalDurationSecs === null) {
            const timerEl = document.getElementById(`cti-timer-${callKey}`);
            if (timerEl && timerEl.textContent.includes(':')) {
                const parts = timerEl.textContent.trim().split(':');
                finalDurationSecs = (parseInt(parts[0], 10) * 60) + parseInt(parts[1], 10);
            } else {
                finalDurationSecs = 0;
            }
        }
        const durMins = Math.floor(finalDurationSecs / 60).toString().padStart(2, '0');
        const durSecs = (finalDurationSecs % 60).toString().padStart(2, '0');
        const formattedDur = `${durMins}:${durSecs}`;

        // Update stored call state
        const updatedCall = {
            ...existing,
            ...endData,
            isEnded: true,
            status: finalStatus,
            duration_seconds: finalDurationSecs,
            duration_formatted: formattedDur,
            endedAt: Date.now()
        };
        this.activeCalls.set(callKey, updatedCall);

        // 2. Update Card DOM to Ended / Dismiss State (Create card if not already rendered)
        let card = document.getElementById(`cti-card-${callKey}`);
        if (!card) {
            this.renderCallCard(callKey, updatedCall);
            card = document.getElementById(`cti-card-${callKey}`);
        }
        if (card) {
            card.classList.remove('ringing');
            card.classList.add(isCompleted ? 'completed' : 'missed');

            // Status Pill
            const statusPill = document.getElementById(`cti-status-pill-${callKey}`);
            if (statusPill) {
                let badgeBg = 'var(--success-subtle)';
                let badgeColor = 'var(--success)';
                let labelText = 'CALL COMPLETED';

                if (finalStatus === 'missed') {
                    badgeBg = 'var(--danger-subtle)';
                    badgeColor = 'var(--danger)';
                    labelText = 'CALL MISSED';
                } else if (finalStatus === 'rejected') {
                    badgeBg = 'rgba(239, 68, 68, 0.15)';
                    badgeColor = 'var(--danger)';
                    labelText = 'CALL REJECTED';
                } else if (finalStatus === 'cancelled' || finalStatus === 'failed') {
                    badgeBg = 'var(--warning-subtle)';
                    badgeColor = 'var(--warning)';
                    labelText = `CALL ${finalStatus.toUpperCase()}`;
                }

                statusPill.style.background = badgeBg;
                statusPill.style.color = badgeColor;
                statusPill.innerHTML = `<span>${labelText}</span>`;
            }

            // Freeze Timer Display
            const timerEl = document.getElementById(`cti-timer-${callKey}`);
            if (timerEl) {
                timerEl.textContent = formattedDur;
                timerEl.style.background = isCompleted ? 'var(--success-subtle)' : 'var(--danger-subtle)';
                timerEl.style.color = isCompleted ? 'var(--success)' : 'var(--danger)';
                timerEl.style.borderColor = isCompleted ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)';
            }

            // Status Details & Recording Box
            const endedBox = document.getElementById(`cti-ended-box-${callKey}`);
            if (endedBox) {
                endedBox.style.display = 'block';
                const hangupReason = [endData.hangup_cause, endData.reason_key].filter(Boolean).join(' • ') || 'Call Disconnected';
                const recUrl = endData.recording_url || updatedCall.recording_url;
                endedBox.innerHTML = `
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: ${recUrl ? '0.35rem' : '0'};">
                        <span style="color: var(--text-secondary); font-weight: 500; font-size: 0.72rem;">Status:</span>
                        <span style="color: var(--text-primary); font-weight: 600; font-size: 0.75rem;">${hangupReason}</span>
                    </div>
                    ${recUrl ? `
                        <div style="text-align: right; margin-top: 0.35rem;">
                            <button class="btn btn-primary btn-xs" onclick="cti.playRecording('${recUrl}', '${updatedCall.phone_number || 'Call Recording'}')" style="display: inline-flex; align-items: center; gap: 4px;">
                                ${Icons.get('play', { size: 11 })}
                                <span>Play Audio Recording</span>
                            </button>
                        </div>
                    ` : ''}
                `;
            }

            // Update Action Buttons: Manual Dismiss + 5-min Auto-Clearing Notice
            const actionsBox = document.getElementById(`cti-actions-${callKey}`);
            if (actionsBox) {
                const custId = updatedCall.customer?.id || updatedCall.customer_id;
                actionsBox.innerHTML = `
                    <div style="grid-column: span 4; display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; flex-wrap: wrap;">
                        <button class="btn btn-secondary btn-xs" onclick="cti.dismissCard('${callKey}', event)" style="font-weight: 700; display: inline-flex; align-items: center; gap: 4px; color: var(--text-primary); border-color: var(--border-strong);" title="Manually remove this card immediately">
                            <span>✕ Dismiss</span>
                        </button>
                        <span style="font-size: 0.6875rem; color: var(--text-muted); display: inline-flex; align-items: center; gap: 3px;" title="Popup will automatically remove in 5 minutes unless dismissed earlier">
                            ⏱ Auto-clears in 5m
                        </span>
                        <div style="display: flex; gap: 0.25rem;">
                            ${custId ? `
                                <button class="btn btn-secondary btn-xs" onclick="cti.openAddNote('${callKey}', event)" title="Add CRM Note">
                                    ${Icons.get('edit', { size: 11 })}
                                    <span>Note</span>
                                </button>
                                <button class="btn btn-secondary btn-xs" onclick="cti.openProfile('${callKey}', event)" title="View Profile">
                                    ${Icons.get('user', { size: 11 })}
                                    <span>Profile</span>
                                </button>
                            ` : `
                                <button class="btn btn-primary btn-xs" onclick="customer.openAddModal('${updatedCall.phone_number}'); event.stopPropagation();">
                                    ${Icons.get('user-plus', { size: 11 })}
                                    <span>+ Quick Register</span>
                                </button>
                            `}
                        </div>
                    </div>
                `;
            }
        }

        // 3. Set 5-Minute Auto-Dismiss Timeout (300,000 ms)
        if (this.dismissTimeouts.has(callKey)) {
            clearTimeout(this.dismissTimeouts.get(callKey));
        }
        const timeoutId = setTimeout(() => {
            this.dismissCard(callKey);
        }, 5 * 60 * 1000); // 5 minutes
        this.dismissTimeouts.set(callKey, timeoutId);

        // 4. Refresh Dashboard & Call Logs tables
        app.refreshDashboard();
        if (app.currentView === 'calls') {
            app.loadCallsView();
        }
    },

    playRecording(recordingUrl, title) {
        if (!recordingUrl) {
            api.toast("No recording URL available for this call", "warning");
            return;
        }

        const player = document.getElementById('audio-modal-player');
        const source = document.getElementById('audio-modal-source');
        const metaEl = document.getElementById('audio-modal-meta');
        const downloadLink = document.getElementById('audio-modal-download-link');
        const loadingEl = document.getElementById('audio-modal-loading');

        // Route through high-speed backend streaming proxy with caching & HTTP range support
        let streamUrl = recordingUrl;
        if (recordingUrl.startsWith('http://') || recordingUrl.startsWith('https://')) {
            streamUrl = `/api/calls/recording-stream?url=${encodeURIComponent(recordingUrl)}`;
        }

        if (loadingEl) loadingEl.style.display = 'flex';
        if (metaEl) metaEl.textContent = title ? `Call Recording: ${title}` : 'Call Audio Recording';
        if (downloadLink) downloadLink.href = streamUrl;

        // Reset speed button state to 1.0x
        document.querySelectorAll('.speed-btn').forEach(b => {
            b.classList.toggle('active', b.dataset.speed === "1");
        });

        if (player) {
            player.playbackRate = 1.0;
            player.pause();
            player.currentTime = 0;
            player.preload = "auto";

            player.oncanplay = () => {
                if (loadingEl) loadingEl.style.display = 'none';
            };
            player.onplaying = () => {
                if (loadingEl) loadingEl.style.display = 'none';
            };
            player.onerror = () => {
                if (loadingEl) {
                    loadingEl.innerHTML = `<span class="text-danger" style="font-size:0.75rem;">Connecting directly to remote recording...</span>`;
                }
                // Fallback to direct URL if proxy encountered network glitch
                if (source && source.src !== recordingUrl) {
                    source.src = recordingUrl;
                    player.load();
                    player.play().catch(() => {});
                }
            };

            if (source) source.src = streamUrl;
            player.load();
            player.play().catch(e => {
                console.log("Autoplay paused or awaiting user action:", e);
            });
        }

        app.openModal('modal-audio-player');
    },

    skipAudio(seconds) {
        const player = document.getElementById('audio-modal-player');
        if (player && !isNaN(player.duration)) {
            player.currentTime = Math.max(0, Math.min(player.duration, player.currentTime + seconds));
        }
    },

    setAudioSpeed(speed, buttonEl) {
        const player = document.getElementById('audio-modal-player');
        if (player) {
            player.playbackRate = parseFloat(speed) || 1.0;
            document.querySelectorAll('.speed-btn').forEach(b => b.classList.remove('active'));
            if (buttonEl) buttonEl.classList.add('active');
        }
    },

    async simulateIncomingCall(phoneNumber) {
        api.toast(`Initiating incoming Smartflo call simulation for ${phoneNumber}...`, "info");

        try {
            const res = await api.post('/calls/simulate', {
                phone_number: phoneNumber,
                direction: "incoming",
                provider: "smartflo",
                call_to_number: "918065908541",
                operator: "Reliance",
                circle: "Punjab",
                agent_name: "Pankaj"
            });

            this.handleIncomingCallEvent(res);
        } catch (err) {
            api.toast(`CTI simulation error: ${err.message}`, "error");
        }
    },

    dialerLookupTimeout: null,
    currentDialerMatchedCustomer: null,

    SMARTFLO_STAFF_VIDS: [
        {
            name: "Shivam",
            role: "System Admin",
            isAdmin: true,
            vid: "918065908540",
            email: "itchd.kogm@gmail.com",
            avatar: "SH"
        },
        {
            name: "Yogesh Khandelia",
            role: "Director",
            isAdmin: true,
            vid: "918065908540",
            email: "infotech@khandelia.com",
            avatar: "YK"
        },
        {
            name: "Sahil Dogra",
            role: "Support Agent",
            isAdmin: false,
            vid: "918065908531",
            email: "kogm.sahildogra@gmail.com",
            avatar: "SD"
        },
        {
            name: "BM Jagga",
            role: "Support Agent",
            isAdmin: false,
            vid: "918065908532",
            email: "bmjagga@khandelia.com",
            avatar: "BJ"
        },
        {
            name: "Utpal Pal",
            role: "Support Agent",
            isAdmin: false,
            vid: "918065908533",
            email: "sales.kol@khandelia.com",
            avatar: "UP"
        },
        {
            name: "Sunil Jain",
            role: "Support Agent",
            isAdmin: false,
            vid: "918065908534",
            email: "sales.gm@khandelia.com",
            avatar: "SJ"
        },
        {
            name: "Ravi Kumar",
            role: "Customer Care",
            isAdmin: false,
            vid: "918065908535",
            email: "customercare@khandelia.com",
            avatar: "RK"
        },
        {
            name: "Ankush Dingra",
            role: "Sales",
            isAdmin: false,
            vid: "918065908536",
            email: "account.unit6@khandelia.com",
            avatar: "AD"
        },
        {
            name: "Sonu Kumar",
            role: "HR manager",
            isAdmin: false,
            vid: "918065908538",
            email: "kogm.sonukumar@gmail.com",
            avatar: "SK"
        },
        {
            name: "Ankush Kapila",
            role: "store manager",
            isAdmin: false,
            vid: "918065908539",
            email: "storepurchase@khandelia.com",
            avatar: "AK"
        },
        {
            name: "Pankaj",
            role: "Sales Team",
            isAdmin: false,
            vid: "918065908541",
            email: "kogm.pankaj@gmail.com",
            avatar: "P"
        }
    ],

    selectedVidRecord: null,

    toggleVidMenu(e) {
        if (e) {
            e.preventDefault();
            e.stopPropagation();
        }
        const dropdown = document.getElementById('vid-picker-dropdown');
        const menu = document.getElementById('vid-picker-menu');
        if (!dropdown || !menu) return;

        const isOpen = dropdown.classList.contains('open');
        if (isOpen) {
            this.closeVidMenu();
        } else {
            dropdown.classList.add('open');
            menu.style.display = 'block';
            this.populateVidPicker();
            
            const closeHandler = (event) => {
                if (!dropdown.contains(event.target)) {
                    this.closeVidMenu();
                    document.removeEventListener('click', closeHandler);
                }
            };
            setTimeout(() => document.addEventListener('click', closeHandler), 50);
        }
    },

    closeVidMenu() {
        const dropdown = document.getElementById('vid-picker-dropdown');
        const menu = document.getElementById('vid-picker-menu');
        if (dropdown) dropdown.classList.remove('open');
        if (menu) menu.style.display = 'none';
    },

    selectVid(vid, staffName, role, avatar, isAdmin, e) {
        if (e) {
            e.preventDefault();
            e.stopPropagation();
        }
        this.selectedVidRecord = { vid, staffName, role, avatar, isAdmin };

        const avatarEl = document.getElementById('vid-picker-selected-avatar');
        const nameEl = document.getElementById('vid-picker-selected-name');
        const roleEl = document.getElementById('vid-picker-selected-role');
        const numEl = document.getElementById('vid-picker-selected-number');
        const selectEl = document.getElementById('dialer-selected-vid');
        const profileEl = document.getElementById('dialer-active-caller-profile');

        if (avatarEl) {
            avatarEl.textContent = avatar;
            if (isAdmin) {
                avatarEl.classList.add('admin');
            } else {
                avatarEl.classList.remove('admin');
            }
        }
        if (nameEl) nameEl.textContent = staffName;
        if (roleEl) {
            roleEl.textContent = role;
            roleEl.className = isAdmin ? 'badge badge-primary' : 'badge badge-standard';
        }
        if (numEl) numEl.textContent = vid;
        if (selectEl) {
            selectEl.innerHTML = `<option value="${vid}" selected>${vid}</option>`;
            selectEl.value = vid;
        }

        const user = api.getCurrentUser();
        if (profileEl) {
            const roleBadge = user && user.role === 'admin' ? 'Admin' : 'Staff';
            profileEl.innerHTML = `Calling As: <strong>${user ? user.full_name : 'Staff'}</strong> (${roleBadge}) • Trunk: <strong style="color: var(--primary);">${vid} (${staffName})</strong>`;
        }

        this.closeVidMenu();
    },

    populateVidPicker() {
        const listEl = document.getElementById('vid-picker-list');
        if (!listEl) return;

        const currentVid = this.selectedVidRecord?.vid || document.getElementById('dialer-selected-vid')?.value || '918065908540';

        listEl.innerHTML = this.SMARTFLO_STAFF_VIDS.map(staff => {
            const isSelected = String(staff.vid) === String(currentVid);
            const avatarClass = staff.isAdmin ? 'vid-picker-avatar admin' : 'vid-picker-avatar';
            const roleBadgeClass = staff.isAdmin ? 'badge badge-primary' : 'badge badge-standard';

            return `
                <div class="vid-picker-item ${isSelected ? 'active' : ''}" 
                    onclick="cti.selectVid('${staff.vid}', '${staff.name.replace(/'/g, "\\'")}', '${staff.role.replace(/'/g, "\\'")}', '${staff.avatar}', ${staff.isAdmin}, event)">
                    <div style="display: flex; align-items: center; gap: 0.55rem; min-width: 0;">
                        <div class="${avatarClass}" style="width: 28px; height: 28px; font-size: 0.72rem;">${staff.avatar}</div>
                        <div style="min-width: 0; text-align: left;">
                            <div style="display: flex; align-items: center; gap: 0.35rem;">
                                <strong style="font-size: 0.8125rem; color: var(--text-primary);">${staff.name}</strong>
                                <span class="${roleBadgeClass}" style="font-size: 0.625rem; padding: 0.05rem 0.3rem;">${staff.role}</span>
                            </div>
                            <div style="font-size: 0.6875rem; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                                ${staff.email}
                            </div>
                        </div>
                    </div>
                    <div style="text-align: right; flex-shrink: 0; margin-left: 0.5rem;">
                        <div style="font-size: 0.75rem; font-weight: 700; color: ${isSelected ? 'var(--success)' : 'var(--text-primary)'}; font-variant-numeric: tabular-nums;">
                            ${staff.vid}
                        </div>
                        ${isSelected ? '<span style="font-size: 0.6875rem; color: var(--success); font-weight: 700;">✓ Selected</span>' : ''}
                    </div>
                </div>
            `;
        }).join('');
    },

    openDialerModal(prefillNumber = '', customerName = '', customerId = null) {
        const modal = document.getElementById('modal-direct-dialer');
        const profileEl = document.getElementById('dialer-active-caller-profile');
        const vidGroup = document.getElementById('dialer-vid-select-group');
        const input = document.getElementById('dialer-phone-input');
        const preview = document.getElementById('dialer-live-customer-preview');

        if (!modal) return;

        const user = api.getCurrentUser();
        const isAdmin = user && user.role === 'admin';
        const userVid = (user && (user.allowed_caller_id || user.vid)) || '918065908540';

        // Find staff matching current user
        const matchedStaff = this.SMARTFLO_STAFF_VIDS.find(s => s.vid === userVid || (user && s.email === user.email)) || this.SMARTFLO_STAFF_VIDS[0];

        if (vidGroup) vidGroup.style.display = 'block';
        this.selectVid(matchedStaff.vid, matchedStaff.name, matchedStaff.role, matchedStaff.avatar, matchedStaff.isAdmin);

        this.currentDialerMatchedCustomer = customerId ? { id: customerId, party_name: customerName } : null;

        if (input) {
            input.value = prefillNumber || '';
        }

        if (prefillNumber) {
            if (customerName) {
                if (preview) preview.innerHTML = `<strong style="color: var(--primary);">🏢 ${customerName}</strong> • Matched Customer`;
            } else {
                this.handleDialerInputChange(prefillNumber);
            }
        } else {
            if (preview) preview.innerHTML = `<span>Type or paste any number to call</span>`;
        }

        app.openModal('modal-direct-dialer');
        setTimeout(() => input && input.focus(), 150);
    },

    dialerPress(digit) {
        const input = document.getElementById('dialer-phone-input');
        if (!input) return;
        input.value = (input.value || '') + digit;
        this.handleDialerInputChange(input.value);
        this.playDtmfTone(digit);
    },

    dialerBackspace() {
        const input = document.getElementById('dialer-phone-input');
        if (!input || !input.value) return;
        input.value = input.value.slice(0, -1);
        this.handleDialerInputChange(input.value);
    },

    handleDialerInputChange(value) {
        const preview = document.getElementById('dialer-live-customer-preview');
        if (!preview) return;

        const clean = String(value || '').trim();
        if (clean.length < 3) {
            preview.innerHTML = `<span>Type or paste any number to call</span>`;
            this.currentDialerMatchedCustomer = null;
            return;
        }

        preview.innerHTML = `<span>Searching customer database...</span>`;
        clearTimeout(this.dialerLookupTimeout);
        this.dialerLookupTimeout = setTimeout(async () => {
            try {
                const results = await api.get(`/customers/search?q=${encodeURIComponent(clean)}`);
                if (results && results.length > 0) {
                    const match = results[0];
                    this.currentDialerMatchedCustomer = match;
                    const custName = match.party_name || match.name || 'Identified Customer';
                    const cityStr = match.city ? ` • ${match.city}` : '';
                    const codeStr = match.party_code ? ` (${match.party_code})` : '';
                    preview.innerHTML = `<strong style="color: var(--primary);">🏢 ${custName}</strong>${codeStr}${cityStr}`;
                } else {
                    this.currentDialerMatchedCustomer = null;
                    preview.innerHTML = `<span style="color: var(--text-muted);">Unregistered Number • Direct Outbound Call</span>`;
                }
            } catch (err) {
                preview.innerHTML = `<span style="color: var(--text-muted);">Direct Outbound Call</span>`;
            }
        }, 200);
    },

    async executeDirectDial() {
        const input = document.getElementById('dialer-phone-input');
        const phone = input ? input.value.trim() : '';
        if (!phone || phone.length < 3) {
            api.toast("Please enter a valid phone number to dial", "error");
            if (input) input.focus();
            return;
        }

        const btn = document.getElementById('btn-dialer-call-submit');
        const originalText = btn ? btn.innerHTML : '';
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = `<span>Connecting Call...</span>`;
        }

        const vidSelect = document.getElementById('dialer-selected-vid');
        const user = api.getCurrentUser();
        const selectedVid = (vidSelect && vidSelect.value) || (user && (user.allowed_caller_id || user.vid)) || '918065908540';
        const customerId = this.currentDialerMatchedCustomer?.id || null;

        try {
            const res = await api.post('/calls/outgoing', {
                phone_number: phone,
                vid: selectedVid,
                customer_id: customerId,
                provider: 'smartflo'
            });

            app.closeModal('modal-direct-dialer');
            const provResp = res.provider_response || {};
            const provMsg = provResp.warning || provResp.error || provResp.message || '';
            if (provResp.status === 'failed' || (provMsg && (provMsg.toLowerCase().includes('offline') || provMsg.toLowerCase().includes('error') || provMsg.toLowerCase().includes('failed') || provMsg.toLowerCase().includes('401')))) {
                api.toast(`Smartflo: ${provMsg || 'Could not place call.'}`, "warning");
            } else {
                api.toast(provResp.message || `Connecting call to ${phone} via VID ${selectedVid}...`, "success");
            }

            // If immediate broadcast response returned
            if (res && res.call_id) {
                this.handleIncomingCallEvent({
                    event: 'outgoing_call',
                    call_id: res.call_id,
                    uuid: res.uuid || res.call_id,
                    call_to_number: phone,
                    phone_number: phone,
                    caller_phone: selectedVid,
                    caller_id: selectedVid,
                    vid: selectedVid,
                    direction: 'outgoing',
                    customer_found: Boolean(res.customer),
                    customer: res.customer,
                    status: 'ringing',
                    start_time: new Date().toISOString()
                });
            }
        } catch (err) {
            console.error("Direct dial error:", err);
            api.toast(`Failed to place call: ${err.message}`, "error");
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = originalText;
            }
        }
    },

    initiateDirectCall(phone, customerId = null, customerName = '') {
        this.openDialerModal(phone, customerName, customerId);
    },

    makeOutgoingCall(phone, customerId = null, customerName = '') {
        this.openDialerModal(phone, customerName, customerId);
    },

    playDtmfTone(digit) {
        try {
            const ctx = new (window.AudioContext || window.webkitAudioContext)();
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            const freqs = {
                '1': 697, '2': 697, '3': 697,
                '4': 770, '5': 770, '6': 770,
                '7': 852, '8': 852, '9': 852,
                '*': 941, '0': 941, '#': 941
            };
            osc.frequency.setValueAtTime(freqs[digit] || 700, ctx.currentTime);
            gain.gain.setValueAtTime(0.08, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.12);
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.start();
            osc.stop(ctx.currentTime + 0.13);
        } catch (e) {}
    },

    playCallChime() {
        try {
            const ctx = new (window.AudioContext || window.webkitAudioContext)();
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            const freqs = [587.33, 880];
            osc.type = 'sine';
            osc.frequency.setValueAtTime(587.33, ctx.currentTime); // D5
            osc.frequency.setValueAtTime(880, ctx.currentTime + 0.15); // A5
            gain.gain.setValueAtTime(0.15, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.start();
            osc.stop(ctx.currentTime + 0.45);
        } catch (e) {
            // Audio context unsupported or user gesture required
        }
    }
};

window.cti = cti;
