const express = require('express');
const cors = require('cors');
const axios = require('axios');
const path = require('path');
const helmet = require('helmet');
const fs = require('fs');
const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');

const app = express();
const PORT = process.env.PORT || 3001;

// Configuration endpoints from environment variables
const CONFIGURATION_API_ENDPOINT = process.env.CONFIGURATION_API_ENDPOINT || 'http://localhost:8000';
const SUPERVISOR_AGENT_ENDPOINT = process.env.SUPERVISOR_AGENT_ENDPOINT || 'http://localhost:9003';
const PROJECT_NAME = process.env.PROJECT_NAME || 'genai-box';

// Enhanced security: Extract allowed domains from environment variables dynamically
const extractHostname = (url) => {
  try {
    return new URL(url).hostname;
  } catch (e) {
    console.error(`[SECURITY] Failed to parse URL: ${url}`);
    return null;
  }
};

const ALLOWED_API_DOMAINS = [
  extractHostname(CONFIGURATION_API_ENDPOINT),
  extractHostname(SUPERVISOR_AGENT_ENDPOINT),
  'localhost' // Always allow localhost for development
].filter(Boolean); // Remove any null values

const ALLOWED_PORTS = [8000, 8080, 9003, 9000, 80, 443]; // Common safe ports

// Configurable AWS infrastructure domain suffixes
// CDK reads config/development.yaml and sets environment variables during deployment
// Format: Comma-separated list of domain suffixes
// Example: ALLOWED_AWS_DOMAINS=".elb.amazonaws.com,.on.aws,.amazonaws.com"
const ALLOWED_AWS_DOMAINS = process.env.ALLOWED_AWS_DOMAINS 
  ? process.env.ALLOWED_AWS_DOMAINS.split(',').map(domain => domain.trim()).filter(Boolean)
  : ['.elb.amazonaws.com', '.on.aws', '.amazonaws.com']; // Local development defaults

console.log('[SECURITY] Allowed AWS infrastructure domains:', ALLOWED_AWS_DOMAINS);

const validateUrl = (url) => {
  try {
    const parsedUrl = new URL(url);
    
    // Only allow HTTP/HTTPS protocols
    if (!['http:', 'https:'].includes(parsedUrl.protocol)) {
      throw new Error('Invalid protocol - only HTTP/HTTPS allowed');
    }
    
    // Enhanced validation for hostname patterns
    const hostname = parsedUrl.hostname.toLowerCase();
    
    // Whitelist approach: Allow domains from environment variables + AWS infrastructure domains
    const isDomainAllowed = ALLOWED_API_DOMAINS.some(allowed => 
      hostname === allowed || hostname.endsWith('.' + allowed)
    );
    
    // Allow AWS infrastructure endpoints configured via ALLOWED_AWS_DOMAINS environment variable
    // Default domains: .elb.amazonaws.com, .on.aws, .amazonaws.com
    // VPC Lattice uses: *.vpc-lattice-svcs.{region}.on.aws
    const isAWSInfrastructure = ALLOWED_AWS_DOMAINS.some(suffix => 
      hostname.endsWith(suffix)
    );
    
    if (!isDomainAllowed && !isAWSInfrastructure) {
      throw new Error(`Hostname not in whitelist: ${hostname}`);
    }
    
    // Additional port restrictions - must be in whitelist
    const port = parsedUrl.port ? parseInt(parsedUrl.port) : (parsedUrl.protocol === 'https:' ? 443 : 80);
    if (parsedUrl.port && !ALLOWED_PORTS.includes(port)) {
      throw new Error(`Port not in whitelist: ${port}`);
    }
    
    // URL length validation
    if (url.length > 2048) {
      throw new Error('URL too long');
    }
    
    return true;
  } catch (e) {
    console.log(`[SECURITY] URL validation failed for ${url}: ${e.message}`);
    return false;
  }
};

// Validate configuration endpoints at startup
console.log('[SECURITY] Allowed API domains:', ALLOWED_API_DOMAINS);
console.log('[SECURITY] Configuration API endpoint:', CONFIGURATION_API_ENDPOINT);
console.log('[SECURITY] Supervisor Agent endpoint:', SUPERVISOR_AGENT_ENDPOINT);

// Enhanced security: Sanitize error messages for logging to prevent XSS
const safeUrlEncode = (str) => {
  if (!str) return 'Unknown';
  // Convert to string and encode special characters
  return String(str)
    .replace(/[<>'"&]/g, (char) => {
      const entities = {
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#x27;',
        '&': '&amp;'
      };
      return entities[char];
    })
    .substring(0, 500); // Limit length to prevent log injection
};

// Enhanced security: Validate agent name parameter
const validateAgentName = (agentName) => {
  if (!agentName || typeof agentName !== 'string') {
    return false;
  }
  // Strict alphanumeric with underscore and dash, limited length
  return /^[a-zA-Z0-9_-]+$/.test(agentName) && 
         agentName.length >= 1 && 
         agentName.length <= 50 &&
         !agentName.includes('..') &&
         !agentName.startsWith('-') &&
         !agentName.endsWith('-');
};

// Enhanced security: Validate component type parameter
const validateComponentType = (componentType) => {
  if (!componentType || typeof componentType !== 'string') {
    return false;
  }
  const allowedTypes = ['models', 'knowledge_base', 'memory', 'observability', 'guardrail', 'tools'];
  return allowedTypes.includes(componentType.toLowerCase()) && componentType.length <= 50;
};

// Security: Validate provider name parameter
const validateProviderName = (providerName) => {
  if (!providerName || typeof providerName !== 'string') {
    return false;
  }
  return /^[a-zA-Z0-9_-]+$/.test(providerName) && 
         providerName.length >= 1 && 
         providerName.length <= 50;
};

// Security: Validate prompt name parameter  
const validatePromptName = (promptName) => {
  if (!promptName || typeof promptName !== 'string') {
    return false;
  }
  return /^[a-zA-Z0-9_\s-]+$/.test(promptName) && 
         promptName.length >= 1 && 
         promptName.length <= 100;
};


// Security: CSRF protection for state-changing operations
const crypto = require('crypto');
const session = require('express-session');

// CSRF token generation and validation
const generateCSRFToken = () => {
  return crypto.randomBytes(32).toString('hex');
};

const validateCSRFToken = (req, providedToken) => {
  const sessionToken = req.session?.csrfToken;
  if (!sessionToken || !providedToken) {
    return false;
  }
  return crypto.timingSafeEqual(
    Buffer.from(sessionToken, 'hex'),
    Buffer.from(providedToken, 'hex')
  );
};

