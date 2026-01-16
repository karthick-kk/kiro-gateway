# -*- coding: utf-8 -*-
"""
Q Developer API client using AWS JSON protocol.

This module provides the interface to Amazon Q Developer API which uses:
- AWS JSON 1.0 protocol with x-amz-target headers
- Two distinct streaming services:
  1. AmazonCodeWhispererStreamingService.GenerateAssistantResponse (CodeWhisperer)
  2. Q Developer SendMessage operation (amzn_qdeveloper_streaming_client)
- Bearer token authentication (httpBearerAuth)

Endpoints:
- https://q.us-east-1.amazonaws.com (us-east-1)
- https://q.eu-central-1.amazonaws.com (eu-central-1)
"""

import uuid
from typing import Any, Dict, List, Optional

from loguru import logger

# AWS service targets for Q Developer API
# CodeWhisperer Streaming Service (for GenerateAssistantResponse)
Q_SERVICE_GENERATE_ASSISTANT = "AmazonCodeWhispererStreamingService.GenerateAssistantResponse"
Q_SERVICE_INVOKE_MCP = "AmazonCodeWhispererStreamingService.InvokeMCP"

# CodeWhisperer Runtime Service (non-streaming operations)
Q_SERVICE_LIST_PROFILES = "AmazonCodeWhispererService.ListAvailableProfiles"
Q_SERVICE_LIST_MODELS = "AmazonCodeWhispererService.ListAvailableModels"
Q_SERVICE_GET_PROFILE = "AmazonCodeWhispererService.GetProfile"
Q_SERVICE_GET_USAGE_LIMITS = "AmazonCodeWhispererService.GetUsageLimits"
Q_SERVICE_SEND_TELEMETRY = "AmazonCodeWhispererService.SendTelemetryEvent"
Q_SERVICE_CREATE_SUBSCRIPTION = "AmazonCodeWhispererService.CreateSubscriptionToken"


def get_q_api_headers(token: str, target: str) -> dict:
    """
    Build headers for Q Developer API request.
    
    Args:
        token: Bearer access token
        target: AWS service target (e.g., AmazonCodeWhispererStreamingService.GenerateAssistantResponse)
    
    Returns:
        Headers dict for AWS JSON protocol request
    """
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/x-amz-json-1.0",
        "x-amz-target": target,
        "x-amzn-codewhisperer-optout": "false",
        "User-Agent": "AmazonQ-For-CLI/1.23.1",
        "amz-sdk-invocation-id": str(uuid.uuid4()),
        "amz-sdk-request": "attempt=1; max=3",
    }


def build_conversation_state(
    messages: List[Dict[str, Any]],
    model_id: str,
    conversation_id: Optional[str] = None,
    profile_arn: Optional[str] = None,
    chat_trigger_type: str = "MANUAL",
) -> Dict[str, Any]:
    """
    Build ConversationState for GenerateAssistantResponse operation.
    
    This is the format used by AmazonCodeWhispererStreamingService.GenerateAssistantResponse.
    
    Args:
        messages: List of chat messages in OpenAI format
        model_id: Model ID (e.g., "claude-sonnet-4-5")
        conversation_id: Optional conversation ID for multi-turn
        profile_arn: Optional AWS profile ARN
        chat_trigger_type: Trigger type (MANUAL, DIAGNOSTIC, etc.)
    
    Returns:
        ConversationState payload for GenerateAssistantResponse
    """
    # Convert messages to history format
    history = []
    current_message = None
    
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        
        # Handle content that might be a list (for vision/multimodal)
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text_parts.append(part.get("text", ""))
            content = "\n".join(text_parts)
        
        if role == "system":
            # System messages go into the first user message or as context
            continue
        elif role == "user":
            current_message = {
                "content": content,
                "userInputMessageContext": {
                    "userSettings": {
                        "hasConsentedToCrossRegionCalls": True
                    }
                }
            }
        elif role == "assistant":
            if current_message:
                history.append({
                    "userInputMessage": current_message,
                    "assistantResponseMessage": {
                        "content": content
                    }
                })
                current_message = None
    
    # Build the conversation state
    conversation_state: Dict[str, Any] = {
        "chatTriggerType": chat_trigger_type,
    }
    
    # Add conversation ID if provided
    if conversation_id:
        conversation_state["conversationId"] = conversation_id
    
    # Add history if we have any
    if history:
        conversation_state["history"] = history
    
    # Add current message (the latest user message)
    if current_message:
        conversation_state["currentMessage"] = current_message
    elif messages:
        # Use the last user message
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, list):
                    text_parts = []
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            text_parts.append(part.get("text", ""))
                    content = "\n".join(text_parts)
                
                conversation_state["currentMessage"] = {
                    "content": content,
                    "userInputMessageContext": {
                        "userSettings": {
                            "hasConsentedToCrossRegionCalls": True
                        }
                    }
                }
                break
    
    return conversation_state


