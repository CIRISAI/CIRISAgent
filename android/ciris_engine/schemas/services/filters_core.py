"""
Filter Schemas v1 - Universal message filtering system for CIRIS Agent

Provides adaptive filtering capabilities across all adapters and services
with graph memory persistence and self-configuration support.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class FilterPriority(str, Enum):
    """Message priority levels for agent attention"""

    CRITICAL = "critical"  # DMs, @mentions, name mentions
    HIGH = "high"  # New users, suspicious patterns
    MEDIUM = "medium"  # Random sampling, periodic health checks
    LOW = "low"  # Normal traffic
    IGNORE = "ignore"  # Filtered out completely


class TriggerType(str, Enum):
    """Types of filter triggers"""

    REGEX = "regex"  # Regular expression pattern
    COUNT = "count"  # Numeric threshold (e.g., emoji count)
    LENGTH = "length"  # Message length threshold
    FREQUENCY = "frequency"  # Message frequency (count:seconds)
    CUSTOM = "custom"  # Custom logic (e.g., is_dm)
    SEMANTIC = "semantic"  # Meaning-based (requires LLM)


class FilterTrigger(BaseModel):
    """Individual filter trigger definition"""

    trigger_id: str = Field(description="Unique identifier")
    name: str = Field(description="Human-readable name")
    pattern_type: TriggerType = Field(description="Type of pattern matching")
    pattern: str = Field(description="Pattern or threshold value")
    priority: FilterPriority = Field(description="Priority level when triggered")
    description: str = Field(description="Human-readable description")
    enabled: bool = Field(default=True, description="Whether trigger is active")

    # Learning metadata
    effectiveness: float = Field(default=0.5, ge=0.0, le=1.0, description="How effective the trigger is")
    false_positive_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="Rate of false positives")
    true_positive_count: int = Field(default=0, description="Count of true positives")
    false_positive_count: int = Field(default=0, description="Count of false positives")
    last_triggered: Optional[datetime] = Field(default=None, description="When last triggered")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Creation timestamp")
    created_by: str = Field(default="system", description="Creator of the trigger")

    # For learned patterns
    learned_from: Optional[str] = Field(default=None, description="Source of learned pattern")

    model_config = ConfigDict(extra="forbid")


class UserTrustProfile(BaseModel):
    """
    Track user behavior for adaptive filtering.

    Works for both identified and anonymous users - when anonymized,
    user_id becomes a hash and PII fields are cleared.
    """

    user_id: str = Field(description="User identifier or hash for anonymous")
    message_count: int = Field(default=0, description="Total messages from user")
    violation_count: int = Field(default=0, description="Count of policy violations")
    helpful_count: int = Field(default=0, description="Count of helpful interactions")
    first_seen: datetime = Field(description="When user was first seen")
    last_seen: datetime = Field(description="When user was last active")
    trust_score: float = Field(default=0.5, ge=0.0, le=1.0, description="User trust score")
    flags: List[str] = Field(default_factory=list, description="Behavioral flags")
    roles: List[str] = Field(default_factory=list, description="User roles in community")

    avg_message_length: float = Field(default=0.0, description="Average message length")
    avg_message_interval: float = Field(default=0.0, description="Average seconds between messages")
    common_triggers: List[str] = Field(default_factory=list, description="Commonly triggered filters")

    # Privacy-preserving fields
    is_anonymous: bool = Field(default=False, description="User has anonymous consent")
    user_hash: Optional[str] = Field(None, description="Stable hash for anonymous tracking")
    consent_stream: str = Field(default="temporary", description="Current consent stream")

    # Anti-gaming measures
    consent_transitions_24h: int = Field(default=0, description="Consent changes in 24 hours")
    rapid_switching_flag: bool = Field(default=False, description="Detected rapid consent switching")
    evasion_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Gaming detection score")
    last_moderation: Optional[datetime] = Field(None, description="Last moderation action time")

    # Safety patterns (retained for anonymous)
    safety_patterns: List[str] = Field(default_factory=list, description="Active safety pattern IDs")
    pattern_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Pattern-based risk score")

    model_config = ConfigDict(extra="forbid")


class ConversationHealth(BaseModel):
    """Metrics for conversation health monitoring"""

    channel_id: str = Field(description="Unique channel identifier")
    sample_rate: float = Field(default=0.1, ge=0.0, le=1.0, description="Sampling rate for messages")
    health_score: float = Field(default=0.5, ge=0.0, le=1.0, description="Overall health score")

    # Detailed metrics
    toxicity_level: float = Field(default=0.0, ge=0.0, le=1.0, description="Level of toxic content")
    engagement_level: float = Field(default=0.5, ge=0.0, le=1.0, description="User engagement level")
    topic_coherence: float = Field(default=0.5, ge=0.0, le=1.0, description="Coherence of discussion topics")
    user_satisfaction: float = Field(default=0.5, ge=0.0, le=1.0, description="Estimated user satisfaction")

    # Sampling data
    last_sample: Optional[datetime] = Field(default=None, description="When last sampled")
    samples_today: int = Field(default=0, description="Samples taken today")
    issues_detected: int = Field(default=0, description="Issues found in samples")

    model_config = ConfigDict(extra="forbid")


class ContextHint(BaseModel):
    """Typed context hint for filter results"""

    key: str = Field(description="Context key")
    value: str = Field(description="Context value")

    model_config = ConfigDict(extra="forbid")


class FilterResult(BaseModel):
    """Result of filtering a message"""

    message_id: str = Field(description="ID of filtered message")
    priority: FilterPriority = Field(description="Assigned priority")
    triggered_filters: List[str] = Field(default_factory=list, description="IDs of triggered filters")
    should_process: bool = Field(description="Whether to process the message")
    should_defer: bool = Field(default=False, description="Whether to defer processing")
    reasoning: str = Field(description="Human-readable reasoning")

    suggested_action: Optional[str] = Field(default=None, description="Suggested action to take")
    context_hints: List[ContextHint] = Field(default_factory=list, description="Additional context")

    model_config = ConfigDict(extra="forbid")


class ChannelConfig(BaseModel):
    """Channel-specific filter configuration"""

    channel_id: str = Field(description="Unique channel identifier")
    health: ConversationHealth = Field(description="Health monitoring settings")
    custom_triggers: List[str] = Field(default_factory=list, description="Channel-specific trigger IDs")
    sample_rate_override: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Override sample rate")

    model_config = ConfigDict(extra="forbid")


class AdaptiveFilterConfig(BaseModel):
    """Complete filter configuration stored in graph memory"""

    config_id: str = Field(default="filter_config", description="Unique configuration ID")
    version: int = Field(default=1, description="Configuration version")

    # Core attention triggers (agent always sees these)
    attention_triggers: List[FilterTrigger] = Field(default_factory=list, description="High-priority triggers")

    # Suspicious pattern triggers
    review_triggers: List[FilterTrigger] = Field(default_factory=list, description="Triggers for review")

    # LLM response filters (protect against malicious LLM)
    llm_filters: List[FilterTrigger] = Field(default_factory=list, description="LLM output filters")

    # Channel-specific settings
    channel_configs: List[ChannelConfig] = Field(default_factory=list, description="Per-channel configurations")

    # User tracking
    new_user_threshold: int = Field(default=5, description="Messages before user is trusted")
    user_profiles: Dict[str, UserTrustProfile] = Field(
        default_factory=dict, description="User trust profiles by user ID"
    )

    # Adaptive learning settings
    auto_adjust: bool = Field(default=True, description="Enable automatic adjustments")
    adjustment_interval: int = Field(default=3600, description="Seconds between adjustments")
    effectiveness_threshold: float = Field(default=0.3, description="Disable filters below this effectiveness")
    false_positive_threshold: float = Field(default=0.2, description="Review filters above this FP rate")

    # Metadata
    last_adjustment: Optional[datetime] = Field(default=None, description="When last adjusted")
    total_messages_processed: int = Field(default=0, description="Total messages filtered")
    total_issues_caught: int = Field(default=0, description="Total issues detected")

    model_config = ConfigDict(extra="forbid")


class PriorityStats(BaseModel):
    """Statistics by priority level"""

    priority: FilterPriority = Field(description="Priority level")
    count: int = Field(default=0, description="Number of messages at this priority")
    percentage: float = Field(default=0.0, ge=0.0, le=100.0, description="Percentage of total")

    model_config = ConfigDict(extra="forbid")


class TriggerStats(BaseModel):
    """Statistics by trigger type"""

    trigger_type: TriggerType = Field(description="Type of trigger")
    count: int = Field(default=0, description="Number of times triggered")
    percentage: float = Field(default=0.0, ge=0.0, le=100.0, description="Percentage of total")

    model_config = ConfigDict(extra="forbid")


class FilterStats(BaseModel):
    """Statistics for filter performance monitoring"""

    total_messages_processed: int = Field(default=0, description="Total messages processed")
    total_filtered: int = Field(default=0, description="Total messages filtered")
    by_priority: Dict[FilterPriority, int] = Field(default_factory=dict, description="Message count by priority")
    by_trigger_type: Dict[TriggerType, int] = Field(default_factory=dict, description="Trigger count by type")
    false_positive_reports: int = Field(default=0, description="Reported false positives")
    true_positive_confirmations: int = Field(default=0, description="Confirmed true positives")
    last_reset: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="When stats were reset"
    )

    model_config = ConfigDict(extra="forbid")


class FilterHealth(BaseModel):
    """Overall health metrics for the filtering system"""

    is_healthy: bool = Field(default=True, description="Whether system is healthy")
    warnings: List[str] = Field(default_factory=list, description="Active warnings")
    errors: List[str] = Field(default_factory=list, description="Active errors")
    stats: FilterStats = Field(default_factory=FilterStats, description="Performance statistics")
    config_version: int = Field(default=1, description="Current config version")
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Last update time")

    model_config = ConfigDict(extra="forbid")


class FilterServiceMetadata(BaseModel):
    """Metadata for adaptive filter service capabilities."""

    description: str = Field(..., description="Service description")
    features: List[str] = Field(..., description="List of features supported")
    filter_types: List[str] = Field(..., description="Types of filters supported")
    max_buffer_size: int = Field(..., description="Maximum message buffer size")


__all__ = [
    "FilterPriority",
    "TriggerType",
    "FilterTrigger",
    "UserTrustProfile",
    "ConversationHealth",
    "ContextHint",
    "FilterResult",
    "ChannelConfig",
    "AdaptiveFilterConfig",
    "PriorityStats",
    "TriggerStats",
    "FilterStats",
    "FilterHealth",
    "FilterServiceMetadata",
]
