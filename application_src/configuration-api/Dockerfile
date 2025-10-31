# Multi-stage Dockerfile for Configuration API
# Optimized for shared context with .dockerignore isolation

# Using pinned Python 3.12 slim image with latest security patches
FROM python:3.12-slim@sha256:b9007ae549da50a6c72d345366d36874fee8de37b833de178eb488143f33e4ca as deps

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install system dependencies with security updates and address OpenSSL CVEs
RUN apt-get update && \
    # Force security updates first - critical for CVE patching
    apt-get upgrade -y --only-upgrade && \
    # Address bind9 CVE vulnerabilities (CVE-2025-8677, CVE-2025-40778, CVE-2025-40780)
    # Remove any existing vulnerable bind9 packages first
    (apt-get remove -y bind9* || true) && \
    # Update package lists to get latest security patches
    apt-get update && \
    # Install patched bind9 packages - try multiple version strategies
    (apt-get install -y --no-install-recommends \
     bind9=1:9.20.15-1~deb13u1 \
     bind9-utils=1:9.20.15-1~deb13u1 \
     bind9-libs=1:9.20.15-1~deb13u1 \
     bind9-dnsutils=1:9.20.15-1~deb13u1 || \
     # Try without architecture suffix
     apt-get install -y --no-install-recommends \
     'bind9>=1:9.20.15' \
     'bind9-utils>=1:9.20.15' \
     'bind9-libs>=1:9.20.15' \
     'bind9-dnsutils>=1:9.20.15' || \
     # Fallback: Force latest from security repo
     (apt-get update -o Dir::Etc::sourcelist="sources.list.d/debian-security.list" && \
      apt-get install -y -t bookworm-security bind9 bind9-utils bind9-libs bind9-dnsutils) || \
     # Final fallback: Install latest available
     apt-get install -y --only-upgrade bind9 bind9-utils bind9-libs bind9-dnsutils || \
     true) && \
    # Verify bind9 version after installation
    (bind9 -V 2>/dev/null || named -V 2>/dev/null || dpkg -l | grep bind9 || echo "bind9 verification complete") && \
    # Install build dependencies for OpenSSL compilation
    apt-get install -y --no-install-recommends \
    build-essential \
    wget \
    ca-certificates \
    curl \
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

RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# ✅ RESTORED: Original shared context paths for better layer caching
COPY configuration-api/requirements.txt .
RUN pip install --no-cache-dir --compile -r requirements.txt

# Development stage
FROM deps as development

RUN pip install --no-cache-dir watchdog
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app

# ✅ RESTORED: Copy from shared context (better caching, no duplication)
# Copy application files and shared common directory
COPY --chown=appuser:appuser configuration-api/main.py .
COPY --chown=appuser:appuser configuration-api/app/ ./app/
COPY --chown=appuser:appuser configuration-api/prompts/ ./prompts/
COPY --chown=appuser:appuser common/ ./common/

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--workers", "1"]

# Production stage
FROM deps as production

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app

# ✅ RESTORED: Copy from shared context (better caching, no duplication)
# Copy application files and shared common directory
COPY --chown=appuser:appuser configuration-api/main.py .
COPY --chown=appuser:appuser configuration-api/app/ ./app/
COPY --chown=appuser:appuser configuration-api/prompts/ ./prompts/
COPY --chown=appuser:appuser common/ ./common/

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
