# Multi-stage Dockerfile for Supervisor Agent
# Optimized for shared context with .dockerignore isolation

# Stage 1: Dependencies layer (cached when requirements don't change)
# Using pinned Python 3.12 slim image with latest security patches
FROM python:3.12-slim@sha256:b9007ae549da50a6c72d345366d36874fee8de37b833de178eb488143f33e4ca as deps

# Set environment variables early to maximize caching
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies with security updates and address OpenSSL CVEs
RUN apt-get update && \
    # Force security updates first - critical for CVE patching
    apt-get upgrade -y --only-upgrade && \
    # Install build dependencies for OpenSSL compilation
    apt-get install -y --no-install-recommends \
    build-essential \
    wget \
    ca-certificates \
    git \
    curl \
    dnsutils \
    procps \
    zlib1g-dev \
    && \
    # Remove vulnerable OpenSSL packages
    apt-get remove -y openssl libssl3 libssl-dev || true && \
    # Download and compile OpenSSL 3.5.2 (patched version addressing CVEs)
    cd /tmp && \
    wget https://github.com/openssl/openssl/releases/download/openssl-3.5.2/openssl-3.5.2.tar.gz && \
    tar -xzf openssl-3.5.2.tar.gz && \
    cd openssl-3.5.2 && \
    ./Configure --prefix=/usr/local/ssl --openssldir=/usr/local/ssl shared zlib && \
    make -j$(nproc) && \
    make install && \
    # Update library path and symlinks
    echo "/usr/local/ssl/lib64" > /etc/ld.so.conf.d/openssl-3.5.2.conf && \
    ldconfig && \
    ln -sf /usr/local/ssl/bin/openssl /usr/bin/openssl && \
    # Verify OpenSSL version
    /usr/local/ssl/bin/openssl version && \
    # Clean up build dependencies and temporary files
    cd / && rm -rf /tmp/openssl-3.5.2* && \
    apt-get remove -y build-essential wget && \
    apt-get autoremove -y && \
    apt-get upgrade -y && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean

# Upgrade pip and install common build tools
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# ✅ RESTORED: Original shared context paths for better layer caching
COPY multi-agent/agent-supervisor/requirements.txt .

# Install Python dependencies with caching and parallel builds
RUN pip install --no-cache-dir --compile -r requirements.txt

# Stage 2: Development stage (with file watching and hot reload)
FROM deps as development

# Install development dependencies for file watching
RUN pip install --no-cache-dir watchdog

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

# ✅ RESTORED: Copy from shared context (better caching, no duplication)
# Copy application files and shared common directory
COPY --chown=appuser:appuser multi-agent/agent-supervisor/ ./
COPY --chown=appuser:appuser common/ ./common/

# Switch to non-root user
USER appuser

# Expose the port the app runs on
EXPOSE 9003

# Add health check for development
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:9003/health || exit 1

# Development command with file watching
CMD ["python", "common/file_watcher.py", "agent.py"]

# Stage 3: Production stage (optimized runtime)
FROM deps as production

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

# ✅ RESTORED: Copy from shared context (better caching, no duplication)
# Copy application files and shared common directory
COPY --chown=appuser:appuser multi-agent/agent-supervisor/ ./
COPY --chown=appuser:appuser common/ ./common/

# Switch to non-root user
USER appuser

# Expose the port the app runs on
EXPOSE 9003

# Add health check for production
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:9003/health || exit 1

# Production command
CMD ["python", "agent.py"]
