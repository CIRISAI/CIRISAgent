"""
Service request/response schemas for contract-driven architecture.

Replaces Dict[str, Any] in service method calls.
"""

from typing import (
    Dict,
    Any,
    List,
    Optional,
    Type
)
from datetime import datetime, timezone
from uuid import UUID
from pydantic import BaseModel, Field

from .metadata import ServiceMetadata
from ciris_engine.schemas.actions.parameters import MemorizeParams, RecallParams

class ServiceRequest(BaseModel):
    """Base request for all service methods."""
    metadata: ServiceMetadata = Field(..., description="Service call metadata")
    correlation_id: UUID = Field(..., description="Correlation ID for tracing")
    
    class Config:
        extra = "forbid"

class ServiceResponse(BaseModel):
    """Base response from all service methods."""
    success: bool = Field(..., description="Whether the operation succeeded")
    correlation_id: UUID = Field(..., description="Correlation ID for tracing")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Response timestamp")
    error: Optional[str] = Field(None, description="Error message if failed")
    
    class Config:
        extra = "forbid"

# Memory Service specific requests/responses

class MemorizeRequest(ServiceRequest):
    """Request for memory service memorize method."""
    node_data: MemorizeParams = Field(..., description="Memory node data")

class MemorizeResponse(ServiceResponse):
    """Response from memory service memorize method."""
    node_id: str = Field(..., description="ID of the memorized node")
    node_type: str = Field(..., description="Type of the memorized node")

class RecallRequest(ServiceRequest):
    """Request for memory service recall method."""
    query_params: RecallParams = Field(..., description="Recall query parameters")

class RecallResponse(ServiceResponse):
    """Response from memory service recall method."""
    nodes: List[dict] = Field(..., description="Retrieved nodes")  # Would be typed as List[GraphNode]
    count: int = Field(..., ge=0, description="Number of nodes retrieved")

# Tool Service specific requests/responses

class ToolExecutionRequest(ServiceRequest):
    """Request for tool service execution."""
    tool_name: str = Field(..., description="Name of tool to execute")
    tool_args: dict = Field(..., description="Tool arguments")
    timeout: Optional[float] = Field(30.0, description="Execution timeout in seconds")

class ToolExecutionResponse(ServiceResponse):
    """Response from tool service execution."""
    tool_name: str = Field(..., description="Name of tool executed")
    result: Optional[Any] = Field(None, description="Tool execution result")
    execution_time: float = Field(..., description="Execution time in seconds")
    
    
# LLM Service specific requests/responses

class LLMRequest(ServiceRequest):
    """Request for LLM service."""
    prompt: str = Field(..., description="LLM prompt")
    temperature: float = Field(0.7, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: Optional[int] = Field(None, description="Maximum tokens to generate")
    model: Optional[str] = Field(None, description="Model to use")

class LLMResponse(ServiceResponse):
    """Response from LLM service."""
    text: str = Field(..., description="Generated text")
    model_used: str = Field(..., description="Model that was used")
    tokens_used: int = Field(..., description="Number of tokens used")
    
    
# Audit Service specific requests/responses

class AuditRequest(ServiceRequest):
    """Request for audit service."""
    event_type: str = Field(..., description="Type of event to audit")
    event_data: dict = Field(..., description="Event data to audit")
    severity: str = Field("info", description="Event severity level")

class AuditResponse(ServiceResponse):
    """Response from audit service."""
    audit_id: str = Field(..., description="ID of the audit entry")
    stored: bool = Field(..., description="Whether the audit was stored")