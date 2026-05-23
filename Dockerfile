# Kiro Gateway - Docker Image
# Optimized single-stage build with kiro-cli token refresh

FROM python:3.10-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies (supervisor for process management, curl for kiro-cli install)
RUN apt-get update && \
    apt-get install -y --no-install-recommends supervisor curl unzip && \
    rm -rf /var/lib/apt/lists/*

# Install kiro-cli
RUN curl -fsSL https://cli.kiro.dev/install | bash && \
    mv /root/.local/bin/kiro-cli /usr/local/bin/

# Create non-root user for security
RUN groupadd -r kiro && useradd -r -g kiro -m kiro

# Set working directory
WORKDIR /app

# Install dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=kiro:kiro . .

# Remove runtime files that should not be in image
RUN rm -f credentials.json state.json

# Create directories with proper permissions
RUN mkdir -p debug_logs /data/kiro-cli /var/log/supervisor && \
    chown -R kiro:kiro debug_logs /data/kiro-cli && \
    chmod +x docker/token-refresh.sh

# Copy supervisord config
COPY docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# kiro-cli SQLite database path (populated by mounted volume or token-refresh)
ENV KIRO_CLI_DB_FILE=/data/kiro-cli/data.sqlite3

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health', timeout=5)"

# Run via supervisord (manages both gateway and token-refresh)
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
