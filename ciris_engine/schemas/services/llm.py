"""
LLM Service specific schemas.

Provides typed schemas for LLM service operations.
"""

from datetime import datetime, timezone
from typing import Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class TokenUsageStats(BaseModel):
    """Token usage statistics from LLM API."""

    prompt_tokens: int = Field(0, description="Number of tokens in the prompt")
    completion_tokens: int = Field(0, description="Number of tokens in the completion")
    total_tokens: int = Field(0, description="Total tokens used")

    model_config = ConfigDict(extra="forbid")


class CircuitBreakerStats(BaseModel):
    """Circuit breaker statistics."""

    state: str = Field(..., description="Current state: closed, open, or half-open")
    failure_count: int = Field(..., description="Number of consecutive failures")
    success_count: int = Field(..., description="Number of consecutive successes")
    last_failure: Optional[datetime] = Field(None, description="Timestamp of last failure")
    last_success: Optional[datetime] = Field(None, description="Timestamp of last success")
    call_count: int = Field(0, description="Total number of calls")
    success_rate: float = Field(1.0, description="Success rate (0-1)")


class LLMHealthResponse(BaseModel):
    """Health check response for LLM service."""

    healthy: bool = Field(..., description="Whether service is healthy")
    service_name: str = Field(..., description="Name of the service")
    model_name: str = Field(..., description="Model being used")
    service_type: str = Field(..., description="Type of service (real/mock)")
    status: str = Field(..., description="Status: healthy, degraded, or unhealthy")
    circuit_breaker: Optional[CircuitBreakerStats] = Field(None, description="Circuit breaker stats")
    error_message: Optional[str] = Field(None, description="Error message if unhealthy")
    last_check: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(protected_namespaces=())


class LLMResponse(BaseModel):
    """Standard LLM response structure."""

    content: str = Field(..., description="Response content")
    model: str = Field(..., description="Model that generated response")
    usage: TokenUsageStats = Field(default_factory=TokenUsageStats, description="Token usage stats")
    finish_reason: Optional[str] = Field(None, description="Why generation stopped")

    model_config = ConfigDict(protected_namespaces=())


class ExtractedJSONData(BaseModel):
    """Structured data extracted from LLM JSON response."""

    # Common fields that appear in LLM JSON responses
    message: Optional[str] = Field(None, description="Message content")
    content: Optional[str] = Field(None, description="Content text")
    result: Optional[str] = Field(None, description="Result value")
    status: Optional[str] = Field(None, description="Status indicator")

    model_config = ConfigDict(extra="allow")


class JSONExtractionResult(BaseModel):
    """Result of JSON extraction from LLM response."""

    success: bool = Field(..., description="Whether extraction succeeded")
    data: Optional[ExtractedJSONData] = Field(None, description="Extracted JSON data")
    error: Optional[str] = Field(None, description="Error message if extraction failed")
    raw_content: Optional[str] = Field(None, description="Raw content that failed to parse")


class LLMCallMetadata(BaseModel):
    """Metadata for an LLM call."""

    prompt_tokens: int = Field(0, description="Number of tokens in prompt")
    completion_tokens: int = Field(0, description="Number of tokens in completion")
    total_tokens: int = Field(0, description="Total tokens used")
    model: str = Field(..., description="Model used")
    temperature: float = Field(..., description="Temperature setting")
    max_tokens: int = Field(..., description="Max tokens setting")
    duration_ms: Optional[float] = Field(None, description="Call duration in milliseconds")
    cached: bool = Field(False, description="Whether response was cached")


class TextContentBlock(BaseModel):
    """Text content block for multimodal messages."""

    type: Literal["text"] = "text"
    text: str = Field(..., description="Text content")

    model_config = ConfigDict(extra="forbid")


class ImageURLDetail(BaseModel):
    """Image URL details for multimodal messages."""

    url: str = Field(..., description="Image URL or data URL (data:image/jpeg;base64,...)")
    detail: Optional[Literal["auto", "low", "high"]] = Field(
        default="auto", description="Image detail level for vision processing"
    )

    model_config = ConfigDict(extra="forbid")


class ImageContentBlock(BaseModel):
    """Image content block for multimodal messages."""

    type: Literal["image_url"] = "image_url"
    image_url: ImageURLDetail = Field(..., description="Image URL details")

    model_config = ConfigDict(extra="forbid")


# Union type for content blocks in multimodal messages
ContentBlock = Union[TextContentBlock, ImageContentBlock]


class LLMMessage(BaseModel):
    """
    Message for LLM conversations.

    Supports both simple text content (str) and multimodal content (List[ContentBlock]).
    For text-only messages, use content="text".
    For multimodal messages with images, use content=[TextContentBlock(...), ImageContentBlock(...)].
    """

    role: Literal["system", "user", "assistant"] = Field(..., description="Message role")
    content: str | List[ContentBlock] = Field(
        ..., description="Message content - string for text, list of blocks for multimodal"
    )
    name: Optional[str] = Field(None, description="Optional name for the message sender")

    def is_multimodal(self) -> bool:
        """Check if this message contains multimodal content."""
        return isinstance(self.content, list)

    def get_text_content(self) -> str:
        """Extract text content from the message."""
        if isinstance(self.content, str):
            return self.content
        # Extract text from content blocks
        texts = []
        for block in self.content:
            if isinstance(block, TextContentBlock):
                texts.append(block.text)
        return "\n".join(texts)


class LLMCallParams(BaseModel):
    """Additional parameters for LLM calls."""

    top_p: Optional[float] = Field(None, description="Nucleus sampling parameter")
    frequency_penalty: Optional[float] = Field(None, description="Frequency penalty")
    presence_penalty: Optional[float] = Field(None, description="Presence penalty")
    stop: Optional[List[str]] = Field(None, description="Stop sequences")
    seed: Optional[int] = Field(None, description="Random seed for deterministic output")


class CachedResponseData(BaseModel):
    """Serialized response data for cached LLM responses."""

    content: str = Field(..., description="Response content")
    model: str = Field(..., description="Model used")
    finish_reason: Optional[str] = Field(None, description="Finish reason")

    model_config = ConfigDict(extra="allow")


class CachedLLMResponse(BaseModel):
    """Cached response from LLM service."""

    response_model_name: str = Field(..., description="Name of the response model type")
    response_data: CachedResponseData = Field(..., description="Serialized response data")
    cache_key: str = Field(..., description="Cache key used")
    cached_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: LLMCallMetadata = Field(..., description="Call metadata")
    expires_at: Optional[datetime] = Field(None, description="When cache entry expires")
