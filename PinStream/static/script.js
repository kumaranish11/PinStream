// DOM Elements
const urlInput = document.getElementById('pinterest-url');
const checkBtn = document.getElementById('check-btn');
const loading = document.getElementById('loading');
const errorMessage = document.getElementById('error-message');
const errorText = document.getElementById('error-text');
const previewCard = document.getElementById('preview-card');
const previewImage = document.getElementById('preview-image');
const previewTitle = document.getElementById('preview-title');
const previewDescription = document.getElementById('preview-description');
const previewAuthor = document.getElementById('preview-author');
const downloadSection = document.getElementById('download-section');
const fallbackSection = document.getElementById('fallback-section');
const consentCheckbox = document.getElementById('consent-checkbox');
const downloadBtn = document.getElementById('download-btn');
const pinterestLink = document.getElementById('pinterest-link');

// State
let currentVideoUrl = null;
let currentPinUrl = null;

// Event Listeners
checkBtn.addEventListener('click', handleCheck);
urlInput.addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        handleCheck();
    }
});
urlInput.addEventListener('input', function() {
    hideAll();
    
    // Add dynamic animation based on URL length - rectangular expansion
    const url = this.value.trim();
    const baseWidth = 100; // percentage
    const maxExpansion = 20; // additional percentage
    
    if (url.length > 0) {
        // Calculate expansion based on URL length (max 150 chars for full expansion)
        const expansionRatio = Math.min(url.length / 150, 1);
        const currentWidth = baseWidth + (maxExpansion * expansionRatio);
        
        // Apply rectangular growth animation
        this.style.width = `${currentWidth}%`;
        this.style.transition = 'width 0.4s ease, box-shadow 0.3s ease, border-color 0.3s ease';
        
        if (url.length > 10) {
            // Add pulsing glow effect for longer URLs
            this.classList.add('animate-pulse');
            this.style.boxShadow = '0 0 15px rgba(99, 102, 241, 0.4)';
            
            // Add gradient border for valid-looking URLs
            if (url.includes('pinterest.com') || url.includes('pin.it')) {
                this.style.borderColor = '#E60023';
                this.style.boxShadow = '0 0 20px rgba(230, 0, 35, 0.3)';
            } else {
                this.style.borderColor = '#6366f1';
            }
        }
    } else {
        // Reset animations for empty input
        this.classList.remove('animate-pulse');
        this.style.width = '100%';
        this.style.boxShadow = 'none';
        this.style.borderColor = '#e5e7eb';
    }
});

urlInput.addEventListener('focus', function() {
    // Add focus animation
    this.style.transform = 'scale(1.02)';
    this.style.transition = 'transform 0.3s ease, box-shadow 0.3s ease';
    this.style.boxShadow = '0 0 20px rgba(99, 102, 241, 0.3)';
});

urlInput.addEventListener('blur', function() {
    // Reset focus animation
    this.style.transform = 'scale(1)';
    this.style.boxShadow = 'none';
});

consentCheckbox.addEventListener('change', function() {
    downloadBtn.disabled = !this.checked;
});

downloadBtn.addEventListener('click', handleDownload);

// Functions
function hideAll() {
    loading.classList.add('hidden');
    errorMessage.classList.add('hidden');
    previewCard.classList.add('hidden');
    downloadSection.classList.add('hidden');
    fallbackSection.classList.add('hidden');
}

function showError(message) {
    hideAll();
    errorText.textContent = message;
    errorMessage.classList.remove('hidden');
}

function showLoading() {
    hideAll();
    loading.classList.remove('hidden');
}

function validateUrl(url) {
    try {
        // Add protocol if missing
        if (!url.startsWith('http://') && !url.startsWith('https://')) {
            url = 'https://' + url;
        }
        
        const urlObj = new URL(url);
        const hostname = urlObj.hostname.toLowerCase();
        const pathname = urlObj.pathname.toLowerCase();
        
        const validDomains = ['pinterest.com', 'www.pinterest.com', 'pin.it', 'pinterest.co.uk', 'br.pinterest.com'];
        
        // Check domain
        if (!validDomains.includes(hostname)) {
            return false;
        }
        
        // For pin.it, any path is valid as it's a redirect service
        if (hostname === 'pin.it') {
            return true;
        }
        
        // For pinterest domains, check for pin in path
        return pathname.includes('/pin/') || pathname.startsWith('/pin/');
        
    } catch (e) {
        return false;
    }
}

async function handleCheck() {
    const url = urlInput.value.trim();
    
    if (!url) {
        showError('Please enter a Pinterest URL');
        return;
    }
    
    if (!validateUrl(url)) {
        showError('Please enter a valid Pinterest pin URL (e.g., pinterest.com/pin/123... or pin.it/abc...)');
        return;
    }
    
    // Add button animation
    checkBtn.innerHTML = `
        <svg class="w-5 h-5 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
        </svg>
        <span>Analyzing...</span>
    `;
    checkBtn.style.transform = 'scale(0.95)';
    
    showLoading();
    checkBtn.disabled = true;
    
    try {
        const response = await fetch('/inspect', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ url: url })
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Failed to inspect pin');
        }
        
        displayPreview(data.metadata, data.downloadable, url);
        
    } catch (error) {
        console.error('Error:', error);
        showError(error.message || 'Failed to check Pinterest URL. Please try again.');
    } finally {
        // Reset button animation
        checkBtn.innerHTML = `
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
            </svg>
            <span>Analyze</span>
        `;
        checkBtn.style.transform = 'scale(1)';
        checkBtn.disabled = false;
    }
}

