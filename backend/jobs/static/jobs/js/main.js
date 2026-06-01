document.addEventListener('DOMContentLoaded', () => {
    // -------------------------------------------------------------
    // Toast Notification System
    // -------------------------------------------------------------
    window.showToast = (message, type = 'success') => {
        const container = document.getElementById('toastContainer');
        if (!container) return;

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        
        const content = document.createElement('div');
        content.className = 'toast-content';
        content.textContent = message;

        const closeBtn = document.createElement('button');
        closeBtn.className = 'toast-close';
        closeBtn.setAttribute('aria-label', 'Close notification');
        closeBtn.textContent = '×';
        closeBtn.addEventListener('click', () => {
            toast.remove();
        });

        toast.appendChild(content);
        toast.appendChild(closeBtn);
        container.appendChild(toast);

        // Auto remove after 5 seconds
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateY(20px)';
            toast.style.transition = 'all 0.3s ease';
            setTimeout(() => {
                toast.remove();
            }, 300);
        }, 5000);
    };


    // -------------------------------------------------------------
    // Filter Form Logic & Tiers Sync
    // -------------------------------------------------------------
    const filterForm = document.getElementById('filterForm');
    const tiersHiddenInput = document.getElementById('tiersHiddenInput');
    const resetFiltersBtn = document.getElementById('resetFiltersBtn');

    if (filterForm) {
        // Sync checkboxes to hidden tiers input when submitting
        filterForm.addEventListener('submit', (e) => {
            const checkedBoxes = filterForm.querySelectorAll('input[name="tier_opt"]:checked');
            const selectedTiers = Array.from(checkedBoxes).map(cb => cb.value).join(',');
            
            // If all checkboxes are checked, or none are checked, we represent it as 'all' or empty, but passing comma-separated list is fine too.
            tiersHiddenInput.value = selectedTiers || 'all';
        });
    }

    if (resetFiltersBtn && filterForm) {
        resetFiltersBtn.addEventListener('click', () => {
            const searchInput = document.getElementById('searchQueryInput');
            if (searchInput) searchInput.value = '';

            const checkboxes = filterForm.querySelectorAll('input[name="tier_opt"]');
            checkboxes.forEach(cb => cb.checked = false);

            const sourceSelect = document.getElementById('scraperSourceSelect');
            if (sourceSelect) sourceSelect.value = '';

            const languageSelect = document.getElementById('languageSelect');
            if (languageSelect) languageSelect.value = '';

            const dateSelect = document.getElementById('dateSelect');
            if (dateSelect) dateSelect.value = 'all';

            if (tiersHiddenInput) tiersHiddenInput.value = 'all';

            // Submit clean search
            filterForm.submit();
        });
    }

    // -------------------------------------------------------------
    // Job Details Slide-over Drawer (Modals)
    // -------------------------------------------------------------
    const overlay = document.getElementById('drawerOverlay');
    const drawer = document.getElementById('jobDetailDrawer');
    const closeBtn = document.getElementById('closeDrawerBtn');

    // Drawer internal elements targets
    const dTitle = document.getElementById('detailDrawerTitle');
    const dCompany = document.getElementById('detailDrawerCompany');
    const dTier = document.getElementById('detailDrawerTier');
    const dRank = document.getElementById('detailDrawerRank');
    const dJdSummary = document.getElementById('detailDrawerJdSummary');
    const dSalary = document.getElementById('detailDrawerSalary');
    const dLanguage = document.getElementById('detailDrawerLanguage');
    const dExperience = document.getElementById('detailDrawerExperience');
    const dSource = document.getElementById('detailDrawerSource');
    const dTechStack = document.getElementById('detailDrawerTechStack');
    const dDescription = document.getElementById('detailDrawerDescription');
    const dApplyLink = document.getElementById('detailDrawerApplyLink');

    const openDrawer = () => {
        overlay.classList.add('active');
        drawer.classList.add('active');
        drawer.setAttribute('aria-hidden', 'false');
        document.body.style.overflow = 'hidden'; // prevent scrolling behind drawer
    };

    const closeDrawer = () => {
        overlay.classList.remove('active');
        drawer.classList.remove('active');
        drawer.setAttribute('aria-hidden', 'true');
        document.body.style.overflow = '';
    };

    if (closeBtn) closeBtn.addEventListener('click', closeDrawer);
    if (overlay) overlay.addEventListener('click', closeDrawer);

    // Escape key closes drawer
    window.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && drawer.classList.contains('active')) {
            closeDrawer();
        }
    });

    // Delegate view details buttons clicks
    const container = document.getElementById('jobsListContainer');
    if (container) {
        container.addEventListener('click', async (e) => {
            const button = e.target.closest('.open-drawer-btn');
            if (!button) return;

            const jobId = button.getAttribute('data-job-id');
            if (!jobId) return;

            // Loading state indication
            button.disabled = true;
            const originalHtml = button.textContent;
            button.textContent = '⌛ Loading...';

            try {
                // Fetch full job detail from the DRF api endpoint
                const response = await fetch(`/api/jobs/${jobId}/`);
                if (!response.ok) throw new Error('Failed to retrieve job details.');

                const data = await response.json();
                
                // Get active profile_id to extract ranking matching this profile
                const urlParams = new URLSearchParams(window.location.search);
                const activeProfileId = urlParams.get('profile_id') || '';

                // Find matching ranking
                let profileRanking = null;
                if (data.rankings && data.rankings.length > 0) {
                    profileRanking = data.rankings.find(r => r.profile_id === activeProfileId) || data.rankings[0];
                }

                // ---------------------------------------------------------
                // SAFE DOM RENDERING - Strictly textContent to prevent XSS
                // ---------------------------------------------------------
                dTitle.textContent = data.title || 'Unknown Position';
                dCompany.textContent = data.company || 'Unknown Company';
                
                // Update match tier badge color class and text
                const tier = profileRanking ? (profileRanking.match_tier || 'C') : 'C';
                dTier.textContent = `${tier} Tier`;
                dTier.className = `badge badge-${tier.toLowerCase()}`;

                // Update rank number
                const rank = profileRanking ? (profileRanking.rank || 0) : 0;
                if (rank > 0) {
                    dRank.textContent = `#${rank}`;
                    dRank.style.display = 'inline-block';
                } else {
                    dRank.style.display = 'none';
                }

                // AI summary
                dJdSummary.textContent = profileRanking ? (profileRanking.jd_summary || 'No AI summary generated.') : 'No AI summary generated.';
                
                // Metadata cards
                dSalary.textContent = data.salary || 'Not disclosed';
                
                // Set language display text
                let langDisplay = 'Not specified';
                if (data.language === 'EN') langDisplay = 'English';
                else if (data.language === 'JP') langDisplay = 'Japanese';
                dLanguage.textContent = langDisplay;

                dExperience.textContent = data.experience_required || 'Not specified';
                
                // Capitalize first letter of source
                let sourceDisplay = data.source || 'Other';
                if (sourceDisplay === 'japan_dev') sourceDisplay = 'Japan Dev';
                else if (sourceDisplay === 'tokyo_dev') sourceDisplay = 'Tokyo Dev';
                else sourceDisplay = sourceDisplay.charAt(0).toUpperCase() + sourceDisplay.slice(1);
                dSource.textContent = sourceDisplay;

                // Tech stack pills creation (Safe DOM creation)
                dTechStack.replaceChildren(); // clear old list safely
                const techList = data.tech_stack;
                if (Array.isArray(techList) && techList.length > 0) {
                    techList.forEach(tech => {
                        const pill = document.createElement('span');
                        pill.className = 'skill-pill';
                        pill.textContent = tech;
                        dTechStack.appendChild(pill);
                    });
                } else {
                    const fallback = document.createElement('span');
                    fallback.style.fontStyle = 'italic';
                    fallback.style.color = 'var(--text-muted)';
                    fallback.textContent = 'None specified';
                    dTechStack.appendChild(fallback);
                }

                // Full description body
                dDescription.textContent = data.full_description || data.description || 'No description content.';

                // Setup apply link url safely
                if (data.url) {
                    dApplyLink.setAttribute('href', data.url);
                    dApplyLink.style.display = 'inline-flex';
                } else {
                    dApplyLink.style.display = 'none';
                }

                // Store active ranking and job IDs on drawer opening
                drawer.dataset.activeRankingId = profileRanking ? profileRanking.id : '';
                drawer.dataset.activeJobId = jobId;

                // Set initial state of tier button selectors and rank input field
                const tierValue = profileRanking ? (profileRanking.match_tier || 'C') : 'C';
                const editTierButtons = drawer.querySelectorAll('.tier-select-btn');
                editTierButtons.forEach(btn => {
                    if (btn.getAttribute('data-tier') === tierValue) {
                        btn.classList.add('selected');
                    } else {
                        btn.classList.remove('selected');
                    }
                });

                const rankValue = profileRanking ? (profileRanking.rank || 0) : 0;
                const rankInput = document.getElementById('rankingRankInput');
                if (rankInput) {
                    rankInput.value = rankValue;
                }

                // Open the slide-over drawer
                openDrawer();

            } catch (err) {
                window.showToast(`❌ Error: ${err.message}`, 'error');
            } finally {
                button.disabled = false;
                button.textContent = originalHtml;
            }
        });
    }

    // -------------------------------------------------------------
    // Edit Ranking UI Handlers
    // -------------------------------------------------------------
    const editTierButtons = document.querySelectorAll('.tier-select-btn');
    editTierButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            editTierButtons.forEach(b => b.classList.remove('selected'));
            btn.classList.add('selected');
        });
    });

    const saveRankingBtn = document.getElementById('saveRankingBtn');
    if (saveRankingBtn) {
        saveRankingBtn.addEventListener('click', async () => {
            const rankingId = drawer.dataset.activeRankingId;
            const jobId = drawer.dataset.activeJobId;
            if (!rankingId) {
                window.showToast("❌ No active ranking to save.", "error");
                return;
            }

            const selectedBtn = drawer.querySelector('.tier-select-btn.selected');
            const newTier = selectedBtn ? selectedBtn.getAttribute('data-tier') : 'C';
            const rankInput = document.getElementById('rankingRankInput');
            const newRank = parseInt(rankInput.value, 10) || 0;

            saveRankingBtn.disabled = true;
            const originalBtnText = saveRankingBtn.textContent;
            saveRankingBtn.textContent = 'Saving...';

            try {
                const csrfToken = window.csrfToken || getCookie('csrftoken');
                const response = await fetch(`/api/rankings/${rankingId}/`, {
                    method: 'PATCH',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken,
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: JSON.stringify({
                        match_tier: newTier,
                        rank: newRank
                    })
                });

                if (!response.ok) {
                    const errData = await response.json();
                    throw new Error(errData.detail || 'Failed to save changes.');
                }

                window.showToast("✅ Ranking updated successfully!", "success");

                // Update drawer UI dynamically
                dTier.textContent = `${newTier} Tier`;
                dTier.className = `badge badge-${newTier.toLowerCase()}`;
                if (newRank > 0) {
                    dRank.textContent = `#${newRank}`;
                    dRank.style.display = 'inline-block';
                } else {
                    dRank.style.display = 'none';
                }

                // Update main dashboard card dynamically
                const card = document.getElementById(`jobCard-${jobId}`);
                if (card) {
                    // Update tier border classes:
                    card.className = card.className.replace(/tier-\w+/, `tier-${newTier}`);
                    
                    // Update badge text and classes:
                    const cardBadge = card.querySelector('.job-meta-top .badge');
                    if (cardBadge) {
                        cardBadge.textContent = `${newTier} Tier`;
                        cardBadge.className = `badge badge-${newTier.toLowerCase()}`;
                    }

                    // Update rank indicator:
                    const cardRank = card.querySelector('.job-meta-top .rank-indicator');
                    if (cardRank) {
                        cardRank.textContent = `#${newRank}`;
                        if (newRank > 0) {
                            cardRank.style.display = 'inline-block';
                        } else {
                            cardRank.style.display = 'none';
                        }
                    }
                }
            } catch (err) {
                window.showToast(`❌ Error: ${err.message}`, 'error');
            } finally {
                saveRankingBtn.disabled = false;
                saveRankingBtn.textContent = originalBtnText;
            }
        });
    }

    // -------------------------------------------------------------
    // Infinite Scrolling Logic (IntersectionObserver)
    // -------------------------------------------------------------
    const jobsListContainer = document.getElementById('jobsListContainer');
    const scrollSentinel = document.getElementById('infiniteScrollSentinel');
    const scrollLoader = document.getElementById('infiniteScrollLoader');

    if (jobsListContainer && scrollSentinel && scrollLoader) {
        let page = 1;
        let hasMore = jobsListContainer.dataset.hasMore === 'true';
        let isLoading = false;

        console.log("[Infinite Scroll] Initialized:", { page, hasMore, totalMatches: jobsListContainer.dataset.totalMatches });

        const loadMoreJobs = async () => {
            if (isLoading || !hasMore) return;
            isLoading = true;
            scrollLoader.style.display = 'flex';

            const nextPage = page + 1;
            const urlParams = new URLSearchParams(window.location.search);
            urlParams.set('page', nextPage);
            urlParams.set('ajax', '1');

            console.log(`[Infinite Scroll] Fetching page ${nextPage}...`, urlParams.toString());

            try {
                const response = await fetch(`${window.location.pathname}?${urlParams.toString()}`);
                if (!response.ok) throw new Error('Failed to load next page.');

                const data = await response.json();
                console.log(`[Infinite Scroll] Received page ${nextPage} data:`, { hasMore: data.has_more, htmlLength: data.html ? data.html.length : 0 });
                
                // Append the new HTML to the list container
                if (data.html && data.html.trim()) {
                    const parser = new DOMParser();
                    const doc = parser.parseFromString(data.html, 'text/html');
                    const cards = doc.body.children;
                    console.log(`[Infinite Scroll] Appending ${cards.length} new cards.`);
                    while (cards.length > 0) {
                        jobsListContainer.appendChild(cards[0]);
                    }
                }

                // Update states
                page = nextPage;
                hasMore = data.has_more;
                jobsListContainer.dataset.hasMore = hasMore;
            } catch (error) {
                console.error("[Infinite Scroll] Error:", error);
                window.showToast('❌ Error loading more jobs: ' + error.message, 'error');
            } finally {
                isLoading = false;
                scrollLoader.style.display = 'none';
                
                // If no more, unobserve and hide sentinel
                if (!hasMore) {
                    console.log("[Infinite Scroll] No more records. Unobserving sentinel.");
                    observer.unobserve(scrollSentinel);
                    scrollSentinel.style.display = 'none';
                }
            }
        };

        const observer = new IntersectionObserver((entries) => {
            const entry = entries[0];
            console.log("[Infinite Scroll] Sentinel intersection:", entry.isIntersecting, { hasMore, isLoading });
            if (entry.isIntersecting && hasMore && !isLoading) {
                loadMoreJobs();
            }
        }, {
            rootMargin: '100px', // Pre-fetch before exact bottom reaches
        });

        if (hasMore) {
            observer.observe(scrollSentinel);
        } else {
            console.log("[Infinite Scroll] hasMore is false initially. Hiding sentinel.");
            scrollSentinel.style.display = 'none';
        }
    } else {
        console.warn("[Infinite Scroll] Required DOM elements not found:", { jobsListContainer, scrollSentinel, scrollLoader });
    }
});

