"""
Deterministic response packaging for Mock LLM.

Provides high-entropy, unambiguous response formatting that:
1. Cannot be confused with user commands ($recall, $memorize, etc.)
2. Is easily parseable by QA tests
3. Contains structured payload data for validation

Format: CIRIS_MOCK_<ACTION>:<base64_json_payload>

Example:
    CIRIS_MOCK_MEMORIZE:eyJzdGF0dXMiOiAic3VjY2VzcyIsICJub2RlX2lkIjogInRlc3QifQ==

This decodes to: {"status": "success", "node_id": "test"}
"""

import base64
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Prefix that is high-entropy and won't be confused with commands
RESPONSE_PREFIX = "CIRIS_MOCK_"


@dataclass
class MockLLMResponse:
    """Structured response from Mock LLM handler actions."""

    action: str  # e.g., "MEMORIZE", "RECALL", "SPEAK", "TASK_COMPLETE"
    status: str  # e.g., "success", "error", "not_found"
    payload: Dict[str, Any] = field(default_factory=dict)
    message: str = ""  # Human-readable summary


def encode_response(
    action: str,
    status: str = "success",
    payload: Optional[Dict[str, Any]] = None,
    message: str = "",
) -> str:
    """Encode a mock LLM response with deterministic, high-entropy format.

    Args:
        action: The handler action type (MEMORIZE, RECALL, SPEAK, etc.)
        status: Status of the action (success, error, not_found)
        payload: Structured data from the action
        message: Human-readable summary

    Returns:
        Encoded string in format: CIRIS_MOCK_<ACTION>:<base64_payload>
    """
    data = {
        "status": status,
        "payload": payload or {},
        "message": message,
    }

    json_str = json.dumps(data, sort_keys=True)
    b64_payload = base64.b64encode(json_str.encode("utf-8")).decode("ascii")

    encoded = f"{RESPONSE_PREFIX}{action.upper()}:{b64_payload}"
    logger.debug(f"[MOCK_RESPONSE] Encoded: {action} -> {encoded[:80]}...")
    return encoded


def decode_response(content: str) -> Optional[MockLLMResponse]:
    """Decode a mock LLM response from encoded format.

    Args:
        content: The response content to decode

    Returns:
        MockLLMResponse if valid encoded response, None otherwise
    """
    if not content or not content.startswith(RESPONSE_PREFIX):
        return None

    try:
        # Extract action and payload
        # Format: CIRIS_MOCK_<ACTION>:<base64>
        rest = content[len(RESPONSE_PREFIX) :]
        if ":" not in rest:
            return None

        action, b64_payload = rest.split(":", 1)

        # Decode base64
        json_str = base64.b64decode(b64_payload.encode("ascii")).decode("utf-8")
        data = json.loads(json_str)

        return MockLLMResponse(
            action=action.upper(),
            status=data.get("status", "unknown"),
            payload=data.get("payload", {}),
            message=data.get("message", ""),
        )

    except Exception as e:
        logger.debug(f"[MOCK_RESPONSE] Failed to decode: {e}")
        return None


def is_encoded_response(content: str) -> bool:
    """Check if content is an encoded mock LLM response."""
    return content.startswith(RESPONSE_PREFIX) if content else False


# Convenience functions for common response types


def memorize_success(node_id: str, scope: str = "LOCAL", **extra: Any) -> str:
    """Create a successful MEMORIZE response."""
    return encode_response(
        action="MEMORIZE",
        status="success",
        payload={"node_id": node_id, "scope": scope, **extra},
        message=f"Stored observation '{node_id}' in {scope} scope",
    )


def memorize_error(reason: str, **extra: Any) -> str:
    """Create an error MEMORIZE response."""
    return encode_response(
        action="MEMORIZE",
        status="error",
        payload={"reason": reason, **extra},
        message=f"Failed to memorize: {reason}",
    )


def recall_success(
    query: str,
    results: Optional[list] = None,
    value: Optional[str] = None,
    **extra: Any,
) -> str:
    """Create a successful RECALL response."""
    payload: Dict[str, Any] = {"query": query, **extra}
    if results is not None:
        payload["results"] = results
        payload["count"] = len(results)
    if value is not None:
        payload["value"] = value

    return encode_response(
        action="RECALL",
        status="success",
        payload=payload,
        message=f"Found {len(results) if results else 0} results for '{query}'",
    )


def recall_not_found(query: str, **extra: Any) -> str:
    """Create a not-found RECALL response."""
    return encode_response(
        action="RECALL",
        status="not_found",
        payload={"query": query, **extra},
        message=f"No results found for '{query}'",
    )


def forget_success(node_id: str, reason: str = "", **extra: Any) -> str:
    """Create a successful FORGET response."""
    return encode_response(
        action="FORGET",
        status="success",
        payload={"node_id": node_id, "reason": reason, **extra},
        message=f"Forgot '{node_id}'",
    )


def speak_success(content: str, channel: str = "", **extra: Any) -> str:
    """Create a successful SPEAK response."""
    return encode_response(
        action="SPEAK",
        status="success",
        payload={"content": content, "channel": channel, **extra},
        message="Message delivered",
    )


def tool_success(name: str, result: Any = None, **extra: Any) -> str:
    """Create a successful TOOL response."""
    return encode_response(
        action="TOOL",
        status="success",
        payload={"tool_name": name, "result": result, **extra},
        message=f"Tool '{name}' executed successfully",
    )


def observe_success(channel: str, message_count: int = 0, **extra: Any) -> str:
    """Create a successful OBSERVE response."""
    return encode_response(
        action="OBSERVE",
        status="success",
        payload={"channel": channel, "message_count": message_count, **extra},
        message=f"Observed {message_count} messages from '{channel}'",
    )


def ponder_success(questions: list, insights: str = "", **extra: Any) -> str:
    """Create a successful PONDER response."""
    return encode_response(
        action="PONDER",
        status="success",
        payload={"questions": questions, "insights": insights, **extra},
        message="Pondering complete",
    )


def defer_success(reason: str, **extra: Any) -> str:
    """Create a successful DEFER response."""
    return encode_response(
        action="DEFER",
        status="success",
        payload={"reason": reason, **extra},
        message=f"Deferred: {reason}",
    )


def reject_success(reason: str, **extra: Any) -> str:
    """Create a successful REJECT response."""
    return encode_response(
        action="REJECT",
        status="success",
        payload={"reason": reason, **extra},
        message=f"Rejected: {reason}",
    )


def task_complete_success(reason: str = "Task completed", **extra: Any) -> str:
    """Create a successful TASK_COMPLETE response."""
    return encode_response(
        action="TASK_COMPLETE",
        status="success",
        payload={"completion_reason": reason, **extra},
        message=reason,
    )
