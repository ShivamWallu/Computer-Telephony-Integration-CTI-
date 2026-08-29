/**
 * Excel / CSV Importer with Strict 15-Column Sequence Validation & Error Reporting
 */
const excelImport = {
    selectedFile: null,

    init() {
        const dropzone = document.getElementById('excel-dropzone');
        const fileInput = document.getElementById('excel-file-input');

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
    },

    async handleFileSelect(file) {
        if (!file.name.match(/\.(xlsx|xls|csv)$/i)) {
            api.toast("Please upload a valid Excel (.xlsx) or CSV file", "error");
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
                        Please ensure your file has exactly 15 columns matching the exact sequence. You can download the official sample template above.
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
                        <span><strong>Schema Validation Passed:</strong> File contains all 15 required columns in exact sequence!</span>
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

    async executeImport() {
        if (!this.selectedFile) {
            api.toast("No file selected for import", "error");
            return;
        }

        const btn = document.getElementById('btn-execute-import');
        const origText = btn ? btn.innerHTML : "Execute Import";

        const importMode = document.querySelector('input[name="import-mode"]:checked')?.value || "update";

        const formData = new FormData();
        formData.append("file", this.selectedFile);
        formData.append("import_mode", importMode);

        if (btn) {
            btn.disabled = true;
            btn.innerHTML = `<span style="display: inline-flex; align-items: center; gap: 0.4rem;">Synchronizing Records...</span>`;
        }

        api.toast("Executing high-speed data synchronization & normalization...", "info");

        const startTime = performance.now();

        try {
            const result = await api.post('/imports/process', formData);
            const durationMs = Math.round(performance.now() - startTime);
            result.duration_ms = durationMs;

            this.renderResultSummary(result);
            this.loadHistory();
            if (typeof customer !== 'undefined') {
                customer.loadCustomers();
            }
            app.refreshDashboard();
            api.toast(`Synchronized ${result.total_rows} records in ${durationMs}ms!`, "success");
        } catch (err) {
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
                        <span>Import Synchronization Completed: ${res.filename}</span>
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

                <div class="grid-4" style="margin-bottom: 1rem;">
                    <div class="kpi-card" style="padding: 0.75rem 1rem;">
                        <span class="meta-label">Total File Rows</span>
                        <div class="kpi-value" style="font-size: 1.35rem;">${res.total_rows}</div>
                    </div>
                    <div class="kpi-card" style="padding: 0.75rem 1rem;">
                        <span class="meta-label" style="color: var(--success);">New Inserted</span>
                        <div class="kpi-value" style="font-size: 1.35rem; color: var(--success);">${res.imported_count}</div>
                    </div>
                    <div class="kpi-card" style="padding: 0.75rem 1rem; cursor: pointer;" onclick="excelImport.openJobUpdatesModal(${res.job_id}, '${safeFilename}', ${res.total_rows}, ${res.imported_count}, ${res.updated_count}, ${res.error_count})">
                        <span class="meta-label" style="color: var(--primary);">Synchronized (Updated)</span>
                        <div class="kpi-value" style="font-size: 1.35rem; color: var(--primary);">
                            ${res.updated_count}
                        </div>
                    </div>
                    <div class="kpi-card" style="padding: 0.75rem 1rem;">
                        <span class="meta-label" style="color: var(--danger);">Failed Rows</span>
                        <div class="kpi-value" style="font-size: 1.35rem; color: var(--danger);">${res.error_count}</div>
                    </div>
                </div>

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
                                            <td><code style="color: var(--danger); background: rgba(239,68,68,0.1); padding: 2px 6px; border-radius: 4px;">${e.mobile}</code></td>
                                            <td>
                                                <div style="color: var(--danger); font-weight: 600; margin-bottom: 2px;">${e.error}</div>
                                                <div style="font-size: 0.75rem; color: var(--text-muted);">
                                                    Fix: Provide a valid 10-digit mobile number in Excel Row ${e.row_number} and re-upload.
                                                </div>
                                            </td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        </div>
                    </div>
                ` : '<div class="badge badge-active" style="padding: 0.5rem 0.85rem; font-size: 0.8125rem;">All customer rows processed cleanly without any validation errors!</div>'}
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
                const dateStr = j.created_at ? new Date(j.created_at).toLocaleString('en-IN', {
                    day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit'
                }) : '—';

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

        app.openModal('modal-import-job-errors');

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

        app.openModal('modal-import-job-updates');

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
            const dateStr = u.created_at ? new Date(u.created_at).toLocaleString('en-IN', {
                day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: true
            }) : '—';

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
    }
};

window.excelImport = excelImport;
