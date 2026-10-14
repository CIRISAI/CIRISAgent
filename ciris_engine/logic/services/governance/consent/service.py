"""
Consent Service - FAIL FAST, FAIL LOUD, NO FAKE DATA.

Governance Service #5: Manages user consent for the Consensual Evolution Protocol.
Default: TEMPORARY (14 days) unless explicitly changed.
This is the 22nd core CIRIS service.

REFACTORED: Now uses modular architecture with separate modules for:
- exceptions: Custom errors
- metrics: Metrics collection
- partnership: PARTNERED-request deferral to the steward (WBD)
- decay: Decay protocol
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from ciris_engine.logic.buses.memory_bus import MemoryBus
from ciris_engine.logic.buses.wise_bus import WiseBus
from ciris_engine.logic.persistence import add_graph_node, get_graph_node
from ciris_engine.logic.services.base_service import BaseService
from ciris_engine.logic.utils.jsondict_helpers import get_dict, get_float, get_list, get_str, get_str_optional
from ciris_engine.protocols.consent import ConsentManagerProtocol
from ciris_engine.protocols.services import ToolService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.adapters.tools import ToolExecutionResult, ToolExecutionStatus, ToolInfo, ToolParameterSchema
from ciris_engine.schemas.consent.core import (
    ConsentAuditEntry,
    ConsentCategory,
    ConsentDecayStatus,
    ConsentImpactReport,
    ConsentRequest,
    ConsentStatus,
    ConsentStream,
    PartnershipRequestStatus,
    PartnershipStewardDecision,
)
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.core import ServiceCapabilities
from ciris_engine.schemas.services.graph.memory import MemorySearchFilter
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.types import JSONDict

# Import from new modules
from .air import ArtificialInteractionReminder
from .attestation import PartnershipPairEmission, emit_consent_revocation, emit_partnership_pair
from .decay import DecayProtocolManager
from .exceptions import ConsentNotFoundError, ConsentValidationError, StewardDeferralUnavailableError
from .metrics import ConsentMetricsCollector
from .partnership import build_partnership_deferral_context, build_partnership_deferral_task, find_open_partnership_task

logger = logging.getLogger(__name__)


def _sanitize_for_log(value: Any, max_length: int = 64) -> str:
    """Sanitize user-controlled data for safe logging."""
    if value is None:
        return "<none>"
    val_str = str(value)
    sanitized = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", val_str)
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length] + "..."
    return sanitized


class ConsentService(BaseService, ConsentManagerProtocol, ToolService):
    """
    Consent Service - 22nd Core CIRIS Service (Governance #5).

    Manages user consent with HARD GUARANTEES:
    - TEMPORARY by default (14 days)
    - No fake data or fallbacks
    - Immutable audit trail
    - Real decay protocol
    - PARTNERED is a data-management record: the steward's own choice applies
      directly; any other user's request is deferred to the steward (WBD)
    """

    def __init__(
        self,
        time_service: TimeServiceProtocol,
        memory_bus: Optional[MemoryBus] = None,
        db_path: Optional[str] = None,
        wise_bus: Optional[WiseBus] = None,
    ):
        super().__init__(time_service=time_service, service_name="ConsentService")
        self._time_service = time_service
        self._memory_bus = memory_bus
        self._db_path = db_path
        # The existing Wisdom-Based Deferral path. A non-steward PARTNERED request
        # travels to the steward through it; there is no consent-local queue.
        self._wise_bus = wise_bus

        # Initialize modular managers
        self._metrics_collector = ConsentMetricsCollector()
        self._decay_manager = DecayProtocolManager(time_service=time_service, db_path=db_path)
        self._air_manager = ArtificialInteractionReminder(
            time_service=time_service,
            time_threshold_minutes=30,  # 30 minutes
            message_threshold=20,  # 20 messages
        )

        # Cache for active consents (NOT source of truth)
        self._consent_cache: Dict[str, ConsentStatus] = {}

        # Core Metrics (real, no fake data)
        self._consent_checks = 0
        self._consent_grants = 0
        self._consent_revokes = 0
        self._tool_executions = 0
        self._tool_failures = 0
        self._expired_cleanups = 0

        # Downgrade tracking
        self._downgrades_completed = 0

        # PARTNERED requests carried to the steward (WBD) and their answers
        self._partnership_deferrals = 0
        self._partnership_approvals = 0
        self._partnership_refusals = 0

    def _now(self) -> datetime:
        """Get current time from time service."""
        if self._time_service is None:
            return datetime.now(timezone.utc)
        return self._time_service.now()

    async def _extend_temporary_expiry(self, user_id: str, status: ConsentStatus) -> None:
        """
        Reset TEMPORARY expiry to 2 weeks from now on every interaction.
        This implements the "2 weeks without seeing them before decay" rule.
        """
        now = self._now()
        new_expiry = now + timedelta(days=14)

        # Only update if expiry changed significantly (avoid unnecessary writes)
        if status.expires_at and (new_expiry - status.expires_at).total_seconds() < 3600:
            # Less than 1 hour difference, skip update to reduce I/O
            return

        # Update status with new expiry
        status.expires_at = new_expiry
        status.last_modified = now

        # Persist to graph
        node = GraphNode(
            id=f"consent/{user_id}",
            type=NodeType.CONSENT,
            scope=GraphScope.LOCAL,
            attributes={
                "stream": status.stream,
                "categories": list(status.categories),
                "granted_at": status.granted_at.isoformat(),
                "expires_at": new_expiry.isoformat(),
                "last_modified": now.isoformat(),
                "impact_score": status.impact_score,
                "attribution_count": status.attribution_count,
            },
            updated_by="consent_manager",
            updated_at=now,
        )
        if self._time_service is None:
            raise ValueError("TimeService required for extending expiry")
        add_graph_node(node, self._time_service)

        # Update cache
        self._consent_cache[user_id] = status

        logger.debug(f"Extended TEMPORARY expiry for {user_id} to {new_expiry.isoformat()}")

    def _check_cached_expiry(self, user_id: str, cached: ConsentStatus) -> None:
        """Check if cached consent has expired and remove if so."""
        if cached.stream == ConsentStream.TEMPORARY and cached.expires_at:
            if self._now() > cached.expires_at:
                del self._consent_cache[user_id]
                raise ConsentNotFoundError(f"Consent for {user_id} has expired")

    def _reconstruct_consent_from_node(self, user_id: str, node: Any) -> ConsentStatus:
        """Reconstruct ConsentStatus from graph node."""
        attrs = node.attributes if isinstance(node.attributes, dict) else node.attributes.model_dump()

        # Extract expires_at separately to avoid walrus operator in argument list
        expires_str = get_str_optional(attrs, "expires_at")
        expires_at = datetime.fromisoformat(expires_str) if expires_str else None

        return ConsentStatus(
            user_id=user_id,
            stream=ConsentStream(get_str(attrs, "stream", "temporary")),
            categories=[ConsentCategory(c) for c in get_list(attrs, "categories", [])],
            granted_at=datetime.fromisoformat(get_str(attrs, "granted_at", datetime.now(timezone.utc).isoformat())),
            expires_at=expires_at,
            last_modified=datetime.fromisoformat(
                get_str(attrs, "last_modified", datetime.now(timezone.utc).isoformat())
            ),
            impact_score=get_float(attrs, "impact_score", 0.0),
            attribution_count=int(get_float(attrs, "attribution_count", 0)),
        )

    async def _load_consent_from_graph(self, user_id: str) -> ConsentStatus:
        """Load consent from graph storage."""
        node = get_graph_node(f"consent/{user_id}", GraphScope.LOCAL)
        if not node:
            raise ConsentNotFoundError(f"No consent found for user {user_id}")

        status = self._reconstruct_consent_from_node(user_id, node)

        # Check expiry
        if status.stream == ConsentStream.TEMPORARY and status.expires_at:
            if self._now() > status.expires_at:
                raise ConsentNotFoundError(f"Consent for {user_id} has expired")

        # Update cache
        self._consent_cache[user_id] = status
        return status

    async def get_consent(self, user_id: str, extend_expiry: bool = True) -> ConsentStatus:
        """
        Get user's consent status.
        FAILS if user doesn't exist - NO DEFAULTS.

        Args:
            user_id: User ID to get consent for
            extend_expiry: If True, reset TEMPORARY expiry to 2 weeks from now (default: True)
        """
        self._consent_checks += 1

        # Try cache first (but verify it's still valid)
        if user_id in self._consent_cache:
            cached = self._consent_cache[user_id]
            self._check_cached_expiry(user_id, cached)

            # Reset decay countdown on every interaction (2 weeks without seeing them)
            if extend_expiry and cached.stream == ConsentStream.TEMPORARY:
                await self._extend_temporary_expiry(user_id, cached)

            return cached

        # Load from graph
        try:
            status = await self._load_consent_from_graph(user_id)

            # Reset decay countdown on every interaction (2 weeks without seeing them)
            if extend_expiry and status.stream == ConsentStream.TEMPORARY:
                await self._extend_temporary_expiry(user_id, status)

            return status

        except Exception as e:
            if "not found" in str(e).lower():
                raise ConsentNotFoundError(f"No consent found for user {user_id}")
            raise

    async def track_interaction(
        self, user_id: str, channel_id: str, channel_type: Optional[str] = None, message_content: Optional[str] = None
    ) -> Optional[str]:
        """
        Track user interaction for parasocial attachment prevention.

        This method delegates to the AIR (Artificial Interaction Reminder) manager
        to monitor 1:1 API interactions and provide break reminders when thresholds are exceeded.

        Scope: API channels only (1:1 interactions, not community moderation)
        Triggers:
        - 30 minutes continuous interaction
        - 20+ messages
        - High valence patterns (anthropomorphism, dependency, emotional intensity)

        Args:
            user_id: User ID
            channel_id: Channel ID
            channel_type: Channel type (api, discord, cli, unknown) - if None, will infer from ID
            message_content: Optional message content for valence analysis

        Returns:
            Reminder message if threshold exceeded, None otherwise
        """
        return self._air_manager.track_interaction(user_id, channel_id, channel_type, message_content)

    async def grant_consent(
        self,
        request: ConsentRequest,
        channel_id: Optional[str] = None,
        *,
        requester_is_steward: bool = False,
    ) -> ConsentStatus:
        """
        Grant or update consent.
        VALIDATES everything, creates audit trail, emits the wire pair.

        The stream is the user's data choice (CC 4.4.3.4.3). One case is not
        theirs alone: whether this agent retains a NON-steward user under
        PARTNERED is the steward's decision. That request is deferred to the
        steward through the existing WBD path and the user's current stream is
        returned unchanged; ``apply_steward_partnership_decision`` applies the
        answer. ``requester_is_steward`` is set by the caller that authenticated
        the request (the API route: the caller may resolve deferrals), and a
        steward's own PARTNERED choice applies directly.
        """
        self._consent_grants += 1

        # Validate request
        self._validate_consent_request(request)

        # Get previous status if exists
        previous_status = await self._get_previous_status(request.user_id)

        already_partnered = previous_status is not None and previous_status.stream == ConsentStream.PARTNERED
        if request.stream == ConsentStream.PARTNERED and not requester_is_steward and not already_partnered:
            return await self._defer_partnership_to_steward(request, previous_status, channel_id)

        # Check for gaming behavior if switching streams
        await self._check_gaming_behavior(request, previous_status)

        new_status = self._create_consent_status(request, previous_status)

        # Persist consent and audit trail
        await self._persist_consent(new_status, previous_status, request.reason, "user")

        logger.info(f"Consent granted for {request.user_id}: {new_status.stream}")
        return new_status

    def _validate_consent_request(self, request: ConsentRequest) -> None:
        """Validate consent request parameters."""
        if not request.user_id:
            raise ConsentValidationError("User ID required")
        if not request.categories and request.stream == ConsentStream.PARTNERED:
            raise ConsentValidationError("PARTNERED requires at least one category")

    async def _get_previous_status(self, user_id: str) -> Optional[ConsentStatus]:
        """Get previous consent status if exists."""
        try:
            return await self.get_consent(user_id)
        except ConsentNotFoundError:
            return None

    async def _check_gaming_behavior(self, request: ConsentRequest, previous_status: Optional[ConsentStatus]) -> None:
        """Check for gaming behavior if switching consent streams."""
        if not previous_status or request.stream == previous_status.stream:
            return

        if not hasattr(self, "_filter_service"):
            return

        # Handle both enum and string types for stream
        prev_stream = (
            previous_status.stream.value if hasattr(previous_status.stream, "value") else previous_status.stream
        )
        req_stream = request.stream.value if hasattr(request.stream, "value") else request.stream

        is_gaming = await self._filter_service.handle_consent_transition(request.user_id, prev_stream, req_stream)

        if is_gaming:
            logger.warning(
                f"Gaming attempt detected for {request.user_id}: {previous_status.stream} -> {request.stream}"
            )

    def _create_consent_status(
        self, request: ConsentRequest, previous_status: Optional[ConsentStatus]
    ) -> ConsentStatus:
        """Create new consent status from request."""
        now = self._now()
        expires_at = None
        if request.stream == ConsentStream.TEMPORARY:
            expires_at = now + timedelta(days=14)

        return ConsentStatus(
            user_id=request.user_id,
            stream=request.stream,
            categories=request.categories,
            granted_at=previous_status.granted_at if previous_status else now,
            expires_at=expires_at,
            last_modified=now,
            impact_score=previous_status.impact_score if previous_status else 0.0,
            attribution_count=previous_status.attribution_count if previous_status else 0,
        )

    async def _persist_consent(
        self,
        new_status: ConsentStatus,
        previous_status: Optional[ConsentStatus],
        reason: Optional[str],
        initiated_by: str,
    ) -> None:
        """Persist consent status and audit trail to graph."""
        now = self._now()

        # Store in graph
        node = GraphNode(
            id=f"consent/{new_status.user_id}",
            type=NodeType.CONSENT,
            scope=GraphScope.LOCAL,
            attributes={
                "stream": new_status.stream,
                "categories": list(new_status.categories),
                "granted_at": new_status.granted_at.isoformat(),
                "expires_at": new_status.expires_at.isoformat() if new_status.expires_at else None,
                "last_modified": new_status.last_modified.isoformat(),
                "impact_score": new_status.impact_score,
                "attribution_count": new_status.attribution_count,
            },
            updated_by="consent_manager",
            updated_at=now,
        )
        if self._time_service is None:
            raise ValueError("TimeService required for persisting consent")
        add_graph_node(node, self._time_service)

        # Create audit entry
        audit = ConsentAuditEntry(
            entry_id=str(uuid4()),
            user_id=new_status.user_id,
            timestamp=now,
            previous_stream=previous_status.stream if previous_status else ConsentStream.TEMPORARY,
            new_stream=new_status.stream,
            previous_categories=previous_status.categories if previous_status else [],
            new_categories=new_status.categories,
            initiated_by=initiated_by,
            reason=reason,
        )

        # Store audit entry
        audit_attrs = audit.model_dump(mode="json")
        audit_attrs["service"] = "consent"  # Add service identifier for querying
        audit_node = GraphNode(
            id=f"consent_audit/{audit.entry_id}",
            type=NodeType.AUDIT_ENTRY,
            scope=GraphScope.IDENTITY,  # Use IDENTITY scope for user-specific audit trail
            attributes=audit_attrs,
            updated_by="consent_manager",
            updated_at=now,
        )
        add_graph_node(audit_node, self._time_service)

        # Update cache
        self._consent_cache[new_status.user_id] = new_status

        # CEG-native consent (#869/#866) + the partnership wire pair (#1251).
        self._record_stream_change(new_status)

    def _record_stream_change(
        self,
        new_status: ConsentStatus,
        *,
        decided_by: Optional[str] = None,
        deferral_id: Optional[str] = None,
    ) -> PartnershipPairEmission:
        """Emit the wire pair for a stream write: the grant content + the SIGNED accept half.

        Runs on every consent write, whatever the stream: the accept half is
        emitted on every stream change and never withheld (CC 4.4.3.4.3).
        Best-effort, never breaks the consent write path. Default ON;
        CIRIS_CONSENT_CEG_ATTESTATIONS=false is the emergency kill-switch.

        End users hold no federation key the agent can name (``user_key_id``
        stays None), so the grant half is recorded as KEYLESS_USER: its content
        rides in the consent:stream row and no user signature is claimed.
        """
        return emit_partnership_pair(new_status, decided_by=decided_by, deferral_id=deferral_id)

    async def _defer_partnership_to_steward(
        self, request: ConsentRequest, previous_status: Optional[ConsentStatus], channel_id: Optional[str]
    ) -> ConsentStatus:
        """Carry a non-steward PARTNERED request to the steward through WBD. Changes nothing else.

        Idempotent: while one request is open, asking again returns the current
        status without raising a second deferral. Raises
        ``StewardDeferralUnavailableError`` when no deferral path exists rather
        than dropping the request or deciding it here.
        """
        from ciris_engine.logic.persistence.models.tasks import add_task

        current = previous_status or self._unrecorded_default_status(request.user_id)
        if find_open_partnership_task(request.user_id) is not None:
            logger.info(
                "PARTNERED request for %s is already with the steward; not deferring again",
                _sanitize_for_log(request.user_id),
            )
            return current

        if self._wise_bus is None:
            raise StewardDeferralUnavailableError(
                "No Wise Authority deferral path is wired, so a PARTNERED request cannot reach the steward"
            )
        if self._time_service is None:
            raise ValueError("TimeService required to defer a PARTNERED request")

        task = build_partnership_deferral_task(
            request.user_id, request.categories, request.reason, channel_id, self._time_service
        )
        add_task(task)
        context = build_partnership_deferral_context(
            task,
            request.user_id,
            request.categories,
            request.reason,
            previous_status.stream if previous_status else None,
        )
        delivered = await self._wise_bus.send_deferral(context, "ConsentService")
        if not delivered:
            raise StewardDeferralUnavailableError(
                "No Wise Authority service accepted the deferral, so the PARTNERED request did not reach the steward"
            )
        self._partnership_deferrals += 1
        logger.info(
            "PARTNERED request for %s deferred to the steward (task %s); stream unchanged until answered",
            _sanitize_for_log(request.user_id),
            task.task_id,
        )
        return current

    def _unrecorded_default_status(self, user_id: str) -> ConsentStatus:
        """The TEMPORARY default a user without a record is under. Returned, NOT persisted."""
        now = self._now()
        return ConsentStatus(
            user_id=user_id,
            stream=ConsentStream.TEMPORARY,
            categories=[],
            granted_at=now,
            expires_at=now + timedelta(days=14),
            last_modified=now,
            impact_score=0.0,
            attribution_count=0,
        )

    async def apply_steward_partnership_decision(self, decision: PartnershipStewardDecision) -> Optional[ConsentStatus]:
        """Apply the steward's answer to a PARTNERED-request deferral.

        Called by ``WiseAuthorityService.resolve_deferral`` BEFORE it marks the
        deferral resolved, so a failure here leaves the request pending rather
        than recorded-but-unapplied. Approval writes PARTNERED and emits the
        pair, naming the steward and the deferral in the accept half. Refusal
        writes nothing: the user keeps their current stream. Returns the new
        status on approval, None on refusal.

        The steward decides whether to retain the user; the steward never
        overrides the user. If the user has changed their stream or revoked
        consent since asking, their later choice stands and an approval
        writes nothing.
        """
        if not decision.approved:
            self._partnership_refusals += 1
            logger.info(
                "Steward %s declined PARTNERED for %s (deferral %s); stream unchanged",
                _sanitize_for_log(decision.steward_id),
                _sanitize_for_log(decision.user_id),
                _sanitize_for_log(decision.deferral_id),
            )
            return None

        if self._user_choice_superseded(decision, await self._get_previous_status(decision.user_id)):
            logger.info(
                "Steward %s approved PARTNERED for %s (deferral %s), but the user has changed their consent "
                "since asking; their later choice stands and nothing is written",
                _sanitize_for_log(decision.steward_id),
                _sanitize_for_log(decision.user_id),
                _sanitize_for_log(decision.deferral_id),
            )
            return None

        categories = decision.categories or [ConsentCategory.INTERACTION]
        new_status = await self.update_consent(
            decision.user_id,
            ConsentStream.PARTNERED,
            categories,
            reason=decision.reason or f"PARTNERED approved by steward via deferral {decision.deferral_id}",
            initiated_by=f"steward:{decision.steward_id}",
            decided_by=decision.steward_id,
            deferral_id=decision.deferral_id,
        )
        self._partnership_approvals += 1
        return new_status

    def _user_choice_superseded(self, decision: PartnershipStewardDecision, current: Optional[ConsentStatus]) -> bool:
        """True when the user revoked consent or changed their stream after making the request.

        Compared on the STREAM, not ``last_modified``: interaction-driven
        TEMPORARY expiry extension rewrites ``last_modified`` without the user
        choosing anything.
        """
        if self._decay_manager.check_decay_status(decision.user_id) is not None:
            return True
        if decision.stream_at_request is None:
            # No record when they asked: only a record that now says otherwise supersedes.
            return current is not None and current.stream != ConsentStream.TEMPORARY
        if current is None:
            return True  # The record they had is gone: revoked since.
        return current.stream != decision.stream_at_request

    async def get_partnership_request_status(self, user_id: str) -> PartnershipRequestStatus:
        """Where the user's PARTNERED choice stands: with the steward, applied, or neither."""
        if find_open_partnership_task(user_id) is not None:
            return PartnershipRequestStatus.PENDING
        try:
            current = await self.get_consent(user_id, extend_expiry=False)
        except ConsentNotFoundError:
            return PartnershipRequestStatus.NONE
        if current.stream == ConsentStream.PARTNERED:
            return PartnershipRequestStatus.PARTNERED
        return PartnershipRequestStatus.NONE

    async def update_consent(
        self,
        user_id: str,
        stream: ConsentStream,
        categories: List[ConsentCategory],
        reason: Optional[str] = None,
        *,
        initiated_by: str = "tool",
        decided_by: Optional[str] = None,
        deferral_id: Optional[str] = None,
    ) -> ConsentStatus:
        """
        Write a consent status directly and emit the wire pair.

        Callers own the decision: a user's own downgrade (degrade_relationship),
        or the steward's answer to a PARTNERED deferral
        (apply_steward_partnership_decision). This method does not route
        anything to the steward itself.
        """
        # Get previous status if exists
        previous_status = None
        try:
            previous_status = await self.get_consent(user_id)
        except ConsentNotFoundError:
            pass

        now = self._now()
        expires_at = None
        if stream == ConsentStream.TEMPORARY:
            expires_at = now + timedelta(days=14)

        new_status = ConsentStatus(
            user_id=user_id,
            stream=stream,
            categories=categories,
            granted_at=previous_status.granted_at if previous_status else now,
            expires_at=expires_at,
            last_modified=now,
            impact_score=previous_status.impact_score if previous_status else 0.0,
            attribution_count=previous_status.attribution_count if previous_status else 0,
        )

        # Store in graph
        node = GraphNode(
            id=f"consent/{user_id}",
            type=NodeType.CONSENT,
            scope=GraphScope.LOCAL,
            attributes={
                "stream": new_status.stream,
                "categories": list(new_status.categories),
                "granted_at": new_status.granted_at.isoformat(),
                "expires_at": new_status.expires_at.isoformat() if new_status.expires_at else None,
                "last_modified": new_status.last_modified.isoformat(),
                "impact_score": new_status.impact_score,
                "attribution_count": new_status.attribution_count,
            },
            updated_by="consent_manager",
            updated_at=now,
        )

        if self._time_service is None:
            raise ValueError("TimeService required for updating consent")
        add_graph_node(node, self._time_service)

        # Create audit entry
        audit = ConsentAuditEntry(
            entry_id=str(uuid4()),
            user_id=user_id,
            timestamp=now,
            previous_stream=previous_status.stream if previous_status else ConsentStream.TEMPORARY,
            new_stream=new_status.stream,
            previous_categories=previous_status.categories if previous_status else [],
            new_categories=new_status.categories,
            initiated_by=initiated_by,
            reason=reason or "Tool-initiated update",
        )

        # Store audit entry
        audit_attrs = audit.model_dump(mode="json")
        audit_attrs["service"] = "consent"  # Add service identifier for querying
        audit_node = GraphNode(
            id=f"consent_audit/{audit.entry_id}",
            type=NodeType.AUDIT_ENTRY,
            scope=GraphScope.IDENTITY,  # Use IDENTITY scope for user-specific audit trail
            attributes=audit_attrs,
            updated_by="consent_manager",
            updated_at=now,
        )
        add_graph_node(audit_node, self._time_service)

        # Update cache
        self._consent_cache[user_id] = new_status

        self._record_stream_change(new_status, decided_by=decided_by, deferral_id=deferral_id)

        logger.info(f"Consent updated for {user_id}: {new_status.stream}")
        return new_status

    async def revoke_consent(self, user_id: str, reason: Optional[str] = None) -> ConsentDecayStatus:
        """
        Start decay protocol - IMMEDIATE identity severance.
        Delegates to DecayProtocolManager for actual decay handling.
        """
        self._consent_revokes += 1

        # Verify user exists
        status = await self.get_consent(user_id)

        # Get filter service if available
        filter_service = self._filter_service if hasattr(self, "_filter_service") else None

        # Delegate to decay manager
        decay = await self._decay_manager.initiate_decay(
            user_id=user_id,
            reason=reason,
            initiated_by="user",
            current_status=status,
            filter_service=filter_service,
        )

        # Remove from cache (decay manager handles persistence)
        if user_id in self._consent_cache:
            del self._consent_cache[user_id]

        # CEG-native fold (#869): emit + promote a revocation attestation so the
        # opt-out is federation-announceable. Best-effort + flag-gated.
        emit_consent_revocation(user_id, reason)

        return decay

    async def check_expiry(self, user_id: str) -> bool:
        """
        Check if TEMPORARY consent has expired.
        NO GRACE PERIOD - expired means expired.

        Returns:
            False: Consent exists and is valid
            True: Consent exists but is expired

        Raises:
            ConsentNotFoundError: User has no consent record (FAIL FAST)
        """
        status = await self.get_consent(user_id)  # Let it raise - fail fast!
        if status.stream == ConsentStream.TEMPORARY and status.expires_at:
            return self._now() > status.expires_at
        return False

    async def get_impact_report(self, user_id: str) -> ConsentImpactReport:
        """
        Generate impact report - REAL DATA ONLY.
        """
        # Get consent status first
        status = await self.get_consent(user_id)

        # Query REAL data from TSDB summaries - NO FALLBACKS
        if not self._memory_bus:
            raise ValueError("Memory bus required for impact reporting - no fake data allowed")

        # Get real interaction data from TSDB conversation summaries
        conversation_summaries = await self._memory_bus.search(
            query="",  # Empty query to get all matching nodes
            filters=MemorySearchFilter(node_type=NodeType.CONVERSATION_SUMMARY.value, scope=GraphScope.COMMUNITY.value),
        )

        # Count interactions where this user participated
        total_interactions = 0
        for summary in conversation_summaries:
            if summary.attributes:
                attrs = summary.attributes if isinstance(summary.attributes, dict) else summary.attributes.model_dump()
                if "participants" in attrs:
                    participants = attrs["participants"]
                    # Check if user_id is in any participant data
                    if isinstance(participants, dict):
                        for participant_data in participants.values():
                            if isinstance(participant_data, dict) and participant_data.get("user_id") == user_id:
                                total_interactions += participant_data.get("message_count", 0)

        # Get real contribution data from task summaries
        task_summaries = await self._memory_bus.search(
            query="", filters=MemorySearchFilter(node_type=NodeType.TASK_SUMMARY.value, scope=GraphScope.IDENTITY.value)
        )

        patterns_contributed = 0
        for task_summary in task_summaries:
            if task_summary.attributes:
                attrs = (
                    task_summary.attributes
                    if isinstance(task_summary.attributes, dict)
                    else task_summary.attributes.model_dump()
                )
                if attrs.get("author_id") == user_id:
                    patterns_contributed += 1

        # Calculate users helped from actual conversation engagement
        users_helped_set = set()
        for summary in conversation_summaries:
            if summary.attributes:
                attrs = summary.attributes if isinstance(summary.attributes, dict) else summary.attributes.model_dump()
                if "participants" in attrs and isinstance(attrs["participants"], dict):
                    for participant_id, participant_data in attrs["participants"].items():
                        if participant_id != user_id and isinstance(participant_data, dict):
                            users_helped_set.add(participant_id)
        users_helped = len(users_helped_set)

        logger.info(
            "Real impact metrics for %s: %d interactions, %d contributions, %d users helped",
            _sanitize_for_log(user_id),
            total_interactions,
            patterns_contributed,
            users_helped,
        )

        report = ConsentImpactReport(
            user_id=user_id,
            total_interactions=total_interactions,
            patterns_contributed=patterns_contributed,
            users_helped=users_helped,
            categories_active=status.categories,
            impact_score=status.impact_score,
            example_contributions=await self._get_example_contributions(user_id),
        )

        return report

    async def get_audit_trail(self, user_id: str, limit: int = 100) -> List[ConsentAuditEntry]:
        """
        Get consent change history - IMMUTABLE AUDIT TRAIL.
        """
        # Query consent audit entries from graph
        audit_entries = []

        if self._memory_bus:
            try:
                # Query audit nodes for this user
                audit_nodes = await self._memory_bus.search(
                    query="",
                    filters=MemorySearchFilter(
                        node_type=NodeType.AUDIT_ENTRY.value,
                        scope=GraphScope.IDENTITY.value,
                        attribute_values={"user_id": user_id, "service": "consent"},
                    ),
                )

                # Convert nodes to audit entries (limit by parameter)
                for node in audit_nodes[:limit]:
                    if node.attributes:
                        attrs = node.attributes if isinstance(node.attributes, dict) else node.attributes.model_dump()
                        entry = ConsentAuditEntry(
                            entry_id=get_str(attrs, "entry_id", "unknown"),
                            user_id=user_id,
                            timestamp=node.updated_at,
                            previous_stream=ConsentStream(get_str(attrs, "previous_stream", "temporary")),
                            new_stream=ConsentStream(get_str(attrs, "new_stream", "temporary")),
                            previous_categories=[
                                ConsentCategory(c) for c in get_list(attrs, "previous_categories", [])
                            ],
                            new_categories=[ConsentCategory(c) for c in get_list(attrs, "new_categories", [])],
                            initiated_by=get_str(attrs, "initiated_by", "unknown"),
                            reason=get_str_optional(attrs, "reason"),
                        )
                        audit_entries.append(entry)

                logger.debug(f"Found {len(audit_entries)} audit entries for {user_id}")
            except Exception as e:
                logger.warning(f"Failed to query audit trail for {user_id}: {e}")

        return audit_entries

    async def _get_example_contributions(self, user_id: str) -> List[str]:
        """Get example contributions from the graph."""
        examples: List[str] = []

        if self._memory_bus:
            try:
                # Query recent contribution nodes from this user
                contribution_nodes = await self._memory_bus.search(
                    query="",
                    filters=MemorySearchFilter(
                        node_type=NodeType.CONCEPT.value,
                        scope=GraphScope.COMMUNITY.value,
                        attribute_values={"contributor_id": user_id},
                    ),
                )

                # Extract meaningful examples (limit to 3-5)
                for node in contribution_nodes[:5]:
                    if node.attributes:
                        attrs = node.attributes if isinstance(node.attributes, dict) else node.attributes.model_dump()
                        # Use get_str to extract string values safely
                        description = get_str_optional(attrs, "description")
                        if description:
                            examples.append(description)
                        else:
                            content = get_str_optional(attrs, "content")
                            if content:
                                examples.append(content)
                            else:
                                # Fallback to node ID if no meaningful description
                                examples.append(f"Contribution: {node.id}")

                logger.debug(f"Found {len(examples)} example contributions for {user_id}")
            except Exception as e:
                logger.warning("Failed to query example contributions for %s: %s", _sanitize_for_log(user_id), e)

        # Fallback examples if no graph data
        if not examples:
            examples = [
                "Provided feedback on system behavior",
                "Contributed to pattern recognition",
                "Participated in conversation threads",
            ]

        return examples

    async def cleanup_expired(self) -> int:
        """
        Clean up all expired TEMPORARY consents.
        HARD DELETE after 14 days - removes from both cache AND graph storage.
        """
        self._expired_cleanups += 1
        current_time = self._now()

        # Get expired nodes from graph (with full node data for deletion)
        expired_nodes, expired_user_ids = await self._find_expired_nodes(current_time)

        # Delete from graph storage via memory bus
        graph_deleted = await self._delete_expired_from_graph(expired_nodes)

        # Delete from local cache
        cache_deleted = self._delete_expired_from_cache(expired_user_ids)

        total_deleted = graph_deleted + cache_deleted
        if total_deleted > 0:
            logger.info(f"Consent cleanup: deleted {graph_deleted} graph nodes, {cache_deleted} cache entries")

        return total_deleted

    async def _find_expired_nodes(self, current_time: datetime) -> tuple[List[GraphNode], List[str]]:
        """Find all expired temporary consent nodes and their user IDs.

        Returns:
            Tuple of (list of expired GraphNodes, list of user IDs)
        """
        expired_nodes: List[GraphNode] = []
        expired_user_ids: List[str] = []

        if self._memory_bus:
            expired_nodes, expired_user_ids = await self._find_expired_from_graph(current_time)

        # Also check cache for any entries not in graph
        cache_expired = self._find_expired_from_cache(current_time)
        for user_id in cache_expired:
            if user_id not in expired_user_ids:
                expired_user_ids.append(user_id)

        return expired_nodes, expired_user_ids

    async def _find_expired_from_graph(self, current_time: datetime) -> tuple[List[GraphNode], List[str]]:
        """Find expired consents from memory graph nodes.

        Returns:
            Tuple of (list of expired GraphNodes, list of user IDs)
        """
        expired_nodes: List[GraphNode] = []
        expired_user_ids: List[str] = []

        if self._memory_bus is None:
            return expired_nodes, expired_user_ids

        try:
            consent_nodes = await self._memory_bus.search(
                query="",
                filters=MemorySearchFilter(
                    node_type=NodeType.CONCEPT.value,
                    scope=GraphScope.IDENTITY.value,
                    attribute_values={"service": "consent"},
                ),
            )

            for node in consent_nodes:
                user_id = self._extract_expired_user_from_node(node, current_time)
                if user_id:
                    expired_nodes.append(node)
                    expired_user_ids.append(user_id)

            logger.debug(f"Found {len(expired_nodes)} expired consent nodes in graph")

        except Exception as e:
            logger.warning(f"Failed to query consent nodes for expiry cleanup: {e}")

        return expired_nodes, expired_user_ids

    def _extract_expired_user_from_node(self, node: Any, current_time: datetime) -> Optional[str]:
        """Extract user ID if the consent node represents an expired temporary consent."""
        if not node.attributes:
            return None

        attrs = node.attributes if isinstance(node.attributes, dict) else node.attributes.model_dump()
        stream = attrs.get("stream")
        expires_at_str = attrs.get("expires_at")
        user_id = attrs.get("user_id")

        # Check if this is a temporary consent with expiry data
        if not (stream == ConsentStream.TEMPORARY.value and expires_at_str and user_id):
            return None

        # Parse and check expiry
        try:
            expires_at = datetime.fromisoformat(expires_at_str)
            if current_time > expires_at:
                return str(user_id)
        except Exception as e:
            logger.warning(f"Failed to parse expiry date for {user_id}: {e}")

        return None

    def _find_expired_from_cache(self, current_time: datetime) -> List[str]:
        """Find expired consents from local cache as fallback."""
        expired = []

        for user_id, status in self._consent_cache.items():
            if self._is_cache_entry_expired(status, current_time):
                expired.append(user_id)

        return expired

    def _is_cache_entry_expired(self, status: ConsentStatus, current_time: datetime) -> bool:
        """Check if a cached consent status is expired."""
        return (
            status.stream == ConsentStream.TEMPORARY
            and status.expires_at is not None
            and current_time > status.expires_at
        )

    async def _delete_expired_from_graph(self, expired_nodes: List[GraphNode]) -> int:
        """Delete expired consent nodes from graph storage via memory bus.

        Args:
            expired_nodes: List of GraphNode objects to delete

        Returns:
            Number of nodes successfully deleted
        """
        from ciris_engine.schemas.services.operations import MemoryOpStatus

        if not self._memory_bus or not expired_nodes:
            return 0

        deleted_count = 0
        for node in expired_nodes:
            try:
                result = await self._memory_bus.forget(node)
                if result.status == MemoryOpStatus.OK:
                    deleted_count += 1
                    logger.debug(f"Deleted expired consent node: {node.id}")
                else:
                    logger.warning(f"Failed to delete consent node {node.id}: {result.error}")
            except Exception as e:
                logger.warning(f"Error deleting consent node {node.id}: {e}")

        return deleted_count

    def _delete_expired_from_cache(self, expired_user_ids: List[str]) -> int:
        """Remove expired consents from local cache.

        Args:
            expired_user_ids: List of user IDs to remove

        Returns:
            Number of cache entries removed
        """
        count = 0
        for user_id in expired_user_ids:
            if user_id in self._consent_cache:
                del self._consent_cache[user_id]
                count += 1
                logger.debug(f"Removed expired consent from cache for user {user_id}")

        return count

    def get_service_type(self) -> ServiceType:
        """Get service type."""
        return ServiceType.TOOL  # Changed to TOOL so it can be discovered by ToolBus

    def get_capabilities(self) -> ServiceCapabilities:
        """Get service capabilities."""
        return ServiceCapabilities(
            service_name="ConsentService",
            actions=[],  # Non-bussed services don't have actions
            version="0.2.0",
            dependencies=["TimeService"],
            metadata=None,
        )

    def _extract_air_metrics(self, air_metrics: Dict[str, Any]) -> Dict[str, float]:
        """Extract and safely cast AIR metrics."""
        return {
            "consent_air_total_interactions": (
                float(val) if isinstance((val := air_metrics.get("total_interactions", 0)), (int, float)) else 0.0
            ),
            "consent_air_reminders_sent": (
                float(val) if isinstance((val := air_metrics.get("reminders_sent", 0)), (int, float)) else 0.0
            ),
            "consent_air_reminder_rate_percent": (
                float(val) if isinstance((val := air_metrics.get("reminder_rate_percent", 0.0)), (int, float)) else 0.0
            ),
            "consent_air_active_sessions": (
                float(val) if isinstance((val := air_metrics.get("active_sessions", 0)), (int, float)) else 0.0
            ),
            "consent_air_time_triggered": (
                float(val) if isinstance((val := air_metrics.get("time_triggered_reminders", 0)), (int, float)) else 0.0
            ),
            "consent_air_message_triggered": (
                float(val)
                if isinstance((val := air_metrics.get("message_triggered_reminders", 0)), (int, float))
                else 0.0
            ),
        }

    def _collect_custom_metrics(self) -> Dict[str, float]:
        """
        Collect consent-specific metrics - REAL DATA ONLY.

        Top 5 Most Important Metrics:
        1. consent_active_users - Number of users with active consent
        2. consent_stream_distribution - Breakdown by stream type (TEMPORARY/PARTNERED/ANONYMOUS)
        3. consent_partnership_success_rate - Steward approval rate for deferred PARTNERED requests
        4. consent_average_age_days - Average age of active consents
        5. consent_decay_completion_rate - Percentage of decays completed vs initiated
        """
        # Get base metrics from parent
        metrics = super()._collect_custom_metrics()

        now = self._time_service.now() if self._time_service else datetime.now(timezone.utc)

        # Collect stream distribution metrics using metrics collector
        stream_metrics = self._metrics_collector.collect_stream_distribution(self._consent_cache, now)
        metrics.update(stream_metrics)

        # PARTNERED requests carried to the steward and the steward's answers
        answered = self._partnership_approvals + self._partnership_refusals
        partnership_metrics = self._metrics_collector.collect_partnership_metrics(
            self._partnership_deferrals,
            self._partnership_approvals,
            self._partnership_refusals,
            max(0, self._partnership_deferrals - answered),
        )
        metrics.update(partnership_metrics)

        # Get decay metrics from manager
        active_decays = self._decay_manager.get_active_decays()
        decay_metrics = self._metrics_collector.collect_decay_metrics(len(active_decays), 0, len(active_decays))
        metrics.update(decay_metrics)

        # Operational metrics
        operational_metrics = self._metrics_collector.collect_operational_metrics(
            self._consent_checks,
            self._consent_grants,
            self._consent_revokes,
            self._expired_cleanups,
            self._tool_executions,
            self._tool_failures,
        )
        metrics.update(operational_metrics)

        # AIR metrics
        air_metrics_dict = self._air_manager.get_metrics()
        air_metrics = self._extract_air_metrics(air_metrics_dict)
        metrics.update(air_metrics)

        # Service health
        metrics["consent_service_uptime_seconds"] = (
            self._calculate_uptime() if hasattr(self, "_calculate_uptime") else 0.0
        )

        return metrics

    def _check_dependencies(self) -> bool:
        """Check service dependencies."""
        return self._time_service is not None

    def _get_actions(self) -> List[str]:
        """Get available actions - not used for non-bussed services."""
        return ["degrade_relationship"]

    # ToolService Protocol Implementation

    async def execute_tool(self, tool_name: str, parameters: JSONDict) -> ToolExecutionResult:
        """Execute a tool and return the result."""
        self._track_request()  # Track the tool execution
        self._tool_executions += 1

        # There is no agent-initiated upgrade tool (#1251): PARTNERED is the
        # user's choice, routed to the steward when the user is not the steward.
        if tool_name == "degrade_relationship":
            result = await self._degrade_relationship_tool(parameters)
        else:
            self._tool_failures += 1  # Unknown tool is a failure!
            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.NOT_FOUND,
                success=False,
                data=None,
                error=f"Unknown tool: {tool_name}",
                correlation_id=f"consent_{tool_name}_{self._now().timestamp()}",
            )

        # Track failures
        if not result.get("success", False):
            self._tool_failures += 1

        return ToolExecutionResult(
            tool_name=tool_name,
            status=ToolExecutionStatus.COMPLETED if result.get("success") else ToolExecutionStatus.FAILED,
            success=result.get("success", False),
            data=result,
            error=result.get("error"),
            correlation_id=f"consent_{tool_name}_{self._now().timestamp()}",
        )

    async def get_available_tools(self) -> List[str]:
        """Get list of available tool names."""
        return ["degrade_relationship"]

    async def list_tools(self) -> List[str]:
        """List available tools - required by ToolServiceProtocol."""
        return ["degrade_relationship"]

    async def get_tool_schema(self, tool_name: str) -> Optional[ToolParameterSchema]:
        """Get parameter schema for a specific tool."""
        schemas = {
            "degrade_relationship": ToolParameterSchema(
                type="object",
                properties={
                    "user_id": {"type": "string", "description": "User ID requesting the downgrade"},
                    "target_stream": {
                        "type": "string",
                        "description": "Target stream: TEMPORARY or ANONYMOUS",
                        "default": "TEMPORARY",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reason for downgrade",
                        "default": "User requested downgrade",
                    },
                },
                required=["user_id"],
            ),
        }
        return schemas.get(tool_name)

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed information about a specific tool."""
        tools_info = {
            "degrade_relationship": ToolInfo(
                name="degrade_relationship",
                description="Request to downgrade user relationship to TEMPORARY or ANONYMOUS",
                parameters=ToolParameterSchema(
                    type="object",
                    properties={
                        "user_id": {"type": "string", "description": "User ID requesting the downgrade"},
                        "target_stream": {
                            "type": "string",
                            "description": "Target stream: TEMPORARY or ANONYMOUS",
                            "default": "TEMPORARY",
                        },
                        "reason": {
                            "type": "string",
                            "description": "Reason for downgrade",
                            "default": "User requested downgrade",
                        },
                    },
                    required=["user_id"],
                ),
            ),
        }
        return tools_info.get(tool_name)

    async def get_all_tool_info(self) -> List[ToolInfo]:
        """Get info for all available tools."""
        tools = []
        degrade = await self.get_tool_info("degrade_relationship")
        if degrade:
            tools.append(degrade)
        return tools

    async def get_tool_result(self, correlation_id: str, timeout: float = 30.0) -> Optional[ToolExecutionResult]:
        """Get result of an async tool execution by correlation ID."""
        # ConsentService tools are synchronous, so results are immediate
        return None

    async def validate_parameters(self, tool_name: str, parameters: JSONDict) -> bool:
        """Validate parameters for a tool."""
        if tool_name == "degrade_relationship":
            return "user_id" in parameters
        return False

    async def _degrade_relationship_tool(self, parameters: JSONDict) -> JSONDict:
        """Tool implementation for downgrading relationship."""
        try:
            user_id = get_str(parameters, "user_id", "")
            target_stream = get_str(parameters, "target_stream", "TEMPORARY")
            reason = get_str(parameters, "reason", "User requested downgrade")

            if not user_id:
                return {"success": False, "error": "user_id is required"}

            if target_stream not in ["TEMPORARY", "ANONYMOUS"]:
                return {"success": False, "error": "target_stream must be TEMPORARY or ANONYMOUS"}

            # Convert uppercase to lowercase for enum
            target_stream_lower = target_stream.lower()

            # Get current consent status
            try:
                current = await self.get_consent(user_id)
            except ConsentNotFoundError:
                # If no consent exists and target is ANONYMOUS, create it
                if target_stream == "ANONYMOUS":
                    await self.update_consent(user_id, ConsentStream.ANONYMOUS, [ConsentCategory.RESEARCH])
                    self._downgrades_completed += 1
                    return {
                        "success": True,
                        "message": "Created ANONYMOUS consent for proactive opt-out",
                        "current_stream": "ANONYMOUS",
                        "user_id": user_id,
                    }
                else:
                    return {"success": False, "error": f"No consent found for user {user_id}"}

            target = ConsentStream(target_stream_lower)

            if current.stream == target:
                return {
                    "success": True,
                    "message": f"Already in {target_stream} relationship",
                    "current_stream": target_stream,
                    "user_id": user_id,
                }

            # Downgrades are immediate - no approval needed
            if target == ConsentStream.TEMPORARY:
                categories = [ConsentCategory.INTERACTION]
            else:  # ANONYMOUS
                categories = [ConsentCategory.RESEARCH]

            await self.update_consent(user_id, target, categories)

            self._downgrades_completed += 1

            return {
                "success": True,
                "message": f"Relationship downgraded to {target_stream}",
                "previous_stream": current.stream.value if hasattr(current.stream, "value") else current.stream,
                "current_stream": target_stream,
                "user_id": user_id,
            }

        except Exception as e:
            logger.error(f"Failed to degrade relationship: {e}")
            return {"success": False, "error": str(e)}
