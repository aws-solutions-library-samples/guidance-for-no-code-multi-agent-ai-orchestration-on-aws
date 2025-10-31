/**
 * Authenticated API Client
 * 
 * Provides axios instances with automatic JWT Bearer token authentication
 * and CSRF token handling for all API requests to the Configuration API through the Express proxy.
 */

import axios from 'axios';
import AuthService from './auth.js';

class AuthenticatedApiClient {
  constructor() {
    // In production, the backend serves the React app, so use relative URLs
    // In development, use the explicit backend URL
    const isProduction = process.env.NODE_ENV === 'production';
    this.backendUrl = isProduction ? '' : (process.env.REACT_APP_BACKEND_URL || 'http://localhost:3001');
    
    // Create authenticated axios instance
    this.api = axios.create({
      baseURL: this.backendUrl,
      timeout: 600000, // 10 minutes timeout for long operations
      withCredentials: true // Enable sending cookies for session management
    });

    // CSRF token cache
    this.csrfToken = null;

    // Add request interceptor to automatically include Authorization and CSRF headers
    this.api.interceptors.request.use(
      async (config) => {
        try {
          // Get JWT token from auth service
          const token = await AuthService.getAuthToken();
          
          if (token) {
            config.headers.Authorization = `Bearer ${token}`;
          }

          // Add CSRF token for state-changing operations
          if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(config.method?.toUpperCase())) {
            // Get CSRF token if we don't have one
            if (!this.csrfToken) {
              await this.fetchCSRFToken();
            }
            
            // Add CSRF token to request header
            if (this.csrfToken) {
              config.headers['x-csrf-token'] = this.csrfToken;
            }
          }
        } catch (error) {
          // Don't reject the request, let it proceed without auth (API will return 401 if needed)
        }
        
        return config;
      },
      (error) => {
        return Promise.reject(error);
      }
    );

    // Add response interceptor to handle authentication errors
    this.api.interceptors.response.use(
      (response) => {
        return response;
      },
      async (error) => {
        // Handle 401 authentication errors
        if (error.response?.status === 401) {
          const isAuthenticated = await AuthService.isAuthenticated();
          if (!isAuthenticated) {
            // Could trigger a redirect to login here if needed
          }
        }
        
        // Handle 403 CSRF errors by refreshing token and retrying
        if (error.response?.status === 403 && 
            error.response?.data?.error?.includes('CSRF')) {
          // Clear cached token and fetch a new one
          this.csrfToken = null;
          await this.fetchCSRFToken();
          
          // Retry the original request with new CSRF token
          const originalRequest = error.config;
          if (this.csrfToken && !originalRequest._retry) {
            originalRequest._retry = true;
            originalRequest.headers['x-csrf-token'] = this.csrfToken;
            return this.api(originalRequest);
          }
        }
        
        return Promise.reject(error);
      }
    );
  }

  /**
   * Fetch CSRF token from the backend
   * @returns {Promise<string>} CSRF token
   */
  async fetchCSRFToken() {
    try {
      const response = await axios.get(`${this.backendUrl}/api/csrf-token`, {
        withCredentials: true // Include session cookies
      });
      
      this.csrfToken = response.data.csrfToken;
      return this.csrfToken;
    } catch (error) {
      console.error('[API Client] Failed to fetch CSRF token:', error);
      return null;
    }
  }

  /**
   * Get the authenticated axios instance
   * @returns {AxiosInstance} Configured axios instance with auth interceptors
   */
  getInstance() {
    return this.api;
  }

  /**
   * Make a GET request with authentication
   * @param {string} url - Request URL
   * @param {Object} config - Axios config options
   * @returns {Promise} Axios response promise
   */
  async get(url, config = {}) {
    return this.api.get(url, config);
  }

  /**
   * Make a POST request with authentication
   * @param {string} url - Request URL
   * @param {Object} data - Request data
   * @param {Object} config - Axios config options
   * @returns {Promise} Axios response promise
   */
  async post(url, data, config = {}) {
    return this.api.post(url, data, config);
  }

  /**
   * Make a PUT request with authentication
   * @param {string} url - Request URL
   * @param {Object} data - Request data
   * @param {Object} config - Axios config options
   * @returns {Promise} Axios response promise
   */
  async put(url, data, config = {}) {
    return this.api.put(url, data, config);
  }

  /**
   * Make a DELETE request with authentication
   * @param {string} url - Request URL
   * @param {Object} config - Axios config options
   * @returns {Promise} Axios response promise
   */
  async delete(url, config = {}) {
    return this.api.delete(url, config);
  }

  /**
   * Make a PATCH request with authentication
   * @param {string} url - Request URL
   * @param {Object} data - Request data
   * @param {Object} config - Axios config options
   * @returns {Promise} Axios response promise
   */
  async patch(url, data, config = {}) {
    return this.api.patch(url, data, config);
  }

  /**
   * Create a new authenticated fetch request with Bearer token and CSRF token
   * Useful for streaming APIs where axios interceptors aren't sufficient
   * @param {string} url - Request URL (relative to backend)
   * @param {Object} options - Fetch options
   * @returns {Promise<Response>} Fetch response promise
   */
  async authenticatedFetch(url, options = {}) {
    try {
      // Get JWT token
      const token = await AuthService.getAuthToken();
      
      // Prepare headers
      const headers = {
        'Content-Type': 'application/json',
        ...options.headers
      };
      
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }

      // Add CSRF token for state-changing operations
      const method = options.method?.toUpperCase() || 'GET';
      if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(method)) {
        // Get CSRF token if we don't have one
        if (!this.csrfToken) {
          await this.fetchCSRFToken();
        }
        
        if (this.csrfToken) {
          headers['x-csrf-token'] = this.csrfToken;
        }
      }
      
      // Make authenticated fetch request
      const response = await fetch(`${this.backendUrl}${url}`, {
        ...options,
        headers,
        credentials: 'include' // Include cookies for session management
      });
      
      return response;
    } catch (error) {
      throw error;
    }
  }
}

// Export singleton instance
const apiClient = new AuthenticatedApiClient();
export default apiClient;
