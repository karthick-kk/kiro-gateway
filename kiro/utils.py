# -*- coding: utf-8 -*-

# Kiro Gateway
# https://github.com/jwadow/kiro-gateway
# Copyright (C) 2025 Jwadow
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
Utility functions for Kiro Gateway.

Contains functions for fingerprint generation, header formatting,
and other common utilities.
"""

import hashlib
import uuid
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from kiro.auth import KiroAuthManager


def get_machine_fingerprint() -> str:
    """
    Generates a unique machine fingerprint based on hostname and username.
    
    Used for User-Agent formation to identify a specific gateway installation.
    
    Returns:
        SHA256 hash of the string "{hostname}-{username}-kiro-gateway"
    """
    try:
        import socket
        import getpass
        
        hostname = socket.gethostname()
        username = getpass.getuser()
        unique_string = f"{hostname}-{username}-kiro-gateway"
        
        return hashlib.sha256(unique_string.encode()).hexdigest()
    except Exception as e:
        logger.warning(f"Failed to get machine fingerprint: {e}")
        return hashlib.sha256(b"default-kiro-gateway").hexdigest()


def get_kiro_headers(auth_manager: "KiroAuthManager", token: str, target: str = None) -> dict:
    """
    Builds headers for Q Developer API requests (AWS JSON protocol).
    
    Args:
        auth_manager: Authentication manager for obtaining fingerprint
        token: Access token for authorization
        target: Optional AWS service target (e.g., "AmazonCodeWhispererStreamingService.GenerateAssistantResponse")
    
    Returns:
        Dictionary with headers for HTTP request
    """
    fingerprint = auth_manager.fingerprint
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/x-amz-json-1.0",
        # Match kiro-cli User-Agent exactly
        "User-Agent": "AmazonQ-For-CLI/1.23.1",
        "x-amz-user-agent": f"aws-sdk-rust/1.0.0 kiro-gateway-{fingerprint[:8]}",
        "x-amzn-codewhisperer-optout": "false",
        "amz-sdk-invocation-id": str(uuid.uuid4()),
        "amz-sdk-request": "attempt=1; max=3",
    }
    
    if target:
        headers["x-amz-target"] = target
    
    return headers


def get_q_api_headers(token: str, target: str) -> dict:
    """
    Builds headers for Q Developer API with x-amz-target.
    
    Args:
        token: Access token for authorization
        target: AWS service target (e.g., "AmazonCodeWhispererService.GenerateCompletions")
    
    Returns:
        Dictionary with headers for AWS JSON protocol request
    """
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/x-amz-json-1.0",
        "x-amz-target": target,
        "User-Agent": "aws-sdk-rust/1.0.0 os/linux lang/rust md/kiro-cli",
        "amz-sdk-invocation-id": str(uuid.uuid4()),
        "amz-sdk-request": "attempt=1; max=3",
    }


def generate_completion_id() -> str:
    """
    Generates a unique ID for chat completion.
    
    Returns:
        ID in format "chatcmpl-{uuid_hex}"
    """
    return f"chatcmpl-{uuid.uuid4().hex}"


def generate_conversation_id() -> str:
    """
    Generates a unique ID for conversation.
    
    Returns:
        UUID in string format
    """
    return str(uuid.uuid4())


def generate_tool_call_id() -> str:
    """
    Generates a unique ID for tool call.
    
    Returns:
        ID in format "call_{uuid_hex[:8]}"
    """
    return f"call_{uuid.uuid4().hex[:8]}"