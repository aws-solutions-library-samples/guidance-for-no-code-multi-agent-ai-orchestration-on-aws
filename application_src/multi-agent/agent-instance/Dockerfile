# Multi-stage build for Generic Agent Instance
# Optimized for shared context with .dockerignore isolation

# Stage 1: Build python-base with system dependencies
# Using pinned Python 3.12 slim image with latest security patches
FROM python:3.12-slim@sha256:b9007ae549da50a6c72d345366d36874fee8de37b833de178eb488143f33e4ca as system-base

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
    gnupg \
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

# Configure DNS (combine with single RUN to reduce layers)
RUN echo "nameserver 8.8.8.8" > /etc/resolv.conf && \
    echo "nameserver 8.8.4.4" >> /etc/resolv.conf && \
    echo "options ndots:0" >> /etc/resolv.conf

# Upgrade pip and install common build tools
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Create non-root user early
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

# Stage 2: Development build with hot reloading
FROM system-base as development

# Set working directory
WORKDIR /app

# ✅ RESTORED: Copy requirements first for better caching (shared context)
COPY multi-agent/agent-instance/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ✅ RESTORED: Copy from shared context (better caching, no duplication)
# Copy application files and shared common directory
COPY --chown=appuser:appuser multi-agent/agent-instance/ ./
COPY --chown=appuser:appuser common/ ./common/

# Set environment variables for development
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/common

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Default command with file watching for development
CMD ["python", "-u", "agent.py"]

# Stage 3: Production build (optimized)
FROM system-base as production

# Set working directory
WORKDIR /app

# ✅ RESTORED: Copy requirements and install (shared context)
COPY multi-agent/agent-instance/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ✅ RESTORED: Copy from shared context (better caching, no duplication)  
# Copy application files and shared common directory
COPY --chown=appuser:appuser multi-agent/agent-instance/agent.py ./
COPY --chown=appuser:appuser common/ ./common/

# Set production environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/common \
    RELOAD=false

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Production command
CMD ["python", "-u", "agent.py"]