function displayPreview(metadata, downloadable, originalUrl) {
    hideAll();
    
    // Set current state
    currentVideoUrl = metadata.video_url;
    currentPinUrl = originalUrl;
    
    // Update preview content
    if (metadata.image_url) {
        previewImage.src = metadata.image_url;
        previewImage.alt = metadata.title || 'Pinterest pin preview';
    } else {
        previewImage.src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWxsPSIjZjNmNGY2Ii8+PHRleHQgeD0iNTAlIiB5PSI1MCUiIGZvbnQtZmFtaWx5PSJBcmlhbCwgc2Fucy1zZXJpZiIgZm9udC1zaXplPSIxNCIgZmlsbD0iIzk3OTc5NyIgdGV4dC1hbmNob3I9Im1pZGRsZSIgZHk9Ii4zZW0iPk5vIGltYWdlPC90ZXh0Pjwvc3ZnPg==';
        previewImage.alt = 'No preview available';
    }
    
    previewTitle.textContent = metadata.title || 'Pinterest Pin';
    previewDescription.textContent = metadata.description || 'No description available';
    
    if (metadata.author) {
        previewAuthor.textContent = `By ${metadata.author}`;
        previewAuthor.classList.remove('hidden');
    } else {
        previewAuthor.classList.add('hidden');
    }
    
    // Show appropriate section with enhanced messaging
    if (downloadable && currentVideoUrl) {
        downloadSection.classList.remove('hidden');
        consentCheckbox.checked = false;
        downloadBtn.disabled = true;
        
        // Show success indicator
        const successMsg = document.createElement('div');
        successMsg.className = 'mb-4 p-3 bg-green-50 border border-green-200 rounded-lg';
        successMsg.innerHTML = `
            <div class="flex items-center text-green-800">
                <svg class="w-5 h-5 mr-2" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path>
                </svg>
                <span class="font-semibold">Video detected! Ready for download.</span>
            </div>
        `;
        // Insert before the download section
        downloadSection.parentNode.insertBefore(successMsg, downloadSection);
        
    } else {
        // Enhanced fallback section for non-downloadable content
        fallbackSection.classList.remove('hidden');
        pinterestLink.href = originalUrl;
        
        // Create enhanced error message
        const errorMsg = document.createElement('div');
        errorMsg.className = 'mb-4 p-4 bg-gradient-to-r from-yellow-50 to-orange-50 border border-yellow-200 rounded-lg';
        errorMsg.innerHTML = `
            <div class="flex items-start">
                <svg class="w-6 h-6 text-yellow-600 mr-3 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path>
                </svg>
                <div class="flex-1">
                    <h4 class="text-yellow-800 font-bold text-lg">Video Not Available for Download</h4>
                    <p class="text-yellow-700 mt-2">This Pinterest pin doesn't contain a downloadable video or it's protected by Pinterest's security measures.</p>
                    
                    <div class="mt-4 space-y-2">
                        <details class="text-yellow-700">
                            <summary class="font-semibold cursor-pointer hover:text-yellow-800">Common reasons (click to expand)</summary>
                            <ul class="mt-2 ml-4 space-y-1 text-sm">
                                <li>• Pin contains only static images (most common case)</li>
                                <li>• Video is DRM-protected by Pinterest</li>
                                <li>• Content uses Pinterest's secure streaming servers</li>
                                <li>• Pin is private or has restricted access</li>
                            </ul>
                        </details>
                    </div>
                    
                    <div class="mt-4 p-3 bg-blue-50 border border-blue-200 rounded">
                        <p class="text-blue-800 text-sm">
                            <strong>💡 Tip:</strong> Try different Pinterest video pins - most unprotected videos can be downloaded successfully.
                        </p>
                    </div>
                </div>
            </div>
        `;
        
        // Insert before the fallback section
        fallbackSection.parentNode.insertBefore(errorMsg, fallbackSection);
    }
    
    previewCard.classList.remove('hidden');
}

async function handleDownload() {
    if (!currentVideoUrl || !consentCheckbox.checked) {
        return;
    }
    
    downloadBtn.disabled = true;
    downloadBtn.textContent = 'Preparing Download...';
    
    try {
        // Generate filename from title or use default
        const title = previewTitle.textContent || 'pinterest_video';
        const sanitizedTitle = title.replace(/[^\w\-_\.]/g, '_').substring(0, 50);
        const filename = `${sanitizedTitle}.mp4`;
        
        // Create download URL
        const downloadUrl = `/download?video_url=${encodeURIComponent(currentVideoUrl)}&filename=${encodeURIComponent(filename)}`;
        
        // Create temporary link and trigger download
        const link = document.createElement('a');
        link.href = downloadUrl;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        
        // Reset button after short delay
        setTimeout(() => {
            downloadBtn.disabled = false;
            downloadBtn.textContent = 'Download Video';
        }, 2000);
        
    } catch (error) {
        console.error('Download error:', error);
        showError('Failed to download video. Please try again.');
        downloadBtn.disabled = false;
        downloadBtn.textContent = 'Download Video';
    }
}

// Utility function to truncate text
function truncateText(text, maxLength) {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
}

// Initialize
document.addEventListener('DOMContentLoaded', function() {
    // Focus on URL input
    urlInput.focus();
    
    // Check if URL was passed via URL params (for sharing)
    const urlParams = new URLSearchParams(window.location.search);
    const sharedUrl = urlParams.get('url');
    if (sharedUrl && validateUrl(sharedUrl)) {
        urlInput.value = sharedUrl;
        handleCheck();
    }
});