// Trust proxy - CRITICAL for CloudFront → ALB → Express architecture
// Set to number of proxies (2: CloudFront + ALB) to properly detect HTTPS
// This ensures req.secure works correctly even when CloudFront → ALB uses HTTP
app.set('trust proxy', 2);

// Additional middleware to handle CloudFront-specific headers
// CloudFront sets CloudFront-Forwarded-Proto based on viewer protocol (HTTPS)
// ALB may overwrite X-Forwarded-Proto with its own value (HTTP)
// This middleware ensures we check CloudFront headers first
app.use((req, res, next) => {
  // If CloudFront forwarded the viewer protocol, use that instead of X-Forwarded-Proto
  const cloudFrontProto = req.headers['cloudfront-forwarded-proto'] || 
                          req.headers['cloudfront-viewer-protocol'];
  
  if (cloudFrontProto === 'https') {
    // Override req.secure to true when CloudFront viewer used HTTPS
    Object.defineProperty(req, 'secure', {
      value: true,
      writable: false,
      configurable: true
    });
    
    // Also set req.protocol for consistency
    Object.defineProperty(req, 'protocol', {
      value: 'https',
      writable: false,
      configurable: true
    });
  }
  
  next();
});


// Middleware
// Configure CORS to allow credentials (cookies) from the frontend
// Security: Implement proper origin whitelist instead of permissive 'true' value
const allowedOrigins = process.env.NODE_ENV === 'production'
  ? (process.env.ALLOWED_ORIGINS ? process.env.ALLOWED_ORIGINS.split(',').map(o => o.trim()) : [])
  : ['http://localhost:3000', 'http://localhost:3001'];

const corsOptions = {
  origin: (origin, callback) => {
    // Allow requests with no origin (like mobile apps, curl, Postman)
    if (!origin) {
      return callback(null, true);
    }
    
    // In production, check against whitelist
    if (process.env.NODE_ENV === 'production') {
      if (allowedOrigins.length === 0) {
        // If no ALLOWED_ORIGINS env var set, reject all cross-origin requests for security
        console.warn('[CORS] No ALLOWED_ORIGINS configured - rejecting cross-origin request from:', origin);
        return callback(new Error('CORS not allowed - no origins configured'), false);
      }
      
      if (allowedOrigins.indexOf(origin) !== -1) {
        callback(null, true);
      } else {
        console.warn('[CORS] Origin not in whitelist:', origin);
        callback(new Error('Not allowed by CORS'), false);
      }
    } else {
      // Development: Allow localhost origins
      if (allowedOrigins.indexOf(origin) !== -1) {
        callback(null, true);
      } else {
        console.warn('[CORS] Development - origin not in whitelist:', origin);
        callback(new Error('Not allowed by CORS'), false);
      }
    }
  },
  credentials: true, // Allow cookies to be sent/received
  optionsSuccessStatus: 200
};
app.use(cors(corsOptions));
app.use(express.json());

// Security: Helmet for various HTTP security headers
app.use(helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      styleSrc: ["'self'", "'unsafe-inline'"],
      scriptSrc: ["'self'"],
      imgSrc: ["'self'", "data:", "https:"],
      connectSrc: ["'self'", "https:"],
      fontSrc: ["'self'", "data:", "https:"], // Allow data URIs and HTTPS fonts for Cloudscape
      objectSrc: ["'none'"],
      mediaSrc: ["'self'"],
      frameSrc: ["'none'"]
    }
  }
}));

// Security: Session middleware for CSRF token management
const sessionConfig = {
  secret: process.env.SESSION_SECRET || crypto.randomBytes(32).toString('hex'),
  name: 'sessionId',
  resave: false,
  saveUninitialized: false, // Only save sessions that have been modified
  cookie: { 
    httpOnly: true,
    maxAge: 24 * 60 * 60 * 1000, // 24 hours
    path: '/'
  }
};

// Configure cookie settings based on environment
if (process.env.NODE_ENV === 'production') {
  // Production: HTTPS via CloudFront/ALB
  sessionConfig.cookie.secure = true; // Require HTTPS
  
  // CRITICAL FIX: Use 'lax' instead of 'none' for CloudFront
  // CloudFront -> ALB is not cross-site from browser perspective (both appear as same origin)
  // 'lax' allows cookies on top-level navigation and GET requests
  // 'none' requires strict CORS and doesn't work well with CloudFront architecture
  sessionConfig.cookie.sameSite = 'lax';
  
  // Do NOT set explicit domain - let browser use request origin (CloudFront domain)
  console.log('[SESSION] Production: secure=true, sameSite=lax, httpOnly=true');
} else {
  // Development: Only allow HTTP (secure=false) if running on true localhost (127.0.0.1 or localhost HOST or origin)
  // Only disable secure cookies for explicit, trusted local development.
  const hostHeader = (process.env.HOST || '').toLowerCase();
  const isLocalhost = (
    hostHeader === 'localhost' ||
    hostHeader === '127.0.0.1' ||
    (process.env.HOST === undefined && (
      process.env.NODE_ENV === 'development' || process.env.NODE_ENV === undefined
    ))
  );

  if (isLocalhost) {
    // SECURITY WARNING: Cookies sent over HTTP are vulnerable to interception!
    // Only allow insecure cookies for true localhost development. Never set secure=false outside this case.
    sessionConfig.cookie.secure = false; // Allow HTTP only on localhost
    sessionConfig.cookie.sameSite = 'lax'; // Allow cross-port requests
    sessionConfig.cookie.domain = 'localhost'; // Explicit domain for dev
  } else {
    // Outside trusted localhost, always enforce secure cookies!
    // This prevents cleartext cookie transmission and mitigates session hijacking risk.
    sessionConfig.cookie.secure = true;
    sessionConfig.cookie.sameSite = 'lax';
    // Remove explicit domain for broader compatibility
    delete sessionConfig.cookie.domain;
  }
}

app.use(session(sessionConfig));

// Security: CSRF token endpoint
app.get('/api/csrf-token', (req, res) => {
  if (!req.session.csrfToken) {
    req.session.csrfToken = generateCSRFToken();
    
    // Explicitly save the session since saveUninitialized is false
    req.session.save((err) => {
      if (err) {
        console.error('[CSRF ERROR] Failed to save session:', err);
        return res.status(500).json({ error: 'Failed to generate CSRF token' });
      }
      
      res.json({ csrfToken: req.session.csrfToken });
    });
  } else {
    res.json({ csrfToken: req.session.csrfToken });
  }
});

