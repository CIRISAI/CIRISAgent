"""
System and runtime context schemas.

Provides type-safe contexts for system state and runtime operations.
"""
from typing import Dict, List, Optional, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, field_serializer
from ciris_engine.schemas.runtime.resources import ResourceUsage

class SystemSnapshot(BaseModel):
    """System state snapshot for processing context.

    This snapshot captures the system state needed for decision-making during
    task and thought processing. The most critical field is channel_context,
    which provides the communication context. All other fields provide
    supplementary information about current processing state and system health.

    Usage patterns:
    1. Minimal: SystemSnapshot(channel_context=create_channel_context(channel_id))
       - Used by: task_manager, shutdown_processor, speak_handler, discord_observer

    2. Full: Built by build_system_snapshot() with all available context
       - Used during: thought context building in processors

    Field usage:
    - ALWAYS SET: channel_context, channel_id
    - COMMONLY SET: current_task_details, current_thought_summary, system_counts
    - IDENTITY FIELDS: agent_identity and related fields loaded from graph
    - RUNTIME FIELDS: service_health, circuit_breaker_status from service registry
    - SECURITY FIELDS: detected_secrets and related from secrets service
    """

    # Channel context (PRIMARY FIELDS - almost always set)
    channel_id: Optional[str] = Field(
        None,
        description="ID of the communication channel (e.g., Discord channel ID, 'cli', 'api')"
    )
    channel_context: Optional['ChannelContext'] = Field(
        None,
        description="Full channel context with metadata - the most important field"
    )

    # Current processing state (set when processing tasks/thoughts)
    current_task_details: Optional['TaskSummary'] = Field(
        None,
        description="Summary of the task currently being processed"
    )
    current_thought_summary: Optional['ThoughtSummary'] = Field(
        None,
        description="Summary of the thought currently being processed"
    )

    # System overview (computed during snapshot building)
    system_counts: Dict[str, int] = Field(
        default_factory=dict,
        description="Counts: total_tasks, total_thoughts, pending_tasks, pending_thoughts"
    )
    top_pending_tasks_summary: List['TaskSummary'] = Field(
        default_factory=list,
        description="Top 10 pending tasks by priority"
    )
    recently_completed_tasks_summary: List['TaskSummary'] = Field(
        default_factory=list,
        description="10 most recently completed tasks"
    )

    # Agent identity (loaded once from graph memory)
    agent_identity: Dict[str, Any] = Field(
        default_factory=dict,
        description="Raw agent identity data from graph node"
    )
    identity_purpose: Optional[str] = Field(
        None,
        description="Agent's purpose statement extracted from identity"
    )
    identity_capabilities: List[str] = Field(
        default_factory=list,
        description="List of agent capabilities from identity"
    )
    identity_restrictions: List[str] = Field(
        default_factory=list,
        description="List of agent restrictions from identity"
    )

    # Security context (from secrets service)
    detected_secrets: List[Any] = Field(
        default_factory=list,
        description="Patterns of secrets detected in current context"
    )
    secrets_filter_version: int = Field(
        0,
        description="Version of the secrets filter being used"
    )
    total_secrets_stored: int = Field(
        0,
        description="Total number of secrets in secure storage"
    )

    # Service health (from service registry)
    service_health: Dict[str, Any] = Field(
        default_factory=dict,
        description="Health status of each service (service_name -> is_healthy)"
    )
    circuit_breaker_status: Dict[str, Any] = Field(
        default_factory=dict,
        description="Circuit breaker status for each service"
    )

    # Runtime context
    shutdown_context: Optional[Any] = Field(
        None,
        description="Shutdown context if system is shutting down"
    )

    # Resource alerts - CRITICAL for mission-critical systems
    resource_alerts: List[str] = Field(
        default_factory=list,
        description="CRITICAL resource alerts that require immediate attention"
    )

    # User profiles (used by context builder)
    user_profiles: List['UserProfile'] = Field(
        default_factory=list,
        description="User profile information"
    )

    # Telemetry summary for resource usage
    telemetry_summary: Optional['TelemetrySummary'] = Field(
        None,
        description="Aggregated telemetry data for resource usage tracking"
    )

    model_config = ConfigDict(extra = "forbid")  # Be strict about fields to catch misuse

