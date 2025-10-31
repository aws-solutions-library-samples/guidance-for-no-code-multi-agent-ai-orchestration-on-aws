# Multi-stage Dockerfile for React UI with Express Backend
# Optimized for fast development builds and efficient production deployments

# Stage 1: Dependencies layer (cached when package.json doesn't change)  
# Using pinned Node.js 20-alpine with latest security patches
FROM node:20-alpine@sha256:1ab6fc5a31d515dc7b6b25f6acfda2001821f2c2400252b6cb61044bd9f9ad48 as deps

WORKDIR /app

# Install system dependencies with security updates
RUN apk update && \
    # Force all security updates first - critical for CVE patching
    apk upgrade --no-cache && \
    # Install additional packages
    apk add --no-cache curl procps && \
    # Final upgrade to catch any dependencies
    apk upgrade --no-cache

# Copy package files first for better caching
COPY package*.json ./

# Install dependencies with fallback strategy
# Try npm ci first (fast, strict), fall back to npm install if lock file is out of sync
SHELL ["/bin/ash", "-o", "pipefail", "-c"]
RUN npm ci --omit=dev 2>/dev/null || \
    (echo "⚠️  package-lock.json out of sync, falling back to npm install..." && \
     npm install --omit=dev && \
     echo "✅ Dependencies installed successfully") && \
    npm cache clean --force

# Stage 2: Development stage (with hot reloading)
FROM node:20-alpine@sha256:1ab6fc5a31d515dc7b6b25f6acfda2001821f2c2400252b6cb61044bd9f9ad48 as development

WORKDIR /app

# Install system dependencies with security updates
RUN apk update && \
    # Force all security updates first - critical for CVE patching
    apk upgrade --no-cache && \
    # Install additional packages
    apk add --no-cache curl procps && \
    # Final upgrade to catch any dependencies
    apk upgrade --no-cache

# Copy package files
COPY package*.json ./

# Install all dependencies (including dev dependencies)
RUN npm install

# Copy source code
COPY . .

# Create non-root user
RUN addgroup -g 1001 -S nodejs && \
    adduser -S reactuser -u 1001 -G nodejs && \
    chown -R reactuser:nodejs /app

USER reactuser

# Expose port for development server
EXPOSE 3001

# Add health check for development
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:3001/health || exit 1

# Development command with hot reloading
CMD ["npm", "run", "dev"]

# Stage 3: Build stage (for production builds)
FROM deps as build

# Set production environment for React build
ENV NODE_ENV=production

# Copy source code
COPY . .

# Build the React app
RUN npm run build

# Stage 4: Production stage (optimized runtime)
FROM node:20-alpine@sha256:1ab6fc5a31d515dc7b6b25f6acfda2001821f2c2400252b6cb61044bd9f9ad48 as production

WORKDIR /app

# Set production environment
ENV NODE_ENV=production

# Install system dependencies with security updates
RUN apk update && \
    # Force all security updates first - critical for CVE patching
    apk upgrade --no-cache && \
    # Install additional packages
    apk add --no-cache curl && \
    # Final upgrade to catch any dependencies
    apk upgrade --no-cache

# Copy production dependencies from deps stage
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/package*.json ./

# Copy built application from build stage
COPY --from=build /app/build ./build

# Copy server files
COPY server.js ./

# Create non-root user
RUN addgroup -g 1001 -S nodejs && \
    adduser -S reactuser -u 1001 -G nodejs && \
    chown -R reactuser:nodejs /app

USER reactuser

# Expose port for Express backend server (serves React build + API)
EXPOSE 3001

# Add health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:3001/health || exit 1

# Production command
CMD ["node", "server.js"]