// Security: CSRF validation middleware for state-changing operations
const requireCSRFToken = (req, res, next) => {
  if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(req.method)) {
    const providedToken = req.headers['x-csrf-token'] || req.body._token;
    
    if (!validateCSRFToken(req, providedToken)) {
      return res.status(403).json({ 
        error: 'CSRF token validation failed',
        details: 'Valid CSRF token required for state-changing operations'
      });
    }
  }
  next();
};

// Apply CSRF protection to all routes except health check and CSRF token endpoint
app.use((req, res, next) => {
  if (req.path === '/api/health' || req.path === '/api/csrf-token') {
    return next();
  }
  return requireCSRFToken(req, res, next);
});

// Health check logging suppression middleware
app.use((req, res, next) => {
  next();
});

// Helper function to forward authentication headers
const getAuthHeaders = (req) => {
  const headers = { 'Content-Type': 'application/json' };
  
  if (req.headers.authorization) {
    headers.Authorization = req.headers.authorization;
  }
  
  return headers;
};

// Helper function to handle OAuth authentication errors
const handleAuthError = (error, res, operation = 'request') => {
  if (error.response?.status === 401) {
    res.status(401).json({ 
      error: 'Authentication required', 
      details: 'Please provide a valid Bearer token',
      oauth_error: error.response?.data 
    });
  } else if (error.response?.status === 403) {
    res.status(403).json({ 
      error: 'Permission denied', 
      details: error.response?.data?.detail || 'Insufficient permissions for this operation',
      oauth_error: error.response?.data
    });
  } else {
    res.status(error.response?.status || 500).json({ 
      error: `Failed to ${operation}`, 
      details: error.response?.data || error.message 
    });
  }
};

// Serve static files from the React app build directory (only in production)
if (process.env.NODE_ENV === 'production') {
  app.use(express.static(path.join(__dirname, 'build')));
}

// Proxy routes for Configuration API with Bearer token forwarding
app.get('/api/config/agents', async (req, res) => {
  try {
    const headers = {};
    if (req.headers.authorization) {
      headers.Authorization = req.headers.authorization;
    }
    
    const response = await axios.get(`${CONFIGURATION_API_ENDPOINT}/config/list`, { headers });
    res.json(response.data);
  } catch (error) {
    if (error.response?.status === 401) {
      res.status(401).json({ error: 'Authentication required', details: 'Please provide a valid Bearer token' });
    } else if (error.response?.status === 403) {
      res.status(403).json({ error: 'Permission denied', details: error.response?.data?.detail || 'Insufficient permissions' });
    } else {
      res.status(500).json({ error: 'Failed to fetch agents', details: safeUrlEncode(error.message) });
    }
  }
});

app.get('/api/config/agent/:agentName', async (req, res) => {
  try {
    const { agentName } = req.params;
    
    // Security validation
    if (!validateAgentName(agentName)) {
      return res.status(400).json({ error: 'Invalid agent name format' });
    }
    
    const response = await axios.get(`${CONFIGURATION_API_ENDPOINT}/config/agent/${agentName}`, {
      headers: getAuthHeaders(req)
    });
    res.json(response.data);
  } catch (error) {
    handleAuthError(error, res, 'fetch agent configuration');
  }
});

app.post('/api/config/agent', async (req, res) => {
  try {
    const response = await axios.post(`${CONFIGURATION_API_ENDPOINT}/config/save`, req.body, {
      headers: getAuthHeaders(req)
    });
    res.json(response.data);
  } catch (error) {
    handleAuthError(error, res, 'save agent configuration');
  }
});

// Additional proxy route for direct /save endpoint (used by CreateAgentWizard)
app.post('/api/config/save', async (req, res) => {
  try {
    const response = await axios.post(`${CONFIGURATION_API_ENDPOINT}/config/save`, req.body, {
      headers: getAuthHeaders(req)
    });
    res.json(response.data);
  } catch (error) {
    handleAuthError(error, res, 'save agent configuration');
  }
});

// Direct proxy route for /config/load endpoint (for agent configuration refresh)
app.post('/api/config/load', async (req, res) => {
  try {
    const response = await axios.post(`${CONFIGURATION_API_ENDPOINT}/config/load`, req.body, {
      headers: getAuthHeaders(req)
    });
    res.json(response.data);
  } catch (error) {
    handleAuthError(error, res, 'load agent configuration');
  }
});

// Form Schema proxy routes (for dynamic form generation)
app.get('/api/form-schema/components', async (req, res) => {
  try {
    // Security: Validate configuration endpoint before use
    if (!validateUrl(CONFIGURATION_API_ENDPOINT)) {
      return res.status(500).json({ error: 'Invalid configuration endpoint' });
    }
    
    const response = await axios.get(`${CONFIGURATION_API_ENDPOINT}/form-schema/components`, {
      headers: getAuthHeaders(req)
    });
    res.json(response.data);
  } catch (error) {
    handleAuthError(error, res, 'fetch form schema components');
  }
});

app.get('/api/form-schema/components/:componentType', async (req, res) => {
  try {
    const { componentType } = req.params;
    
    // Security validation
    if (!validateComponentType(componentType)) {
      return res.status(400).json({ error: 'Invalid component type' });
    }
    
    // Security: Validate configuration endpoint before use
    if (!validateUrl(CONFIGURATION_API_ENDPOINT)) {
      return res.status(500).json({ error: 'Invalid configuration endpoint' });
    }
    
    // Security: Construct URL using URL API to prevent SSRF
    const baseUrl = new URL(CONFIGURATION_API_ENDPOINT);
    baseUrl.pathname = `/form-schema/components/${encodeURIComponent(componentType)}`;
    const targetUrl = baseUrl.toString();
    
    // Additional URL validation before request
    if (!validateUrl(targetUrl)) {
      return res.status(500).json({ error: 'Generated URL validation failed' });
    }
    
    const response = await axios.get(targetUrl, {
      headers: getAuthHeaders(req)
    });
    res.json(response.data);
  } catch (error) {
    handleAuthError(error, res, 'fetch form schema for component');
  }
});

app.get('/api/form-schema/providers/:componentType', async (req, res) => {
  try {
    const { componentType } = req.params;
    
    // Security validation
    if (!validateComponentType(componentType)) {
      return res.status(400).json({ error: 'Invalid component type' });
    }
    
    // Security: Validate configuration endpoint before use
    if (!validateUrl(CONFIGURATION_API_ENDPOINT)) {
      return res.status(500).json({ error: 'Invalid configuration endpoint' });
    }
    
    // Security: Construct URL using URL API to prevent SSRF
    const baseUrl = new URL(CONFIGURATION_API_ENDPOINT);
    baseUrl.pathname = `/form-schema/providers/${encodeURIComponent(componentType)}`;
    const targetUrl = baseUrl.toString();
    
    // Additional URL validation before request
    if (!validateUrl(targetUrl)) {
      return res.status(500).json({ error: 'Generated URL validation failed' });
    }
    
    const response = await axios.get(targetUrl, {
      headers: getAuthHeaders(req)
    });
    res.json(response.data);
  } catch (error) {
    handleAuthError(error, res, 'fetch providers for component');
  }
});

