/**
 * Customer Intelligence & Rating Management Controller Module
 * Handles ranked customer insights, 1-5 star ratings, performance categories,
 * continuous pagination ranking, filters, and sliding detail panel.
 */
const intelligence = {
    activeTab: 'rankings',
    currentPage: 1,
    limit: 15,
    sortOrder: 'desc',
    ratingFilter: '',
    categoryFilter: '',
    searchQuery: '',
    currentCustomerId: null,
    currentCustomerData: null,
    selectedRating: 5,
    searchTimer: null,
    recentlyChanged: new Map(), // customerId -> { rating, category, changedBy, changedAt }
    
    // Recent Rating Changes Audit State
    recentChanges: [],
    recentSearch: '',
    recentUserFilter: 'all',
    recentSearchTimer: null,
    recentCurrentPage: 1,
    recentPageSize: 10,

    init() {
        console.log("Initializing Customer Intelligence module...");

        // Connect escape key to close drawer
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                const overlay = document.getElementById('intel-drawer-overlay');
                if (overlay && overlay.classList.contains('open')) {
                    this.closeDetailPanel();
                }
            }
        });
    },

    switchTab(tabName) {
        this.activeTab = tabName || 'rankings';
        const btnRankings = document.getElementById('tab-btn-intel-rankings');
        const btnRecent = document.getElementById('tab-btn-intel-recent');
        const secRankings = document.getElementById('intel-section-rankings');
        const secRecent = document.getElementById('intel-section-recent');

        if (this.activeTab === 'recent') {
            if (btnRankings) btnRankings.classList.remove('active');
            if (btnRecent) btnRecent.classList.add('active');
            if (secRankings) secRankings.style.display = 'none';
            if (secRecent) secRecent.style.display = 'block';
            this.loadRecentChanges();
        } else {
            if (btnRecent) btnRecent.classList.remove('active');
            if (btnRankings) btnRankings.classList.add('active');
            if (secRecent) secRecent.style.display = 'none';
            if (secRankings) secRankings.style.display = 'block';
        }
    },


    handleSearchInput(val) {
        clearTimeout(this.searchTimer);
        const clearBtn = document.getElementById('btn-intel-clear-search');
        if (clearBtn) {
            clearBtn.style.display = val.trim() ? 'block' : 'none';
        }

        this.searchTimer = setTimeout(() => {
            this.searchQuery = val.trim();
            this.currentPage = 1;
            this.loadIntelligence();
        }, 250);
    },

    clearSearch() {
        const inp = document.getElementById('intel-search-input');
        if (inp) inp.value = '';
        const clearBtn = document.getElementById('btn-intel-clear-search');
        if (clearBtn) clearBtn.style.display = 'none';
        this.searchQuery = '';
        this.currentPage = 1;
        this.loadIntelligence();
    },

    handleFilterChange() {
        const rSelect = document.getElementById('intel-filter-rating');
        const cSelect = document.getElementById('intel-filter-category');
        this.ratingFilter = rSelect ? rSelect.value : '';
        this.categoryFilter = cSelect ? cSelect.value : '';
        this.currentPage = 1;
        this.updateResetButtonVisibility();
        this.loadIntelligence();
    },

    handleSortChange() {
        const sSelect = document.getElementById('intel-sort-order');
        this.sortOrder = sSelect ? sSelect.value : 'desc';
        this.currentPage = 1;
        this.updateResetButtonVisibility();
        this.loadIntelligence();
    },

    resetFilters() {
        const sInp = document.getElementById('intel-search-input');
        const rSelect = document.getElementById('intel-filter-rating');
        const cSelect = document.getElementById('intel-filter-category');
        const sSelect = document.getElementById('intel-sort-order');
        const clearBtn = document.getElementById('btn-intel-clear-search');

        if (sInp) sInp.value = '';
        if (rSelect) rSelect.value = '';
        if (cSelect) cSelect.value = '';
        if (sSelect) sSelect.value = 'desc';
        if (clearBtn) clearBtn.style.display = 'none';

        this.searchQuery = '';
        this.ratingFilter = '';
        this.categoryFilter = '';
        this.sortOrder = 'desc';
        this.currentPage = 1;

        this.updateResetButtonVisibility();
        this.loadIntelligence();
    },

    updateResetButtonVisibility() {
        const resetBtn = document.getElementById('btn-intel-reset-filters');
        const hasFilters = this.searchQuery || this.ratingFilter || this.categoryFilter || this.sortOrder !== 'desc';
        if (resetBtn) {
            resetBtn.style.display = hasFilters ? 'inline-flex' : 'none';
        }
    },

    changePageSize(newSize) {
        this.limit = parseInt(newSize, 10) || 15;
        this.currentPage = 1;
        this.loadIntelligence();
    },

    goToPage(action) {
        if (action === 'first') this.currentPage = 1;
        else if (action === 'prev' && this.currentPage > 1) this.currentPage--;
        else if (action === 'next') this.currentPage++;
        else if (typeof action === 'number') this.currentPage = action;
        this.loadIntelligence();
    },

    async loadIntelligence() {
        const tableBody = document.getElementById('intel-table-body');
        if (tableBody) {
            tableBody.innerHTML = `
                <tr>
                    <td colspan="7" style="text-align: center; color: var(--text-muted); padding: 2.5rem;">
                        <div style="display: flex; flex-direction: column; align-items: center; gap: 0.75rem;">
                            <div class="spinner-sm" style="width: 22px; height: 22px; border-width: 3px; color: var(--primary);"></div>
                            <span style="font-size: 0.8125rem;">Loading Customer Intelligence data...</span>
                        </div>
                    </td>
                </tr>
            `;
        }

        try {
            const params = new URLSearchParams();
            params.set('page', this.currentPage);
            params.set('limit', this.limit);
            params.set('sort_order', this.sortOrder);
            if (this.ratingFilter) params.set('rating', this.ratingFilter);
            if (this.categoryFilter) params.set('category', this.categoryFilter);
            if (this.searchQuery) params.set('search', this.searchQuery);

            const data = await api.get(`/intelligence/customers?${params.toString()}`);
            this.currentItems = data.items || [];
            this.updateKPIs(data.kpis);

            // Update Rankings Badge
            const badgeRankings = document.getElementById('intel-tab-badge-rankings');
            if (badgeRankings) badgeRankings.textContent = (data.total || 0).toLocaleString();

            this.renderTable(data.items, data.total, data.page, data.limit);
            this.renderPagination(data.total, data.page, data.limit, data.total_pages);

            // Load recent changes badge count in background
            this.loadRecentChanges(true);
        } catch (err) {
            console.error("Error loading Customer Intelligence:", err);
            if (tableBody) {
                tableBody.innerHTML = `
                    <tr>
                        <td colspan="7" style="text-align: center; color: var(--danger); padding: 2rem;">
                            Failed to load customer intelligence: ${err.message || 'Server error'}.
                            <button class="btn btn-secondary btn-xs" onclick="intelligence.loadIntelligence()" style="margin-left: 0.5rem;">Retry</button>
                        </td>
                    </tr>
                `;
            }
        }
    },

    updateKPIs(kpis) {
        if (!kpis) return;
        const elTotal = document.getElementById('intel-kpi-total');
        const elAvg = document.getElementById('intel-kpi-avg');
        const elTop = document.getElementById('intel-kpi-top');
        const elAttention = document.getElementById('intel-kpi-attention');
        const elTopSub = document.getElementById('intel-kpi-top-sub');

        if (elTotal) elTotal.textContent = (kpis.total_customers || 0).toLocaleString();
        if (elAvg) elAvg.innerHTML = `${(kpis.average_rating || 0).toFixed(1)} <span style="font-size: 1.1rem; color: #F59E0B;">★</span>`;
        if (elTop) elTop.textContent = ((kpis.top_customers || 0) + (kpis.premium_customers || 0)).toLocaleString();
        if (elTopSub) elTopSub.textContent = `${kpis.top_customers || 0} Top, ${kpis.premium_customers || 0} Premium`;
        if (elAttention) elAttention.textContent = (kpis.needs_attention || 0).toLocaleString();
    },

    renderTable(items, total, page, limit) {
        const tbody = document.getElementById('intel-table-body');
        if (!tbody) return;

        if (!items || items.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="7" style="text-align: center; color: var(--text-muted); padding: 3rem 1.5rem;">
                        <div style="display: flex; flex-direction: column; align-items: center; gap: 0.5rem;">
                            <div style="font-size: 2rem; opacity: 0.5;">🔍</div>
                            <div style="font-weight: 600; color: var(--text-primary);">No customers match the current criteria</div>
                            <div style="font-size: 0.8125rem; max-width: 360px;">Try adjusting your rating, category filter, or search query.</div>
                            <button class="btn btn-secondary btn-sm" onclick="intelligence.resetFilters()" style="margin-top: 0.5rem;">Clear All Filters</button>
                        </div>
                    </td>
                </tr>
            `;
            return;
        }

        const currentUser = typeof api !== 'undefined' ? api.getCurrentUser() : null;
        // Both Admin and Employees can change customer ratings
        const canEdit = currentUser && currentUser.is_active;


        let html = '';
        items.forEach((item) => {
            // Rank Badge
            let rankHtml = '';
            if (item.rank === 1) {
                rankHtml = `<span class="rank-badge rank-gold" title="Rank 1 - Top Rated">🥇 #1</span>`;
            } else if (item.rank === 2) {
                rankHtml = `<span class="rank-badge rank-silver" title="Rank 2">🥈 #2</span>`;
            } else if (item.rank === 3) {
                rankHtml = `<span class="rank-badge rank-bronze" title="Rank 3">🥉 #3</span>`;
            } else {
                rankHtml = `<span class="rank-badge rank-regular">#${item.rank}</span>`;
            }

            // Customer Name & Subtitle
            const locationStr = [item.city, item.state].filter(Boolean).join(', ');
            const subStr = item.contact_person_1 ? `Contact: ${item.contact_person_1}` : (locationStr || item.phone_1);

            // Stars — clickable inline if user can edit
            const starsHtml = canEdit
                ? this.renderClickableStars(item.id, item.rating, item.category)
                : this.renderRatingStars(item.rating);

            // Category Badge
            const catBadgeHtml = this.renderCategoryBadge(item.category);

            // Status Badge
            const statusClass = item.status === 'Active' ? 'badge-active' : (item.status === 'Lead' ? 'badge-lead' : 'badge-standard');
            const statusHtml = `<span class="badge ${statusClass}">${item.status || 'Active'}</span>`;

            html += `
                <tr class="intel-row-clickable" data-customer-id="${item.id}" onclick="intelligence.openDetailPanel(${item.id})">
                    <td style="text-align: center; vertical-align: middle;">${rankHtml}</td>
                    <td style="vertical-align: middle;">
                        <div style="font-weight: 600; color: var(--text-primary); font-size: 0.875rem;">${this.escapeHtml(item.party_name)}</div>
                        <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 0.15rem;">${this.escapeHtml(subStr)}</div>
                    </td>
                    <td style="vertical-align: middle;">
                        <code style="background: var(--bg-surface-elevated); padding: 0.15rem 0.4rem; border-radius: var(--radius-xs); border: 1px solid var(--border-color); font-size: 0.75rem; color: var(--text-secondary); font-weight: 600;">
                            ${this.escapeHtml(item.party_code)}
                        </code>
                    </td>
                    <td style="vertical-align: middle;" onclick="event.stopPropagation();">
                        ${starsHtml}
                    </td>
                    <td style="vertical-align: middle;">${catBadgeHtml}</td>
                    <td style="text-align: center; vertical-align: middle;">${statusHtml}</td>
                    <td style="text-align: right; vertical-align: middle;">
                        <button class="btn btn-secondary btn-xs" onclick="event.stopPropagation(); intelligence.openDetailPanel(${item.id})" style="display: inline-flex; align-items: center; gap: 4px;">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                            <span>Manage</span>
                        </button>
                    </td>
                </tr>
            `;
        });

        tbody.innerHTML = html;
    },

    renderClickableStars(customerId, currentRating, currentCategory) {
        const r = Math.max(0, Math.min(5, parseInt(currentRating, 10) || 0));
        const recentInfo = this.recentlyChanged.get(customerId);
        let stars = '';
        for (let i = 1; i <= 5; i++) {
            const filled = i <= r;
            stars += `
                <button type="button" class="inline-star-btn ${filled ? 'filled' : 'empty'}" 
                    onclick="intelligence.quickSetRating(${customerId}, ${i})"
                    title="Set ${i} Star${i > 1 ? 's' : ''}"
                    data-star="${i}">
                    <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                        <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
                    </svg>
                </button>
            `;
        }
        const recentBadge = recentInfo ? `
            <span class="badge-just-updated" title="Updated by ${this.escapeHtml(recentInfo.changedBy)} at ${recentInfo.changedAt}">
                <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
                Just updated
            </span>` : '';
        return `<div class="inline-star-row" data-customer-id="${customerId}" data-rating="${r}" title="${r} of 5 Stars — Click any star to change">${stars}<span class="inline-star-val">${r > 0 ? r + '.0' : '—'}</span>${recentBadge}</div>`;
    },


    renderRatingStars(rating) {
        const r = Math.max(0, Math.min(5, parseInt(rating, 10) || 0));
        let stars = '';
        for (let i = 1; i <= 5; i++) {
            if (i <= r) {
                stars += `<svg class="star-icon" viewBox="0 0 24 24"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg>`;
            } else {
                stars += `<svg class="star-icon empty" viewBox="0 0 24 24"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg>`;
            }
        }
        return `
            <div class="stars-display" title="${r} of 5 Stars">
                ${stars}
                <span class="star-rating-val">${r.toFixed(1)}</span>
            </div>
        `;
    },

    renderStarsSvg(rating, size = 12, gap = 1.5) {
        const r = Math.max(0, Math.min(5, parseInt(rating, 10) || 0));
        let html = `<span class="stars-svg-inline" style="display: inline-flex; align-items: center; gap: ${gap}px; vertical-align: middle;">`;
        for (let i = 1; i <= 5; i++) {
            const filled = i <= r;
            if (filled) {
                html += `<svg width="${size}" height="${size}" viewBox="0 0 24 24" style="fill: #F59E0B; stroke: #F59E0B; stroke-width: 1px; flex-shrink: 0;"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>`;
            } else {
                html += `<svg width="${size}" height="${size}" viewBox="0 0 24 24" style="fill: rgba(245, 158, 11, 0.04); stroke: #F59E0B; stroke-width: 1.8px; opacity: 0.85; flex-shrink: 0;"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>`;
            }
        }
        html += '</span>';
        return html;
    },

    renderCategoryBadge(category) {
        const cat = category || 'Regular';
        let cls = 'badge-cat-regular';
        let icon = '●';

        if (cat === 'Top Customer') {
            cls = 'badge-cat-top';
            icon = '👑';
        } else if (cat === 'Premium') {
            cls = 'badge-cat-premium';
            icon = '💎';
        } else if (cat === 'Regular') {
            cls = 'badge-cat-regular';
            icon = '⚡';
        } else if (cat === 'New Customer') {
            cls = 'badge-cat-new';
            icon = '🌱';
        } else if (cat === 'Potential') {
            cls = 'badge-cat-potential';
            icon = '🚀';
        } else if (cat === 'Needs Attention') {
            cls = 'badge-cat-attention';
            icon = '⚠️';
        }

        return `<span class="badge-cat ${cls}"><span style="font-size: 0.75rem;">${icon}</span> <span>${cat}</span></span>`;
    },

    renderPagination(total, page, limit, totalPages) {
        const infoEl = document.getElementById('intel-pagination-info');
        const firstBtn = document.getElementById('btn-intel-first');
        const prevBtn = document.getElementById('btn-intel-prev');
        const nextBtn = document.getElementById('btn-intel-next');
        const lastBtn = document.getElementById('btn-intel-last');
        const pillsEl = document.getElementById('intel-page-pills');

        const from = total === 0 ? 0 : (page - 1) * limit + 1;
        const to = Math.min(total, page * limit);
        if (infoEl) infoEl.textContent = `Showing ${from.toLocaleString()} to ${to.toLocaleString()} of ${total.toLocaleString()} customers`;

        if (firstBtn) firstBtn.disabled = page <= 1;
        if (prevBtn) prevBtn.disabled = page <= 1;
        if (nextBtn) nextBtn.disabled = page >= totalPages;
        if (lastBtn) lastBtn.disabled = page >= totalPages;

        if (lastBtn) {
            lastBtn.onclick = () => this.goToPage(totalPages);
        }

        if (pillsEl) {
            let pillsHtml = '';
            const maxPills = 5;
            let start = Math.max(1, page - Math.floor(maxPills / 2));
            let end = Math.min(totalPages, start + maxPills - 1);
            if (end - start + 1 < maxPills) {
                start = Math.max(1, end - maxPills + 1);
            }

            for (let p = start; p <= end; p++) {
                const isActive = p === page;
                pillsHtml += `
                    <button class="btn ${isActive ? 'btn-primary' : 'btn-secondary'} btn-xs" 
                        onclick="intelligence.goToPage(${p})" 
                        style="min-width: 28px; height: 26px; padding: 0 0.35rem; font-weight: ${isActive ? '700' : '500'};">
                        ${p}
                    </button>
                `;
            }
            pillsEl.innerHTML = pillsHtml;
        }
    },

    // =========================================================================
    // SLIDING RIGHT DETAIL PANEL CONTROLLER
    // =========================================================================

    handleDrawerOverlayClick(e) {
        // ONLY close when user directly clicks the dark semi-transparent backdrop overlay itself
        if (e.target !== e.currentTarget && e.target.id !== 'intel-drawer-overlay') {
            return;
        }
        this.closeDetailPanel();
    },

    closeDetailPanel() {
        const overlay = document.getElementById('intel-drawer-overlay');
        if (overlay) overlay.classList.remove('open');
        this.currentCustomerId = null;
        this.currentCustomerData = null;
    },

    async openDetailPanel(customerId) {
        this.currentCustomerId = customerId;
        const overlay = document.getElementById('intel-drawer-overlay');
        if (overlay) overlay.classList.add('open');

        // Loading state inside panel
        const nameEl = document.getElementById('intel-drawer-party-name');
        const codeEl = document.getElementById('intel-drawer-party-code');
        if (nameEl) nameEl.textContent = "Loading customer details...";
        if (codeEl) codeEl.textContent = "—";

        try {
            const data = await api.get(`/intelligence/customers/${customerId}`);
            this.currentCustomerData = data;
            this.populateDrawerUI(data);
        } catch (err) {
            api.toast(`Failed to load customer details: ${err.message}`, "error");
            this.closeDetailPanel();
        }
    },

    populateDrawerUI(c) {
        const nameEl = document.getElementById('intel-drawer-party-name');
        const codeEl = document.getElementById('intel-drawer-party-code');
        const statusEl = document.getElementById('intel-drawer-status-badge');
        const avatarEl = document.getElementById('intel-drawer-avatar');
        const repEl = document.getElementById('intel-drawer-rep');
        const phoneEl = document.getElementById('intel-drawer-phone');
        const emailEl = document.getElementById('intel-drawer-email');
        const contactEl = document.getElementById('intel-drawer-contact');
        const locationEl = document.getElementById('intel-drawer-location');
        const notesInp = document.getElementById('dinp-intel-notes');
        const catSelect = document.getElementById('dinp-intel-category');
        const permBadge = document.getElementById('intel-permission-badge');
        const readonlyNote = document.getElementById('intel-readonly-note');
        const saveBtn = document.getElementById('btn-save-intel-rating');

        if (nameEl) nameEl.textContent = c.party_name;
        if (codeEl) codeEl.textContent = c.party_code;
        if (statusEl) {
            statusEl.textContent = c.status || 'Active';
            statusEl.className = `badge ${c.status === 'Active' ? 'badge-active' : (c.status === 'Lead' ? 'badge-lead' : 'badge-standard')}`;
        }
        if (avatarEl) {
            avatarEl.textContent = c.party_name.substring(0, 2).toUpperCase();
        }
        if (repEl) repEl.textContent = `Assigned: ${c.assigned_employee_name || 'System'}`;
        if (phoneEl) phoneEl.textContent = c.phone_1 || '—';
        if (emailEl) emailEl.textContent = c.email_id_1 || '—';
        if (contactEl) contactEl.textContent = c.contact_person_1 || c.party_name;
        if (locationEl) {
            const parts = [c.city, c.state, c.country].filter(Boolean);
            locationEl.textContent = parts.length > 0 ? parts.join(', ') : 'India';
        }

        // Update latest rating display in header profile card
        const latestRatingEl = document.getElementById('intel-drawer-latest-rating');
        if (latestRatingEl) {
            const r = Math.max(0, Math.min(5, parseInt(c.rating, 10) || 0));
            const ratingLabels = { 0: 'Not Rated', 1: 'Needs Attention', 2: 'Growth Potential', 3: 'Good', 4: 'Premium', 5: 'Top Customer' };
            const ratingColors = { 0: '#94A3B8', 1: '#EF4444', 2: '#F97316', 3: '#EAB308', 4: '#3B82F6', 5: '#10B981' };
            const ratingBgColors = { 0: 'rgba(148,163,184,0.1)', 1: 'rgba(239,68,68,0.08)', 2: 'rgba(249,115,22,0.08)', 3: 'rgba(234,179,8,0.1)', 4: 'rgba(59,130,246,0.08)', 5: 'rgba(16,185,129,0.1)' };
            const color = ratingColors[r] || '#94A3B8';
            const bg = ratingBgColors[r] || 'rgba(148,163,184,0.1)';
            const label = ratingLabels[r] || `${r} Stars`;
            const starsHtml = this.renderStarsSvg(r, 15, 3);
            latestRatingEl.innerHTML = `
                <div style="display: flex; align-items: center; gap: 0.5rem; background: ${bg}; border: 1.5px solid ${color}22; border-radius: 8px; padding: 5px 10px; margin-top: 4px;">
                    <div>${starsHtml}</div>
                    <div style="width: 1px; height: 16px; background: ${color}33; margin: 0 2px;"></div>
                    <span style="font-size: 0.8rem; font-weight: 800; color: ${color}; letter-spacing: 0.01em;">${r > 0 ? r + '.0' : '—'}</span>
                    <span style="font-size: 0.72rem; font-weight: 700; color: ${color}; background: ${color}18; border-radius: 4px; padding: 1px 6px; letter-spacing: 0.02em;">${label.toUpperCase()}</span>
                </div>
            `;
        }

        // Category
        if (catSelect) {
            catSelect.value = c.category || 'Regular';
        }
        if (notesInp) notesInp.value = '';

        // Role Permission Control — Both Admin & Employees can change ratings
        const currentUser = api.getCurrentUser();
        const isAdmin = currentUser && currentUser.role === 'admin';
        const canEdit = currentUser && currentUser.is_active;

        if (permBadge) {
            if (isAdmin) {
                permBadge.innerHTML = `<span style="color: #A855F7;">&#9679;</span> Admin Access`;
                permBadge.className = `badge badge-role-admin`;
            } else {
                permBadge.innerHTML = `<span style="color: #0284C7;">&#9679;</span> Employee Access`;
                permBadge.className = `badge badge-role-employee`;
            }
        }

        // Initialize Star Picker — enabled for all active users
        this.selectedRating = Math.max(1, Math.min(5, c.rating || 5));
        this.renderStarPicker(this.selectedRating, canEdit);

        if (saveBtn) saveBtn.disabled = !canEdit;
        if (readonlyNote) readonlyNote.style.display = canEdit ? 'none' : 'block';

        // Render History
        this.renderRatingHistory(c.history || []);
    },

    renderStarPicker(rating, isInteractive) {
        const picker = document.getElementById('intel-star-picker');
        const labelEl = document.getElementById('intel-star-label');
        const hiddenInp = document.getElementById('dinp-intel-rating');

        if (hiddenInp) hiddenInp.value = rating;

        const labels = {
            1: "1 Star — Needs Immediate Attention",
            2: "2 Stars — Fair / Growth Potential",
            3: "3 Stars — Good / Consistent Regular",
            4: "4 Stars — Very Good / Premium Tier",
            5: "5 Stars — Outstanding / Top Customer"
        };
        if (labelEl) labelEl.textContent = labels[rating] || `${rating} Stars`;

        if (!picker) return;

        let html = '';
        for (let i = 1; i <= 5; i++) {
            const isActive = i <= rating;
            html += `
                <button type="button" class="star-pick-btn ${isActive ? 'active' : 'inactive'}" 
                    ${isInteractive ? `onclick="intelligence.selectStarRating(${i})"` : 'disabled'}
                    title="${i} Star${i > 1 ? 's' : ''}">
                    <svg viewBox="0 0 24 24">
                        <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon>
                    </svg>
                </button>
            `;
        }
        picker.innerHTML = html;
    },

    decreaseRating() {
        const current = this.selectedRating || parseInt(document.getElementById('dinp-intel-rating')?.value, 10) || 1;
        if (current > 1) {
            this.selectStarRating(current - 1);
        } else {
            if (typeof api !== 'undefined') api.toast("Rating is already at the minimum (1 Star)", "info");
        }
    },

    increaseRating() {
        const current = this.selectedRating || parseInt(document.getElementById('dinp-intel-rating')?.value, 10) || 5;
        if (current < 5) {
            this.selectStarRating(current + 1);
        } else {
            if (typeof api !== 'undefined') api.toast("Rating is already at the maximum (5 Stars)", "info");
        }
    },


    selectStarRating(starNum) {
        this.selectedRating = Math.max(1, Math.min(5, starNum));
        const hiddenInp = document.getElementById('dinp-intel-rating');
        if (hiddenInp) hiddenInp.value = this.selectedRating;

        // Automatically suggest category if default matches
        const catSelect = document.getElementById('dinp-intel-category');
        if (catSelect) {
            if (this.selectedRating === 5) catSelect.value = "Top Customer";
            else if (this.selectedRating === 4) catSelect.value = "Premium";
            else if (this.selectedRating === 3) catSelect.value = "Regular";
            else if (this.selectedRating === 2) catSelect.value = "Potential";
            else if (this.selectedRating === 1) catSelect.value = "Needs Attention";
        }

        const currentUser = typeof api !== 'undefined' ? api.getCurrentUser() : null;
        const isAuthorized = currentUser && currentUser.is_active;
        this.renderStarPicker(this.selectedRating, isAuthorized);
    },

    // Mark a customer row as recently changed (live badge in table)
    markRowAsRecentlyChanged(customerId, newRating, newCategory, changedBy, changedAt) {
        const timeLabel = changedAt ? this.formatRelativeTime(changedAt) : 'Just now';
        this.recentlyChanged.set(customerId, {
            rating: newRating,
            category: newCategory,
            changedBy: changedBy || 'Staff',
            changedAt: timeLabel
        });
        // Auto-expire after 5 minutes
        setTimeout(() => {
            this.recentlyChanged.delete(customerId);
        }, 5 * 60 * 1000);

        // Live update the badge in the existing row without full reload
        const row = document.querySelector(`tr[data-customer-id="${customerId}"]`);
        if (row) {
            // Glow animation
            row.classList.add('rating-live-glow');
            setTimeout(() => row.classList.remove('rating-live-glow'), 1800);

            // Add/update recently-changed badge in stars cell
            const starRow = row.querySelector('.inline-star-row');
            if (starRow) {
                // Update filled/empty star state
                starRow.querySelectorAll('.inline-star-btn').forEach((btn, i) => {
                    btn.classList.toggle('filled', i < newRating);
                    btn.classList.toggle('empty', i >= newRating);
                });
                const valEl = starRow.querySelector('.inline-star-val');
                if (valEl) valEl.textContent = newRating + '.0';
                starRow.dataset.rating = newRating;

                // Inject or update "Just updated" badge
                let badge = starRow.querySelector('.badge-just-updated');
                if (!badge) {
                    badge = document.createElement('span');
                    badge.className = 'badge-just-updated';
                    starRow.appendChild(badge);
                }
                badge.innerHTML = `<svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg> Just updated`;
                badge.title = `Updated by ${changedBy} — ${timeLabel}`;
            }

            // Add left-border highlight to row
            row.classList.add('intel-row-recent');
        }
    },

    // Show an in-drawer success banner (stays in panel, drawer does NOT close)
    showDrawerSuccessBanner(ratingVal, catVal, changedBy, prevRating = null, prevCat = null) {
        const container = document.getElementById('intel-drawer-success-banner');
        if (!container) return;

        const starsHtml = this.renderStarsSvg(ratingVal, 13, 2);

        let deltaHtml = '';
        if (prevRating !== null && prevRating !== undefined && prevRating > 0 && prevRating !== ratingVal) {
            const delta = ratingVal - prevRating;
            deltaHtml = `<span class="${delta > 0 ? 'badge-diff-zyada' : 'badge-diff-kam'}" style="font-size: 0.65rem; margin-left: 3px;">${delta > 0 ? '▲ +' + delta : '▼ ' + delta} Star${Math.abs(delta) > 1 ? 's' : ''}</span>`;
        }

        const catTransition = (prevCat && prevCat !== catVal)
            ? `<span style="font-size: 0.72rem; color: var(--text-muted);">${this.escapeHtml(prevCat)} &rarr; </span><strong>${this.escapeHtml(catVal)}</strong>`
            : `<strong>${this.escapeHtml(catVal)}</strong>`;

        container.innerHTML = `
            <div class="intel-success-banner" id="intel-success-inner" style="box-shadow: 0 4px 14px rgba(16,185,129,0.15);">
                <div style="display: flex; align-items: center; gap: 0.6rem; flex: 1; min-width: 0;">
                    <div style="width: 32px; height: 32px; border-radius: 50%; background: rgba(16,185,129,0.18); border: 1.5px solid #10B981; display: flex; align-items: center; justify-content: center; flex-shrink: 0;">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2.8"><polyline points="20 6 9 17 4 12"/></svg>
                    </div>
                    <div style="min-width: 0;">
                        <div style="display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap;">
                            <span style="font-weight: 700; color: #10B981; font-size: 0.85rem;">Rating Updated Successfully</span>
                            <span class="badge" style="background: rgba(16,185,129,0.15); color: #10B981; font-size: 0.62rem; padding: 1px 5px; border-radius: 4px;">Realtime Synced</span>
                        </div>
                        <div style="font-size: 0.74rem; color: var(--text-secondary); margin-top: 2px; display: flex; align-items: center; gap: 4px; flex-wrap: wrap;">
                            <span>${starsHtml}</span>
                            <span>(${ratingVal}.0 Stars)</span>
                            ${deltaHtml}
                            <span>•</span>
                            <span>${catTransition}</span>
                            <span>•</span>
                            <span style="color: var(--text-muted);">by ${this.escapeHtml(changedBy)}</span>
                        </div>
                    </div>
                </div>
                <button type="button" onclick="document.getElementById('intel-success-inner').parentElement.innerHTML=''" 
                    style="background:none;border:none;cursor:pointer;color:var(--text-muted);padding:4px;border-radius:4px;line-height:1;flex-shrink:0;" title="Dismiss">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
            </div>
        `;
        container.style.display = 'block';

        // Auto-hide after 8 seconds
        clearTimeout(this._successBannerTimer);
        this._successBannerTimer = setTimeout(() => {
            const inner = document.getElementById('intel-success-inner');
            if (inner) {
                inner.style.animation = 'successFadeOut 0.4s ease forwards';
                setTimeout(() => { if (container) container.innerHTML = ''; }, 400);
            }
        }, 8000);
    },

    async quickSetRating(customerId, newRating) {
        // Called by clicking a star directly in the table row
        const item = (this.currentItems || []).find(c => c.id === customerId);
        if (!item) return;

        newRating = Math.max(1, Math.min(5, newRating));
        const currentRating = parseInt(item.rating, 10) || 0;

        if (newRating === currentRating) return; // No change — star already at that value

        // Smart category suggestion based on star value
        let newCat = item.category || 'Regular';
        if (newRating === 5)      newCat = 'Top Customer';
        else if (newRating === 4) newCat = 'Premium';
        else if (newRating === 3) newCat = 'Regular';
        else if (newRating === 2) newCat = 'Potential';
        else if (newRating === 1) newCat = 'Needs Attention';

        const currentUser = typeof api !== 'undefined' ? api.getCurrentUser() : null;
        const noteText = `Rating set to ${newRating} Star${newRating > 1 ? 's' : ''} (${newCat}) by ${currentUser?.full_name || 'Staff'} via quick star selection`;

        // Optimistic UI update on row stars
        const row = document.querySelector(`tr[data-customer-id="${customerId}"]`);
        if (row) {
            const starRow = row.querySelector('.inline-star-row');
            if (starRow) {
                starRow.querySelectorAll('.inline-star-btn').forEach((btn, i) => {
                    btn.classList.toggle('filled', i < newRating);
                    btn.classList.toggle('empty', i >= newRating);
                });
                const valEl = starRow.querySelector('.inline-star-val');
                if (valEl) valEl.textContent = newRating + '.0';
                starRow.dataset.rating = newRating;
            }
        }

        try {
            const updated = await api.put(`/intelligence/customers/${customerId}/rating`, {
                rating: newRating,
                category: newCat,
                notes: noteText
            });

            api.toast(`⭐ ${item.party_name}: ${newRating} Star${newRating > 1 ? 's' : ''} — ${newCat}`, "success");

            // Update in-memory item
            item.rating = newRating;
            item.category = newCat;

            // Mark row as recently changed with live badge
            const currentUser = typeof api !== 'undefined' ? api.getCurrentUser() : null;
            this.markRowAsRecentlyChanged(customerId, newRating, newCat, currentUser?.full_name || 'Staff', new Date().toISOString());

            // Update drawer if open for this customer
            if (this.currentCustomerId === customerId) {
                this.currentCustomerData = updated;
                this.populateDrawerUI(updated);
                // Ensure drawer stays open
                const overlay = document.getElementById('intel-drawer-overlay');
                if (overlay && !overlay.classList.contains('open')) overlay.classList.add('open');
            }

            // Refresh table ranking after short delay
            clearTimeout(this._tableReloadTimer);
            this._tableReloadTimer = setTimeout(() => this.loadIntelligence(), 1200);
        } catch (err) {
            // Revert optimistic update on failure
            if (row) {
                const starRow = row.querySelector('.inline-star-row');
                if (starRow) {
                    starRow.querySelectorAll('.inline-star-btn').forEach((btn, i) => {
                        btn.classList.toggle('filled', i < currentRating);
                        btn.classList.toggle('empty', i >= currentRating);
                    });
                    const valEl = starRow.querySelector('.inline-star-val');
                    if (valEl) valEl.textContent = currentRating > 0 ? currentRating + '.0' : '—';
                    starRow.dataset.rating = currentRating;
                }
            }
            api.toast(`Failed to update rating: ${err.message || 'Server error'}`, "error");
        }
    },

    async quickAdjustRating(customerId, delta) {
        // Legacy — kept for compatibility, delegates to quickSetRating
        const item = (this.currentItems || []).find(c => c.id === customerId);
        if (!item) return;
        const newRating = Math.max(1, Math.min(5, (parseInt(item.rating, 10) || 0) + delta));
        await this.quickSetRating(customerId, newRating);
    },

    formatRelativeTime(isoStr) {
        if (!isoStr) return '—';
        let str = String(isoStr);
        if (!str.endsWith('Z') && !str.includes('+') && !str.match(/-\d{2}:\d{2}$/)) str += 'Z';
        const d = new Date(str);
        if (isNaN(d.getTime())) return isoStr;
        const now = new Date();
        const diffMs = now - d;
        const diffSec = Math.floor(diffMs / 1000);
        if (diffSec < 30) return 'Just now';
        if (diffSec < 3600) return `${Math.floor(diffSec / 60)} min ago`;
        if (diffSec < 86400) return `${Math.floor(diffSec / 3600)} hr ago`;
        if (diffSec < 172800) return 'Yesterday';
        return d.toLocaleString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: true });
    },

    buildHistoryItemHtml(h, isNew = false) {
        const fullTimeStr = typeof app !== 'undefined' && app.formatDateTime ? app.formatDateTime(h.created_at) : (h.created_at || '—');
        const relativeTime = this.formatRelativeTime(h.created_at);
        const prevRating = h.previous_rating || 0;
        const newRating = h.new_rating;
        const ratingDelta = newRating - prevRating;

        const prevStars = prevRating > 0
            ? this.renderStarsSvg(prevRating, 11, 1)
            : '<span style="font-size:0.7rem;color:var(--text-muted);font-style:italic;">Unrated</span>';
        const newStars = this.renderStarsSvg(newRating, 11, 1);

        const deltaHtml = ratingDelta !== 0 ? `
            <span class="${ratingDelta > 0 ? 'badge-diff-zyada' : 'badge-diff-kam'}">
                ${ratingDelta > 0 ? '▲' : '▼'} ${Math.abs(ratingDelta)} Star${Math.abs(ratingDelta) > 1 ? 's' : ''}
            </span>
        ` : '';

        const roleClass = (h.user_role || 'EMPLOYEE').toUpperCase() === 'ADMIN' ? 'badge-role-admin' : 'badge-role-employee';
        const userInitials = (h.user_name || 'S').split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();

        const prevCat = h.previous_category || 'Unset';
        const newCat = h.new_category || '—';
        const catChanged = prevCat !== newCat;

        return `
            <div class="intel-history-item${isNew ? ' newly-added' : ''}">
                <div class="intel-history-header">
                    <div style="display: flex; align-items: center; gap: 0.5rem;">
                        <div style="width: 26px; height: 26px; border-radius: 50%; background: var(--primary-subtle); display: flex; align-items: center; justify-content: center; font-size: 0.65rem; font-weight: 700; color: var(--primary); flex-shrink: 0;">${this.escapeHtml(userInitials)}</div>
                        <div>
                            <div style="font-weight: 700; color: var(--text-primary); font-size: 0.8125rem; line-height: 1;">${this.escapeHtml(h.user_name || 'System')}</div>
                            <span class="badge ${roleClass}" style="font-size: 0.6rem; margin-top: 2px; display: inline-block;">${(h.user_role || 'EMPLOYEE').toUpperCase()}</span>
                        </div>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-size: 0.72rem; font-weight: 600; color: var(--text-secondary);" title="${fullTimeStr}">${relativeTime}</div>
                        <div style="font-size: 0.65rem; color: var(--text-muted); margin-top: 1px;">${fullTimeStr}</div>
                    </div>
                </div>
                <div class="intel-history-change">
                    <div style="display: flex; align-items: center; gap: 0.3rem;">
                        <div style="display:flex;gap:1px;align-items:center;">${prevStars}</div>
                        <span style="color: var(--text-muted); font-size: 0.85rem; margin: 0 2px;">&#8594;</span>
                        <div style="display:flex;gap:1px;align-items:center;">${newStars}</div>
                    </div>
                    ${deltaHtml}
                    ${catChanged ? `<span style="background: rgba(99, 102, 241, 0.12); color: #6366F1; border: 1px solid rgba(99,102,241,0.25); padding: 0.1rem 0.4rem; border-radius: var(--radius-xs); font-size: 0.68rem; font-weight: 700;">${this.escapeHtml(prevCat)} &rarr; ${this.escapeHtml(newCat)}</span>` : `<span style="font-size: 0.7rem; color: var(--text-muted); background: var(--bg-surface-elevated); padding: 0.1rem 0.4rem; border-radius: var(--radius-xs); border: 1px solid var(--border-color);">${this.escapeHtml(newCat)}</span>`}
                </div>
                ${h.notes ? `<div class="intel-history-notes"><svg style="width:10px;height:10px;flex-shrink:0;margin-right:4px;vertical-align:middle;" viewBox="0 0 24 24" fill="none" stroke="var(--primary)" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>${this.escapeHtml(h.notes)}</div>` : ''}
            </div>
        `;
    },

    renderRatingHistory(history, prependNewItem = null) {
        const stream = document.getElementById('intel-history-stream');
        const countEl = document.getElementById('intel-history-count');
        const total = (history ? history.length : 0) + (prependNewItem ? 0 : 0);
        if (countEl) countEl.textContent = `${history ? history.length : 0} change${history && history.length !== 1 ? 's' : ''}`;

        if (!stream) return;

        if (!history || history.length === 0) {
            stream.innerHTML = `
                <div style="text-align: center; color: var(--text-muted); padding: 2rem 1rem; font-size: 0.8125rem;">
                    <div style="font-size: 1.75rem; opacity: 0.35; margin-bottom: 0.5rem;">&#128203;</div>
                    <div style="font-weight: 600; color: var(--text-secondary);">No changes recorded yet</div>
                    <div style="margin-top: 0.25rem; opacity: 0.7;">Every rating update will appear here with full audit trail.</div>
                </div>
            `;
            return;
        }

        stream.innerHTML = history.map((h, idx) => this.buildHistoryItemHtml(h, idx === 0 && prependNewItem)).join('');
    },

    prependHistoryItem(historyEntry) {
        // Live inject a new history item at the top without full re-render
        const stream = document.getElementById('intel-history-stream');
        const countEl = document.getElementById('intel-history-count');
        if (!stream) return;

        // Remove empty state if present
        const emptyState = stream.querySelector('div[style*="text-align: center"]');
        if (emptyState) stream.innerHTML = '';

        // Update count
        const existing = stream.querySelectorAll('.intel-history-item').length;
        if (countEl) countEl.textContent = `${existing + 1} change${existing + 1 !== 1 ? 's' : ''}`;

        // Inject new item at top
        const wrapper = document.createElement('div');
        wrapper.innerHTML = this.buildHistoryItemHtml(historyEntry, true);
        stream.insertBefore(wrapper.firstElementChild, stream.firstChild);
    },

    handleLiveRatingUpdate(data) {
        // Called via SSE when any user changes a rating
        const { customer_id, party_name, old_rating, new_rating, old_category, new_category,
                user_name, user_role, notes, timestamp } = data;

        // Live glow on the table row
        const row = document.querySelector(`tr[data-customer-id="${customer_id}"]`);
        if (row) {
            row.classList.add('rating-live-glow');
            setTimeout(() => row.classList.remove('rating-live-glow'), 1800);
            // Update stars in row without full reload
            const starsCell = row.querySelector('.stars-display');
            if (starsCell) {
                starsCell.outerHTML = this.renderRatingStars(new_rating).trim();
            }
        }

        // Update in-memory items
        if (this.currentItems) {
            const item = this.currentItems.find(c => c.id === customer_id);
            if (item) {
                item.rating = new_rating;
                item.category = new_category;
            }
        }

        // If drawer is open for this customer, prepend the live history entry
        if (this.currentCustomerId === customer_id) {
            const newEntry = {
                id: Date.now(),
                customer_id,
                previous_rating: old_rating,
                new_rating,
                previous_category: old_category,
                new_category,
                user_name: user_name || 'Staff',
                user_role: user_role || 'EMPLOYEE',
                notes: notes || `Rating changed from ${old_rating}★ to ${new_rating}★`,
                created_at: timestamp || new Date().toISOString()
            };
            this.prependHistoryItem(newEntry);

            // Also refresh the star picker in drawer
            const currentUser = api.getCurrentUser();
            const canEdit = currentUser && currentUser.is_active;
            this.selectedRating = new_rating;
            this.renderStarPicker(new_rating, canEdit);

            // Update category in drawer
            const catEl = document.getElementById('dinp-intel-category');
            if (catEl) catEl.value = new_category;
        }

        // Toast notification for OTHER users
        const currentUser = api.getCurrentUser();
        const isMyChange = currentUser && currentUser.full_name === user_name;
        if (!isMyChange) {
            const delta = new_rating - old_rating;
            const dir = delta > 0 ? `▲ +${delta}` : `▼ ${delta}`;
            api.toast(
                `Live Update: ${party_name} rating ${dir} (${new_rating}★) by ${user_name}`,
                delta > 0 ? 'success' : 'info',
                3500
            );
        }

        // Prepend to Recent Rating Changes audit table in real-time
        this.prependRecentChange({
            id: Date.now(),
            customer_id,
            party_code: data.party_code || '—',
            party_name,
            phone_1: data.phone_1 || '',
            city: data.city || '',
            state: data.state || '',
            previous_rating: old_rating,
            new_rating,
            previous_category: old_category,
            new_category,
            user_id: data.user_id,
            user_name: user_name || 'Staff',
            user_role: (user_role || 'EMPLOYEE').toUpperCase(),
            notes: notes || `Rating updated to ${new_rating}★`,
            created_at: timestamp || new Date().toISOString()
        });

        // Mark row as recently changed
        this.markRowAsRecentlyChanged(customer_id, new_rating, new_category, user_name, timestamp);

        // Refresh table ranking after a short delay
        clearTimeout(this._liveReloadTimer);
        this._liveReloadTimer = setTimeout(() => this.loadIntelligence(), 1500);
    },

    async saveRatingAndCategory() {
        if (!this.currentCustomerId) return;

        const ratingVal = parseInt(document.getElementById('dinp-intel-rating')?.value, 10) || this.selectedRating;
        const catVal = document.getElementById('dinp-intel-category')?.value;
        const notesVal = document.getElementById('dinp-intel-notes')?.value.trim();

        if (!ratingVal || ratingVal < 1 || ratingVal > 5) {
            api.toast("Please select a rating between 1 and 5 stars", "error");
            return;
        }
        if (!catVal) {
            api.toast("Please select a category tier", "error");
            return;
        }

        const saveBtn = document.getElementById('btn-save-intel-rating');
        const origText = saveBtn ? saveBtn.innerHTML : '';
        if (saveBtn) {
            saveBtn.disabled = true;
            saveBtn.innerHTML = `<div class="spinner-sm" style="width: 14px; height: 14px; border-color: currentColor;"></div> <span>Saving...</span>`;
        }

        try {
            const currentUser = api.getCurrentUser();
            const notesFinal = notesVal || `Rating set to ${ratingVal}★ (${catVal}) by ${currentUser?.full_name || 'Staff'}`;
            const oldRating = this.currentCustomerData?.rating || null;
            const oldCat = this.currentCustomerData?.category || null;

            const updated = await api.put(`/intelligence/customers/${this.currentCustomerId}/rating`, {
                rating: ratingVal,
                category: catVal,
                notes: notesFinal
            });

            this.currentCustomerData = updated;

            // Clear notes field after save
            const notesInp = document.getElementById('dinp-intel-notes');
            if (notesInp) notesInp.value = '';

            // Show in-drawer success banner (drawer stays OPEN)
            this.showDrawerSuccessBanner(ratingVal, catVal, currentUser?.full_name || 'Staff', oldRating, oldCat);

            // Instant Real-time Toast Feedback
            api.toast(`⭐ ${updated.party_name}: Rating updated to ${ratingVal} Stars (${catVal})!`, "success", 4500);

            // Mark this customer row as recently changed in rankings table
            this.markRowAsRecentlyChanged(
                this.currentCustomerId,
                ratingVal,
                catVal,
                currentUser?.full_name || 'Staff',
                new Date().toISOString()
            );

            // Prepend directly to recent changes table in real-time
            const newAuditEntry = {
                id: Date.now(),
                customer_id: this.currentCustomerId,
                party_code: updated.party_code,
                party_name: updated.party_name,
                phone_1: updated.phone_1,
                city: updated.city,
                state: updated.state,
                previous_rating: oldRating,
                new_rating: ratingVal,
                previous_category: oldCat,
                new_category: catVal,
                user_id: currentUser?.id,
                user_name: currentUser?.full_name || 'Staff',
                user_role: (currentUser?.role || 'EMPLOYEE').toUpperCase(),
                notes: notesFinal,
                created_at: new Date().toISOString()
            };
            this.prependRecentChange(newAuditEntry);

            // Re-populate drawer with fresh history (drawer DOES NOT close)
            this.populateDrawerUI(updated);

            // Ensure drawer stays open
            const overlay = document.getElementById('intel-drawer-overlay');
            if (overlay && !overlay.classList.contains('open')) overlay.classList.add('open');

            // Refresh table in background
            clearTimeout(this._tableReloadTimer);
            this._tableReloadTimer = setTimeout(() => this.loadIntelligence(), 800);

        } catch (err) {
            api.toast(`Failed to update rating: ${err.message}`, "error");
        } finally {
            if (saveBtn) {
                saveBtn.disabled = false;
                saveBtn.innerHTML = origText;
            }
        }
    },

    // =========================================================================
    // RECENT RATING CHANGES AUDIT TABLE CONTROLLER
    // =========================================================================

    handleRecentSearch(val) {
        clearTimeout(this.recentSearchTimer);
        const clearBtn = document.getElementById('btn-intel-clear-recent-search');
        if (clearBtn) {
            clearBtn.style.display = val.trim() ? 'block' : 'none';
        }

        this.recentSearchTimer = setTimeout(() => {
            this.recentSearch = val.trim();
            this.recentCurrentPage = 1;
            this.loadRecentChanges();
        }, 250);
    },

    clearRecentSearch() {
        const inp = document.getElementById('intel-recent-search-input');
        if (inp) inp.value = '';
        const clearBtn = document.getElementById('btn-intel-clear-recent-search');
        if (clearBtn) clearBtn.style.display = 'none';
        this.recentSearch = '';
        this.recentCurrentPage = 1;
        this.loadRecentChanges();
    },

    filterRecentChanges(scope) {
        this.recentUserFilter = scope || 'all';
        this.recentCurrentPage = 1;
        this.loadRecentChanges();
    },

    changeRecentPageSize(newSize) {
        this.recentPageSize = parseInt(newSize, 10) || 10;
        this.recentCurrentPage = 1;
        this.renderRecentChangesTable(this.recentChanges);
    },

    goToRecentPage(action) {
        const total = (this.recentChanges || []).length;
        const totalPages = Math.max(1, Math.ceil(total / this.recentPageSize));
        if (action === 'first') {
            this.recentCurrentPage = 1;
        } else if (action === 'prev') {
            if (this.recentCurrentPage > 1) this.recentCurrentPage--;
        } else if (action === 'next') {
            if (this.recentCurrentPage < totalPages) this.recentCurrentPage++;
        } else if (action === 'last') {
            this.recentCurrentPage = totalPages;
        } else if (typeof action === 'number') {
            this.recentCurrentPage = Math.max(1, Math.min(totalPages, action));
        }
        this.renderRecentChangesTable(this.recentChanges);
    },

    renderRecentPagination(total, page, limit, totalPages) {
        const infoEl = document.getElementById('recent-pagination-info');
        const firstBtn = document.getElementById('btn-recent-first');
        const prevBtn = document.getElementById('btn-recent-prev');
        const nextBtn = document.getElementById('btn-recent-next');
        const lastBtn = document.getElementById('btn-recent-last');
        const pillsEl = document.getElementById('recent-page-pills');

        const from = total === 0 ? 0 : (page - 1) * limit + 1;
        const to = Math.min(total, page * limit);
        if (infoEl) {
            infoEl.textContent = `Showing ${from.toLocaleString()} to ${to.toLocaleString()} of ${total.toLocaleString()} changes`;
        }

        if (firstBtn) firstBtn.disabled = page <= 1;
        if (prevBtn) prevBtn.disabled = page <= 1;
        if (nextBtn) nextBtn.disabled = page >= totalPages;
        if (lastBtn) {
            lastBtn.disabled = page >= totalPages;
            lastBtn.onclick = () => this.goToRecentPage('last');
        }

        if (pillsEl) {
            let pillsHtml = '';
            const maxPills = 5;
            let start = Math.max(1, page - Math.floor(maxPills / 2));
            let end = Math.min(totalPages, start + maxPills - 1);
            if (end - start + 1 < maxPills) {
                start = Math.max(1, end - maxPills + 1);
            }

            for (let p = start; p <= end; p++) {
                const isActive = p === page;
                pillsHtml += `
                    <button class="btn ${isActive ? 'btn-primary' : 'btn-secondary'} btn-xs" 
                        onclick="intelligence.goToRecentPage(${p})" 
                        style="min-width: 28px; height: 26px; padding: 0 0.35rem; font-weight: ${isActive ? '700' : '500'};">
                        ${p}
                    </button>
                `;
            }
            pillsEl.innerHTML = pillsHtml;
        }
    },

    async loadRecentChanges(badgeOnly = false) {
        const refreshBtn = document.getElementById('btn-refresh-recent-ratings');
        if (refreshBtn && !badgeOnly) {
            refreshBtn.disabled = true;
            refreshBtn.style.opacity = '0.7';
        }

        try {
            const params = new URLSearchParams();
            params.set('limit', '100');
            if (this.recentSearch) params.set('search', this.recentSearch);

            const currentUser = typeof api !== 'undefined' ? api.getCurrentUser() : null;
            if (this.recentUserFilter === 'my' && currentUser && currentUser.id) {
                params.set('user_id', currentUser.id);
            }

            const data = await api.get(`/intelligence/recent-changes?${params.toString()}`);
            this.recentChanges = data || [];

            // Update badge count in Tab bar
            const badgeEl = document.getElementById('intel-tab-badge-recent');
            if (badgeEl) {
                badgeEl.textContent = this.recentChanges.length.toLocaleString();
            }

            if (!badgeOnly) {
                this.renderRecentChangesTable(this.recentChanges);
            }
        } catch (err) {
            console.error("Error loading recent rating changes:", err);
            if (!badgeOnly) {
                const tbody = document.getElementById('intel-recent-table-body');
                if (tbody) {
                    tbody.innerHTML = `
                        <tr>
                            <td colspan="7" style="text-align: center; color: var(--danger); padding: 2.5rem 1rem;">
                                <div>Failed to load recent rating changes: ${this.escapeHtml(err.message || 'Server error')}</div>
                                <button class="btn btn-secondary btn-xs" onclick="intelligence.loadRecentChanges()" style="margin-top: 0.5rem;">Retry</button>
                            </td>
                        </tr>
                    `;
                }
                this.renderRecentPagination(0, 1, this.recentPageSize, 1);
            }
        } finally {
            if (refreshBtn && !badgeOnly) {
                refreshBtn.disabled = false;
                refreshBtn.style.opacity = '1';
            }
        }
    },

    renderRecentChangesTable(items) {
        const allItems = items !== undefined ? items : (this.recentChanges || []);
        const tbody = document.getElementById('intel-recent-table-body');
        const summaryEl = document.getElementById('intel-recent-summary-info');
        if (!tbody) return;

        const total = allItems.length;

        if (summaryEl) {
            summaryEl.textContent = `Showing ${total} recent rating update${total !== 1 ? 's' : ''}${this.recentUserFilter === 'my' ? ' by you' : ' across all team members'}`;
        }

        if (total === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="7" style="text-align: center; color: var(--text-muted); padding: 3rem 1.5rem;">
                        <div style="display: flex; flex-direction: column; align-items: center; gap: 0.65rem;">
                            <div style="font-size: 2.25rem; opacity: 0.4;">📋</div>
                            <div style="font-weight: 700; color: var(--text-primary); font-size: 0.95rem;">No recent rating changes found</div>
                            <div style="font-size: 0.8125rem; max-width: 380px;">
                                ${this.recentSearch ? 'No rating updates match your search term.' : 'Every rating modification made by you or your team will appear here in real-time.'}
                            </div>
                            ${this.recentSearch || this.recentUserFilter !== 'all' ? `
                                <button class="btn btn-secondary btn-xs" onclick="intelligence.clearRecentSearch(); const sel = document.getElementById('intel-recent-user-filter'); if(sel) sel.value='all'; intelligence.filterRecentChanges('all');" style="margin-top: 0.5rem;">
                                    Reset Filters
                                </button>
                            ` : ''}
                        </div>
                    </td>
                </tr>
            `;
            this.renderRecentPagination(0, 1, this.recentPageSize, 1);
            return;
        }

        // Pagination slice
        const totalPages = Math.max(1, Math.ceil(total / this.recentPageSize));
        if (this.recentCurrentPage > totalPages) this.recentCurrentPage = totalPages;
        if (this.recentCurrentPage < 1) this.recentCurrentPage = 1;

        const startIdx = (this.recentCurrentPage - 1) * this.recentPageSize;
        const pageItems = allItems.slice(startIdx, startIdx + this.recentPageSize);

        const currentUser = typeof api !== 'undefined' ? api.getCurrentUser() : null;

        let html = '';
        pageItems.forEach((item) => {
            const isMe = currentUser && (
                (item.user_id && item.user_id === currentUser.id) ||
                (item.user_name && currentUser.full_name && item.user_name.toLowerCase() === currentUser.full_name.toLowerCase())
            );

            // User initials
            const userInitials = (item.user_name || 'Staff').split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
            const roleClass = (item.user_role || 'EMPLOYEE').toUpperCase() === 'ADMIN' ? 'badge-role-admin' : 'badge-role-employee';

            // Rating transition
            const prevR = item.previous_rating || 0;
            const newR = item.new_rating || 0;
            const delta = newR - prevR;

            const prevStars = prevR > 0
                ? this.renderStarsSvg(prevR, 12, 1.5)
                : '<span style="font-size:0.72rem;color:var(--text-muted);font-style:italic;">Unrated</span>';
            const newStars = this.renderStarsSvg(newR, 12, 1.5);

            let deltaHtml = '';
            if (prevR === 0) {
                deltaHtml = `<span class="badge-diff-zyada" style="font-size:0.65rem;">NEW RATED</span>`;
            } else if (delta > 0) {
                deltaHtml = `<span class="badge-diff-zyada">▲ +${delta}</span>`;
            } else if (delta < 0) {
                deltaHtml = `<span class="badge-diff-kam">▼ ${delta}</span>`;
            } else {
                deltaHtml = `<span style="font-size:0.65rem; color:var(--text-muted); background:var(--bg-surface-elevated); padding:0.1rem 0.35rem; border-radius:var(--radius-xs); border:1px solid var(--border-color);">= Same</span>`;
            }

            // Category transition
            const prevCat = item.previous_category || 'Unset';
            const newCat = item.new_category || 'Regular';
            const catBadgeHtml = (prevCat && prevCat !== newCat && prevCat !== 'Unset')
                ? `<div style="display:flex; align-items:center; gap:4px; flex-wrap:wrap;">
                       <span style="font-size:0.7rem; color:var(--text-muted); text-decoration:line-through;">${this.escapeHtml(prevCat)}</span>
                       <span style="color:var(--text-muted); font-size:0.75rem;">&rarr;</span>
                       ${this.renderCategoryBadge(newCat)}
                   </div>`
                : this.renderCategoryBadge(newCat);

            // Relative and full time
            const relativeTime = this.formatRelativeTime(item.created_at);
            const fullTimeStr = typeof app !== 'undefined' && app.formatDateTime ? app.formatDateTime(item.created_at) : (item.created_at || '—');

            // Location
            const locationStr = [item.city, item.state].filter(Boolean).join(', ');

            html += `
                <tr class="recent-change-row" data-change-id="${item.id}" data-customer-id="${item.customer_id}">
                    <!-- Customer Details -->
                    <td style="vertical-align: middle;">
                        <div style="display: flex; align-items: flex-start; gap: 0.55rem;">
                            <div style="width: 34px; height: 34px; border-radius: var(--radius-sm); background: var(--primary-subtle); color: var(--primary); display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 0.8rem; flex-shrink: 0; margin-top: 1px;">
                                ${(item.party_name || 'CU').substring(0, 2).toUpperCase()}
                            </div>
                            <div style="min-width: 0;">
                                <div style="font-weight: 700; color: var(--text-primary); font-size: 0.875rem; cursor: pointer;" onclick="intelligence.openDetailPanel(${item.customer_id})">
                                    ${this.escapeHtml(item.party_name)}
                                </div>
                                <div style="display: flex; align-items: center; gap: 0.4rem; margin-top: 0.15rem; flex-wrap: wrap;">
                                    <code style="font-size: 0.72rem; padding: 0.1rem 0.35rem; background: var(--bg-surface-elevated); border: 1px solid var(--border-color); border-radius: var(--radius-xs); color: var(--text-secondary); font-weight: 600;">
                                        ${this.escapeHtml(item.party_code)}
                                    </code>
                                    ${item.phone_1 ? `<span style="font-size: 0.72rem; color: var(--text-muted);">${this.escapeHtml(item.phone_1)}</span>` : ''}
                                    ${locationStr ? `<span style="font-size: 0.72rem; color: var(--text-muted);">• ${this.escapeHtml(locationStr)}</span>` : ''}
                                </div>
                            </div>
                        </div>
                    </td>

                    <!-- Rating Change -->
                    <td style="vertical-align: middle;">
                        <div class="rating-delta-box">
                            <div style="display: flex; flex-direction: column; gap: 2px;">
                                <div style="display: flex; align-items: center; gap: 5px;">
                                    <span>${prevStars}</span>
                                    <span style="color: var(--text-muted); font-size: 0.75rem;">&rarr;</span>
                                    <span>${newStars}</span>
                                </div>
                                <div style="display: flex; align-items: center; gap: 4px; font-size: 0.72rem; color: var(--text-secondary);">
                                    <span>${prevR > 0 ? prevR + '.0' : 'Unrated'} &rarr; <strong>${newR}.0</strong></span>
                                    ${deltaHtml}
                                </div>
                            </div>
                        </div>
                    </td>

                    <!-- Category Tier -->
                    <td style="vertical-align: middle;">
                        ${catBadgeHtml}
                    </td>

                    <!-- Changed By -->
                    <td style="vertical-align: middle;">
                        <div style="display: flex; align-items: center; gap: 0.45rem;">
                            <div style="width: 28px; height: 28px; border-radius: 50%; background: var(--primary-subtle); color: var(--primary); display: flex; align-items: center; justify-content: center; font-size: 0.65rem; font-weight: 700; flex-shrink: 0;">
                                ${this.escapeHtml(userInitials)}
                            </div>
                            <div style="min-width: 0;">
                                <div style="display: flex; align-items: center; gap: 4px; flex-wrap: wrap;">
                                    <span style="font-weight: 600; font-size: 0.8125rem; color: var(--text-primary); line-height: 1.2;">
                                        ${this.escapeHtml(item.user_name || 'Staff')}
                                    </span>
                                    ${isMe ? `<span class="badge-you-indicator">★ You</span>` : ''}
                                </div>
                                <span class="badge ${roleClass}" style="font-size: 0.6rem; margin-top: 2px; display: inline-block;">
                                    ${(item.user_role || 'EMPLOYEE').toUpperCase()}
                                </span>
                            </div>
                        </div>
                    </td>

                    <!-- Audit Notes / Reason -->
                    <td style="vertical-align: middle;">
                        ${item.notes ? `
                            <div class="audit-notes-bubble" title="${this.escapeHtml(item.notes)}">
                                <svg style="width: 10px; height: 10px; flex-shrink: 0; vertical-align: middle; margin-right: 3px;" viewBox="0 0 24 24" fill="none" stroke="var(--primary)" stroke-width="2.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                                <span>${this.escapeHtml(item.notes)}</span>
                            </div>
                        ` : `<span style="font-size: 0.72rem; color: var(--text-muted); font-style: italic;">No audit remarks</span>`}
                    </td>

                    <!-- Changed At -->
                    <td style="vertical-align: middle;">
                        <div style="font-weight: 600; font-size: 0.75rem; color: var(--text-secondary);" title="${fullTimeStr}">
                            ${relativeTime}
                        </div>
                        <div style="font-size: 0.68rem; color: var(--text-muted); margin-top: 1px;" title="${fullTimeStr}">
                            ${fullTimeStr}
                        </div>
                    </td>

                    <!-- Action -->
                    <td style="text-align: right; vertical-align: middle;">
                        <button class="btn btn-secondary btn-xs" onclick="intelligence.openDetailPanel(${item.customer_id})" title="Manage Customer Rating &amp; Details" style="display: inline-flex; align-items: center; gap: 3px; height: 26px; padding: 0 0.5rem; font-weight: 600;">
                            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                            <span>Manage</span>
                        </button>
                    </td>
                </tr>
            `;
        });

        tbody.innerHTML = html;
        this.renderRecentPagination(total, this.recentCurrentPage, this.recentPageSize, totalPages);
    },

    prependRecentChange(newEntry) {
        if (!newEntry) return;

        // Add to in-memory array at index 0
        if (!this.recentChanges) this.recentChanges = [];
        this.recentChanges.unshift(newEntry);

        // Update badge
        const badgeEl = document.getElementById('intel-tab-badge-recent');
        if (badgeEl) {
            badgeEl.textContent = this.recentChanges.length.toLocaleString();
        }

        const tbody = document.getElementById('intel-recent-table-body');
        if (!tbody) return;

        // If empty state was shown, clear it
        const emptyState = tbody.querySelector('div[style*="text-align: center"]');
        if (emptyState) tbody.innerHTML = '';

        // Check if filter excludes this
        const currentUser = typeof api !== 'undefined' ? api.getCurrentUser() : null;
        if (this.recentUserFilter === 'my' && currentUser && newEntry.user_id && newEntry.user_id !== currentUser.id) {
            return;
        }

        // Reset to page 1 to display the new item right at top
        this.recentCurrentPage = 1;
        this.renderRecentChangesTable(this.recentChanges);
        const topRow = tbody.firstElementChild;
        if (topRow) {
            topRow.classList.add('highlight-new');
            setTimeout(() => topRow.classList.remove('highlight-new'), 2500);
        }
    },

    openCustomer360() {
        if (!this.currentCustomerId) return;
        const custId = this.currentCustomerId;
        this.closeDetailPanel();
        if (typeof customer !== 'undefined' && typeof customer.openDrawer === 'function') {
            customer.openDrawer(custId);
        } else if (typeof app !== 'undefined' && typeof app.switchView === 'function') {
            app.switchView('customers');
        }
    },

    triggerCall() {
        if (!this.currentCustomerData || !this.currentCustomerData.phone_1) {
            api.toast("No valid phone number for direct calling", "warning");
            return;
        }
        const c = this.currentCustomerData;
        if (typeof cti !== 'undefined' && typeof cti.directDialCustomer === 'function') {
            cti.directDialCustomer(c.phone_1, c.party_name, c.party_code);
        } else {
            api.toast(`Initiating call to ${c.party_name} (${c.phone_1})...`, "info");
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
    }
};

window.intelligence = intelligence;