class TaskSummary(BaseModel):
    """Summary of a task for system snapshot."""
    task_id: str = Field(..., description="Unique task identifier")
    channel_id: str = Field(..., description="Channel where task originated")
    created_at: datetime = Field(..., description="Task creation time")
    status: str = Field(..., description="Current task status")

    # Task metadata
    priority: int = Field(0, description="Task priority")
    retry_count: int = Field(0, description="Number of retries")
    parent_task_id: Optional[str] = Field(None, description="Parent task if nested")

    # Execution context
    assigned_agent: Optional[str] = Field(None, description="Agent handling the task")
    deadline: Optional[datetime] = Field(None, description="Task deadline")
    tags: List[str] = Field(default_factory=list, description="Task tags")

    # Results
    result: Optional[str] = Field(None, description="Task result")
    result_data: Optional[Dict[str, str]] = Field(None, description="Structured result data")
    error: Optional[str] = Field(None, description="Error if failed")

    model_config = ConfigDict(extra = "forbid")

class ThoughtState(BaseModel):
    """State for a thought being processed."""
    thought_id: str = Field(..., description="Unique thought identifier")
    task_id: str = Field(..., description="Associated task ID")
    content: str = Field(..., description="Thought content")
    thought_type: str = Field(..., description="Type of thought")

    # Processing state
    created_at: datetime = Field(..., description="When thought was created")
    processing_depth: int = Field(0, description="How many times processed")
    is_pondering: bool = Field(False, description="Whether in ponder state")

    # Relationships
    parent_thought_id: Optional[str] = Field(None, description="Parent thought if nested")
    child_thought_ids: List[str] = Field(default_factory=list, description="Child thoughts")

    # DMA results (stored as JSON strings for flexibility)
    pdma_result: Optional[str] = Field(None, description="PDMA evaluation JSON")
    csdma_result: Optional[str] = Field(None, description="CSDMA evaluation JSON")
    dsdma_result: Optional[str] = Field(None, description="DSDMA evaluation JSON")

    # Decision
    selected_action: Optional[str] = Field(None, description="Action selected")

    model_config = ConfigDict(extra = "forbid")

class UserProfile(BaseModel):
    """User profile information."""
    user_id: str = Field(..., description="Unique user identifier")
    display_name: str = Field(..., description="User display name")
    created_at: datetime = Field(..., description="Profile creation time")

    # Preferences
    preferred_language: str = Field("en", description="Preferred language code")
    timezone: str = Field("UTC", description="User timezone")
    communication_style: str = Field("formal", description="Preferred communication style")

    # Interaction history
    total_interactions: int = Field(0, description="Total interactions")
    last_interaction: Optional[datetime] = Field(None, description="Last interaction time")
    trust_level: float = Field(0.5, description="Trust level (0.0-1.0)")

    # Permissions
    is_wa: bool = Field(False, description="Whether user is Wise Authority")
    permissions: List[str] = Field(default_factory=list, description="Granted permissions")
    restrictions: List[str] = Field(default_factory=list, description="Applied restrictions")

    model_config = ConfigDict(extra = "forbid")