app.get('/api/form-schema/providers/:componentType/:providerName', async (req, res) => {
  try {
    const { componentType, providerName } = req.params;
    
    // Security validation
    if (!validateComponentType(componentType)) {
      return res.status(400).json({ error: 'Invalid component type' });
    }
    if (!validateProviderName(providerName)) {
      return res.status(400).json({ error: 'Invalid provider name' });
    }
    
    // Security: Validate configuration endpoint before use
    if (!validateUrl(CONFIGURATION_API_ENDPOINT)) {
      return res.status(500).json({ error: 'Invalid configuration endpoint' });
    }
    
    // Security: Construct URL using URL API to prevent SSRF
    const baseUrl = new URL(CONFIGURATION_API_ENDPOINT);
    baseUrl.pathname = `/form-schema/providers/${encodeURIComponent(componentType)}/${encodeURIComponent(providerName)}`;
    const targetUrl = baseUrl.toString();
    
    // Additional URL validation before request
    if (!validateUrl(targetUrl)) {
      return res.status(500).json({ error: 'Generated URL validation failed' });
    }
    
    const response = await axios.get(targetUrl, {
      headers: getAuthHeaders(req)
    });
    res.json(response.data);
  } catch (error) {
    handleAuthError(error, res, 'fetch form schema for provider');
  }
});

// Add specific route for models bedrock that was causing issues
app.get('/api/form-schema/models/bedrock', async (req, res) => {
  try {
    const response = await axios.get(`${CONFIGURATION_API_ENDPOINT}/form-schema/providers/models/bedrock`, {
      headers: getAuthHeaders(req)
    });
    res.json(response.data);
  } catch (error) {
    handleAuthError(error, res, 'fetch bedrock models schema');
  }
});

// Tool Management API proxy routes (for ToolManager component)
app.get('/api/form-schema/tools/categories', async (req, res) => {
  try {
    const response = await axios.get(`${CONFIGURATION_API_ENDPOINT}/form-schema/tools/categories`, {
      headers: getAuthHeaders(req)
    });
    res.json(response.data);
  } catch (error) {
    console.error('[PROXY ERROR] Failed to fetch tool categories');
    if (error.message) {
      console.error('[PROXY ERROR] Error details:', safeUrlEncode(error.message));
    }
    handleAuthError(error, res, 'fetch tool categories');
  }
});

app.get('/api/form-schema/tools/:category/available', async (req, res) => {
  try {
    const { category } = req.params;
    
    // Security validation for category parameter
    if (!category || typeof category !== 'string' || !/^[a-zA-Z0-9_-]+$/.test(category) || category.length > 50) {
      return res.status(400).json({ error: 'Invalid tool category format' });
    }
    
    const response = await axios.get(`${CONFIGURATION_API_ENDPOINT}/form-schema/tools/${safeUrlEncode(category)}/available`, {
      headers: getAuthHeaders(req)
    });
    res.json(response.data);
  } catch (error) {
    console.error('[PROXY ERROR] Failed to fetch available tools for category:', safeUrlEncode(error.message));
    handleAuthError(error, res, 'fetch available tools for category');
  }
});

app.get('/api/form-schema/tools/:category/:toolName', async (req, res) => {
  try {
    const { category, toolName } = req.params;
    
    // Security validation for both parameters
    if (!category || typeof category !== 'string' || !/^[a-zA-Z0-9_-]+$/.test(category) || category.length > 50) {
      return res.status(400).json({ error: 'Invalid tool category format' });
    }
    if (!toolName || typeof toolName !== 'string' || !/^[a-zA-Z0-9_-]+$/.test(toolName) || toolName.length > 100) {
      return res.status(400).json({ error: 'Invalid tool name format' });
    }
    
    const response = await axios.get(`${CONFIGURATION_API_ENDPOINT}/form-schema/tools/${safeUrlEncode(category)}/${safeUrlEncode(toolName)}`, {
      headers: getAuthHeaders(req)
    });
    res.json(response.data);
  } catch (error) {
    console.error('[PROXY ERROR] Failed to fetch tool schema:', safeUrlEncode(error.message));
    handleAuthError(error, res, 'fetch tool schema');
  }
});

app.post('/api/form-schema/tools/validate', async (req, res) => {
  try {
    const response = await axios.post(`${CONFIGURATION_API_ENDPOINT}/form-schema/tools/validate`, req.body, {
      headers: getAuthHeaders(req)
    });
    res.json(response.data);
  } catch (error) {
    console.error('[PROXY ERROR] Failed to validate tool configuration:', safeUrlEncode(error.message));
    handleAuthError(error, res, 'validate tool configuration');
  }
});

// System Prompts API proxy routes
app.get('/api/config/system-prompts/available/:agentName', async (req, res) => {
  try {
    const { agentName } = req.params;
    
    // Security validation
    if (!validateAgentName(agentName)) {
      return res.status(400).json({ error: 'Invalid agent name format' });
    }
    
    console.log(`[PROXY] GET ${CONFIGURATION_API_ENDPOINT}/config/system-prompts/available/${agentName}`);
    const response = await axios.get(`${CONFIGURATION_API_ENDPOINT}/config/system-prompts/available/${safeUrlEncode(agentName)}`, {
      headers: getAuthHeaders(req)
    });
    res.json(response.data);
  } catch (error) {
    console.error('[PROXY ERROR] Failed to fetch available system prompts:', safeUrlEncode(error.message));
    handleAuthError(error, res, 'fetch available system prompts');
  }
});

app.get('/api/config/system-prompts/content/:agentName/:promptName', async (req, res) => {
  try {
    const { agentName, promptName } = req.params;
    
    // Security validation
    if (!validateAgentName(agentName)) {
      return res.status(400).json({ error: 'Invalid agent name format' });
    }
    if (!validatePromptName(promptName)) {
      return res.status(400).json({ error: 'Invalid prompt name format' });
    }
    
    console.log(`[PROXY] GET ${CONFIGURATION_API_ENDPOINT}/config/system-prompts/content/${agentName}/${promptName}`);
    const response = await axios.get(`${CONFIGURATION_API_ENDPOINT}/config/system-prompts/content/${safeUrlEncode(agentName)}/${safeUrlEncode(promptName)}`, {
      headers: getAuthHeaders(req)
    });
    res.json(response.data);
  } catch (error) {
    console.error('[PROXY ERROR] Failed to fetch system prompt content:', safeUrlEncode(error.message));
    handleAuthError(error, res, 'fetch system prompt content');
  }
});

