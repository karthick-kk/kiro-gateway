#!/bin/bash
# Token refresh loop - keeps kiro-cli token fresh
# Runs a minimal kiro-cli command every 30 minutes to trigger token refresh

while true; do
    echo "[$(date)] Refreshing kiro-cli token..."
    # Run a simple command that requires auth - this triggers token refresh
    timeout 30 kiro-cli chat -e "hi" --no-interactive 2>/dev/null || true
    echo "[$(date)] Token refresh complete, sleeping 30 minutes..."
    sleep 1800  # 30 minutes
done