class ChannelContext(BaseModel):
    """Context for a communication channel."""
    channel_id: str = Field(..., description="Unique channel identifier")
    channel_type: str = Field(..., description="Type of channel (discord, cli, api)")
    created_at: datetime = Field(..., description="Channel creation time")

    # Channel metadata
    channel_name: Optional[str] = Field(None, description="Human-readable channel name")
    is_private: bool = Field(False, description="Whether channel is private")
    participants: List[str] = Field(default_factory=list, description="Channel participants")

    # State
    is_active: bool = Field(True, description="Whether channel is active")
    last_activity: Optional[datetime] = Field(None, description="Last activity time")
    message_count: int = Field(0, description="Total messages in channel")

    # Configuration
    allowed_actions: List[str] = Field(default_factory=list, description="Allowed actions in channel")
    moderation_level: str = Field("standard", description="Moderation level")

    @field_serializer('created_at', 'last_activity')
    def serialize_datetimes(self, dt: Optional[datetime], _info):
        return dt.isoformat() if dt else None

    model_config = ConfigDict(extra = "forbid")


class AuditVerification(BaseModel):
    """Audit chain verification result."""
    verified_at: datetime = Field(..., description="When verification occurred")
    result: str = Field(..., description="Verification result: valid, invalid, partial")
    entries_verified: int = Field(..., description="Number of entries verified")
    hash_chain_valid: bool = Field(..., description="Whether hash chain is intact")
    signatures_valid: bool = Field(..., description="Whether signatures are valid")

    # Issues found
    issues: List[str] = Field(default_factory=list, description="Issues found during verification")
    missing_entries: List[str] = Field(default_factory=list, description="Missing entry IDs")

    model_config = ConfigDict(extra = "forbid")



class ThoughtSummary(BaseModel):
    """Summary of a thought for context."""
    thought_id: str = Field(..., description="Thought ID")
    content: Optional[str] = Field(None, description="Thought content")
    status: Optional[str] = Field(None, description="Thought status")
    source_task_id: Optional[str] = Field(None, description="Source task ID")
    thought_type: Optional[str] = Field(None, description="Type of thought")
    thought_depth: Optional[int] = Field(None, description="Processing depth")

    model_config = ConfigDict(extra = "allow")

class TelemetrySummary(BaseModel):
    """Summary of recent telemetry metrics for system context."""

    # Time window
    window_start: datetime = Field(..., description="Start of telemetry window")
    window_end: datetime = Field(..., description="End of telemetry window")
    uptime_seconds: float = Field(..., description="System uptime in seconds")

    # Activity metrics (last 24h)
    messages_processed_24h: int = Field(0, description="Messages processed in last 24h")
    thoughts_processed_24h: int = Field(0, description="Thoughts processed in last 24h")
    tasks_completed_24h: int = Field(0, description="Tasks completed in last 24h")
    errors_24h: int = Field(0, description="Errors in last 24h")

    # Current hour metrics
    messages_current_hour: int = Field(0, description="Messages this hour")
    thoughts_current_hour: int = Field(0, description="Thoughts this hour")
    errors_current_hour: int = Field(0, description="Errors this hour")

    # Service breakdowns
    service_calls: Dict[str, int] = Field(default_factory=dict, description="Calls per service type")
    service_errors: Dict[str, int] = Field(default_factory=dict, description="Errors per service type")
    service_latency_ms: Dict[str, float] = Field(default_factory=dict, description="Avg latency per service")

    # Resource consumption rates
    tokens_per_hour: float = Field(0.0, description="Average tokens per hour")
    cost_per_hour_cents: float = Field(0.0, description="Average cost per hour in cents")
    carbon_per_hour_grams: float = Field(0.0, description="Average carbon per hour in grams")

    # Health indicators
    error_rate_percent: float = Field(0.0, description="Error rate as percentage")
    avg_thought_depth: float = Field(0.0, description="Average thought processing depth")
    queue_saturation: float = Field(0.0, description="Queue saturation 0-1")

    @field_serializer('window_start', 'window_end')
    def serialize_datetimes(self, dt: datetime, _info):
        return dt.isoformat() if dt else None

    model_config = ConfigDict(extra = "forbid")

__all__ = [
    "SystemSnapshot",
    "TaskSummary",
    "ThoughtState",
    "UserProfile",
    "ChannelContext",
    "ResourceUsage",  # Re-exported from resources module
    "AuditVerification",
    "TelemetrySummary",
    "ThoughtSummary"
]