app.get('/api/config/system-prompts/templates', async (req, res) => {
  try {
    console.log(`[PROXY] GET ${CONFIGURATION_API_ENDPOINT}/config/system-prompts/templates`);
    const response = await axios.get(`${CONFIGURATION_API_ENDPOINT}/config/system-prompts/templates`, {
      headers: getAuthHeaders(req)
    });
    res.json(response.data);
  } catch (error) {
    console.error('[PROXY ERROR] Failed to fetch global prompt templates:', safeUrlEncode(error.message));
    handleAuthError(error, res, 'fetch global prompt templates');
  }
});

app.get('/api/config/system-prompts/all-across-agents', async (req, res) => {
  try {
    console.log(`[PROXY] GET ${CONFIGURATION_API_ENDPOINT}/config/system-prompts/all-across-agents`);
    const response = await axios.get(`${CONFIGURATION_API_ENDPOINT}/config/system-prompts/all-across-agents`, {
      headers: getAuthHeaders(req)
    });
    res.json(response.data);
  } catch (error) {
    console.error('[PROXY ERROR] Failed to fetch system prompts across agents:', safeUrlEncode(error.message));
    handleAuthError(error, res, 'fetch system prompts across agents');
  }
});

app.post('/api/config/system-prompts/create/:agentName', async (req, res) => {
  try {
    const { agentName } = req.params;
    
    // Security validation
    if (!validateAgentName(agentName)) {
      return res.status(400).json({ error: 'Invalid agent name format' });
    }
    
    console.log(`[PROXY] POST ${CONFIGURATION_API_ENDPOINT}/config/system-prompts/create/${safeUrlEncode(agentName)}`);
    console.log('[PROXY] 🔐 Forwarding Authorization header for system prompt creation');
    const response = await axios.post(`${CONFIGURATION_API_ENDPOINT}/config/system-prompts/create/${safeUrlEncode(agentName)}`, req.body, {
      headers: getAuthHeaders(req) // ← FIX: Forward auth headers for system prompt creation
    });
    res.json(response.data);
  } catch (error) {
    console.error('[PROXY ERROR] Failed to create system prompt:', safeUrlEncode(error.message));
    handleAuthError(error, res, 'create system prompt');
  }
});

// Discovery API proxy route
app.get('/api/config/discover', async (req, res) => {
  try {
    console.log(`[PROXY] GET ${CONFIGURATION_API_ENDPOINT}/discover`);
    const response = await axios.get(`${CONFIGURATION_API_ENDPOINT}/discover`, {
      headers: getAuthHeaders(req)
    });
    res.json(response.data);
  } catch (error) {
    console.error('[PROXY ERROR] Failed to discover services:', safeUrlEncode(error.message));
    console.error('[PROXY ERROR] Error details:', safeUrlEncode(JSON.stringify(error.response?.data) || error.message || 'Unknown error'));
    handleAuthError(error, res, 'discover services');
  }
});

// Agent Mapping API proxy route (new enhanced discovery endpoint)
app.get('/api/config/agent-mapping', async (req, res) => {
  try {
    console.log(`[PROXY] GET ${CONFIGURATION_API_ENDPOINT}/agent-mapping`);
    const response = await axios.get(`${CONFIGURATION_API_ENDPOINT}/agent-mapping`, {
      headers: getAuthHeaders(req)
    });
    
    res.json(response.data);
  } catch (error) {
    console.error('[PROXY ERROR] Failed to get agent mapping:', safeUrlEncode(error.message));
    console.error('[PROXY ERROR] Error details:', safeUrlEncode(JSON.stringify(error.response?.data) || error.message || 'Unknown error'));
    handleAuthError(error, res, 'get agent mapping');
  }
});

// Agent Card API proxy route (for fetching agent skills via /.well-known/agent-card.json)
app.get('/api/discover/agent-card/:agentUrl(*)', async (req, res) => {
  try {
    const agentUrl = req.params.agentUrl;
    
    // Security validation: Ensure URL is valid and safe
    if (!validateUrl(agentUrl)) {
      return res.status(400).json({ error: 'Invalid agent URL format' });
    }
    
    console.log('[PROXY] Agent Card Request:', agentUrl);
    console.log('[PROXY] GET', `${CONFIGURATION_API_ENDPOINT}/agent-card/${encodeURIComponent(agentUrl)}`);
    const response = await axios.get(`${CONFIGURATION_API_ENDPOINT}/agent-card/${encodeURIComponent(agentUrl)}`, {
      headers: getAuthHeaders(req)
    });
    console.log('[PROXY] Agent Card Response:', response.status);
    res.json(response.data);
  } catch (error) {
    console.error('[PROXY ERROR] Failed to fetch agent card:', safeUrlEncode(error.message));
    console.error('[PROXY ERROR] Error details:', safeUrlEncode(JSON.stringify(error.response?.data) || error.message || 'Unknown error'));
    console.error('[PROXY ERROR] Full error:', safeUrlEncode(JSON.stringify(error.response || {}) || error.message || 'Unknown error'));
    handleAuthError(error, res, 'fetch agent card');
  }
});

// Agent Refresh proxy route (handles calls to /api/config/refresh-agent/{agentName})
app.post('/api/config/refresh-agent/:agentName', async (req, res) => {
  try {
    const { agentName } = req.params;
    
    // Security validation
    if (!validateAgentName(agentName)) {
      return res.status(400).json({ error: 'Invalid agent name format' });
    }
    
    console.log('[PROXY] POST /api/config/refresh-agent/', agentName, '->', `${CONFIGURATION_API_ENDPOINT}/config/refresh-agent/${agentName}`);
    console.log('[PROXY] 🔐 Forwarding Authorization header for agent refresh');
    
    const response = await axios.post(`${CONFIGURATION_API_ENDPOINT}/config/refresh-agent/${safeUrlEncode(agentName)}`, {}, {
      headers: getAuthHeaders(req), // ← FIX: Forward auth headers for agent refresh
      timeout: 60000 // 1 minute timeout for agent refresh operations
    });
    
    // Security: Sanitize agentName and status to prevent format string injection
    const sanitizedAgent = safeUrlEncode(agentName);
    const sanitizedStatus = safeUrlEncode(String(response.data?.status || 'unknown'));
    console.log('[PROXY] Agent refresh successful');
    console.log('[PROXY] Agent name:', sanitizedAgent);
    console.log('[PROXY] Status:', sanitizedStatus);
    res.json(response.data);
  } catch (error) {
    console.error(`[PROXY ERROR] Failed to refresh agent:`, safeUrlEncode(agentName), safeUrlEncode(error.message || 'Unknown error'));
    console.error('[PROXY ERROR] Error details:', safeUrlEncode(JSON.stringify(error.response?.data || {}) || error.message || 'Unknown error'));
    handleAuthError(error, res, 'refresh agent instances');
  }
});

