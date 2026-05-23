#!/bin/bash
# Token refresh loop for kiro-cli
# Runs kiro-cli periodically to keep the access token in SQLite fresh.
# The gateway reads the token via KIRO_CLI_DB_FILE.

REFRESH_INTERVAL=${TOKEN_REFRESH_INTERVAL:-1800}  # Default: 30 minutes

# Auto-update kiro-cli on container start
echo "[token-refresh] Checking for kiro-cli updates..."
if curl -fsSL https://cli.kiro.dev/install | bash 2>&1; then
    # Installer puts binary in ~/.local/bin, move to system path
    if [ -f "$HOME/.local/bin/kiro-cli" ]; then
        mv "$HOME/.local/bin/kiro-cli" /usr/local/bin/kiro-cli
        echo "[token-refresh] kiro-cli updated successfully: $(kiro-cli --version 2>/dev/null || echo 'unknown version')"
    fi
else
    echo "[token-refresh] Warning: kiro-cli update failed, using existing version"
fi

echo "[token-refresh] Starting kiro-cli token refresh loop (interval: ${REFRESH_INTERVAL}s)"

while true; do
    echo "[token-refresh] Refreshing kiro-cli token..."
    kiro-cli chat -e "hi" --no-interactive 2>&1 || echo "[token-refresh] Warning: kiro-cli refresh failed (will retry)"
    echo "[token-refresh] Next refresh in ${REFRESH_INTERVAL}s"
    sleep "$REFRESH_INTERVAL"
done
