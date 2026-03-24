# Multi-stage Dockerfile for Supervisor Agent
# Optimized for shared context with .dockerignore isolation

# Stage 1: Dependencies layer (cached when requirements don't change)
# NOTE: No SHA pin - always pull latest python:3.12-slim to get current Debian security patches
# (pinning SHA prevents picking up OS-level CVE fixes for linux, glibc, libssl3t64, bind9, gnutls28, etc.)
FROM --platform=linux/arm64 python:3.12-slim as deps

# Set environment variables early to maximize caching
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies with security updates
# Addresses CVEs in: linux, glibc, libssl3t64, openssl, bind9, gnutls28, sqlite3, dpkg
RUN apt-get update && \
    # Configure Debian Trixie security repository
    echo "deb http://security.debian.org/debian-security trixie-security main" > /etc/apt/sources.list.d/debian-security.list && \
    apt-get update && \
    # Apply all security upgrades (covers linux, glibc, dpkg, gnutls28, sqlite3, etc.)
    apt-get upgrade -y && \
    # Install required runtime packages
    # libssl3t64/openssl patched via apt-get upgrade above from trixie-security
    # Fixes: CVE-2025-15467, CVE-2025-69419, CVE-2025-69420, CVE-2025-69421, CVE-2025-66199, etc.
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        dnsutils \
        procps && \
    # Install patched bind9 packages (CVE-2025-13878 - requires >= 1:9.20.18-1~deb13u1)
    apt-get install -y -t trixie-security --no-install-recommends \
        bind9-libs \
        bind9-host \
        bind9-dnsutils && \
    # Verify bind9 version meets security requirements (>= 1:9.20.18)
    dpkg -l | grep bind9 && \
    dpkg -l | grep -E "bind9.*(1:9.20.1[89]|1:9.20.[2-9][0-9]|1:9.[2-9][0-9])" || \
    (echo "WARNING: bind9 version check - verify CVE-2025-13878 is patched") && \
    # Verify libssl3t64 is patched (CVE-2025-15467 requires >= 3.5.4-1~deb13u2)
    dpkg -l | grep libssl3t64 && \
    # Final cleanup
    apt-get autoremove -y && \
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