// Agent Configuration Reload proxy route with OAuth forwarding
app.post('/api/config/agent/:agentName/reload', async (req, res) => {
  try {
    const { agentName } = req.params;
    
    // Security validation
    if (!validateAgentName(agentName)) {
      return res.status(400).json({ error: 'Invalid agent name format' });
    }
    
    console.log(`[PROXY] POST /api/config/agent/${agentName}/reload`);
    console.log('[PROXY] 🔐 Forwarding Authorization header for agent reload');
    
    // Step 1: Get agent mapping to find agent endpoint (with auth)
    const mappingResponse = await axios.get(`${CONFIGURATION_API_ENDPOINT}/agent-mapping`, {
      headers: getAuthHeaders(req) // ← FIX: Forward auth headers for agent mapping
    });
    const agentMapping = mappingResponse.data?.agent_mapping || {};
    
    // FIXED: Agent mapping structure is { "http://agent-url": {"agent_name": "name"} }
    // Need to find URL where agent_name matches the requested agent
    let agentEndpoint = null;
    const availableAgentNames = [];
    
    for (const [url, agentInfo] of Object.entries(agentMapping)) {
      const mappedAgentName = agentInfo?.agent_name;
      availableAgentNames.push(mappedAgentName);
      
      if (mappedAgentName === agentName) {
        agentEndpoint = url;
        break;
      }
    }
    
    
    if (!agentEndpoint) {
      console.error(`[PROXY ERROR] No endpoint found for agent '${agentName}'`);
      console.error('[PROXY ERROR] Available agent names:', availableAgentNames);
      console.error('[PROXY ERROR] Full agent mapping:', agentMapping);
      return res.status(404).json({ 
        error: `No endpoint found for agent '${agentName}'. Agent may not be deployed yet.`, // nosemgrep: tainted-sql-string # This is error logging, not SQL
        available_agents: availableAgentNames,
        available_urls: Object.keys(agentMapping),
        agent_mapping: agentMapping
      });
    }
    
    // Step 2: Call agent's /config/load endpoint with the agent's configuration name
    const reloadResponse = await axios.post(`${agentEndpoint}/config/load`, {
      config_name: agentName  // Agent should reload its own configuration
    }, {
      timeout: 30000,
      headers: { 'Content-Type': 'application/json' } // Note: Direct agent call, no auth needed
    });
    
    // Step 3: Automatically refresh supervisor cache (with auth)
    try {
      const supervisorResponse = await axios.post(`${SUPERVISOR_AGENT_ENDPOINT}/refresh-agent-urls`, {}, {
        headers: getAuthHeaders(req), // ← FIX: Forward auth headers for supervisor refresh
        timeout: 15000
      });
      res.json({
        success: true,
        message: `Agent '${agentName}' configuration reloaded successfully`,
        agentEndpoint: agentEndpoint,
        responseData: reloadResponse.data,
        supervisorCacheRefresh: {
          success: true,
          responseData: supervisorResponse.data
        }
      });
      
    } catch (supervisorError) {
      // Security: Use structured logging to prevent log injection
      console.warn('[PROXY WARN] Supervisor cache refresh failed (non-critical)');
      console.warn('[PROXY WARN] Error details:', { 
        message: supervisorError.message ? String(supervisorError.message).substring(0, 200) : 'Unknown error',
        type: supervisorError.name || 'UnknownError'
      });
      // Security: Sanitize all error data before sending to client
      const sanitizedMessage = safeUrlEncode(supervisorError.message || 'Unknown error');
      res.json({
        success: true,
        message: `Agent '${agentName}' configuration reloaded successfully`,
        agentEndpoint: agentEndpoint,
        responseData: reloadResponse.data,
        supervisorCacheRefresh: {
          success: false,
          message: `Failed to refresh supervisor cache: ${sanitizedMessage}`,
          error: sanitizedMessage
        }
      });
    }
    
  } catch (error) {
    console.error('[PROXY ERROR] Failed to reload agent configuration for %s:', safeUrlEncode(req.params.agentName), safeUrlEncode(error.message || 'Unknown error'));
    console.error('[PROXY ERROR] Error details:', safeUrlEncode(JSON.stringify(error.response?.data) || error.message || 'Unknown error'));

    if (error.message.includes('No endpoint found') || error.response?.status === 404) {
      res.status(404).json({ error: 'Agent configuration not found' });
    } else {
      handleAuthError(error, res, 'reload agent configuration');
    }
  }
});

// Dynamic Agent Deployment API proxy routes with OAuth forwarding
app.post('/api/deployment/create-agent', async (req, res) => {
  try {
    console.log('[PROXY] POST /api/deployment/create-agent');
    console.log('[PROXY] 🔐 Forwarding Authorization header for deployment API');
    console.log('[PROXY] Request body:', req.body);
    
    // Forward the request directly to the Config API's create-agent endpoint
    const response = await axios.post(`${CONFIGURATION_API_ENDPOINT}/api/deployment/create-agent`, req.body, {
      headers: getAuthHeaders(req),
      timeout: 600000 // 10 minutes timeout for deployment
    });
    
    console.log('[PROXY] Agent creation successful:', response.data);
    res.json(response.data);
  } catch (error) {
    console.error('[PROXY ERROR] Failed to create agent:', safeUrlEncode(error.message));
    console.error('[PROXY ERROR] Error details:', safeUrlEncode(JSON.stringify(error.response?.data) || error.message || 'Unknown error'));
    handleAuthError(error, res, 'create agent');
  }
});

app.get('/api/deployment/stack-status/:agentName', async (req, res) => {
  try {
    const { agentName } = req.params;
    
    // Security validation
    if (!validateAgentName(agentName)) {
      return res.status(400).json({ error: 'Invalid agent name format' });
    }
    
    console.log(`[PROXY] GET /api/deployment/stack-status/${agentName}`);
    console.log('[PROXY] 🔐 Forwarding Authorization header for stack status check');
    
    const response = await axios.get(`${CONFIGURATION_API_ENDPOINT}/api/deployment/stack-status/${safeUrlEncode(agentName)}`, {
      headers: getAuthHeaders(req),
      timeout: 30000 // 30 seconds timeout for status check
    });
    
    res.json(response.data);
  } catch (error) {
    console.error('[PROXY ERROR] Failed to get stack status:', safeUrlEncode(error.message));
    console.error('[PROXY ERROR] Error details:', safeUrlEncode(JSON.stringify(error.response?.data) || error.message || 'Unknown error'));
    handleAuthError(error, res, 'get stack status');
  }
});

