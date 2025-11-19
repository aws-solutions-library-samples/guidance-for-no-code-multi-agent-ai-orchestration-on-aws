# AL2023-based Dockerfile for React UI with Express Backend
# Leverages automatic security updates and simplified maintenance

# Stage 1: Base with Node.js 20 runtime from AL2023
FROM amazonlinux:2023 as base

# Install Node.js 20 and system dependencies  
RUN dnf update -y && \
    dnf install -y \
        nodejs \
        npm \
        ca-certificates \
        shadow-utils \
        && \
    dnf clean all && \
    # Create non-root user and group
    useradd -l -m -s /bin/bash -u 1000 nodejs

WORKDIR /app

# Stage 2: Dependencies (cached when package.json doesn't change)
FROM base as deps

# Copy package files
COPY package*.json ./

# Install dependencies with fallback strategy
RUN npm ci --omit=dev 2>/dev/null || \
    (echo "⚠️  package-lock.json out of sync, falling back to npm install..." && \
     npm install --omit=dev && \
     echo "✅ Dependencies installed successfully") && \
    npm cache clean --force

# Stage 3: Development stage
FROM base as development

# Copy package files and install all dependencies
COPY package*.json ./
RUN npm install

# Copy source code
COPY --chown=nodejs:nodejs . .

USER nodejs
EXPOSE 3001

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:3001/health || exit 1

CMD ["npm", "run", "dev"]

# Stage 4: Build stage
FROM deps as build

ENV NODE_ENV=production

# Copy source code and build
COPY . .
RUN npm run build

# Stage 5: Production stage
FROM base as production

ENV NODE_ENV=production

# Copy production dependencies and built app
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/package*.json ./
COPY --from=build /app/build ./build
COPY server.js ./

# Set ownership
RUN chown -R nodejs:nodejs /app

USER nodejs
EXPOSE 3001

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:3001/health || exit 1

CMD ["node", "server.js"]
