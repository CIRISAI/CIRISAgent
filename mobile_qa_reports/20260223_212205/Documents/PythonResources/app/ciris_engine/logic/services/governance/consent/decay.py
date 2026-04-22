"""
Decay Protocol Management - 90-Day Anonymization.

Manages the decay protocol for consent revocation.
Philosophy: Real deletion, phased anonymization, safety-aware retention.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
from uuid import uuid4

from ciris_engine.logic.persistence import add_graph_node
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.consent.core import (
    ConsentAuditEntry,
    ConsentCategory,
    ConsentDecayStatus,
    ConsentStatus,
    ConsentStream,
)
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType

logger = logging.getLogger(__name__)


class DecayProtocolManager:
    """
    Manage 90-day decay protocol for consent revocation.

    Decay Phases:
    1. Identity Severance (Immediate): User ID disconnected from all patterns
    2. Pattern Anonymization (0-90 days): Gradual conversion to anonymous form
    3. Decay Completion (90 days): All user-linked data removed or anonymized
    """

    def __init__(self, time_service: TimeServiceProtocol, db_path: Optional[str] = None):
        """
        Initialize decay protocol manager.

        Args:
            time_service: Time service for consistent timestamps
            db_path: Database path for persistence
        """
        self._time_service = time_service
        self._db_path = db_path
        self._active_decays: Dict[str, ConsentDecayStatus] = {}

    def _now(self) -> datetime:
        """Get current time from time service."""
        if self._time_service is None:
            return datetime.now(timezone.utc)
        return self._time_service.now()

    async def initiate_decay(
        self,
        user_id: str,
        reason: Optional[str],
        initiated_by: str,
        current_status: ConsentStatus,
        filter_service: Optional[object] = None,
    ) -> ConsentDecayStatus:
        """
        Start decay protocol - IMMEDIATE identity severance.

        Args:
            user_id: User requesting deletion
            reason: Reason for deletion
            initiated_by: Who initiated (user/system/dsar)
            current_status: Current consent status
            filter_service: Optional adaptive filter for profile anonymization

        Returns:
            Decay status tracking object
        """
        now = self._now()

        # Trigger anonymization in filter service if available
        if filter_service and hasattr(filter_service, "anonymize_user_profile"):
            await filter_service.anonymize_user_profile(user_id)
            logger.info(f"Triggered filter profile anonymization for {user_id}")

        # Create decay status
        decay = ConsentDecayStatus(
            user_id=user_id,
            decay_started=now,
            identity_severed=True,  # Immediate
            patterns_anonymized=False,  # Over 90 days
            decay_complete_at=now + timedelta(days=90),
            safety_patterns_retained=0,  # Will be calculated during anonymization
        )

        # Store decay status in graph
        decay_node = GraphNode(
            id=f"consent_decay/{user_id}",
            type=NodeType.DECAY,
            scope=GraphScope.LOCAL,
            attributes=decay.model_dump(mode="json"),
            updated_by="consent_manager",
            updated_at=now,
        )
        if self._time_service is None:
            raise ValueError("TimeService required for decay protocol")
        add_graph_node(decay_node, self._time_service, self._db_path)

        # Update consent to expired (identity severed immediately)
        revoked_status = ConsentStatus(
            user_id=user_id,
            stream=ConsentStream.TEMPORARY,
            categories=[],
            granted_at=current_status.granted_at,
            expires_at=now,  # Expired immediately
            last_modified=now,
            impact_score=current_status.impact_score,
            attribution_count=current_status.attribution_count,
        )

        # Store revoked consent
        revoked_node = GraphNode(
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
                "decay_initiated": now.isoformat(),
            },
            updated_by="consent_manager",
            updated_at=now,
        )
        add_graph_node(revoked_node, self._time_service, self._db_path)

        # Create audit entry for decay initiation
        audit = ConsentAuditEntry(
            entry_id=str(uuid4()),
            user_id=user_id,
            timestamp=now,
            previous_stream=current_status.stream,
            new_stream=ConsentStream.TEMPORARY,
            previous_categories=current_status.categories,
            new_categories=[],
            initiated_by=initiated_by,
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

        # Track active decay
        self._active_decays[user_id] = decay

        logger.info(f"Decay protocol started for {user_id}: completes {decay.decay_complete_at}")
        return decay

    def check_decay_status(self, user_id: str) -> Optional[ConsentDecayStatus]:
        """
        Check status of active decay for user.

        Args:
            user_id: User to check

        Returns:
            Decay status if active, None otherwise
        """
        return self._active_decays.get(user_id)

    def get_active_decays(self) -> Dict[str, ConsentDecayStatus]:
        """
        Get all active decay protocols.

        Returns:
            Dictionary of user_id -> decay status
        """
        return self._active_decays.copy()

    async def complete_decay_phase(self, user_id: str, phase: str, safety_patterns_retained: int = 0) -> bool:
        """
        Mark a decay phase as complete.

        Args:
            user_id: User whose decay is progressing
            phase: Phase completed (identity_severed, patterns_anonymized)
            safety_patterns_retained: Number of safety patterns kept (anonymized)

        Returns:
            True if phase update successful, False otherwise
        """
        if user_id not in self._active_decays:
            logger.warning(f"No active decay found for {user_id}")
            return False

        decay = self._active_decays[user_id]
        now = self._now()

        if phase == "patterns_anonymized":
            decay.patterns_anonymized = True
            decay.safety_patterns_retained = safety_patterns_retained

            # Update decay status in graph
            decay_node = GraphNode(
                id=f"consent_decay/{user_id}",
                type=NodeType.DECAY,
                scope=GraphScope.LOCAL,
                attributes=decay.model_dump(mode="json"),
                updated_by="consent_manager",
                updated_at=now,
            )
            if self._time_service is None:
                raise ValueError("TimeService required for decay phase update")
            add_graph_node(decay_node, self._time_service, self._db_path)

            logger.info(
                f"Decay phase '{phase}' completed for {user_id}, "
                f"safety patterns retained: {safety_patterns_retained}"
            )
            return True

        return False

    async def cleanup_completed_decays(self) -> int:
        """
        Clean up decays that have completed (past 90 days).

        Returns:
            Number of decays cleaned up
        """
        now = self._now()
        completed_users = []

        for user_id, decay in self._active_decays.items():
            if now >= decay.decay_complete_at:
                completed_users.append(user_id)

        # Remove completed decays from tracking
        for user_id in completed_users:
            del self._active_decays[user_id]
            logger.info(f"Decay protocol completed and cleaned up for {user_id}")

        return len(completed_users)

    def _determine_decay_phase(self, decay: ConsentDecayStatus) -> str:
        """
        Determine current decay phase based on status.

        Args:
            decay: Decay status to evaluate

        Returns:
            Current phase name
        """
        if decay.patterns_anonymized:
            return "complete"
        if decay.identity_severed:
            return "anonymizing_patterns"
        return "severing_identity"

    def get_decay_progress(self, user_id: str) -> Optional[Dict[str, object]]:
        """
        Get detailed progress information for a decay.

        Args:
            user_id: User to check

        Returns:
            Dictionary with progress details or None
        """
        decay = self.check_decay_status(user_id)
        if not decay:
            return None

        now = self._now()
        days_elapsed = (now - decay.decay_started).days
        days_remaining = (decay.decay_complete_at - now).days
        completion_percentage = min((days_elapsed / 90.0) * 100.0, 100.0)

        return {
            "user_id": user_id,
            "started": decay.decay_started.isoformat(),
            "completes": decay.decay_complete_at.isoformat(),
            "days_elapsed": days_elapsed,
            "days_remaining": max(days_remaining, 0),
            "completion_percentage": completion_percentage,
            "identity_severed": decay.identity_severed,
            "patterns_anonymized": decay.patterns_anonymized,
            "safety_patterns_retained": decay.safety_patterns_retained,
            "current_phase": self._determine_decay_phase(decay),
        }

    def get_decay_milestones(self, user_id: str) -> Optional[Dict[str, str]]:
        """
        Get milestone dates for a decay protocol.

        Args:
            user_id: User to check

        Returns:
            Dictionary with milestone dates or None
        """
        decay = self.check_decay_status(user_id)
        if not decay:
            return None

        day_30 = decay.decay_started + timedelta(days=30)
        day_60 = decay.decay_started + timedelta(days=60)

        return {
            "initiated": decay.decay_started.strftime("%Y-%m-%d"),
            "one_third_complete": day_30.strftime("%Y-%m-%d"),
            "two_thirds_complete": day_60.strftime("%Y-%m-%d"),
            "completion": decay.decay_complete_at.strftime("%Y-%m-%d"),
        }