app.post('/api/deployment/refresh-agent-urls', async (req, res) => {
  try {
    console.log(`[PROXY] POST ${SUPERVISOR_AGENT_ENDPOINT}/refresh-agent-urls`);
    console.log('[PROXY] 🔐 Forwarding Authorization header to Supervisor Agent for refresh');
    
    const response = await axios.post(`${SUPERVISOR_AGENT_ENDPOINT}/refresh-agent-urls`, {}, {
      headers: getAuthHeaders(req),  // ← FIX: Forward auth headers for refresh
      timeout: 30000 // 30 seconds timeout
    });
    
    console.log('[PROXY] Agent URLs refreshed successfully');
    res.json(response.data);
  } catch (error) {
    console.error('[PROXY ERROR] Failed to refresh agent URLs:', safeUrlEncode(error.message));
    console.error('[PROXY ERROR] Error details:', safeUrlEncode(JSON.stringify(error.response?.data) || error.message || 'Unknown error'));
    handleAuthError(error, res, 'refresh agent URLs');
  }
});

// STREAMING ONLY Proxy routes for Supervisor Agent (UX Optimized) with OAuth forwarding
app.post('/api/agent/chat', async (req, res) => {
  try {
    console.log('[PROXY] 🌊 STREAMING-ONLY: POST /api/agent/chat -> Supervisor Agent Streaming');
    console.log('[PROXY] 🔐 Forwarding Authorization header to Supervisor Agent');
    
    const response = await axios.post(`${SUPERVISOR_AGENT_ENDPOINT}/agent-streaming`, req.body, {
      headers: getAuthHeaders(req),  // ← FIX: Forward auth headers
      responseType: 'stream'
    });
    
    // Set appropriate headers for streaming
    res.setHeader('Content-Type', 'text/plain; charset=utf-8');
    res.setHeader('Transfer-Encoding', 'chunked');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');
    
    // Pipe the stream response
    response.data.pipe(res);
  } catch (error) {
    console.error('[PROXY ERROR] Failed to stream with supervisor agent:', safeUrlEncode(error.message));
    handleAuthError(error, res, 'stream with supervisor agent');
  }
});

// DEPRECATED: Redirect sync calls to streaming for consistency with OAuth forwarding
app.post('/api/agent/chat-sync', async (req, res) => {
  console.log('[PROXY] 🚨 DEPRECATED: chat-sync called - redirecting to streaming for optimal UX');
  console.log('[PROXY] 💡 STREAMING ENFORCED: All UI communication uses streaming');
  console.log('[PROXY] 🔐 Forwarding Authorization header to Supervisor Agent');
  
  try {
    // Redirect to streaming endpoint with proper auth headers
    const response = await axios.post(`${SUPERVISOR_AGENT_ENDPOINT}/agent-streaming`, req.body, {
      headers: getAuthHeaders(req),  // ← FIX: Forward auth headers
      responseType: 'stream'
    });
    
    // For sync endpoint, we'll collect the full streaming response and return it as one response
    let completeResponse = '';
    
    return new Promise((resolve, reject) => {
      response.data.on('data', (chunk) => {
        completeResponse += chunk.toString();
      });
      
      response.data.on('end', () => {
        console.log('[PROXY] 💡 Streaming->Sync conversion complete');
        res.json({ response: completeResponse });
        resolve();
      });
      
      response.data.on('error', (error) => {
        console.error('[PROXY ERROR] Streaming error in sync conversion:', safeUrlEncode(error.message || 'Unknown error'));
        res.status(500).json({ error: 'Failed to chat with supervisor agent', details: safeUrlEncode(error.message || 'Unknown error') });
        reject(error);
      });
    });
    
  } catch (error) {
    console.error('[PROXY ERROR] Failed to redirect sync to streaming:', safeUrlEncode(error.message));
    handleAuthError(error, res, 'chat with supervisor agent');
  }
});

// Agent Deletion proxy routes with OAuth forwarding
app.delete('/api/config/delete/:agentName', async (req, res) => {
  try {
    const { agentName } = req.params;
    
    // Security validation
    if (!validateAgentName(agentName)) {
      return res.status(400).json({ error: 'Invalid agent name format' });
    }
    
    console.log(`[PROXY] DELETE /api/config/delete/${agentName} -> ${CONFIGURATION_API_ENDPOINT}/config/delete/${agentName}`);
    console.log('[PROXY] 🔐 Forwarding Authorization header for agent deletion');
    
    const response = await axios.delete(`${CONFIGURATION_API_ENDPOINT}/config/delete/${safeUrlEncode(agentName)}`, {
      headers: getAuthHeaders(req) // ← FIX: Forward auth headers for deletion
    });
    
    console.log(`[PROXY] Agent configuration deletion successful for ${safeUrlEncode(agentName)}`);
    res.json(response.data);
  } catch (error) {
    console.error(`[PROXY ERROR] Failed to delete agent configuration for ${agentName}:`, safeUrlEncode(error.message || 'Unknown error'));
    console.error('[PROXY ERROR] Error details:', safeUrlEncode(JSON.stringify(error.response?.data) || error.message || 'Unknown error'));
    handleAuthError(error, res, 'delete agent configuration');
  }
});

app.delete('/api/config/delete-complete/:agentName', async (req, res) => {
  const { agentName } = req.params;
  
  try {
    // Security validation
    if (!validateAgentName(agentName)) {
      return res.status(400).json({ error: 'Invalid agent name format' });
    }
    
    const includeInfrastructure = req.query.include_infrastructure !== 'false';
    
    console.log(`[PROXY] DELETE /api/config/delete-complete/${agentName} -> ${CONFIGURATION_API_ENDPOINT}/config/delete-complete/${agentName}`);
    console.log(`[PROXY] Include infrastructure: ${includeInfrastructure}`);
    console.log('[PROXY] 🔐 Forwarding Authorization header for complete agent deletion');
    
    const response = await axios.delete(`${CONFIGURATION_API_ENDPOINT}/config/delete-complete/${safeUrlEncode(agentName)}`, {
      params: {
        include_infrastructure: includeInfrastructure
      },
      headers: getAuthHeaders(req), // ← FIX: Forward auth headers for complete deletion
      timeout: 600000 // 10 minutes timeout for deletion operations
    });
    
    console.log(`[PROXY] Complete agent deletion initiated for ${safeUrlEncode(agentName)}`);
    res.json(response.data);
  } catch (error) {
    console.error('[PROXY ERROR] Failed to complete deletion for agent:', safeUrlEncode(agentName), safeUrlEncode(error.message || 'Unknown error'));
    console.error('[PROXY ERROR] Error details:', safeUrlEncode(JSON.stringify(error.response?.data || {}) || error.message || 'Unknown error'));
    handleAuthError(error, res, 'delete agent completely');
  }
});

