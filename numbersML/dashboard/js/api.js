/**
 * API Utility Module
 * 
 * Provides API base URL configuration and fetch helper.
 * Include this file before other JS files on each page.
 */

// API Configuration
const API_BASE_URL = '/api';
const API_BASE = '/api';  // Alias for compatibility

/**
 * Fetch wrapper that prepends API base URL
 * @param {string} url - API endpoint (with or without /api prefix)
 * @param {object} options - Fetch options
 * @returns {Promise<Response>}
 */
async function apiFetch(url, options = {}) {
    const fullUrl = url.startsWith('/api') ? url : `${API_BASE}${url}`;
    return fetch(fullUrl, {
        ...options,
        headers: {
            'Content-Type': 'application/json',
            ...options.headers,
        },
    });
}
