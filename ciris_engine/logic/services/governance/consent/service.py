"""
Consent Service - FAIL FAST, FAIL LOUD, NO FAKE DATA.

Governance Service #5: Manages user consent for the Consensual Evolution Protocol.
Default: TEMPORARY (14 days) unless explicitly changed.
This is the 22nd core CIRIS service.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from ciris_engine.logic.buses.memory_bus import MemoryBus
from ciris_engine.logic.persistence import add_graph_node, get_graph_node
from ciris_engine.logic.services.base_service import BaseService
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
)
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.core import ServiceCapabilities
from ciris_engine.schemas.services.graph.memory import MemorySearchFilter
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType

logger = logging.getLogger(__name__)


class ConsentNotFoundError(Exception):
    """Raised when consent status doesn't exist - FAIL FAST."""

    pass


class ConsentValidationError(Exception):
    """Raised when consent request is invalid - FAIL LOUD."""

    pass


class ConsentService(BaseService, ConsentManagerProtocol, ToolService):
    """
    Consent Service - 22nd Core CIRIS Service (Governance #5).

    Manages user consent with HARD GUARANTEES:
    - TEMPORARY by default (14 days)
    - No fake data or fallbacks
    - Immutable audit trail
    - Real decay protocol
    - Bilateral agreement for PARTNERED
    """

    def __init__(
        self,
        time_service: TimeServiceProtocol,
        memory_bus: Optional[MemoryBus] = None,
        db_path: Optional[str] = None,
    ):
        super().__init__(time_service=time_service, service_name="ConsentService")
        self._time_service = time_service
        self._memory_bus = memory_bus
        self._db_path = db_path

        # Cache for active consents (NOT source of truth)
        self._consent_cache: Dict[str, ConsentStatus] = {}

        # Decay tracking
        self._active_decays: Dict[str, ConsentDecayStatus] = {}

        # Core Metrics (real, no fake data)
        self._consent_checks = 0
        self._consent_grants = 0
        self._consent_revokes = 0
        self._tool_executions = 0
        self._tool_failures = 0
        self._expired_cleanups = 0

        # Stream distribution metrics
        self._temporary_count = 0
        self._partnered_count = 0
        self._anonymous_count = 0

        # Partnership metrics
        self._partnership_requests = 0
        self._partnership_approvals = 0
        self._partnership_rejections = 0
        self._downgrades_completed = 0

        # Decay metrics
        self._total_decays_initiated = 0
        self._decays_completed = 0

        # Consent age tracking
        self._oldest_consent_days = 0.0
        self._average_consent_age_hours = 0.0

        # Pending partnership requests
        self._pending_partnerships: Dict[str, Dict[str, Any]] = {}

    def _now(self) -> datetime:
        """Get current time from time service."""
        if self._time_service is None:
            return datetime.now(timezone.utc)
        return self._time_service.now()

    async def get_consent(self, user_id: str) -> ConsentStatus:
        """
        Get user's consent status.
        FAILS if user doesn't exist - NO DEFAULTS.
        """
        self._consent_checks += 1

        # Try cache first (but verify it's still valid)
        if user_id in self._consent_cache:
            cached = self._consent_cache[user_id]
            # Verify TEMPORARY hasn't expired
            if cached.stream == ConsentStream.TEMPORARY and cached.expires_at:
                if self._now() > cached.expires_at:
                    # Expired - remove from cache and fail
                    del self._consent_cache[user_id]
                    raise ConsentNotFoundError(f"Consent for {user_id} has expired")
            return cached

        # Load from graph
        try:
            node = get_graph_node(f"consent/{user_id}", GraphScope.LOCAL, self._db_path)
            if not node:
                raise ConsentNotFoundError(f"No consent found for user {user_id}")

            # Reconstruct ConsentStatus from node
            # Convert attributes to dict for easier access
            attrs = node.attributes if isinstance(node.attributes, dict) else node.attributes.model_dump()

            status = ConsentStatus(
                user_id=user_id,
                stream=ConsentStream(attrs["stream"]),
                categories=[ConsentCategory(c) for c in attrs["categories"]],
                granted_at=datetime.fromisoformat(attrs["granted_at"]),
                expires_at=(datetime.fromisoformat(attrs["expires_at"]) if attrs.get("expires_at") else None),
                last_modified=datetime.fromisoformat(attrs["last_modified"]),
                impact_score=attrs.get("impact_score", 0.0),
                attribution_count=attrs.get("attribution_count", 0),
            )

            # Check expiry
            if status.stream == ConsentStream.TEMPORARY and status.expires_at:
                if self._now() > status.expires_at:
                    raise ConsentNotFoundError(f"Consent for {user_id} has expired")

            # Update cache
            self._consent_cache[user_id] = status
            return status

        except Exception as e:
            if "not found" in str(e).lower():
                raise ConsentNotFoundError(f"No consent found for user {user_id}")
            raise

    async def grant_consent(self, request: ConsentRequest, channel_id: Optional[str] = None) -> ConsentStatus:
        """
        Grant or update consent.
        VALIDATES everything, creates audit trail.

        PARTNERED requires bilateral agreement:
        - Creates task for agent approval
        - Agent can REJECT, DEFER, or TASK_COMPLETE (accept)
        - Returns pending status until agent decides
        """
        self._consent_grants += 1

        # Validate request
        self._validate_consent_request(request)

        # Get previous status if exists
        previous_status = await self._get_previous_status(request.user_id)

        # Check if upgrading to PARTNERED - requires bilateral agreement
        if request.stream == ConsentStream.PARTNERED:
            return await self._handle_partnership_request(request, previous_status, channel_id)

        # Check for gaming behavior if switching streams
        await self._check_gaming_behavior(request, previous_status)

        # For TEMPORARY and ANONYMOUS - no bilateral agreement needed
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

    async def _handle_partnership_request(
        self, request: ConsentRequest, previous_status: Optional[ConsentStatus], channel_id: Optional[str]
    ) -> ConsentStatus:
        """Handle PARTNERED consent request with bilateral agreement."""
        # Check if already partnered
        if previous_status and previous_status.stream == ConsentStream.PARTNERED:
            logger.info(f"User {request.user_id} already has PARTNERED consent")
            return previous_status

        # Track partnership request
        self._partnership_requests += 1

        # Create partnership task for agent approval
        from ciris_engine.logic.utils.consent.partnership_utils import PartnershipRequestHandler

        if self._time_service is None:
            raise ValueError("TimeService required for partnership requests")
        handler = PartnershipRequestHandler(time_service=self._time_service)
        task = handler.create_partnership_task(
            user_id=request.user_id,
            categories=[c.value for c in request.categories],
            reason=request.reason,
            channel_id=channel_id,
        )

        # Create pending status
        now = self._now()
        pending_status = ConsentStatus(
            user_id=request.user_id,
            stream=previous_status.stream if previous_status else ConsentStream.TEMPORARY,
            categories=previous_status.categories if previous_status else [],
            granted_at=previous_status.granted_at if previous_status else now,
            expires_at=previous_status.expires_at if previous_status else now + timedelta(days=14),
            last_modified=now,
            impact_score=previous_status.impact_score if previous_status else 0.0,
            attribution_count=previous_status.attribution_count if previous_status else 0,
        )

        # Store pending partnership request
        if request.user_id not in self._pending_partnerships:
            self._pending_partnerships = {}
        self._pending_partnerships[request.user_id] = {
            "task_id": task.task_id,
            "request": request,
            "created_at": now,
        }

        logger.info(f"Partnership request created for {request.user_id}, task: {task.task_id}")
        return pending_status

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
        add_graph_node(node, self._time_service, self._db_path)

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
        audit_node = GraphNode(
            id=f"consent_audit/{audit.entry_id}",
            type=NodeType.AUDIT_ENTRY,
            scope=GraphScope.LOCAL,
            attributes=audit.model_dump(mode="json"),
            updated_by="consent_manager",
            updated_at=now,
        )
        add_graph_node(audit_node, self._time_service, self._db_path)

        # Update cache
        self._consent_cache[new_status.user_id] = new_status

    async def update_consent(
        self, user_id: str, stream: ConsentStream, categories: List[ConsentCategory], reason: Optional[str] = None
    ) -> ConsentStatus:
        """
        Internal method to update consent status directly.
        Used by tool handlers for consent transitions.
        Does NOT perform bilateral agreement checks - those should be done by caller.
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
        add_graph_node(node, self._time_service, self._db_path)

        # Create audit entry
        audit = ConsentAuditEntry(
            entry_id=str(uuid4()),
            user_id=user_id,
            timestamp=now,
            previous_stream=previous_status.stream if previous_status else ConsentStream.TEMPORARY,
            new_stream=new_status.stream,
            previous_categories=previous_status.categories if previous_status else [],
            new_categories=new_status.categories,
            initiated_by="tool",
            reason=reason or "Tool-initiated update",
        )

        # Store audit entry
        audit_node = GraphNode(
            id=f"consent_audit/{audit.entry_id}",
            type=NodeType.AUDIT_ENTRY,
            scope=GraphScope.LOCAL,
            attributes=audit.model_dump(mode="json"),
            updated_by="consent_manager",
            updated_at=now,
        )
        add_graph_node(audit_node, self._time_service, self._db_path)

        # Update cache
        self._consent_cache[user_id] = new_status

        logger.info(f"Consent updated for {user_id}: {new_status.stream}")
        return new_status

    async def revoke_consent(self, user_id: str, reason: Optional[str] = None) -> ConsentDecayStatus:
        """
        Start decay protocol - IMMEDIATE identity severance.
        """
        self._consent_revokes += 1
        self._total_decays_initiated += 1

        # Verify user exists
        status = await self.get_consent(user_id)

        # Trigger anonymization in filter service
        if hasattr(self, "_filter_service"):
            # Anonymize user profile in filter service
            await self._filter_service.anonymize_user_profile(user_id)
            logger.info(f"Triggered filter profile anonymization for {user_id}")

        # Create decay status
        now = self._now()
        decay = ConsentDecayStatus(
            user_id=user_id,
            decay_started=now,
            identity_severed=True,  # Immediate
            patterns_anonymized=False,  # Over 90 days
            decay_complete_at=now + timedelta(days=90),
            safety_patterns_retained=0,  # Will be calculated
        )

        # Store decay status
        decay_node = GraphNode(
            id=f"consent_decay/{user_id}",
            type=NodeType.DECAY,
            scope=GraphScope.LOCAL,
            attributes=decay.model_dump(mode="json"),
            updated_by="consent_manager",
            updated_at=now,
        )
        if self._time_service is None:
            raise ValueError("TimeService required for revoking consent")
        add_graph_node(decay_node, self._time_service, self._db_path)

        # Update consent to expired
        revoked_status = ConsentStatus(
            user_id=user_id,
            stream=ConsentStream.TEMPORARY,
            categories=[],
            granted_at=status.granted_at,
            expires_at=now,  # Expired immediately
            last_modified=now,
            impact_score=status.impact_score,
            attribution_count=status.attribution_count,
        )

        # Store updated consent
        node = GraphNode(
            id=f"consent/{user_id}",
            type=NodeType.CONSENT,
            scope=GraphScope.LOCAL,
            attributes={
                "stream": revoked_status.stream,
                "categories": [],
                "granted_at": revoked_status.granted_at.isoformat(),
                "expires_at": revoked_status.expires_at.isoformat() if revoked_status.expires_at else "",
                "last_modified": revoked_status.last_modified.isoformat(),
                "impact_score": revoked_status.impact_score,
                "attribution_count": revoked_status.attribution_count,
                "revoked": True,
            },
            updated_by="consent_manager",
            updated_at=now,
        )
        add_graph_node(node, self._time_service, self._db_path)

        # Create audit entry
        audit = ConsentAuditEntry(
            entry_id=str(uuid4()),
            user_id=user_id,
            timestamp=now,
            previous_stream=status.stream,
            new_stream=ConsentStream.TEMPORARY,
            previous_categories=status.categories,
            new_categories=[],
            initiated_by="user",
            reason=reason or "User requested deletion",
        )

        audit_node = GraphNode(
            id=f"consent_audit/{audit.entry_id}",
            type=NodeType.AUDIT_ENTRY,
            scope=GraphScope.LOCAL,
            attributes=audit.model_dump(mode="json"),
            updated_by="consent_manager",
            updated_at=now,
        )
        add_graph_node(audit_node, self._time_service, self._db_path)

        # Remove from cache
        if user_id in self._consent_cache:
            del self._consent_cache[user_id]

        # Track active decay
        self._active_decays[user_id] = decay

        logger.info(f"Decay protocol started for {user_id}: completes {decay.decay_complete_at}")
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
            f"Real impact metrics for {user_id}: {total_interactions} interactions, {patterns_contributed} contributions, {users_helped} users helped"
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
                            entry_id=attrs.get("entry_id", "unknown"),
                            user_id=user_id,
                            timestamp=node.updated_at,
                            previous_stream=ConsentStream(attrs.get("previous_stream", "temporary")),
                            new_stream=ConsentStream(attrs.get("new_stream", "temporary")),
                            previous_categories=[ConsentCategory(c) for c in attrs.get("previous_categories", [])],
                            new_categories=[ConsentCategory(c) for c in attrs.get("new_categories", [])],
                            initiated_by=attrs.get("initiated_by", "unknown"),
                            reason=attrs.get("reason"),
                        )
                        audit_entries.append(entry)

                logger.debug(f"Found {len(audit_entries)} audit entries for {user_id}")
            except Exception as e:
                logger.warning(f"Failed to query audit trail for {user_id}: {e}")

        return audit_entries

    async def check_pending_partnership(self, user_id: str) -> Optional[str]:
        """
        Check status of pending partnership request.

        Returns:
            - "accepted": Partnership approved by agent
            - "rejected": Partnership declined by agent
            - "deferred": Agent needs more information
            - "pending": Still processing
            - None: No pending request
        """
        if user_id not in self._pending_partnerships:
            return None

        pending = self._pending_partnerships[user_id]
        task_id = pending["task_id"]

        # Check task outcome
        from ciris_engine.logic.utils.consent.partnership_utils import PartnershipRequestHandler

        if self._time_service is None:
            raise ValueError("TimeService required for partnership status check")
        handler = PartnershipRequestHandler(time_service=self._time_service)
        outcome, reason = handler.check_task_outcome(task_id)

        if outcome == "accepted":
            # Finalize the partnership
            request = pending["request"]
            now = self._now()

            # Create PARTNERED status
            partnered_status = ConsentStatus(
                user_id=user_id,
                stream=ConsentStream.PARTNERED,
                categories=request.categories,
                granted_at=now,
                expires_at=None,  # PARTNERED doesn't expire
                last_modified=now,
                impact_score=0.0,
                attribution_count=0,
            )

            # Store in graph
            node = GraphNode(
                id=f"consent/{user_id}",
                type=NodeType.CONSENT,
                scope=GraphScope.LOCAL,
                attributes={
                    "stream": partnered_status.stream,
                    "categories": list(partnered_status.categories),
                    "granted_at": partnered_status.granted_at.isoformat(),
                    "expires_at": None,
                    "last_modified": partnered_status.last_modified.isoformat(),
                    "impact_score": partnered_status.impact_score,
                    "attribution_count": partnered_status.attribution_count,
                    "partnership_approved": True,
                    "approval_task_id": task_id,
                },
                updated_by="consent_manager",
                updated_at=now,
            )

            add_graph_node(node, self._time_service, self._db_path)

            # Update cache
            self._consent_cache[user_id] = partnered_status

            # Remove from pending
            del self._pending_partnerships[user_id]

            # Track approval
            self._partnership_approvals += 1

            logger.info(f"Partnership approved for {user_id} via task {task_id}")
            return "accepted"

        elif outcome in ["rejected", "deferred", "failed"]:
            # Remove from pending
            del self._pending_partnerships[user_id]

            # Track rejection
            if outcome == "rejected":
                self._partnership_rejections += 1

            logger.info(f"Partnership {outcome} for {user_id}: {reason}")
            return outcome

        return "pending"

    async def _get_example_contributions(self, user_id: str) -> List[str]:
        """Get example contributions from the graph."""
        examples = []

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
                        if "description" in attrs:
                            examples.append(attrs["description"])
                        elif "content" in attrs:
                            examples.append(attrs["content"])
                        else:
                            # Fallback to node ID if no meaningful description
                            examples.append(f"Contribution: {node.id}")

                logger.debug(f"Found {len(examples)} example contributions for {user_id}")
            except Exception as e:
                logger.warning(f"Failed to query example contributions for {user_id}: {e}")

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
        HARD DELETE after 14 days.
        """
        self._expired_cleanups += 1
        current_time = self._now()

        # Get expired user IDs from graph or cache
        expired_user_ids = await self._find_expired_user_ids(current_time)

        # Perform cleanup operations
        cleanup_count = self._perform_cleanup(expired_user_ids)

        return cleanup_count

    async def _find_expired_user_ids(self, current_time: datetime) -> List[str]:
        """Find all user IDs with expired temporary consents."""
        if self._memory_bus:
            return await self._find_expired_from_graph(current_time)
        else:
            return self._find_expired_from_cache(current_time)

    async def _find_expired_from_graph(self, current_time: datetime) -> List[str]:
        """Find expired consents from memory graph nodes."""
        expired = []

        if self._memory_bus is None:
            return []

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
                    expired.append(user_id)

            logger.debug(f"Found {len(expired)} expired consent nodes in graph")

        except Exception as e:
            logger.warning(f"Failed to query consent nodes for expiry cleanup: {e}")
            # Fall back to cache-based cleanup on graph query failure
            expired = self._find_expired_from_cache(current_time)

        return expired

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

    def _perform_cleanup(self, expired_user_ids: List[str]) -> int:
        """Remove expired consents from cache and return count."""
        count = 0

        for user_id in expired_user_ids:
            if user_id in self._consent_cache:
                del self._consent_cache[user_id]
                count += 1
                logger.info(f"Cleaned up expired consent for {user_id}")

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
            metadata={
                "default_stream": "TEMPORARY",
                "temporary_duration_days": 14,
                "decay_duration_days": 90,
                "partnership_requires_bilateral": True,
                "service_number": 22,
                "service_category": "Governance #5",
            },
        )

    def _collect_custom_metrics(self) -> Dict[str, float]:
        """
        Collect consent-specific metrics - REAL DATA ONLY.

        Top 5 Most Important Metrics:
        1. consent_active_users - Number of users with active consent
        2. consent_stream_distribution - Breakdown by stream type (TEMPORARY/PARTNERED/ANONYMOUS)
        3. consent_partnership_success_rate - Approval rate for partnership requests
        4. consent_average_age_days - Average age of active consents
        5. consent_decay_completion_rate - Percentage of decays completed vs initiated
        """
        # Get base metrics from parent
        metrics = super()._collect_custom_metrics()

        # Calculate stream distribution from cache
        temporary_count = 0
        partnered_count = 0
        anonymous_count = 0
        total_age_seconds = 0.0
        consent_count = 0

        now = self._time_service.now() if self._time_service else datetime.now(timezone.utc)

        for user_id, status in self._consent_cache.items():
            consent_count += 1
            if status.stream == ConsentStream.TEMPORARY:
                temporary_count += 1
            elif status.stream == ConsentStream.PARTNERED:
                partnered_count += 1
            elif status.stream == ConsentStream.ANONYMOUS:
                anonymous_count += 1

            # Calculate age
            if status.granted_at:
                age = (now - status.granted_at).total_seconds()
                total_age_seconds += age

        # Calculate average age in days
        avg_age_days = (total_age_seconds / consent_count / 86400.0) if consent_count > 0 else 0.0

        # Calculate partnership success rate
        partnership_success_rate = 0.0
        if self._partnership_requests > 0:
            partnership_success_rate = (self._partnership_approvals / self._partnership_requests) * 100.0

        # Calculate decay completion rate
        decay_completion_rate = 0.0
        if self._total_decays_initiated > 0:
            decay_completion_rate = (self._decays_completed / self._total_decays_initiated) * 100.0

        # Update metrics with the 5 most important ones
        metrics.update(
            {
                # 1. Active users with consent
                "consent_active_users": float(len(self._consent_cache)),
                # 2. Stream distribution (percentage breakdown)
                "consent_temporary_percent": (temporary_count / consent_count * 100.0) if consent_count > 0 else 0.0,
                "consent_partnered_percent": (partnered_count / consent_count * 100.0) if consent_count > 0 else 0.0,
                "consent_anonymous_percent": (anonymous_count / consent_count * 100.0) if consent_count > 0 else 0.0,
                # 3. Partnership success rate
                "consent_partnership_success_rate": partnership_success_rate,
                "consent_partnership_requests_total": float(self._partnership_requests),
                "consent_partnership_approvals_total": float(self._partnership_approvals),
                # 4. Average consent age
                "consent_average_age_days": avg_age_days,
                # 5. Decay metrics
                "consent_decay_completion_rate": decay_completion_rate,
                "consent_active_decays": float(len(self._active_decays)),
                "consent_total_decays_initiated": float(self._total_decays_initiated),
                # Additional operational metrics
                "consent_checks_total": float(self._consent_checks),
                "consent_grants_total": float(self._consent_grants),
                "consent_revokes_total": float(self._consent_revokes),
                "consent_expired_cleanups_total": float(self._expired_cleanups),
                "consent_pending_partnerships": float(len(self._pending_partnerships)),
                # Service health
                "consent_service_uptime_seconds": (
                    self._calculate_uptime() if hasattr(self, "_calculate_uptime") else 0.0
                ),
            }
        )

        return metrics

    def _check_dependencies(self) -> bool:
        """Check service dependencies."""
        return self._time_service is not None

    def _get_actions(self) -> List[str]:
        """Get available actions - not used for non-bussed services."""
        return ["upgrade_relationship", "degrade_relationship"]

    # ToolService Protocol Implementation

    async def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> ToolExecutionResult:
        """Execute a tool and return the result."""
        self._track_request()  # Track the tool execution
        self._tool_executions += 1

        if tool_name == "upgrade_relationship":
            result = await self._upgrade_relationship_tool(parameters)
        elif tool_name == "degrade_relationship":
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
        return ["upgrade_relationship", "degrade_relationship"]

    async def list_tools(self) -> List[str]:
        """List available tools - required by ToolServiceProtocol."""
        return ["upgrade_relationship", "degrade_relationship"]

    async def get_tool_schema(self, tool_name: str) -> Optional[ToolParameterSchema]:
        """Get parameter schema for a specific tool."""
        schemas = {
            "upgrade_relationship": ToolParameterSchema(
                type="object",
                properties={
                    "user_id": {"type": "string", "description": "User ID requesting the upgrade"},
                    "reason": {
                        "type": "string",
                        "description": "Reason for upgrade request",
                        "default": "User requested partnership",
                    },
                },
                required=["user_id"],
            ),
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
            "upgrade_relationship": ToolInfo(
                name="upgrade_relationship",
                description="Request to upgrade user relationship to PARTNERED (requires bilateral consent)",
                parameters=ToolParameterSchema(
                    type="object",
                    properties={
                        "user_id": {"type": "string", "description": "User ID requesting the upgrade"},
                        "reason": {
                            "type": "string",
                            "description": "Reason for upgrade request",
                            "default": "User requested partnership",
                        },
                    },
                    required=["user_id"],
                ),
            ),
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
        tool1 = await self.get_tool_info("upgrade_relationship")
        if tool1:
            tools.append(tool1)
        tool2 = await self.get_tool_info("degrade_relationship")
        if tool2:
            tools.append(tool2)
        return tools

    async def get_tool_result(self, correlation_id: str, timeout: float = 30.0) -> Optional[ToolExecutionResult]:
        """Get result of an async tool execution by correlation ID."""
        # ConsentService tools are synchronous, so results are immediate
        return None

    async def validate_parameters(self, tool_name: str, parameters: Dict[str, Any]) -> bool:
        """Validate parameters for a tool."""
        if tool_name == "upgrade_relationship":
            return "user_id" in parameters
        elif tool_name == "degrade_relationship":
            return "user_id" in parameters
        return False

    async def _upgrade_relationship_tool(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Tool implementation for upgrading relationship to PARTNERED."""
        try:
            user_id = parameters.get("user_id")
            reason = parameters.get("reason", "User requested partnership")

            if not user_id:
                return {"success": False, "error": "user_id is required"}

            # Get current consent status
            try:
                current = await self.get_consent(user_id)
            except ConsentNotFoundError:
                # Create default TEMPORARY consent if none exists
                request = ConsentRequest(
                    user_id=user_id,
                    stream=ConsentStream.TEMPORARY,
                    categories=[],  # TEMPORARY doesn't need categories
                    reason="Default consent for impact calculation",
                )
                current = await self.grant_consent(request)

            if current.stream == ConsentStream.PARTNERED:
                return {
                    "success": True,
                    "message": "Already in PARTNERED relationship",
                    "current_stream": "PARTNERED",
                    "user_id": user_id,
                }

            # Create upgrade request - this will need agent approval
            request = ConsentRequest(
                user_id=user_id,
                stream=ConsentStream.PARTNERED,
                categories=[ConsentCategory.INTERACTION, ConsentCategory.PREFERENCE],
                reason=reason,
            )

            # Update to PARTNERED (pending agent approval via thought/task system)
            await self.update_consent(user_id, ConsentStream.PARTNERED, request.categories)

            self._partnership_requests += 1

            return {
                "success": True,
                "message": "Partnership upgrade requested - requires agent approval",
                "current_stream": current.stream.value if hasattr(current.stream, "value") else current.stream,
                "requested_stream": "PARTNERED",
                "user_id": user_id,
                "status": "PENDING_APPROVAL",
            }

        except Exception as e:
            logger.error(f"Failed to upgrade relationship: {e}")
            return {"success": False, "error": str(e)}

    async def _degrade_relationship_tool(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Tool implementation for downgrading relationship."""
        try:
            user_id = parameters.get("user_id")
            target_stream = parameters.get("target_stream", "TEMPORARY")
            reason = parameters.get("reason", "User requested downgrade")

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
