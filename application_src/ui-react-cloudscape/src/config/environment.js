// Environment configuration for API endpoints
const getApiBaseUrl = () => {
  // In production, the Express server serves both React and API on the same port
  // so we use relative URLs
  if (process.env.NODE_ENV === 'production') {
    return '';
  }
  
  // In development, check if we're running in Docker container
  // Docker containers can communicate via container names
  if (process.env.REACT_APP_API_BASE_URL) {
    return process.env.REACT_APP_API_BASE_URL;
  }
  
  // For local development, try to detect if backend is running on 3001
  // This is a fallback for the containerized development environment
  return 'http://localhost:3001';
};

export const API_BASE_URL = getApiBaseUrl();

export const getApiUrl = (endpoint) => {
  return `${API_BASE_URL}${endpoint}`;
};
