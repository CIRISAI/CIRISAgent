"""
Core enums for CIRIS Trinity Architecture.

All enums are case-insensitive for robustness.
"""

from enum import Enum


class CaseInsensitiveEnum(str, Enum):
    """Enum that allows case-insensitive value lookup."""

    @classmethod
    def _missing_(cls, value: object) -> "CaseInsensitiveEnum | None":
        if isinstance(value, str):
            lowered = value.lower()
            for member in cls:
                if member.value.lower() == lowered or member.name.lower() == lowered:
                    return member
        return None


class ServiceType(CaseInsensitiveEnum):
    """Core service types in the Trinity Architecture."""

    # Core services
    COMMUNICATION = "communication"
    TOOL = "tool"
    WISE_AUTHORITY = "wise_authority"
    MEMORY = "memory"
    AUDIT = "audit"
    LLM = "llm"

    # Infrastructure services
    TELEMETRY = "telemetry"
    ORCHESTRATOR = "orchestrator"
    SECRETS = "secrets"
    RUNTIME_CONTROL = "runtime_control"
    FILTER = "filter"
    CONFIG = "config"
    MAINTENANCE = "maintenance"
    TIME = "time"
    SHUTDOWN = "shutdown"
    INITIALIZATION = "initialization"
    VISIBILITY = "visibility"
    TSDB_CONSOLIDATION = "tsdb_consolidation"

    # Adapter services
    ADAPTER = "adapter"


class HandlerActionType(CaseInsensitiveEnum):
    """Core 3×3×3 action model + terminal."""

    # External actions
    OBSERVE = "observe"
    SPEAK = "speak"
    TOOL = "tool"

    # Control responses
    REJECT = "reject"
    PONDER = "ponder"
    DEFER = "defer"

    # Memory operations
    MEMORIZE = "memorize"
    RECALL = "recall"
    FORGET = "forget"

    # Terminal action
    TASK_COMPLETE = "task_complete"


class TaskStatus(CaseInsensitiveEnum):
    """Status of a task in the system."""

    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    DEFERRED = "deferred"
    REJECTED = "rejected"


class TaskOrigin(CaseInsensitiveEnum):
    """Who created a task, set structurally by the code that creates it (#1366).

    Never inferred: in particular, a task with no verified sender is not thereby an engine task (an adapter can
    fail to attach one). ``USER`` and ``WISE_AUTHORITY`` are tasks created from a person's message; every
    ``ENGINE_*`` value is a task the engine created for itself.
    """

    USER = "user"
    #: A task created from a Wise Authority's own message on its deferral channel (a person, not the engine).
    WISE_AUTHORITY = "wise_authority"
    ENGINE_WAKEUP = "engine_wakeup"
    ENGINE_SHUTDOWN = "engine_shutdown"
    ENGINE_DREAM = "engine_dream"
    ENGINE_SYSTEM = "engine_system"
    #: The task a Wise Authority's resolution of a deferral creates.
    ENGINE_GUIDANCE = "engine_guidance"
    ENGINE_PARTNERSHIP = "engine_partnership"

    @property
    def is_engine(self) -> bool:
        return self not in (TaskOrigin.USER, TaskOrigin.WISE_AUTHORITY)


class ThoughtStatus(CaseInsensitiveEnum):
    """Status of a thought being processed."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DEFERRED = "deferred"


class ThoughtType(CaseInsensitiveEnum):
    """Types of thoughts for different processing needs."""

    # Core thought types
    STANDARD = "standard"
    FOLLOW_UP = "follow_up"
    ERROR = "error"
    OBSERVATION = "observation"
    MEMORY = "memory"
    DEFERRED = "deferred"
    PONDER = "ponder"

    # Feedback and guidance
    FEEDBACK = "feedback"
    GUIDANCE = "guidance"
    IDENTITY_UPDATE = "identity_update"

    # Decision-making
    ETHICAL_REVIEW = "ethical_review"
    conscience = "conscience"
    CONSENSUS = "consensus"

    # System and meta
    REFLECTION = "reflection"
    SYNTHESIS = "synthesis"
    DELEGATION = "delegation"

    # Communication
    CLARIFICATION = "clarification"
    SUMMARY = "summary"

    # Tool and action
    TOOL_RESULT = "tool_result"
    ACTION_REVIEW = "action_review"

    # Urgency and priority
    URGENT = "urgent"
    SCHEDULED = "scheduled"

    # Learning and adaptation
    PATTERN = "pattern"
    ADAPTATION = "adaptation"


class SensitivityLevel(CaseInsensitiveEnum):
    """Security sensitivity levels."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ObservationSourceType(CaseInsensitiveEnum):
    """Types of observation sources."""

    CHAT_MESSAGE = "chat_message"
    FEEDBACK_PACKAGE = "feedback_package"
    USER_REQUEST = "user_request"
    AGENT_MESSAGE = "agent_message"
    INTERNAL_SIGNAL = "internal_signal"


__all__ = [
    "CaseInsensitiveEnum",
    "ServiceType",
    "HandlerActionType",
    "TaskStatus",
    "TaskOrigin",
    "ThoughtStatus",
    "ThoughtType",
    "SensitivityLevel",
    "ObservationSourceType",
]
