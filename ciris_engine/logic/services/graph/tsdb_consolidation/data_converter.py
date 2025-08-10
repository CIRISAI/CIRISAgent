"""
Data converter for TSDB consolidation.

Converts raw database rows (represented as typed models or dicts) to typed Pydantic schemas.
The converter accepts both dictionary inputs (for backward compatibility) and typed RawData models.
"""

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator

from ciris_engine.schemas.services.graph.consolidation import (
    InteractionContext,
    MetricCorrelationData,
    RequestData,
    ResponseData,
    ServiceInteractionData,
    SpanTags,
    TaskCorrelationData,
    TaskMetadata,
    ThoughtSummary,
    TraceSpanData,
)

logger = logging.getLogger(__name__)


class RateLimitedLogger:
    """Logger that suppresses repetitive warnings."""

    def __init__(self, logger, max_warnings_per_type=5, reset_interval_seconds=3600):
        self.logger = logger
        self.max_warnings = max_warnings_per_type
        self.reset_interval = reset_interval_seconds
        self.warning_counts = defaultdict(int)
        self.last_reset = datetime.now(timezone.utc)
        self.suppressed_counts = defaultdict(int)

    def should_log(self, error_key: str) -> bool:
        """Check if we should log this error or suppress it."""
        now = datetime.now(timezone.utc)

        # Reset counts if interval has passed
        if (now - self.last_reset).total_seconds() > self.reset_interval:
            if self.suppressed_counts:
                # Log summary of suppressed warnings
                for key, count in self.suppressed_counts.items():
                    if count > 0:
                        self.logger.info(f"Suppressed {count} additional occurrences of: {key}")

            self.warning_counts.clear()
            self.suppressed_counts.clear()
            self.last_reset = now

        # Check if we should log
        if self.warning_counts[error_key] < self.max_warnings:
            self.warning_counts[error_key] += 1
            return True
        else:
            self.suppressed_counts[error_key] += 1
            return False

    def warning(self, message: str, error_key: Optional[str] = None):
        """Log a warning with rate limiting."""
        if error_key is None:
            error_key = message[:100]  # Use first 100 chars as key

        if self.should_log(error_key):
            if self.warning_counts[error_key] == self.max_warnings:
                self.logger.warning(f"{message} (Further occurrences will be suppressed)")
            else:
                self.logger.warning(message)


# Create rate-limited logger instance
rate_limited_logger = RateLimitedLogger(logger)


# Raw data models representing database rows
class RawCorrelationData(BaseModel):
    """Raw correlation data from database row."""

    correlation_id: str
    correlation_type: str
    service_type: str
    action_type: str
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    parent_span_id: Optional[str] = None
    timestamp: datetime
    request_data: Optional[Dict[str, Union[str, int, float, bool, list, dict, None]]] = Field(default_factory=dict)
    response_data: Optional[Dict[str, Union[str, int, float, bool, list, dict, None]]] = Field(default_factory=dict)
    tags: Optional[Dict[str, Union[str, int, float, bool]]] = Field(default_factory=dict)
    context: Optional[Dict[str, Union[str, int, float, bool, list]]] = Field(default=None)

    @field_validator("request_data", "response_data", "tags", mode="before")
    @classmethod
    def convert_none_to_empty_dict(cls, v):
        """Convert None values to empty dict for proper type safety."""
        if v is None:
            return {}
        return v


class RawTaskData(BaseModel):
    """Raw task data from database row."""

    task_id: str
    status: str
    created_at: Union[str, datetime]
    updated_at: Union[str, datetime]
    channel_id: Optional[str] = None
    user_id: Optional[str] = None
    description: Optional[str] = None
    retry_count: int = 0
    error_message: Optional[str] = None
    thoughts: List[Dict[str, Union[str, int, float, bool]]] = Field(default_factory=list)
    metadata: Optional[Dict[str, Union[str, int, float, bool]]] = None


class RawThoughtData(BaseModel):
    """Raw thought data from database row."""

    thought_id: str = "unknown"
    thought_type: str = "standard"
    status: str = "unknown"
    created_at: str = ""
    content: Optional[str] = None
    final_action: Optional[Union[str, Dict[str, Union[str, int, float, bool]]]] = None
    round_number: int = 0
    depth: int = 0


