# AL2023-based Dockerfile for Configuration API
# Leverages automatic security updates and simplified maintenance

# Stage 1: Base with Python runtime from AL2023
FROM amazonlinux:2023 as base

# Install Python 3.11 (AL2023 default) and system dependencies
RUN dnf update -y && \
    dnf install -y \
        python3.11 \
        python3.11-pip \
        python3.11-devel \
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
    PYTHONPATH=/app

WORKDIR /app

# Upgrade pip and install build tools
RUN python3.11 -m pip install --upgrade pip setuptools wheel

# Stage 2: Development build
FROM base as development

# Install Python dependencies including dev tools
COPY configuration-api/requirements.txt .
RUN python3.11 -m pip install -r requirements.txt && \
    python3.11 -m pip install watchdog

# Copy application files
COPY --chown=appuser:appuser configuration-api/main.py .
COPY --chown=appuser:appuser configuration-api/app/ ./app/
COPY --chown=appuser:appuser configuration-api/prompts/ ./prompts/
COPY --chown=appuser:appuser common/ ./common/

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--workers", "1"]

# Stage 3: Production build
FROM base as production

# Install Python dependencies
COPY configuration-api/requirements.txt .
RUN python3.11 -m pip install -r requirements.txt

# Copy application files
COPY --chown=appuser:appuser configuration-api/main.py .
COPY --chown=appuser:appuser configuration-api/app/ ./app/
COPY --chown=appuser:appuser configuration-api/prompts/ ./prompts/
COPY --chown=appuser:appuser common/ ./common/

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
