# syntax=docker/dockerfile:1.4
# Dockerfile — clarity-retail-hub
# Multi-tenant cloud management platform for Clarity Retail

FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies (libpq for postgres, curl for healthchecks, netcat for db readiness)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq5 \
    libpq-dev \
    curl \
    netcat-traditional \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install python dependencies with caching
COPY requirements-docker.txt requirements.txt /app/
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install --timeout=120 --retries=5 -r requirements-docker.txt

# Copy application code
COPY . /app/

# Ensure runtime directories exist
RUN mkdir -p /app/logs /app/media /app/staticfiles /app/tmp /app/data

# BUILD_HASH injected by CI build (commit SHA)
ARG BUILD_HASH=unknown
ENV APP_BUILD_HASH=${BUILD_HASH}

ENV DJANGO_SETTINGS_MODULE=retail_hub.settings_prod
ENV DEBUG=False

# Normalize entrypoint line endings and make executable
RUN sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh

EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8000/ || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]

# Default command: Gunicorn WSGI Server (workers dynamically set by entrypoint.sh)
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--timeout", "120", "retail_hub.wsgi:application"]
