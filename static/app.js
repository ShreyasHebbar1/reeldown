document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const downloaderForm = document.getElementById('downloader-form');
    const reelUrlInput = document.getElementById('reel-url');
    const pasteBtn = document.getElementById('paste-btn');
    const clearBtn = document.getElementById('clear-btn');

    const previewArea = document.getElementById('preview-area');
    const previewThumb = document.getElementById('preview-thumb');
    const previewDuration = document.getElementById('preview-duration');
    const previewCreator = document.getElementById('preview-creator');
    const previewTitle = document.getElementById('preview-title');
    const downloadBtn = document.getElementById('download-btn');
    const cancelPreviewBtn = document.getElementById('cancel-preview-btn');
    
    const fetchingLoader = document.getElementById('fetching-loader');
    const successActions = document.getElementById('success-actions');
    const downloadAgainBtn = document.getElementById('download-again-btn');
    
    const toastContainer = document.getElementById('toast-container');
    
    let currentReelInfo = null;

    // --- Helper: Toast Messages ---
    function showToast(message, type = 'success') {
        if (!toastContainer) return;
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        
        const iconSvg = type === 'success' 
            ? `<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>`
            : `<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`;
            
        toast.innerHTML = `
            ${iconSvg}
            <span class="toast-message">${message}</span>
        `;
        
        toastContainer.appendChild(toast);
        
        setTimeout(() => {
            toast.remove();
        }, 5000);
    }

    // --- Helper: Reset UI ---
    function resetUIState() {
        if (previewArea) previewArea.classList.add('hidden');
        if (fetchingLoader) fetchingLoader.classList.add('hidden');
        if (successActions) successActions.classList.add('hidden');
        
        if (reelUrlInput) {
            reelUrlInput.disabled = false;
            reelUrlInput.value = '';
        }
        if (clearBtn) clearBtn.classList.add('hidden');
        currentReelInfo = null;
    }

    // --- Validation function ---
    function isValidInstagramUrl(url) {
        const lowerUrl = url.toLowerCase().trim();
        return lowerUrl.includes('instagram.com') || lowerUrl.includes('instagr.am');
    }

    // --- Auto-Fetch / Analyze Link Function ---
    async function fetchReelMetadata(url) {
        if (!url) return;
        
        // Ensure UI is clean, hide old preview & success cards, keep current input
        if (previewArea) previewArea.classList.add('hidden');
        if (successActions) successActions.classList.add('hidden');
        
        // Disable input while loading
        if (reelUrlInput) {
            reelUrlInput.value = url;
            reelUrlInput.disabled = true;
        }
        
        // Show Pulsing Skeleton Loader
        if (fetchingLoader) {
            fetchingLoader.classList.remove('hidden');
            fetchingLoader.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
        
        try {
            const response = await fetch('/api/info', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    url: url,
                    cookies: 'none'
                })
            });

            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.error || 'Failed to fetch Reel metadata');
            }

            // Display Metadata
            currentReelInfo = data;
            
            if (previewThumb) {
                previewThumb.src = `/api/proxy-image?url=${encodeURIComponent(data.thumbnail)}`;
            }
            if (previewDuration) previewDuration.textContent = data.duration;
            if (previewCreator) previewCreator.textContent = `@${data.uploader}`;
            if (previewTitle) previewTitle.textContent = data.title || 'Instagram Video (No Description)';
            
            // Show preview, scroll to it
            if (previewArea) {
                previewArea.classList.remove('hidden');
                previewArea.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
            showToast('Video details loaded successfully!', 'success');

        } catch (err) {
            let msg = err.message;
            if (msg.includes('Failed to fetch') || msg.includes('Unexpected token')) {
                msg = "We couldn't process this Reel right now. Please try again.";
            } else if (msg.includes('private') || msg.includes('unauthorized') || msg.includes('403') || msg.includes('401')) {
                msg = "This Reel may be private or unavailable.";
            } else {
                msg = "We couldn't process this Reel right now. Please try again.";
            }
            showToast(msg, 'error');
            resetUIState();
        } finally {
            if (fetchingLoader) fetchingLoader.classList.add('hidden');
            if (reelUrlInput) reelUrlInput.disabled = false;
        }
    }

    // --- Wire up Auto-Fetching Input Listeners ---
    if (reelUrlInput) {
        // Form submit handler
        if (downloaderForm) {
            downloaderForm.addEventListener('submit', (e) => {
                e.preventDefault();
                const url = reelUrlInput.value.trim();
                if (isValidInstagramUrl(url)) {
                    fetchReelMetadata(url);
                } else if (url.length > 0) {
                    showToast('Please enter a valid Instagram Reel link.', 'error');
                }
            });
        }

        // Monitor manual typing or text change
        reelUrlInput.addEventListener('input', () => {
            const url = reelUrlInput.value.trim();
            if (clearBtn) clearBtn.classList.toggle('hidden', url.length === 0);
            if (isValidInstagramUrl(url)) {
                fetchReelMetadata(url);
            }
        });

        // Clear button handler
        if (clearBtn) {
            clearBtn.addEventListener('click', () => {
                resetUIState();
            });
        }

        // Clipboard Paste Button handler
        if (pasteBtn) {
            pasteBtn.addEventListener('click', async () => {
                try {
                    const text = await navigator.clipboard.readText();
                    const url = text.trim();
                    if (isValidInstagramUrl(url)) {
                        reelUrlInput.value = url;
                        fetchReelMetadata(url);
                    } else {
                        showToast('Clipboard does not contain a supported Instagram link', 'error');
                    }
                } catch (err) {
                    showToast('Unable to access clipboard. Please paste manually.', 'error');
                }
            });
        }
        
        if (cancelPreviewBtn) {
            cancelPreviewBtn.addEventListener('click', resetUIState);
        }
        
        if (downloadBtn) {
            downloadBtn.addEventListener('click', async () => {
                if (!currentReelInfo || !currentReelInfo.video_url) {
                    showToast('Invalid video URL. Please try again.', 'error');
                    return;
                }

                // Hide preview and show success panel
                if (previewArea) previewArea.classList.add('hidden');
                if (successActions) successActions.classList.remove('hidden');
                reelUrlInput.disabled = true;

                try {
                    // Trigger direct stream download in browser
                    const downloadUrl = `/api/download-stream?url=${encodeURIComponent(currentReelInfo.video_url)}&filename=${encodeURIComponent(currentReelInfo.title || 'instagram_video')}`;
                    
                    if (downloadAgainBtn) {
                        downloadAgainBtn.href = downloadUrl;
                        downloadAgainBtn.download = (currentReelInfo.title || 'instagram_video') + '.mp4';
                    }
                    
                    // Programmatically start download
                    const tempLink = document.createElement('a');
                    tempLink.href = downloadUrl;
                    tempLink.download = (currentReelInfo.title || 'instagram_video') + '.mp4';
                    document.body.appendChild(tempLink);
                    tempLink.click();
                    document.body.removeChild(tempLink);

                    showToast('Download started in browser!', 'success');

                    // Reset input after small timeout
                    setTimeout(() => {
                        resetUIState();
                    }, 1500);

                } catch (err) {
                    showToast('Failed to trigger download: ' + err.message, 'error');
                    resetUIState();
                }
            });
        }
    }

    // --- Accordion component (FAQ) ---
    const accordionHeaders = document.querySelectorAll('.accordion-header');
    accordionHeaders.forEach(header => {
        header.addEventListener('click', () => {
            const item = header.parentElement;
            const content = item.querySelector('.accordion-content');
            
            // Toggle active state
            item.classList.toggle('active');
            
            if (item.classList.contains('active')) {
                content.style.maxHeight = content.scrollHeight + 'px';
            } else {
                content.style.maxHeight = '0';
            }
        });
    });

    // --- Smooth Scrolling for Local Anchor Links ---
    document.querySelectorAll('a').forEach(link => {
        const href = link.getAttribute('href');
        if (!href) return;

        if (href.startsWith('#') || href.includes('#')) {
            const parts = href.split('#');
            const targetId = parts[1];
            if (!targetId) return;
            
            // Only handle smooth scroll if we are on the page containing that element
            const isLocalPage = parts[0] === '' || window.location.pathname === parts[0] || (window.location.pathname === '/' && parts[0] === '');
            
            if (isLocalPage) {
                link.addEventListener('click', (e) => {
                    const targetEl = document.getElementById(targetId);
                    if (targetEl) {
                        e.preventDefault();
                        targetEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    }
                });
            }
        }
    });
});