// Cognito configuration endpoint (moved from Configuration API)
app.get('/api/auth/cognito-config', async (req, res) => {
  try {
    const secretsManagerArn = process.env.SECRETS_MANAGER_ARN;
    const region = process.env.AWS_REGION || 'us-east-1';
    
    // For local development without Secrets Manager, return disabled auth config
    if (!secretsManagerArn) {
      console.log('[COGNITO CONFIG] Local development mode - authentication disabled');
      return res.json({ 
        enabled: false,
        message: 'Authentication disabled for local development'
      });
    }
    
    // Get Cognito parameters from Secrets Manager using AWS SDK v3
    const secretsManager = new SecretsManagerClient({ region });
    const command = new GetSecretValueCommand({ SecretId: secretsManagerArn });
    const response = await secretsManager.send(command);
    const secretData = JSON.parse(response.SecretString);
    
    console.log(`[COGNITO CONFIG] Successfully retrieved Cognito config from Secrets Manager`);
    
    res.json({
      enabled: true,
      userPoolId: secretData.pool_id,
      clientId: secretData.app_client_id,
      region: region
    });
  } catch (error) {
    console.error('[COGNITO CONFIG ERROR] Failed to retrieve Cognito config:', safeUrlEncode(error.message));
    // For local dev, return disabled auth on errors instead of 500
    if (process.env.NODE_ENV !== 'production') {
      console.log('[COGNITO CONFIG] Falling back to disabled auth for local development');
      return res.json({ 
        enabled: false,
        message: 'Authentication disabled - Secrets Manager not accessible'
      });
    }
    res.status(500).json({ 
      error: 'Failed to retrieve Cognito config', 
      details: safeUrlEncode(error.message || 'Unknown error')
    });
  }
});

// Health check endpoint
app.get('/api/health', (req, res) => {
  res.json({ 
    status: 'healthy', 
    service: 'react-ui-backend',
    environment: process.env.NODE_ENV || 'development',
    endpoints: {
      configApi: CONFIGURATION_API_ENDPOINT,
      supervisorAgent: SUPERVISOR_AGENT_ENDPOINT
    },
    timestamp: new Date().toISOString()
  });
});

// Catch all handler: proxy to React dev server in development, serve build in production
app.get('*', (req, res) => {
  if (process.env.NODE_ENV === 'production') {
    res.sendFile(path.join(__dirname, 'build', 'index.html'));
  } else {
    // In development mode, proxy to React dev server
    const reactDevServerUrl = 'http://localhost:3000';
    console.log('[PROXY] Proxying', req.url, 'to React dev server at', reactDevServerUrl);
    
    // Redirect to React dev server for HTML requests
    if (req.headers.accept && req.headers.accept.includes('text/html')) {
      // Security: Enhanced redirect URL validation to prevent open redirects
      const safeRedirectUrl = `${reactDevServerUrl}${req.url}`;
      
      // Strict validation: Only allow exact localhost:3000 with safe paths
      const isValidRedirect = (
        validateUrl(safeRedirectUrl) && 
        safeRedirectUrl.startsWith('http://localhost:3000') &&
        !safeRedirectUrl.includes('..') &&
        !safeRedirectUrl.includes('<') &&
        !safeRedirectUrl.includes('>') &&
        safeRedirectUrl.length <= 200 &&
        // Only redirect to known safe paths
        (req.url === '/' || req.url.startsWith('/static/') || req.url.startsWith('/assets/'))
      );
      
      if (isValidRedirect) {
        // Use a 307 redirect to preserve request method and prevent caching
        // Additional validation: Ensure the URL is exactly localhost:3000 with no query params or fragments
        try {
          const urlObj = new URL(safeRedirectUrl);
          // Strict hostname, port, and protocol validation
          if (urlObj.hostname === 'localhost' && 
              urlObj.port === '3000' && 
              urlObj.protocol === 'http:' &&
              urlObj.pathname === req.url &&
              !urlObj.search && // No query params
              !urlObj.hash) {   // No fragments
            // Security: Enhanced validation - only allow specific safe paths
            const safePath = req.url.replace(/[^a-zA-Z0-9/_.-]/g, '');
            const allowedPaths = ['/', '/static/', '/assets/'];
            const isPathAllowed = allowedPaths.some(allowed => safePath === '/' || safePath.startsWith(allowed));
            
            if (isPathAllowed && safePath.length <= 100) {
              // Security: Hardcoded base URL, sanitized path
              res.redirect(307, `http://localhost:3000${safePath}`);
            } else {
              res.status(400).json({ 
                error: 'Invalid redirect URL',
                message: 'Redirect blocked for security reasons - path not in whitelist'
              });
            }
          } else {
            res.status(400).json({ 
              error: 'Invalid redirect URL',
              message: 'Redirect blocked for security reasons - invalid destination'
            });
          }
        } catch (parseError) {
          res.status(400).json({ 
            error: 'Invalid redirect URL',
            message: 'Redirect blocked for security reasons - URL parse error'
          });
        }
      } else {
        res.status(400).json({ 
          error: 'Invalid redirect URL',
          message: 'Redirect blocked for security reasons'
        });
      }
    } else {
      res.status(404).json({ 
        error: 'Route not found', 
        message: 'In development mode, access the React app at http://localhost:3000',
        backend_api: 'http://localhost:3001/api'
      });
    }
  }
});

// Determine host based on environment - bind to all interfaces for container networking
const HOST = '0.0.0.0';

app.listen(PORT, HOST, () => {
  console.log(`🚀 React UI Backend Server running on ${HOST}:${PORT}`);
  console.log(`📡 Configuration API: ${CONFIGURATION_API_ENDPOINT}`);
  console.log(`🤖 Supervisor Agent: ${SUPERVISOR_AGENT_ENDPOINT}`);
  console.log(`🔧 NODE_ENV: ${process.env.NODE_ENV || 'undefined'}`);
  console.log(` Current directory: ${__dirname}`);
  
  const fs = require('fs');
  try {
    const buildExists = fs.existsSync(path.join(__dirname, 'build'));
    console.log(`📦 Build directory exists: ${buildExists}`);
  } catch (e) {
    console.log(`📦 Error checking build directory: ${e.message}`);
  }
});

module.exports = app;
