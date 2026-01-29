# AL2023-based Dockerfile for Generic Agent Instance
# Leverages automatic security updates and simplified maintenance

# Stage 1: Base with Python runtime from AL2023
FROM amazonlinux:2023 as base

# Install Python 3.11 (AL2023 default) and system dependencies
RUN dnf update -y && \
    dnf install -y \
        python3.11 \
        python3.11-pip \
        python3.11-devel \
        git \
        ca-certificates \
        procps-ng \
        shadow-utils \
        && \
    dnf clean all && \
    # Create non-root user
    useradd -m -u 1000 appuser

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app:/app/common

WORKDIR /app

# Upgrade pip and install build tools
RUN python3.11 -m pip install --upgrade pip setuptools wheel

# Stage 2: Development build
FROM base as development

# Install Python dependencies from agent-instance requirements only
# (already includes all needed dependencies)
COPY multi-agent/agent-instance/requirements.txt .
RUN python3.11 -m pip install -r requirements.txt

# Copy application files
COPY --chown=appuser:appuser multi-agent/agent-instance/ ./
COPY --chown=appuser:appuser common/ ./common/

USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

CMD ["python3.11", "-u", "agent.py"]

# Stage 3: Production build
FROM base as production

# Install Python dependencies from agent-instance requirements only
# (already includes all needed dependencies)
COPY multi-agent/agent-instance/requirements.txt .
RUN python3.11 -m pip install -r requirements.txt

# Copy application files (production optimized)
COPY --chown=appuser:appuser multi-agent/agent-instance/agent.py ./
COPY --chown=appuser:appuser common/ ./common/

# Set production environment
ENV RELOAD=false

USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

CMD ["python3.11", "-u", "agent.py"]