// --- Settings Drawer logic ---
window.settingsDrawer = {
    overlay: document.getElementById('settingsDrawerOverlay'),
    drawer: document.getElementById('settingsDrawer'),
    form: document.getElementById('settingsForm'),

    show: async function() {
        this.overlay.classList.add('active');
        this.drawer.classList.add('active');
        this.drawer.setAttribute('aria-hidden', 'false');
        document.body.style.overflow = 'hidden';

        // Fetch current settings
        try {
            const resp = await fetch('/api/settings/');
            if (!resp.ok) throw new Error('Failed to load settings');
            const data = await resp.json();

            document.getElementById('openaiApiKey').value = data.OPENAI_API_KEY || '';
            document.getElementById('openaiBaseUrl').value = data.OPENAI_BASE_URL || '';
            document.getElementById('openaiModel').value = data.OPENAI_MODEL || '';
            document.getElementById('apifyApiToken').value = data.APIFY_API_TOKEN || '';
        } catch (err) {
            window.window.showToast(`Error loading settings: ${err.message}`, 'error');
        }
    },

    hide: function() {
        this.overlay.classList.remove('active');
        this.drawer.classList.remove('active');
        this.drawer.setAttribute('aria-hidden', 'true');
        document.body.style.overflow = '';
    },

    save: async function() {
        const btn = document.getElementById('saveSettingsBtn');
        const originalText = btn.textContent;
        btn.textContent = 'Saving...';
        btn.disabled = true;

        const formData = {
            OPENAI_API_KEY: document.getElementById('openaiApiKey').value,
            OPENAI_BASE_URL: document.getElementById('openaiBaseUrl').value,
            OPENAI_MODEL: document.getElementById('openaiModel').value,
            APIFY_API_TOKEN: document.getElementById('apifyApiToken').value
        };

        try {
            const resp = await fetch('/api/settings/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken') // Ensure CSRF is passed
                },
                body: JSON.stringify(formData)
            });

            if (!resp.ok) throw new Error('Failed to save settings');

            const result = await resp.json();
            if (result.status === 'success') {
                window.window.showToast('Settings saved successfully! ⚙️', 'success');
                this.hide();
            } else {
                throw new Error(result.message || 'Unknown error');
            }
        } catch (err) {
            window.window.showToast(`Error saving settings: ${err.message}`, 'error');
        } finally {
            btn.textContent = originalText;
            btn.disabled = false;
        }
    }
};

// Add event listener to overlay to close the settings drawer when clicked outside
if (window.settingsDrawer.overlay) {
    window.settingsDrawer.overlay.addEventListener('click', () => {
        window.settingsDrawer.hide();
    });
}
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}