def build_generate_assistant_request(
    messages: List[Dict[str, Any]],
    model_id: str,
    conversation_id: Optional[str] = None,
    profile_arn: Optional[str] = None,
    agent_mode: bool = False,
    tools: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Build request payload for GenerateAssistantResponse operation.
    
    This is the main chat operation for Q Developer API using the
    AmazonCodeWhispererStreamingService.
    
    Args:
        messages: List of chat messages in OpenAI format
        model_id: Model ID (e.g., "claude-sonnet-4-5")
        conversation_id: Optional conversation ID for multi-turn
        profile_arn: Optional AWS profile ARN
        agent_mode: Whether to enable agent mode
        tools: Optional list of tools for function calling
    
    Returns:
        Request payload for GenerateAssistantResponse
    """
    request: Dict[str, Any] = {
        "conversationState": build_conversation_state(
            messages=messages,
            model_id=model_id,
            conversation_id=conversation_id,
            profile_arn=profile_arn,
        )
    }
    
    # Add agent mode if enabled
    if agent_mode:
        request["agentMode"] = True
    
    # Add tools if provided
    if tools:
        tool_specs = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool.get("function", {})
                tool_specs.append({
                    "name": func.get("name", ""),
                    "description": func.get("description", ""),
                    "inputSchema": func.get("parameters", {})
                })
        
        if tool_specs:
            request["conversationState"]["currentMessage"]["userInputMessageContext"]["tools"] = tool_specs
    
    return request


def build_user_input_message(
    content: str,
    user_intent: Optional[str] = None,
    editor_state: Optional[Dict[str, Any]] = None,
    shell_state: Optional[Dict[str, Any]] = None,
    env_state: Optional[Dict[str, Any]] = None,
    tool_results: Optional[List[Dict[str, Any]]] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Build UserInputMessage for Q Developer SendMessage operation.
    
    This is the format used by the Q Developer streaming client (amzn_qdeveloper_streaming_client).
    
    Args:
        content: User message content
        user_intent: Optional user intent
        editor_state: Optional editor state
        shell_state: Optional shell state
        env_state: Optional environment state
        tool_results: Optional tool results from previous tool calls
        tools: Optional list of available tools
    
    Returns:
        UserInputMessage payload
    """
    message: Dict[str, Any] = {
        "content": content,
    }
    
    # Build user input message context
    context: Dict[str, Any] = {
        "userSettings": {
            "hasConsentedToCrossRegionCalls": True
        }
    }
    
    if editor_state:
        context["editorState"] = editor_state
    
    if shell_state:
        context["shellState"] = shell_state
    
    if env_state:
        context["envState"] = env_state
    
    if tool_results:
        context["toolResults"] = tool_results
    
    if tools:
        context["tools"] = tools
    
    message["userInputMessageContext"] = context
    
    if user_intent:
        message["userIntent"] = user_intent
    
    return message


def build_list_models_request(
    max_results: int = 100,
    model_provider: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build request payload for ListAvailableModels operation.
    
    Args:
        max_results: Maximum number of models to return
        model_provider: Optional model provider filter
    
    Returns:
        Request payload for ListAvailableModels
    """
    request: Dict[str, Any] = {
        "maxResults": max_results
    }
    
    if model_provider:
        request["modelProvider"] = model_provider
    
    return request


def build_list_profiles_request(max_results: int = 100) -> Dict[str, Any]:
    """
    Build request payload for ListAvailableProfiles operation.
    
    Args:
        max_results: Maximum number of profiles to return
    
    Returns:
        Request payload for ListAvailableProfiles
    """
    return {
        "maxResults": max_results
    }


def build_get_usage_limits_request(
    origin: str = "CLI",
    resource_type: str = "AGENTIC_REQUEST",
) -> Dict[str, Any]:
    """
    Build request payload for GetUsageLimits operation.
    
    Args:
        origin: Origin of the request (CLI, IDE, etc.)
        resource_type: Type of resource to get limits for
    
    Returns:
        Request payload for GetUsageLimits
    """
    return {
        "origin": origin,
        "resourceType": resource_type,
    }


def parse_assistant_response_event(event_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse an event from the GenerateAssistantResponse stream.
    
    Event types:
    - AssistantResponseMessage: Main response content
    - ToolUseEvent: Tool call request
    - MetadataEvent: Token usage and metadata
    - CodeEvent: Code block
    - FollowupPromptEvent: Suggested follow-up
    - IntentsEvent: Detected intents
    - InvalidStateEvent: Error state
    - SupplementaryWebLinksEvent: Reference links
    
    Args:
        event_data: Raw event data from stream
    
    Returns:
        Parsed event with type and content
    """
    # Check for different event types
    if "assistantResponseMessage" in event_data:
        msg = event_data["assistantResponseMessage"]
        return {
            "type": "message",
            "message_id": msg.get("messageId", ""),
            "content": msg.get("content", ""),
            "tool_uses": msg.get("toolUses", []),
            "references": msg.get("references", []),
            "followup_prompt": msg.get("followupPrompt"),
            "cache_point": msg.get("cachePoint"),
            "reasoning_content": msg.get("reasoningContent"),
        }
    
    if "toolUseEvent" in event_data:
        tool = event_data["toolUseEvent"]
        return {
            "type": "tool_use",
            "tool_use_id": tool.get("toolUseId", ""),
            "name": tool.get("name", ""),
            "input": tool.get("input", {}),
        }
    
    if "metadataEvent" in event_data or "meteringEvent" in event_data:
        meta = event_data.get("metadataEvent") or event_data.get("meteringEvent", {})
        return {
            "type": "metadata",
            "conversation_id": meta.get("conversationId"),
            "utterance_id": meta.get("utteranceId"),
            "total_tokens": meta.get("totalTokens"),
            "input_tokens": meta.get("uncachedInputTokens"),
            "output_tokens": meta.get("outputTokens"),
            "cache_read_tokens": meta.get("cacheReadInputTokens"),
            "cache_write_tokens": meta.get("cacheWriteInputTokens"),
        }
    
    if "codeEvent" in event_data:
        code = event_data["codeEvent"]
        return {
            "type": "code",
            "content": code.get("content", ""),
        }
    
    if "followupPromptEvent" in event_data:
        followup = event_data["followupPromptEvent"]
        return {
            "type": "followup",
            "content": followup.get("content", ""),
        }
    
    if "intentsEvent" in event_data:
        intents = event_data["intentsEvent"]
        return {
            "type": "intents",
            "intents": intents.get("intents", []),
        }
    
    if "invalidStateEvent" in event_data:
        error = event_data["invalidStateEvent"]
        return {
            "type": "error",
            "reason": error.get("reason", "Unknown error"),
        }
    
    if "supplementaryWebLinksEvent" in event_data:
        links = event_data["supplementaryWebLinksEvent"]
        return {
            "type": "web_links",
            "links": links.get("supplementaryWebLinks", []),
        }
    
    # Unknown event type
    return {
        "type": "unknown",
        "data": event_data,
    }


def parse_list_models_response(response_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Parse response from ListAvailableModels operation.
    
    Args:
        response_data: Raw response from API
    
    Returns:
        List of available models
    """
    models = response_data.get("models", [])
    default_model = response_data.get("defaultModel")
    
    result = []
    for model in models:
        result.append({
            "id": model.get("modelName", ""),
            "name": model.get("modelName", ""),
            "context_window": model.get("contextWindowTokens"),
            "rate_multiplier": model.get("rateMultiplier"),
            "rate_unit": model.get("rateUnit"),
            "token_limits": model.get("tokenLimits", {}),
            "supported_input_types": model.get("supportedInputTypes", []),
            "supports_prompt_cache": model.get("supportsPromptCache", False),
            "is_default": model.get("modelName") == default_model,
        })
    
    return result


def parse_list_profiles_response(response_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Parse response from ListAvailableProfiles operation.
    
    Args:
        response_data: Raw response from API
    
    Returns:
        List of available profiles
    """
    return response_data.get("profiles", [])


def parse_usage_limits_response(response_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse response from GetUsageLimits operation.
    
    Args:
        response_data: Raw response from API
    
    Returns:
        Usage limits information
    """
    return {
        "limits": response_data.get("limits", {}),
        "next_date_reset": response_data.get("nextDateReset"),
        "usage_breakdown": response_data.get("usageBreakdown", []),
        "usage_breakdown_list": response_data.get("usageBreakdownList", []),
        "subscription_info": response_data.get("subscriptionInfo", {}),
        "overage_configuration": response_data.get("overageConfiguration", {}),
        "user_info": response_data.get("userInfo", {}),
    }
