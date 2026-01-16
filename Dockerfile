FROM python:3.11-slim

WORKDIR /app

# Install kiro-cli for token refresh
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl unzip supervisor && \
    rm -rf /var/lib/apt/lists/* && \
    curl -fsSL https://cli.kiro.dev/install | bash && \
    mv /root/.local/bin/kiro-cli /usr/local/bin/

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x docker/token-refresh.sh

# Create empty .env (config comes from environment variables)
RUN touch /app/.env

COPY docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

ENV KIRO_CLI_DB_FILE=/data/kiro-cli/data.sqlite3
ENV USE_KIRO_CLI_TOKEN=true

EXPOSE 8000

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
