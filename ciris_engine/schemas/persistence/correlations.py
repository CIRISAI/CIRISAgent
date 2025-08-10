"""
Schemas for correlation data to ensure type safety.

This module defines Pydantic models for correlation data structures,
replacing Dict[str, Any] usage for better type safety and validation.
"""

from datetime import datetime
from typing import Any, Dict, Optional, Union

from pydantic import BaseModel, Field


class CorrelationRequestData(BaseModel):
    """Schema for correlation request data."""

    channel_id: Optional[str] = Field(None, description="Channel identifier")
    author_id: Optional[str] = Field(None, description="Author identifier")
    author_name: Optional[str] = Field(None, description="Author display name")
    content: Optional[str] = Field(None, description="Message content")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Additional parameters")
    headers: Dict[str, str] = Field(default_factory=dict, description="Request headers")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Request metadata")


class CorrelationResponseData(BaseModel):
    """Schema for correlation response data."""

    response_timestamp: str = Field(..., description="ISO timestamp of response")
    execution_time_ms: Optional[float] = Field(None, description="Execution time in milliseconds")
    success: bool = Field(True, description="Whether the operation succeeded")
    error: Optional[str] = Field(None, description="Error message if failed")
    error_type: Optional[str] = Field(None, description="Type of error")
    result: Optional[Any] = Field(None, description="Operation result")
    resource_usage: Dict[str, float] = Field(default_factory=dict, description="Resource metrics")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Response metadata")


class ChannelInfo(BaseModel):
    """Schema for channel information."""

    channel_id: str = Field(..., description="Unique channel identifier")
    channel_type: str = Field(..., description="Adapter type (discord, api, cli)")
    last_activity: datetime = Field(..., description="Last activity timestamp")
    message_count: int = Field(0, description="Number of messages")
    is_active: bool = Field(True, description="Whether channel is active")

    # Optional fields for enriched channel info
    channel_name: Optional[str] = Field(None, description="Human-readable channel name")
    participants: Optional[int] = Field(None, description="Number of participants")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional channel metadata")


class ConversationSummaryData(BaseModel):
    """Schema for conversation summary from TSDB consolidation."""

    channel_id: str = Field(..., description="Channel identifier")
    period_start: datetime = Field(..., description="Period start time")
    period_end: datetime = Field(..., description="Period end time")
    message_count: int = Field(0, description="Messages in period")
    unique_users: int = Field(0, description="Unique users in period")
    summary: Optional[str] = Field(None, description="Conversation summary")
    key_topics: list[str] = Field(default_factory=list, description="Key topics discussed")
