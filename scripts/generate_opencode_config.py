#!/usr/bin/env python3
"""Generate opencode.json config from kiro-gateway models.

Usage:
    python3 generate_opencode_config.py [GATEWAY_URL] [API_KEY]
    
Examples:
    python3 generate_opencode_config.py > ~/.config/opencode/opencode.json
    python3 generate_opencode_config.py http://localhost:8000 my-api-key > ~/.config/opencode/opencode.json
"""
import json
import os
import sys

import requests

GATEWAY_URL = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("GATEWAY_URL", "http://localhost:8000")
API_KEY = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("PROXY_API_KEY", "your-api-key")

# Fetch models from gateway
resp = requests.get(f"{GATEWAY_URL}/v1/models")
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
