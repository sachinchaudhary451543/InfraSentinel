FROM python:3.11-slim

# ============================================================================
# OPTIMIZED PRODUCTION DOCKERFILE
# ============================================================================

# Environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FLASK_APP=web/app.py \
    FLASK_ENV=production \
    FLASK_DEBUG=0

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install gunicorn gevent gevent-websocket

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p logs data uploads instance

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/api/v2/health || exit 1

# Run with Gunicorn + Gevent for production
# Use a single worker by default when Redis is unavailable, since Flask-SocketIO
# requires a shared message queue across workers for stable polling/upgrade behavior.
CMD ["sh", "-lc", "gunicorn -k geventwebsocket.gunicorn.workers.GeventWebSocketWorker -w ${GUNICORN_WORKERS:-1} -b 0.0.0.0:8080 --access-logfile - --error-logfile - --log-level info --timeout 120 --graceful-timeout 30 --keep-alive 10 --max-requests 1000 --max-requests-jitter 50 web.app:app"]
