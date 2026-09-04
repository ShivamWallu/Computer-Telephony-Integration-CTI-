/**
 * Ultra-Fast Global Customer Search Module with Debouncing & Keyboard Navigation
 */
const search = {
    debounceTimer: null,
    selectedIndex: -1,
    currentResults: [],

    init() {
        const input = document.getElementById('global-search-input');
        const dropdown = document.getElementById('search-results-dropdown');
        if (!input || !dropdown) return;

        // Input search listener with debounce
        input.addEventListener('input', (e) => {
            clearTimeout(this.debounceTimer);
            const query = e.target.value.trim();
            const clearBtn = document.getElementById('btn-clear-global-search');
            if (clearBtn) clearBtn.style.display = query ? 'block' : 'none';

            if (!query) {
                dropdown.classList.remove('show');
                this.currentResults = [];
                this.selectedIndex = -1;
                return;
            }

            this.debounceTimer = setTimeout(() => {
                this.performSearch(query);
            }, 120);
        });

        // Focus listener to show results if query exists
        input.addEventListener('focus', () => {
            if (input.value.trim().length > 0 && this.currentResults.length > 0) {
                dropdown.classList.add('show');
            }
        });

        // Keyboard navigation (ArrowDown, ArrowUp, Enter, Escape)
        input.addEventListener('keydown', (e) => {
            if (!dropdown.classList.contains('show') || this.currentResults.length === 0) {
                if (e.key === 'Enter') {
                    const q = input.value.trim();
                    if (q) this.performSearch(q);
                }
                return;
            }

            if (e.key === 'ArrowDown') {
                e.preventDefault();
                this.selectedIndex = (this.selectedIndex + 1) % this.currentResults.length;
                this.updateSelectionVisuals();
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                this.selectedIndex = (this.selectedIndex - 1 + this.currentResults.length) % this.currentResults.length;
                this.updateSelectionVisuals();
            } else if (e.key === 'Enter') {
                e.preventDefault();
                if (this.selectedIndex >= 0 && this.selectedIndex < this.currentResults.length) {
                    const selected = this.currentResults[this.selectedIndex];
                    this.selectCustomer(selected.id);
                }
            } else if (e.key === 'Escape') {
                dropdown.classList.remove('show');
            }
        });

        // Close on click outside
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.global-search-container')) {
                dropdown.classList.remove('show');
            }
        });

        // Global hotkeys: '/' or 'Ctrl+K' / 'Cmd+K' to focus search
        document.addEventListener('keydown', (e) => {
            const isK = (e.key === 'k' || e.key === 'K') && (e.ctrlKey || e.metaKey);
            const isSlash = e.key === '/' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName);
            
            if (isK || isSlash) {
                e.preventDefault();
                input.focus();
                input.select();
            }
        });
    },

    clearSearch() {
        const input = document.getElementById('global-search-input');
        const dropdown = document.getElementById('search-results-dropdown');
        const clearBtn = document.getElementById('btn-clear-global-search');
        if (input) {
            input.value = '';
            input.focus();
        }
        if (dropdown) dropdown.classList.remove('show');
        if (clearBtn) clearBtn.style.display = 'none';
        this.currentResults = [];
        this.selectedIndex = -1;
    },

    async performSearch(query) {
        const dropdown = document.getElementById('search-results-dropdown');
        const list = document.getElementById('search-results-list');
        const statusText = document.getElementById('search-status-text');
        const latencyBadge = document.getElementById('search-latency-badge');

        statusText.textContent = `Searching for "${query}"...`;
        dropdown.classList.add('show');

        try {
            const data = await api.get(`/customers/search?q=${encodeURIComponent(query)}&limit=10`);
            this.currentResults = data.results || [];
            this.selectedIndex = -1;

            latencyBadge.textContent = `${data.latency_ms}ms`;
            statusText.textContent = `${data.count} customer${data.count === 1 ? '' : 's'} matched`;

            if (this.currentResults.length === 0) {
                list.innerHTML = `
                    <div style="padding: 1.5rem; text-align: center; color: var(--text-muted);">
                        <p style="font-weight: 500; margin-bottom: 0.5rem; font-size: 0.8125rem;">No customer found for "${query}"</p>
                        <button class="btn btn-primary btn-xs" onclick="customer.openAddModal('${query}')">+ Create Customer</button>
                    </div>
                `;
                return;
            }

            list.innerHTML = this.currentResults.map((c, idx) => {
                const partyName = c.party_name || c.name;
                const partyCode = c.party_code || c.customer_id;
                const phone1 = c.phone_1 || c.mobile;
                const contactPerson = c.contact_person_1 || '';
                const matchTag = c.match_type === 'exact_phone' ? 'Exact Phone' : (c.match_type === 'exact_code' ? 'Code Match' : 'Match');
                return `
                    <div class="search-result-item" data-index="${idx}" onclick="search.selectCustomer(${c.id})">
                        <div class="search-item-info">
                            <div class="search-item-name">
                                <span>${partyName}</span>
                                <span class="badge badge-standard">${partyCode}</span>
                                <span class="badge ${c.status === 'Active' ? 'badge-active' : 'badge-lead'}">${c.status}</span>
                            </div>
                            <div class="search-item-meta">
                                <span style="color: var(--primary); font-weight: 600; font-variant-numeric: tabular-nums;">${phone1}</span>
                                ${contactPerson ? `<span>${contactPerson}</span>` : ''}
                                ${c.city ? `<span>${c.city}</span>` : ''}
                                ${c.email_id_1 ? `<span>${c.email_id_1}</span>` : ''}
                            </div>
                        </div>
                        <div>
                            <span class="badge badge-active">${matchTag}</span>
                        </div>
                    </div>
                `;
            }).join('');

        } catch (err) {
            console.error("Search error:", err);
            statusText.textContent = "Search failed";
        }
    },

    updateSelectionVisuals() {
        const items = document.querySelectorAll('.search-result-item');
        items.forEach((el, idx) => {
            if (idx === this.selectedIndex) {
                el.classList.add('selected');
                el.scrollIntoView({ block: 'nearest' });
            } else {
                el.classList.remove('selected');
            }
        });
    },

    selectCustomer(customerId) {
        const dropdown = document.getElementById('search-results-dropdown');
        dropdown.classList.remove('show');
        customer.openDrawer(customerId);
    }
};

window.search = search;
