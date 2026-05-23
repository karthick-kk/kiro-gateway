#!/usr/bin/env python3
"""Generate opencode.json config from kiro-gateway models.

Fetches available models from the gateway and generates an opencode-compatible
configuration file using the @ai-sdk/openai-compatible provider.

Usage:
    python3 scripts/generate_opencode_config.py [GATEWAY_URL] [API_KEY]

Examples:
    python3 scripts/generate_opencode_config.py
    python3 scripts/generate_opencode_config.py http://localhost:8000 my-api-key
    python3 scripts/generate_opencode_config.py > ~/.config/opencode/opencode.json
"""
import json
import os
import sys

import httpx

GATEWAY_URL = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("GATEWAY_URL", "http://localhost:8000")
API_KEY = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("PROXY_API_KEY", "my-super-secret-password-123")

# Fetch models from gateway (auth required)
headers = {"Authorization": f"Bearer {API_KEY}"}
resp = httpx.get(f"{GATEWAY_URL}/v1/models", headers=headers, timeout=10)
resp.raise_for_status()
models = {m["id"]: m for m in resp.json()["data"] if m["id"] != "auto"}

# Generate config
config = {
    "$schema": "https://opencode.ai/config.json",
    "provider": {
        "kiro-gateway": {
            "npm": "@ai-sdk/openai-compatible",
            "name": "Kiro Gateway",
            "options": {"baseURL": f"{GATEWAY_URL}/v1", "apiKey": API_KEY},
            "models": {
                model_id: {
                    "name": model_id.replace("-", " ").title(),
                    "modalities": {"input": ["text", "image"], "output": ["text"]},
                }
                for model_id in models
            },
        }
    },
}

print(json.dumps(config, indent=2))
