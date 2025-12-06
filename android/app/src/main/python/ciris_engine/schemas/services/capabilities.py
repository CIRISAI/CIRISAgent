"""
Service capability enums for CIRIS Engine.

MISSION CRITICAL: These enums define the ONLY capabilities that services can advertise.
Each capability MUST map to an @abstractmethod in the corresponding service protocol.
"""

from enum import Enum


class LLMCapabilities(str, Enum):
    """Core capabilities for LLM services - maps to LLMService protocol"""

    CALL_LLM_STRUCTURED = "call_llm_structured"


class AuditCapabilities(str, Enum):
    """Core capabilities for Audit services - maps to AuditService protocol"""

    LOG_EVENT = "log_event"
    GET_AUDIT_TRAIL = "get_audit_trail"


class CommunicationCapabilities(str, Enum):
    """Core capabilities for Communication services - maps to CommunicationService protocol"""

    SEND_MESSAGE = "send_message"
    FETCH_MESSAGES = "fetch_messages"


class WiseAuthorityCapabilities(str, Enum):
    """Core capabilities for Wise Authority services - maps to WiseAuthorityService protocol"""

    FETCH_GUIDANCE = "fetch_guidance"
    SEND_DEFERRAL = "send_deferral"


class MemoryCapabilities(str, Enum):
    """Core capabilities for Memory services - maps to MemoryService protocol"""

    MEMORIZE = "memorize"
    RECALL = "recall"
    FORGET = "forget"


class ToolCapabilities(str, Enum):
    """Core capabilities for Tool services - maps to ToolService protocol"""

    EXECUTE_TOOL = "execute_tool"
    GET_AVAILABLE_TOOLS = "get_available_tools"
    GET_TOOL_RESULT = "get_tool_result"


class TelemetryCapabilities(str, Enum):
    """Core capabilities for Telemetry services - maps to TelemetryService protocol"""

    RECORD_METRIC = "record_metric"
    RECORD_RESOURCE_USAGE = "record_resource_usage"
    QUERY_METRICS = "query_metrics"
    GET_SERVICE_STATUS = "get_service_status"
    GET_RESOURCE_LIMITS = "get_resource_limits"


__all__ = [
    "LLMCapabilities",
    "AuditCapabilities",
    "CommunicationCapabilities",
    "WiseAuthorityCapabilities",
    "MemoryCapabilities",
    "ToolCapabilities",
    "TelemetryCapabilities",
]