class TSDBDataConverter:
    """Converts raw dictionary data to typed schemas."""

    @staticmethod
    def convert_service_interaction(raw_data: Union[dict, RawCorrelationData]) -> Optional[ServiceInteractionData]:
        """Convert raw correlation data to ServiceInteractionData."""
        try:
            # Convert dict to typed model if needed
            if isinstance(raw_data, dict):
                raw_data = RawCorrelationData(**raw_data)
            # Extract raw request/response data
            raw_request = raw_data.request_data
            raw_response = raw_data.response_data

            # Build typed request data
            request_data = None
            if raw_request:
                parameters = raw_request.get("parameters", {})
                request_data = RequestData(
                    channel_id=raw_request.get("channel_id"),
                    author_id=parameters.get("author_id") or raw_request.get("author_id"),
                    author_name=parameters.get("author_name") or raw_request.get("author_name"),
                    content=parameters.get("content") or raw_request.get("content"),
                    parameters=parameters,
                    headers=raw_request.get("headers", {}),
                    metadata=raw_request.get("metadata", {}),
                )

            # Build typed response data
            response_data = None
            if raw_response:
                response_data = ResponseData(
                    execution_time_ms=raw_response.get("execution_time_ms"),
                    success=raw_response.get("success"),
                    error=raw_response.get("error"),
                    error_type=raw_response.get("error_type"),
                    result=raw_response.get("result"),
                    resource_usage=raw_response.get("resource_usage", {}),
                    metadata=raw_response.get("metadata", {}),
                )

            # Build interaction context if available
            context = None
            context_data = raw_data.context
            if context_data:
                context = InteractionContext(
                    trace_id=context_data.get("trace_id"),
                    span_id=context_data.get("span_id"),
                    parent_span_id=context_data.get("parent_span_id"),
                    user_id=context_data.get("user_id"),
                    session_id=context_data.get("session_id"),
                    environment=context_data.get("environment"),
                    additional_data=context_data.get("additional_data", {}),
                )

            # Create ServiceInteractionData
            return ServiceInteractionData(
                correlation_id=raw_data.correlation_id,
                action_type=raw_data.action_type,
                service_type=raw_data.service_type,
                timestamp=raw_data.timestamp,
                channel_id=raw_request.get("channel_id", "unknown") if raw_request else "unknown",
                request_data=request_data,
                author_id=request_data.author_id if request_data else None,
                author_name=request_data.author_name if request_data else None,
                content=request_data.content if request_data else None,
                response_data=response_data,
                execution_time_ms=response_data.execution_time_ms if response_data else 0.0,
                success=response_data.success if response_data else True,
                error_message=response_data.error if response_data else None,
                context=context,
            )
        except Exception as e:
            error_msg = f"Failed to convert service interaction data: {str(e)[:200]}"
            rate_limited_logger.warning(error_msg, error_key="service_interaction_conversion")
            return None

    @staticmethod
    def convert_metric_correlation(raw_data: Union[dict, RawCorrelationData]) -> Optional[MetricCorrelationData]:
        """Convert raw correlation data to MetricCorrelationData."""
        try:
            # Convert dict to typed model if needed
            if isinstance(raw_data, dict):
                raw_data = RawCorrelationData(**raw_data)

            raw_request = raw_data.request_data
            raw_response = raw_data.response_data

            # Build typed request/response data
            request_data = None
            if raw_request:
                request_data = RequestData(
                    channel_id=raw_request.get("channel_id"),
                    parameters=raw_request.get("parameters", {}),
                    headers=raw_request.get("headers", {}),
                    metadata=raw_request.get("metadata", {}),
                )

            response_data = None
            if raw_response:
                response_data = ResponseData(
                    execution_time_ms=raw_response.get("execution_time_ms"),
                    success=raw_response.get("success"),
                    error=raw_response.get("error"),
                    error_type=raw_response.get("error_type"),
                    resource_usage=raw_response.get("resource_usage", {}),
                    metadata=raw_response.get("metadata", {}),
                )

            return MetricCorrelationData(
                correlation_id=raw_data.correlation_id,
                metric_name=raw_request.get("metric_name", "unknown"),
                value=float(raw_request.get("value", 0)),
                timestamp=raw_data.timestamp,
                request_data=request_data,
                response_data=response_data,
                tags=raw_data.tags,
                source="correlation",
                unit=raw_request.get("unit"),
                aggregation_type=raw_request.get("aggregation_type"),
            )
        except Exception as e:
            error_msg = f"Failed to convert metric correlation data: {str(e)[:200]}"
            rate_limited_logger.warning(error_msg, error_key="metric_correlation_conversion")
            return None

    @staticmethod
    def convert_trace_span(raw_data: Union[dict, RawCorrelationData]) -> Optional[TraceSpanData]:
        """Convert raw correlation data to TraceSpanData."""
        try:
            # Convert dict to typed model if needed
            if isinstance(raw_data, dict):
                raw_data = RawCorrelationData(**raw_data)

            raw_tags = raw_data.tags
            raw_request = raw_data.request_data
            raw_response = raw_data.response_data

            # Build typed span tags
            tags = None
            if raw_tags:
                tags = SpanTags(
                    task_id=raw_tags.get("task_id") or raw_request.get("task_id"),
                    thought_id=raw_tags.get("thought_id") or raw_request.get("thought_id"),
                    component_type=raw_tags.get("component_type") or raw_data.service_type,
                    handler_name=raw_tags.get("handler_name"),
                    user_id=raw_tags.get("user_id"),
                    channel_id=raw_tags.get("channel_id"),
                    environment=raw_tags.get("environment"),
                    version=raw_tags.get("version"),
                    additional_tags={
                        k: v
                        for k, v in raw_tags.items()
                        if k
                        not in [
                            "task_id",
                            "thought_id",
                            "component_type",
                            "handler_name",
                            "user_id",
                            "channel_id",
                            "environment",
                            "version",
                        ]
                        and v is not None
                    },
                )

            return TraceSpanData(
                trace_id=raw_data.trace_id or "",
                span_id=raw_data.span_id or "",
                parent_span_id=raw_data.parent_span_id,
                timestamp=raw_data.timestamp,
                duration_ms=raw_response.get("duration_ms", 0.0),
                operation_name=raw_data.action_type,
                service_name=raw_data.service_type,
                status="ok" if raw_response.get("success", True) else "error",
                tags=tags,
                task_id=tags.task_id if tags else None,
                thought_id=tags.thought_id if tags else None,
                component_type=tags.component_type if tags else None,
                error=not raw_response.get("success", True),
                error_message=raw_response.get("error"),
                error_type=raw_response.get("error_type"),
                latency_ms=raw_response.get("execution_time_ms"),
                resource_usage=raw_response.get("resource_usage", {}),
            )
        except Exception as e:
            error_msg = f"Failed to convert trace span data: {str(e)[:200]}"
            rate_limited_logger.warning(error_msg, error_key="trace_span_conversion")
            return None

    @staticmethod
    def convert_task(raw_task: Union[dict, RawTaskData]) -> Optional[TaskCorrelationData]:
        """Convert raw task data to TaskCorrelationData."""
        try:
            # Convert dict to typed model if needed
            if isinstance(raw_task, dict):
                # Clean thoughts list before creating RawTaskData
                if "thoughts" in raw_task and raw_task["thoughts"]:
                    cleaned_thoughts = []
                    for thought in raw_task["thoughts"]:
                        # Remove None values from thought dicts
                        cleaned_thought = {k: v for k, v in thought.items() if v is not None}
                        cleaned_thoughts.append(cleaned_thought)
                    raw_task["thoughts"] = cleaned_thoughts
                raw_task = RawTaskData(**raw_task)
            # Extract handlers from thoughts
            handlers_used = []
            final_handler = None
            thoughts = []

            for raw_thought in raw_task.thoughts:
                # Convert thought to ThoughtSummary
                thought_summary = TSDBDataConverter._convert_thought(raw_thought)
                if thought_summary:
                    thoughts.append(thought_summary)
                    if thought_summary.handler:
                        handlers_used.append(thought_summary.handler)
                        final_handler = thought_summary.handler  # Last one is final

            # Parse dates
            created_at = TSDBDataConverter._parse_datetime(
                raw_task.created_at if isinstance(raw_task.created_at, str) else raw_task.created_at.isoformat()
            )
            updated_at = TSDBDataConverter._parse_datetime(
                raw_task.updated_at if isinstance(raw_task.updated_at, str) else raw_task.updated_at.isoformat()
            )

            # Build task metadata
            metadata = None
            if raw_task.metadata:
                raw_meta = raw_task.metadata
                metadata = TaskMetadata(
                    priority=raw_meta.get("priority"),
                    tags=raw_meta.get("tags", []),
                    source=raw_meta.get("source"),
                    parent_task_id=raw_meta.get("parent_task_id"),
                    correlation_id=raw_meta.get("correlation_id"),
                    custom_fields={
                        k: v
                        for k, v in raw_meta.items()
                        if k not in ["priority", "tags", "source", "parent_task_id", "correlation_id"]
                    },
                )

            return TaskCorrelationData(
                task_id=raw_task.task_id,
                status=raw_task.status,
                created_at=created_at,
                updated_at=updated_at,
                channel_id=raw_task.channel_id,
                user_id=raw_task.user_id,
                task_type=raw_task.description.split()[0] if raw_task.description else None,
                retry_count=raw_task.retry_count,
                duration_ms=(updated_at - created_at).total_seconds() * 1000,
                thoughts=thoughts,
                handlers_used=handlers_used,
                final_handler=final_handler,
                success=raw_task.status in ["completed", "success"],
                error_message=raw_task.error_message,
                result_summary=raw_task.description,
                metadata=metadata,
            )
        except Exception as e:
            error_msg = f"Failed to convert task data: {str(e)[:200]}"
            rate_limited_logger.warning(error_msg, error_key="task_data_conversion")
            return None

    @staticmethod
    def _convert_thought(raw_thought: Union[dict, RawThoughtData]) -> Optional[ThoughtSummary]:
        """Convert raw thought data to ThoughtSummary."""
        try:
            # Convert dict to typed model if needed
            if isinstance(raw_thought, dict):
                # Filter out None values that cause validation issues
                cleaned_thought = {k: v for k, v in raw_thought.items() if v is not None}
                raw_thought = RawThoughtData(**cleaned_thought)
            final_action = None
            handler = None

            if raw_thought.final_action:
                try:
                    action_data = (
                        json.loads(raw_thought.final_action)
                        if isinstance(raw_thought.final_action, str)
                        else raw_thought.final_action
                    )
                    final_action = action_data
                    handler = action_data.get("handler")
                except (json.JSONDecodeError, TypeError):
                    pass

            return ThoughtSummary(
                thought_id=raw_thought.thought_id,
                thought_type=raw_thought.thought_type,
                status=raw_thought.status,
                created_at=raw_thought.created_at,
                content=raw_thought.content,
                final_action=final_action,
                handler=handler,
                round_number=raw_thought.round_number,
                depth=raw_thought.depth,
            )
        except Exception as e:
            error_msg = f"Failed to convert thought data: {str(e)[:200]}"
            rate_limited_logger.warning(error_msg, error_key="thought_data_conversion")
            return None

    @staticmethod
    def _parse_datetime(date_str: Optional[Union[str, datetime]]) -> datetime:
        """Parse datetime string to datetime object."""
        if not date_str:
            return datetime.now(timezone.utc)

        # If already a datetime, return it
        if isinstance(date_str, datetime):
            return date_str

        try:
            # Handle ISO format with Z suffix
            if date_str.endswith("Z"):
                date_str = date_str[:-1] + "+00:00"
            return datetime.fromisoformat(date_str)
        except (ValueError, AttributeError):
            return datetime.now(timezone.utc)


__all__ = ["TSDBDataConverter", "RawCorrelationData", "RawTaskData", "RawThoughtData"]
