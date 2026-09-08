/**
 * Excel / CSV Importer with 25-Column Sequence Validation, Permission Enforcement & Duplicate Protection
 */
const excelImport = {
    selectedFile: null,

    canUploadToCategory(category) {
        const user = (typeof api !== 'undefined' && api.getCurrentUser) ? api.getCurrentUser() : null;
        if (!user) return false;
        if (user.role === 'admin' || user.role === 'ADMIN') return true;

        let allowed = [];
        let raw = user.allowed_upload_categories;
        if (Array.isArray(raw)) {
            allowed = raw.map(c => String(c).trim().toUpperCase());
        } else if (typeof raw === 'string') {
            let s = raw.replace(/[\[\]\'\"]/g, '').trim();
            if (s) allowed = s.split(',').map(c => c.trim().toUpperCase());
        }

        if (allowed.includes('*') || allowed.includes('ALL') || allowed.length >= 10) return true;
        if (!category || category === 'auto') {
            return allowed.length > 0;
        }
        return allowed.includes(category.toUpperCase());
    },

    checkUploadAccess() {
        const catSelect = document.getElementById('excel-import-category-select');
        const selectedCat = catSelect ? catSelect.value : 'auto';
        const isAllowed = this.canUploadToCategory(selectedCat);

        const alertBox = document.getElementById('import-permission-alert');
        const dropzone = document.getElementById('excel-dropzone');
        const fileInput = document.getElementById('excel-file-input');
        const btnImport = document.getElementById('btn-execute-import');

        if (!isAllowed) {
            if (alertBox) {
                alertBox.style.display = 'block';
                alertBox.innerHTML = `
                    <div style="background: rgba(239,68,68,0.12); border: 1.5px solid var(--danger); border-radius: var(--radius-md); padding: 0.85rem 1rem; color: var(--danger); display: flex; align-items: flex-start; gap: 0.6rem;">
                        <svg class="icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="flex-shrink: 0; margin-top: 2px;"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                        <div>
                            <div style="font-weight: 700; font-size: 0.875rem;">🔒 Upload Permission Restricted</div>
                            <div style="font-size: 0.8125rem; margin-top: 2px; line-height: 1.4;">
                                New data upload access is restricted by default. You do not have permission to upload data for <strong>${selectedCat === 'auto' ? 'this category' : selectedCat}</strong>. Please contact your System Administrator to request category upload permissions.
                            </div>
                        </div>
                    </div>
                `;
            }
            if (dropzone) {
                dropzone.style.opacity = '0.5';
                dropzone.style.pointerEvents = 'none';
            }
            if (fileInput) fileInput.disabled = true;
            if (btnImport) btnImport.disabled = true;
        } else {
            if (alertBox) {
                alertBox.style.display = 'none';
            }
            if (dropzone) {
                dropzone.style.opacity = '1';
                dropzone.style.pointerEvents = 'auto';
            }
            if (fileInput) fileInput.disabled = false;
            if (btnImport) btnImport.disabled = false;
        }
        return isAllowed;
    },

    init() {
        const dropzone = document.getElementById('excel-dropzone');
        const fileInput = document.getElementById('excel-file-input');
        const catSelect = document.getElementById('excel-import-category-select');

        if (catSelect) {
            catSelect.addEventListener('change', () => {
                this.checkUploadAccess();
            });
        }

        if (dropzone && fileInput) {
            dropzone.addEventListener('dragover', (e) => {
                e.preventDefault();
                dropzone.classList.add('dragover');
            });
            dropzone.addEventListener('dragleave', () => {
                dropzone.classList.remove('dragover');
            });
            dropzone.addEventListener('drop', (e) => {
                e.preventDefault();
                dropzone.classList.remove('dragover');
                if (e.dataTransfer.files.length > 0) {
                    this.handleFileSelect(e.dataTransfer.files[0]);
                }
            });

            fileInput.addEventListener('change', (e) => {
                if (e.target.files.length > 0) {
                    this.handleFileSelect(e.target.files[0]);
                }
            });
        }

        // Execute import button
        document.getElementById('btn-execute-import')?.addEventListener('click', () => {
            this.executeImport();
        });

        // Initialize Quick Permissions Employee Dropdown if present
        this.populateQuickPermEmployees();

        // Check current upload permissions
        this.checkUploadAccess();
    },

    async handleFileSelect(file) {
        if (!file.name.match(/\.(xlsx|xls|csv)$/i)) {
            api.toast("Please upload a valid Excel (.xlsx) or CSV file", "error");
            return;
        }

        if (!this.checkUploadAccess()) {
            api.toast("🔒 You do not have permission to upload new data files for this category.", "error");
            return;
        }

        this.selectedFile = file;
        api.toast(`Inspecting and validating ${file.name}...`, "info");

        const formData = new FormData();
        formData.append("file", file);

        try {
            const preview = await api.post('/imports/preview', formData);
            this.renderPreview(preview);
        } catch (err) {
            this.renderValidationError(err.message);
            api.toast(`Validation Error: ${err.message}`, "error");
        }
    },

    renderValidationError(errorMessage) {
        const section = document.getElementById('import-preview-section');
        const statusDiv = document.getElementById('import-validation-status');
        const sampleContainer = document.getElementById('import-sample-table-container');

        if (section) section.style.display = 'block';
        if (sampleContainer) sampleContainer.style.display = 'none';

        if (statusDiv) {
            statusDiv.innerHTML = `
                <div style="background: var(--danger-subtle); border: 1px solid var(--danger); border-radius: var(--radius-md); padding: 0.875rem 1rem; color: var(--danger);">
                    <div style="font-weight: 600; font-size: 0.875rem; margin-bottom: 0.25rem; display: flex; align-items: center; gap: 0.4rem;">
                        ${Icons.get('alert-triangle', { size: 16 })}
                        <span>Column Validation Failed</span>
                    </div>
                    <div style="font-size: 0.8125rem; line-height: 1.5;">${errorMessage}</div>
                    <div style="margin-top: 0.5rem; font-size: 0.75rem; color: var(--text-secondary);">
                        Please ensure your file adheres to the 25-column schema where <strong>Address Code*</strong> is mandatory. You can download the official sample template above.
                    </div>
                </div>
            `;
        }
    },

    renderPreview(previewData) {
        const section = document.getElementById('import-preview-section');
        const statusDiv = document.getElementById('import-validation-status');
        const sampleContainer = document.getElementById('import-sample-table-container');
        const thead = document.getElementById('import-sample-thead');
        const tbody = document.getElementById('import-sample-tbody');

        if (section) section.style.display = 'block';
        if (sampleContainer) sampleContainer.style.display = 'block';

        if (statusDiv) {
            statusDiv.innerHTML = `
                <div style="background: var(--success-subtle); border: 1px solid var(--success); border-radius: var(--radius-md); padding: 0.75rem 1rem; color: var(--success); display: flex; align-items: center; justify-content: space-between; gap: 0.75rem;">
                    <div style="display: flex; align-items: center; gap: 0.4rem; font-size: 0.8125rem;">
                        ${Icons.get('check', { size: 16 })}
                        <span><strong>Schema Validation Passed:</strong> File contains all required columns and Address Code* is valid!</span>
                    </div>
                    <span class="badge badge-active">${previewData.total_detected_rows} Rows Ready</span>
                </div>
            `;
        }

        // Render Sample Table Headers
        if (thead && previewData.headers) {
            thead.innerHTML = `
                <tr>
                    <th style="padding: 6px 10px;">#</th>
                    ${previewData.headers.map((h, i) => `<th style="padding: 6px 10px;">${i+1}. ${h}</th>`).join('')}
                </tr>
            `;
        }

        // Render Sample Table Rows
        if (tbody && previewData.sample_rows) {
            tbody.innerHTML = previewData.sample_rows.map((row, idx) => `
                <tr>
                    <td style="padding: 6px 10px; font-weight: 600;">${idx+1}</td>
                    ${previewData.headers.map(h => `<td style="padding: 6px 10px;">${row[h] || '—'}</td>`).join('')}
                </tr>
            `).join('');
        }

        api.toast(`Validated ${previewData.total_detected_rows} data rows successfully!`, "success");
    },

    showProgressModal(filename, totalRows) {
        let modal = document.getElementById('import-progress-modal');
        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'import-progress-modal';
            modal.style.cssText = 'position: fixed; inset: 0; background: rgba(0, 0, 0, 0.65); backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px); display: flex; align-items: center; justify-content: center; z-index: 999999; opacity: 0; transition: opacity 0.25s ease;';
            modal.innerHTML = `
                <div class="card" style="width: 92%; max-width: 420px; text-align: center; padding: 2.25rem 1.75rem; background: var(--bg-surface); border: 1px solid var(--border-color); border-radius: var(--radius-xl); box-shadow: 0 20px 50px rgba(0,0,0,0.3); transform: scale(0.95); transition: transform 0.25s ease;">
                    <div style="position: relative; width: 130px; height: 130px; margin: 0 auto 1.25rem;">
                        <svg width="130" height="130" viewBox="0 0 130 130" style="transform: rotate(-90deg);">
                            <circle cx="65" cy="65" r="54" fill="none" stroke="var(--border-color)" stroke-width="8" opacity="0.35" />
                            <circle id="import-circle-bar" cx="65" cy="65" r="54" fill="none" stroke="url(#import-circle-gradient)" stroke-width="8" stroke-linecap="round" stroke-dasharray="339.292" stroke-dashoffset="339.292" style="transition: stroke-dashoffset 0.25s ease;" />
                            <defs>
                                <linearGradient id="import-circle-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
                                    <stop offset="0%" stop-color="#3b82f6" />
                                    <stop offset="100%" stop-color="#10b981" />
                                </linearGradient>
                            </defs>
                        </svg>
                        <div style="position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center;">
                            <span id="import-circle-percent" style="font-size: 1.75rem; font-weight: 800; color: var(--text-primary); letter-spacing: -0.02em;">0%</span>
                            <span id="import-circle-icon" style="display: none; color: #10b981; font-size: 2.2rem; font-weight: 700; line-height: 1;">✓</span>
                        </div>
                    </div>

                    <h3 id="import-circle-title" style="font-size: 1.15rem; font-weight: 700; margin: 0 0 0.35rem; color: var(--text-primary);">Processing Import...</h3>
                    <p id="import-circle-desc" style="font-size: 0.8125rem; color: var(--text-muted); margin: 0 0 1.25rem; line-height: 1.4;">Synchronizing records with database</p>

                    <div style="display: flex; justify-content: center; gap: 0.4rem; margin-top: 0.5rem;">
                        <span id="import-step-dot-1" style="width: 28px; height: 4px; border-radius: 2px; background: var(--primary); transition: background 0.2s;"></span>
                        <span id="import-step-dot-2" style="width: 28px; height: 4px; border-radius: 2px; background: var(--border-color); transition: background 0.2s;"></span>
                        <span id="import-step-dot-3" style="width: 28px; height: 4px; border-radius: 2px; background: var(--border-color); transition: background 0.2s;"></span>
                        <span id="import-step-dot-4" style="width: 28px; height: 4px; border-radius: 2px; background: var(--border-color); transition: background 0.2s;"></span>
                    </div>
                </div>
            `;
            document.body.appendChild(modal);
        }

        modal.style.display = 'flex';
        // Force reflow
        modal.offsetHeight;
        modal.style.opacity = '1';
        const card = modal.querySelector('.card');
        if (card) card.style.transform = 'scale(1)';

        this.updateProgress(5, "Uploading File Buffer...", `Preparing ${totalRows || ''} rows for processing`, 1);
    },

    updateProgress(percent, title, desc, step = 1) {
        const modal = document.getElementById('import-progress-modal');
        if (!modal) return;

        const circleBar = document.getElementById('import-circle-bar');
        const percentText = document.getElementById('import-circle-percent');
        const checkIcon = document.getElementById('import-circle-icon');
        const titleEl = document.getElementById('import-circle-title');
        const descEl = document.getElementById('import-circle-desc');

        const circumference = 339.292;
        const offset = circumference - (percent / 100) * circumference;

        if (circleBar) {
            circleBar.style.strokeDashoffset = offset;
            if (percent >= 100) {
                circleBar.setAttribute('stroke', '#10b981');
            } else {
                circleBar.setAttribute('stroke', 'url(#import-circle-gradient)');
            }
        }

        if (percentText) {
            if (percent >= 100) {
                percentText.style.display = 'none';
                if (checkIcon) checkIcon.style.display = 'block';
            } else {
                percentText.style.display = 'block';
                percentText.textContent = `${Math.round(percent)}%`;
                if (checkIcon) checkIcon.style.display = 'none';
            }
        }

        if (titleEl && title) titleEl.textContent = title;
        if (descEl && desc) descEl.textContent = desc;

        for (let i = 1; i <= 4; i++) {
            const dot = document.getElementById(`import-step-dot-${i}`);
            if (dot) {
                dot.style.background = (i <= step) ? 'var(--primary)' : 'var(--border-color)';
                if (percent >= 100) dot.style.background = '#10b981';
            }
        }
    },

    hideProgressModal() {
        const modal = document.getElementById('import-progress-modal');
        if (!modal) return;
        modal.style.opacity = '0';
        const card = modal.querySelector('.card');
        if (card) card.style.transform = 'scale(0.95)';
        setTimeout(() => {
            modal.style.display = 'none';
        }, 260);
    },

    syncCountersInstantly(result) {
        if (!result) return;

        // Calculate accurate total customer count
        let totalCount = result.total_customers;
        if (totalCount === undefined || totalCount === null) {
            const currBadge = document.getElementById('nav-badge-customers');
            let currVal = 0;
            if (currBadge && currBadge.textContent) {
                let txt = currBadge.textContent.trim().toUpperCase();
                if (txt.endsWith('K')) currVal = Math.round(parseFloat(txt) * 1000);
                else currVal = parseInt(txt.replace(/,/g, ''), 10) || 0;
            }
            totalCount = currVal + (result.imported_count || 0);
        }

        const formattedDisplay = (window.app && typeof app.formatNumberDisplay === 'function') 
            ? app.formatNumberDisplay(totalCount) 
            : totalCount.toLocaleString();
        const formattedFull = (window.app && typeof app.formatFullNumber === 'function')
            ? app.formatFullNumber(totalCount)
            : totalCount.toLocaleString();

        // 1. Instantaneously update ALL sidebar customer badges (Desktop + Mobile)
        const allBadges = document.querySelectorAll('#nav-badge-customers');
        allBadges.forEach(b => {
            b.textContent = formattedDisplay;
            b.title = `${formattedFull} Total Customers`;
            b.style.transition = 'transform 0.2s ease, background-color 0.2s ease';
            b.style.transform = 'scale(1.25)';
            setTimeout(() => { b.style.transform = 'scale(1)'; }, 350);
        });

        // 2. Instantaneously update Dashboard "Active Directory" KPI Card
        const kpiCards = document.querySelectorAll('#dashboard-kpis .kpi-card');
        if (kpiCards.length > 0) {
            const firstCardVal = kpiCards[0].querySelector('.kpi-value');
            if (firstCardVal) {
                firstCardVal.textContent = formattedDisplay;
                firstCardVal.title = `${formattedFull} Total Records`;
                firstCardVal.style.transition = 'transform 0.2s ease, color 0.2s ease';
                firstCardVal.style.transform = 'scale(1.08)';
                setTimeout(() => { firstCardVal.style.transform = 'scale(1)'; }, 350);
            }
        }

        // 3. Update cached stats in app memory so any view switch is 100% instant
        if (window.app && window.app._cachedDashboardStats) {
            if (window.app._cachedDashboardStats.kpis) {
                window.app._cachedDashboardStats.kpis.total_customers = totalCount;
            } else {
                window.app._cachedDashboardStats.total_customers = totalCount;
            }
        }

        // 4. Invalidate Customers table cached data
        if (typeof customer !== 'undefined') {
            customer.cachedData = null;
        }
    },

    async executeImport() {
        if (!this.selectedFile) {
            api.toast("No file selected for import", "error");
            return;
        }

        if (!this.checkUploadAccess()) {
            api.toast("🔒 Upload permission denied for selected category.", "error");
            return;
        }

        const btn = document.getElementById('btn-execute-import');
        const origText = btn ? btn.innerHTML : "Confirm & Start Import";

        const importMode = document.querySelector('input[name="import-mode"]:checked')?.value || "skip";
        const catSelect = document.getElementById('excel-import-category-select');

        const formData = new FormData();
        formData.append("file", this.selectedFile);
        formData.append("import_mode", importMode);
        if (catSelect && catSelect.value && catSelect.value !== 'auto') {
            formData.append("category", catSelect.value);
        }

        if (btn) {
            btn.disabled = true;
            btn.innerHTML = `<span style="display: inline-flex; align-items: center; gap: 0.4rem;">Synchronizing...</span>`;
        }

        const previewRows = this.selectedFile ? "File Stream" : "";
        this.showProgressModal(this.selectedFile.name, previewRows);

        // Smooth simulated progress while server processes
        let currentProgress = 10;
        const progressInterval = setInterval(() => {
            if (currentProgress < 30) {
                currentProgress += 4;
                this.updateProgress(currentProgress, "Uploading File Stream...", "Reading file bytes into memory buffer", 1);
            } else if (currentProgress < 65) {
                currentProgress += 3;
                this.updateProgress(currentProgress, "Validating 25 Columns & Phones...", "Normalizing primary & alternate phone numbers", 2);
            } else if (currentProgress < 90) {
                currentProgress += 1.5;
                this.updateProgress(currentProgress, "O(1) Hash Deduplication...", "Matching existing records and checking diffs", 3);
            } else if (currentProgress < 96) {
                currentProgress += 0.5;
                this.updateProgress(currentProgress, "Batch Flushing to Database...", "Writing optimized batch chunks to PostgreSQL", 4);
            }
        }, 120);

        const startTime = performance.now();

        try {
            const result = await api.post('/imports/process', formData);
            clearInterval(progressInterval);

            const durationMs = Math.round(performance.now() - startTime);
            result.duration_ms = durationMs;

            // Step 1: Instant 100% Progress Completion
            this.updateProgress(100, "Import Completed!", `Successfully processed ${result.total_rows} rows in ${durationMs}ms`, 4);

            // Step 2: Instantaneously ("Palak Jhapaktay Hi") update all counters & badges across UI in 0ms!
            this.syncCountersInstantly(result);

            // Step 3: Wait 500ms for user to admire the 100% checkmark, then hide modal & show summary
            setTimeout(() => {
                this.hideProgressModal();
                this.renderResultSummary(result);
                this.loadHistory();

                // Re-hydrate full tables and lists in background
                if (typeof customer !== 'undefined' && typeof customer.loadCustomers === 'function') {
                    customer.loadCustomers();
                }
                if (window.app && typeof app.refreshDashboard === 'function') {
                    app.refreshDashboard();
                }

                api.toast(`Synchronized ${result.total_rows} records in ${durationMs}ms!`, "success");
            }, 600);

        } catch (err) {
            clearInterval(progressInterval);
            this.hideProgressModal();
            api.toast(`Import failed: ${err.message}`, "error");
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = origText;
            }
        }
    },

    renderResultSummary(res) {
        const summaryBox = document.getElementById('import-result-summary');
        if (!summaryBox) return;
        summaryBox.style.display = 'block';

        const safeFilename = (res.filename || '').replace(/'/g, "\\'");

        summaryBox.innerHTML = `
            <div class="card" style="background: var(--bg-surface-elevated); border: 1px solid var(--primary); margin-bottom: 1.25rem;">
                <div class="card-header" style="flex-wrap: wrap; gap: 0.5rem;">
                    <div class="card-title" style="color: var(--success); display: flex; align-items: center; gap: 0.4rem;">
                        ${Icons.get('check', { size: 16 })}
                        <span>Import Completed: ${res.filename}</span>
                    </div>
                    <div style="display: flex; gap: 0.4rem; flex-wrap: wrap;">
                        ${res.updated_count > 0 ? `
                            <button type="button" class="btn btn-secondary btn-xs" onclick="excelImport.openJobUpdatesModal(${res.job_id}, '${safeFilename}', ${res.total_rows}, ${res.imported_count}, ${res.updated_count}, ${res.error_count})" style="color: var(--primary); font-weight: 600;">
                                ${Icons.get('refresh-cw', { size: 12 })}
                                <span>View ${res.updated_count} Updated Records</span>
                            </button>
                        ` : ''}
                        ${res.error_count > 0 ? `
                            <a href="/api/imports/${res.job_id}/download-errors" class="btn btn-danger btn-xs">
                                ${Icons.get('download', { size: 12 })}
                                <span>Download Error Report</span>
                            </a>
                        ` : ''}
                    </div>
                </div>

                <div class="grid-4" style="margin-bottom: 1rem; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));">
                    <div class="kpi-card" style="padding: 0.75rem 1rem;">
                        <span class="meta-label">Total File Rows</span>
                        <div class="kpi-value" style="font-size: 1.35rem;">${res.total_rows}</div>
                    </div>
                    <div class="kpi-card" style="padding: 0.75rem 1rem;">
                        <span class="meta-label" style="color: var(--success);">New Inserted</span>
                        <div class="kpi-value" style="font-size: 1.35rem; color: var(--success);">${res.imported_count}</div>
                    </div>
                    ${(res.updated_count > 0 || res.import_mode === 'update') ? `
                    <div class="kpi-card" style="padding: 0.75rem 1rem;">
                        <span class="meta-label" style="color: var(--primary);">Existing Updated</span>
                        <div class="kpi-value" style="font-size: 1.35rem; color: var(--primary);">${res.updated_count || 0}</div>
                    </div>
                    ` : ''}
                    <div class="kpi-card" style="padding: 0.75rem 1rem;">
                        <span class="meta-label" style="color: #d97706;">Duplicates Skipped</span>
                        <div class="kpi-value" style="font-size: 1.35rem; color: #d97706;">
                            ${res.duplicate_count || (res.duplicate_records ? res.duplicate_records.length : 0)}
                        </div>
                    </div>
                    <div class="kpi-card" style="padding: 0.75rem 1rem;">
                        <span class="meta-label" style="color: var(--danger);">Failed Rows</span>
                        <div class="kpi-value" style="font-size: 1.35rem; color: var(--danger);">${res.error_count}</div>
                    </div>
                </div>

                ${res.duplicate_records && res.duplicate_records.length > 0 ? `
                    <div style="background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.35); border-radius: var(--radius-md); padding: 0.875rem; margin-top: 0.75rem;">
                        <div style="font-weight: 600; color: #b45309; margin-bottom: 0.5rem; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.4rem;">
                            <span>${res.duplicate_records.length} Duplicate Record(s) Skipped (Unchanged):</span>
                            <span class="badge badge-warning" style="background: rgba(245, 158, 11, 0.2); color: #b45309; font-weight: 700;">This data already exists</span>
                        </div>
                        <div class="table-container" style="max-height: 220px; overflow-y: auto;">
                            <table class="table" style="font-size: 0.8125rem;">
                                <thead>
                                    <tr>
                                        <th>Excel Row #</th>
                                        <th>Address Code</th>
                                        <th>Party Name</th>
                                        <th>Validation Status</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${res.duplicate_records.map(d => `
                                        <tr>
                                            <td><span class="badge badge-standard">Row ${d.row_number || '—'}</span></td>
                                            <td><code style="color: #b45309; font-weight: 700;">${d.address_code || '—'}</code></td>
                                            <td><strong>${d.party_name || '—'}</strong></td>
                                            <td>
                                                <span class="badge badge-warning" style="background: rgba(245, 158, 11, 0.15); color: #b45309; font-size: 0.72rem; font-weight: 600;">
                                                    This data already exists
                                                </span>
                                            </td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        </div>
                    </div>
                ` : ''}

                ${res.errors && res.errors.length > 0 ? `
                    <div style="background: var(--danger-subtle); border: 1px solid var(--danger); border-radius: var(--radius-md); padding: 0.875rem; margin-top: 0.75rem;">
                        <div style="font-weight: 600; color: var(--danger); margin-bottom: 0.5rem; display: flex; align-items: center; justify-content: space-between;">
                            <span>${res.errors.length} Row(s) Failed Validation & Need Correction:</span>
                            <span class="badge badge-overdue">Skipped from Database</span>
                        </div>
                        <div class="table-container">
                            <table class="table">
                                <thead>
                                    <tr>
                                        <th>Excel Row #</th>
                                        <th>Party Name</th>
                                        <th>Submitted Phone 1</th>
                                        <th>Validation Failure Reason & How to Fix</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${res.errors.map(e => `
                                        <tr>
                                            <td><span class="badge badge-standard">Row ${e.row_number}</span></td>
                                            <td><strong>${e.customer_name}</strong></td>
                                            <td><code style="color: var(--danger); background: rgba(239,68,68,0.1); padding: 2px 6px; border-radius: 4px;">${e.mobile || '—'}</code></td>
                                            <td>
                                                <div style="color: var(--danger); font-weight: 600; margin-bottom: 2px;">${e.error}</div>
                                                <div style="font-size: 0.75rem; color: var(--text-muted);">
                                                    Fix: Check row ${e.row_number} and re-upload.
                                                </div>
                                            </td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        </div>
                    </div>
                ` : ''}
            </div>
        `;
    },

    async loadHistory() {
        const tbody = document.getElementById('import-history-table-body');
        if (!tbody) return;

        try {
            const history = await api.get('/imports/history');
            if (history.length === 0) {
                tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">No import jobs on record.</td></tr>`;
                return;
            }

            tbody.innerHTML = history.map(j => {
                const safeFilename = (j.filename || '').replace(/'/g, "\\'");
                const dateStr = (window.app && typeof app.formatDateTime === 'function')
                    ? app.formatDateTime(j.created_at)
                    : (j.created_at ? new Date(j.created_at).toLocaleString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: true }) : '—');

                return `
                <tr>
                    <td><span class="badge badge-standard">#${j.id}</span></td>
                    <td><strong>${j.filename}</strong></td>
                    <td style="font-weight: 600;">${j.total_rows}</td>
                    <td style="color: var(--success); font-weight: 600;">${j.imported_count}</td>
                    <td>
                        ${j.updated_count > 0 ? `
                            <button type="button" class="btn btn-secondary btn-xs" onclick="excelImport.openJobUpdatesModal(${j.id}, '${safeFilename}', ${j.total_rows}, ${j.imported_count}, ${j.updated_count}, ${j.error_count})" style="color: var(--primary); font-weight: 600;" title="Click to view all updated Excel rows">
                                ${Icons.get('refresh-cw', { size: 11 })}
                                <span>${j.updated_count} Updated</span>
                            </button>
                        ` : '<span style="color: var(--text-muted); font-size: 0.75rem;">0</span>'}
                    </td>
                    <td>${j.duplicate_count}</td>
                    <td>
                        ${j.error_count > 0 ? `
                            <button type="button" class="btn btn-danger btn-xs" onclick="excelImport.openJobErrorsModal(${j.id}, '${safeFilename}', ${j.total_rows}, ${j.imported_count}, ${j.updated_count}, ${j.error_count})" title="Click to view exact failed row numbers">
                                ${Icons.get('alert-triangle', { size: 11 })}
                                <span>${j.error_count} Error(s)</span>
                            </button>
                        ` : '<span style="color: var(--success); font-weight: 600; font-size: 0.75rem;">0 (Clean)</span>'}
                    </td>
                    <td><span style="font-size: 0.75rem;">${j.uploaded_by}</span></td>
                    <td style="font-size: 0.75rem; color: var(--text-muted);">${dateStr}</td>
                </tr>
            `;}).join('');
        } catch (err) {
            console.error("Error loading import history:", err);
        }
    },

    async openJobErrorsModal(jobId, filename, totalRows, importedCount, updatedCount, errorCount) {
        const titleEl = document.getElementById('modal-import-errors-title');
        const summaryEl = document.getElementById('modal-import-errors-summary');
        const tbodyEl = document.getElementById('modal-import-errors-tbody');
        const dlBtn = document.getElementById('btn-download-modal-errors-csv');

        if (titleEl) {
            titleEl.textContent = `Import Job #${jobId} Errors — ${filename}`;
        }

        if (summaryEl) {
            summaryEl.innerHTML = `
                <div style="background: var(--bg-surface-elevated); padding: 0.75rem 1rem; border-radius: var(--radius-md); border: 1px solid var(--border-color); display: flex; gap: 1.25rem; flex-wrap: wrap; font-size: 0.8125rem;">
                    <div><strong>Total Rows:</strong> ${totalRows}</div>
                    <div style="color: var(--success);"><strong>Inserted:</strong> ${importedCount}</div>
                    <div style="color: var(--primary);"><strong>Updated:</strong> ${updatedCount}</div>
                    <div style="color: var(--danger);"><strong>Failed:</strong> ${errorCount}</div>
                </div>
            `;
        }

        if (dlBtn) {
            dlBtn.href = `/api/imports/${jobId}/download-errors`;
        }

        if (tbodyEl) {
            tbodyEl.innerHTML = `<tr><td colspan="5" style="text-align:center; padding: 1.5rem; color: var(--text-muted);">Loading row error log...</td></tr>`;
        }

        if (window.app && typeof app.openModal === 'function') {
            app.openModal('modal-import-job-errors');
        }

        try {
            const errors = await api.get(`/imports/${jobId}/errors`);
            if (!errors || errors.length === 0) {
                tbodyEl.innerHTML = `<tr><td colspan="5" style="text-align:center; padding: 1.5rem; color: var(--success);">No error rows recorded for this job.</td></tr>`;
                return;
            }

            tbodyEl.innerHTML = errors.map(e => `
                <tr>
                    <td style="font-weight: 600; color: var(--text-primary);">
                        <span class="badge badge-standard">Row ${e.row_number}</span>
                    </td>
                    <td><code style="color: var(--primary); font-size: 0.75rem;">${e.party_code || '—'}</code></td>
                    <td><strong>${e.party_name || '—'}</strong></td>
                    <td>
                        <code style="color: var(--danger); background: rgba(239,68,68,0.1); padding: 2px 6px; border-radius: 4px; font-weight: 600; font-size: 0.75rem;">
                            ${e.phone_1 || '—'}
                        </code>
                    </td>
                    <td>
                        <div style="color: var(--danger); font-weight: 600; margin-bottom: 2px;">${e.error_reason}</div>
                        <div style="font-size: 0.75rem; color: var(--text-muted); line-height: 1.4;">
                            Correction: ${e.suggestion}
                        </div>
                    </td>
                </tr>
            `).join('');
        } catch (err) {
            if (tbodyEl) {
                tbodyEl.innerHTML = `<tr><td colspan="5" style="text-align:center; padding: 1.5rem; color: var(--danger);">Failed to load errors: ${err.message}</td></tr>`;
            }
        }
    },

    cachedUpdates: [],

    async openJobUpdatesModal(jobId, filename, totalRows, importedCount, updatedCount, errorCount) {
        const titleEl = document.getElementById('modal-import-updates-title');
        const summaryEl = document.getElementById('modal-import-updates-summary');
        const tbodyEl = document.getElementById('modal-import-updates-tbody');
        const dlBtn = document.getElementById('btn-download-modal-updates-csv');
        const searchInput = document.getElementById('modal-updates-search-input');

        if (titleEl) {
            titleEl.textContent = `Import Job #${jobId} Updated Records — ${filename}`;
        }

        if (summaryEl) {
            summaryEl.innerHTML = `
                <div style="background: var(--bg-surface-elevated); padding: 0.75rem 1rem; border-radius: var(--radius-md); border: 1px solid var(--border-color); display: flex; gap: 1.25rem; flex-wrap: wrap; font-size: 0.8125rem;">
                    <div><strong>Total Rows:</strong> ${totalRows}</div>
                    <div style="color: var(--success);"><strong>Inserted:</strong> ${importedCount}</div>
                    <div style="color: var(--primary);"><strong>Updated:</strong> ${updatedCount}</div>
                    <div style="color: var(--danger);"><strong>Failed:</strong> ${errorCount}</div>
                </div>
            `;
        }

        if (dlBtn) {
            dlBtn.href = `/api/imports/${jobId}/download-updates`;
        }

        if (tbodyEl) {
            tbodyEl.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 1.5rem; color: var(--text-muted);">Loading updated records...</td></tr>`;
        }

        if (searchInput) {
            searchInput.value = '';
        }

        if (window.app && typeof app.openModal === 'function') {
            app.openModal('modal-import-job-updates');
        }

        try {
            const updates = await api.get(`/imports/${jobId}/updates`);
            this.cachedUpdates = updates || [];
            this.renderUpdatesTable(this.cachedUpdates);

            if (searchInput) {
                searchInput.oninput = (e) => {
                    const q = (e.target.value || '').toLowerCase().trim();
                    if (!q) {
                        this.renderUpdatesTable(this.cachedUpdates);
                    } else {
                        const filtered = this.cachedUpdates.filter(u => 
                            (u.party_code && u.party_code.toLowerCase().includes(q)) ||
                            (u.party_name && u.party_name.toLowerCase().includes(q)) ||
                            (u.changed_fields && JSON.stringify(u.changed_fields).toLowerCase().includes(q)) ||
                            (u.row_number && String(u.row_number).includes(q))
                        );
                        this.renderUpdatesTable(filtered);
                    }
                };
            }
        } catch (err) {
            if (tbodyEl) {
                tbodyEl.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 1.5rem; color: var(--danger);">Failed to load updated records: ${err.message}</td></tr>`;
            }
        }
    },

    renderUpdatesTable(updates) {
        const tbodyEl = document.getElementById('modal-import-updates-tbody');
        const countBadge = document.getElementById('modal-updates-filtered-count');

        if (countBadge) {
            countBadge.textContent = `${updates.length} Records`;
        }

        if (!tbodyEl) return;

        if (!updates || updates.length === 0) {
            tbodyEl.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 1.5rem; color: var(--text-muted);">No synchronized/updated records found for this job.</td></tr>`;
            return;
        }

        tbodyEl.innerHTML = updates.map(u => {
            const dateStr = (window.app && typeof app.formatDateTime === 'function')
                ? app.formatDateTime(u.created_at)
                : (u.created_at ? new Date(u.created_at).toLocaleString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: true }) : '—');

            let fieldsBadges = '—';
            if (Array.isArray(u.changed_fields) && u.changed_fields.length > 0) {
                fieldsBadges = u.changed_fields.map(f => `<span class="badge badge-active" style="font-size: 0.6875rem; margin: 1px 2px;">${f}</span>`).join('');
            } else if (u.changed_fields) {
                fieldsBadges = `<span class="badge badge-active" style="font-size: 0.6875rem;">${u.changed_fields}</span>`;
            }

            let prevHtml = '<span style="color: var(--text-muted); font-size: 0.75rem;">—</span>';
            if (u.previous_data && Object.keys(u.previous_data).length > 0) {
                prevHtml = `<div style="font-size: 0.75rem; line-height: 1.4; color: var(--text-secondary); max-width: 220px;">` +
                    Object.entries(u.previous_data).map(([k, v]) => `<div><strong style="color: var(--text-muted);">${k}:</strong> <span style="text-decoration: line-through; opacity: 0.8;">${v || 'empty'}</span></div>`).join('') +
                    `</div>`;
            }

            let newHtml = '<span style="color: var(--text-muted); font-size: 0.75rem;">—</span>';
            if (u.new_data && Object.keys(u.new_data).length > 0) {
                newHtml = `<div style="font-size: 0.75rem; line-height: 1.4; color: var(--primary); max-width: 220px;">` +
                    Object.entries(u.new_data).map(([k, v]) => `<div><strong style="color: var(--text-primary);">${k}:</strong> <span style="font-weight: 600;">${v || 'empty'}</span></div>`).join('') +
                    `</div>`;
            }

            return `
                <tr>
                    <td style="font-weight: 600; color: var(--text-primary); white-space: nowrap;">
                        <span class="badge badge-standard">Row ${u.row_number}</span>
                    </td>
                    <td><code style="color: var(--primary); font-weight: 600; font-size: 0.75rem;">${u.party_code}</code></td>
                    <td><strong>${u.party_name}</strong></td>
                    <td>${fieldsBadges}</td>
                    <td>${prevHtml}</td>
                    <td>${newHtml}</td>
                    <td style="font-size: 0.75rem; color: var(--text-muted); white-space: nowrap;">${dateStr}</td>
                </tr>
            `;
        }).join('');
    },

    quickPermEmployees: [],

    async populateQuickPermEmployees() {
        const empSelect = document.getElementById('quick-perm-emp-select');
        if (!empSelect) return;

        try {
            const employees = await api.get('/employees');
            this.quickPermEmployees = employees || [];

            if (this.quickPermEmployees.length === 0) {
                empSelect.innerHTML = '<option value="">No employees found</option>';
                return;
            }

            empSelect.innerHTML = this.quickPermEmployees.map(emp =>
                `<option value="${emp.id}">${emp.full_name || emp.email} (${(emp.role || 'employee').toUpperCase()})</option>`
            ).join('');

            // Automatically select first employee and render permissions
            if (this.quickPermEmployees.length > 0) {
                empSelect.value = this.quickPermEmployees[0].id;
                this.handleQuickPermEmployeeChange(this.quickPermEmployees[0].id);
            }
        } catch (err) {
            console.error("Failed to load employees for quick permissions:", err);
            if (empSelect) empSelect.innerHTML = '<option value="">Error loading employees</option>';
        }
    },

    handleQuickPermEmployeeChange(empId) {
        if (!empId) return;
        const emp = this.quickPermEmployees.find(e => String(e.id) === String(empId));
        if (!emp) return;

        // Update employee summary card
        const nameEl = document.getElementById('quick-perm-emp-name');
        const emailEl = document.getElementById('quick-perm-emp-email');
        const roleEl = document.getElementById('quick-perm-emp-role');

        if (nameEl) nameEl.textContent = emp.full_name || 'Unnamed Employee';
        if (emailEl) emailEl.textContent = emp.email || '—';
        if (roleEl) {
            roleEl.textContent = (emp.role || 'EMPLOYEE').toUpperCase();
            roleEl.className = emp.role === 'admin' ? 'badge badge-vip' : 'badge badge-standard';
        }

        // Parse allowed_categories
        let allowedCats = [];
        if (Array.isArray(emp.allowed_categories)) {
            allowedCats = emp.allowed_categories.map(c => String(c).trim().toUpperCase());
        } else if (typeof emp.allowed_categories === 'string' && emp.allowed_categories.trim()) {
            allowedCats = emp.allowed_categories.split(',').map(c => c.trim().toUpperCase());
        }

        // Update category checkboxes
        document.querySelectorAll('.chk-quick-cat').forEach(chk => {
            chk.checked = allowedCats.includes(chk.value.toUpperCase()) || allowedCats.includes('ALL');
        });

        // Update action permissions
        const setCheck = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.checked = Boolean(val);
        };

        setCheck('chk-quick-perm-add', emp.can_add_customer !== false);
        setCheck('chk-quick-perm-edit', emp.can_edit_customer !== false);
        setCheck('chk-quick-perm-delete', Boolean(emp.can_delete_customer));
        setCheck('chk-quick-perm-rate', emp.can_rate_customer !== false);
        setCheck('chk-quick-perm-calls', emp.can_make_calls !== false);
        setCheck('chk-quick-perm-recordings', emp.can_listen_recordings !== false);
        setCheck('chk-quick-perm-export', emp.can_export_data !== false);
        setCheck('chk-quick-perm-unassigned', emp.can_view_unassigned !== false);
    },

    toggleQuickPermAllCategories() {
        const checkboxes = document.querySelectorAll('.chk-quick-cat');
        const allChecked = Array.from(checkboxes).every(c => c.checked);
        checkboxes.forEach(c => { c.checked = !allChecked; });
    },

    async saveQuickPermissions() {
        const empSelect = document.getElementById('quick-perm-emp-select');
        const empId = empSelect ? empSelect.value : null;
        if (!empId) {
            api.toast("Please select an employee first", "warning");
            return;
        }

        const btn = document.getElementById('btn-save-quick-perms');
        const origHtml = btn ? btn.innerHTML : "Save Employee Permissions";

        // Collect selected categories
        const checkedCats = [];
        document.querySelectorAll('.chk-quick-cat:checked').forEach(c => {
            checkedCats.push(c.value);
        });

        // Collect feature flags
        const getCheck = (id) => {
            const el = document.getElementById(id);
            return el ? el.checked : false;
        };

        const payload = {
            allowed_categories: checkedCats,
            can_add_customer: getCheck('chk-quick-perm-add'),
            can_edit_customer: getCheck('chk-quick-perm-edit'),
            can_delete_customer: getCheck('chk-quick-perm-delete'),
            can_rate_customer: getCheck('chk-quick-perm-rate'),
            can_make_calls: getCheck('chk-quick-perm-calls'),
            can_listen_recordings: getCheck('chk-quick-perm-recordings'),
            can_export_data: getCheck('chk-quick-perm-export'),
            can_view_unassigned: getCheck('chk-quick-perm-unassigned')
        };

        if (btn) {
            btn.disabled = true;
            btn.innerHTML = `<span style="display: inline-flex; align-items: center; gap: 0.4rem;">Updating Permissions...</span>`;
        }

        try {
            const updated = await api.put(`/employees/${empId}/permissions`, payload);

            // Update local cache
            const idx = this.quickPermEmployees.findIndex(e => String(e.id) === String(empId));
            if (idx !== -1) {
                this.quickPermEmployees[idx] = { ...this.quickPermEmployees[idx], ...updated };
            }

            api.toast(`Permissions updated successfully for ${updated.full_name || 'Employee'}!`, "success");
        } catch (err) {
            api.toast(`Failed to save permissions: ${err.message}`, "error");
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = origHtml;
            }
        }
    },

    /**
     * Apply active employee upload permissions and category scoping to Excel Import View
     */
    applyUserUploadScoping(user) {
        if (!user) return;
        const isAdmin = user.role === 'admin' || user.role === 'ADMIN';

        let uploadCats = [];
        if (user.allowed_upload_categories) {
            const raw = user.allowed_upload_categories;
            if (Array.isArray(raw)) {
                uploadCats = raw.map(c => String(c).trim().toUpperCase()).filter(c => c && c !== '***');
            } else if (typeof raw === 'string') {
                const s = raw.replace(/[\[\]\'\"]/g, '').trim();
                if (s && s !== '***') uploadCats = s.split(',').map(c => c.trim().toUpperCase());
            }
        }

        const hasAllUpload = isAdmin || uploadCats.includes('*') || uploadCats.includes('ALL') || uploadCats.length >= 10;
        const canUploadAny = hasAllUpload || uploadCats.length > 0;

        const dropzone = document.getElementById('import-dropzone');
        const fileInput = document.getElementById('excel-file-input');
        const uploadBtn = document.getElementById('btn-upload-file');
        const lockedNotice = document.getElementById('import-locked-banner');

        if (!canUploadAny) {
            if (dropzone) {
                dropzone.style.pointerEvents = 'none';
                dropzone.style.opacity = '0.5';
            }
            if (fileInput) fileInput.disabled = true;
            if (uploadBtn) uploadBtn.disabled = true;
            if (lockedNotice) {
                lockedNotice.style.display = 'block';
                lockedNotice.innerHTML = `🔒 <strong>Upload Access Restricted:</strong> Your employee account does not have permission to upload Excel/CSV customer records. Please contact your system administrator.`;
            }
        } else {
            if (dropzone) {
                dropzone.style.pointerEvents = '';
                dropzone.style.opacity = '';
            }
            if (fileInput) fileInput.disabled = false;
            if (uploadBtn) uploadBtn.disabled = false;
            if (lockedNotice) lockedNotice.style.display = 'none';
        }
    }
};

window.excelImport = excelImport;
