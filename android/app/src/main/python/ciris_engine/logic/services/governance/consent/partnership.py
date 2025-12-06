"""
Partnership Management - Bilateral Consent System.

Manages partnership requests requiring agent approval.
Philosophy: Mutual consent, transparent approval, no unilateral upgrades.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from ciris_engine.logic.utils.jsondict_helpers import get_dict, get_list, get_str
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.consent.core import (
    ConsentCategory,
    ConsentRequest,
    ConsentStatus,
    ConsentStream,
    PartnershipAgingStatus,
    PartnershipHistory,
    PartnershipMetrics,
    PartnershipOutcome,
    PartnershipOutcomeType,
    PartnershipPriority,
    PartnershipRequest,
)
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


class PartnershipManager:
    """
    Manage bilateral consent partnerships.

    Partnership Flow:
    1. User requests PARTNERED stream
    2. System creates approval task for agent
    3. Agent approves/rejects/defers
    4. System updates consent based on agent decision
    """

    def __init__(self, time_service: TimeServiceProtocol):
        """
        Initialize partnership manager.

        Args:
            time_service: Time service for consistent timestamps
        """
        self._time_service = time_service
        self._pending_partnerships: Dict[str, JSONDict] = {}
        self._partnership_history: Dict[str, List[PartnershipOutcome]] = {}  # user_id -> outcomes

        # Metrics
        self._partnership_requests = 0
        self._partnership_approvals = 0
        self._partnership_rejections = 0
        self._partnership_deferrals = 0

    def _now(self) -> datetime:
        """Get current time from time service."""
        if self._time_service is None:
            return datetime.now(timezone.utc)
        return self._time_service.now()

    def _create_pending_status(self, user_id: str, previous_status: Optional[ConsentStatus]) -> ConsentStatus:
        """Create a pending consent status while partnership is being reviewed."""
        now = self._now()
        return ConsentStatus(
            user_id=user_id,
            stream=previous_status.stream if previous_status else ConsentStream.TEMPORARY,
            categories=previous_status.categories if previous_status else [],
            granted_at=previous_status.granted_at if previous_status else now,
            expires_at=previous_status.expires_at if previous_status else now + timedelta(days=14),
            last_modified=now,
            impact_score=previous_status.impact_score if previous_status else 0.0,
            attribution_count=previous_status.attribution_count if previous_status else 0,
        )

    def _create_partnership_task(
        self, user_id: str, categories: List[ConsentCategory], reason: Optional[str], channel_id: Optional[str]
    ) -> Any:
        """Create partnership approval task."""
        from ciris_engine.logic.utils.consent.partnership_utils import PartnershipRequestHandler

        if self._time_service is None:
            raise ValueError("TimeService required for partnership requests")
        handler = PartnershipRequestHandler(time_service=self._time_service)
        return handler.create_partnership_task(
            user_id=user_id,
            categories=[c.value for c in categories],
            reason=reason,
            channel_id=channel_id,
        )

    def _store_pending_partnership(
        self, user_id: str, task_id: str, request: ConsentRequest, channel_id: Optional[str]
    ) -> None:
        """Store pending partnership request in tracking dict."""
        now = self._now()
        self._pending_partnerships[user_id] = {
            "task_id": task_id,
            "request": request.model_dump(mode="json"),
            "created_at": now.isoformat(),
            "channel_id": channel_id or "unknown",
        }

    async def create_partnership_request(
        self,
        request: ConsentRequest,
        previous_status: Optional[ConsentStatus],
        channel_id: Optional[str],
    ) -> ConsentStatus:
        """
        Create partnership approval request.

        Args:
            request: Consent request for PARTNERED stream
            previous_status: User's previous consent status (if any)
            channel_id: Channel where request originated

        Returns:
            Pending status (stays on current stream until approved)
        """
        # Check if already partnered
        if previous_status and previous_status.stream == ConsentStream.PARTNERED:
            logger.info(f"User {request.user_id} already has PARTNERED consent")
            return previous_status

        # Check for duplicate pending request
        if request.user_id in self._pending_partnerships:
            logger.warning(f"User {request.user_id} already has pending partnership request")
            return self._create_pending_status(request.user_id, previous_status)

        # Track partnership request
        self._partnership_requests += 1

        # Create partnership task for agent approval
        task = self._create_partnership_task(request.user_id, request.categories, request.reason, channel_id)

        # Create pending status (stays on current stream)
        pending_status = self._create_pending_status(request.user_id, previous_status)

        # Store pending partnership request
        self._store_pending_partnership(request.user_id, task.task_id, request, channel_id)

        logger.info(f"Partnership request created for {request.user_id}, task: {task.task_id}")
        return pending_status

    async def check_partnership_status(self, user_id: str) -> Optional[str]:
        """
        Check status of pending partnership request.

        Args:
            user_id: User to check

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
        task_id = get_str(pending, "task_id", "")

        # Check task outcome
        from ciris_engine.logic.utils.consent.partnership_utils import PartnershipRequestHandler

        if self._time_service is None:
            raise ValueError("TimeService required for partnership status check")
        handler = PartnershipRequestHandler(time_service=self._time_service)
        outcome, reason = handler.check_task_outcome(task_id)

        if outcome in ["rejected", "deferred", "failed"]:
            # Remove from pending
            del self._pending_partnerships[user_id]

            # Track outcome
            if outcome == "rejected":
                self._partnership_rejections += 1
            elif outcome == "deferred":
                self._partnership_deferrals += 1

            logger.info(f"Partnership {outcome} for {user_id}: {reason}")
            return outcome

        return "pending"

    def finalize_partnership_approval(self, user_id: str, task_id: str) -> Optional[Dict[str, object]]:
        """
        Finalize an approved partnership (called by ConsentService after agent approval).

        This is used by check_pending_partnership() when the agent approves a request.
        NOT for manual admin bypass - that violates "No Bypass Patterns" philosophy.

        Args:
            user_id: User whose partnership was approved
            task_id: Task ID that was approved

        Returns:
            Dictionary with partnership data for consent update, or None
        """
        if user_id not in self._pending_partnerships:
            logger.warning(f"No pending partnership found for {user_id}")
            return None

        pending = self._pending_partnerships[user_id]
        pending_task_id = get_str(pending, "task_id", "")

        if pending_task_id != task_id:
            logger.warning(f"Task ID mismatch for {user_id}: expected {pending_task_id}, got {task_id}")
            return None

        # Extract request data
        request_dict = get_dict(pending, "request", {})
        categories_data = get_list(request_dict, "categories", [])
        categories = [
            ConsentCategory(c) if isinstance(c, str) else ConsentCategory(c.get("value", "interaction"))
            for c in categories_data
        ]

        # Remove from pending
        del self._pending_partnerships[user_id]

        # Track approval
        self._partnership_approvals += 1

        logger.info(f"Partnership approved for {user_id} via task {task_id}")

        return {
            "user_id": user_id,
            "categories": categories,
            "task_id": task_id,
            "approved_at": self._now(),
        }

    def list_pending_partnerships(self) -> List[Dict[str, object]]:
        """
        Get all pending partnership requests.

        Returns:
            List of pending partnership dictionaries
        """
        pending_list = []
        now = self._now()

        for user_id, pending in self._pending_partnerships.items():
            created_at_str = get_str(pending, "created_at", "")
            created_at = datetime.fromisoformat(created_at_str) if created_at_str else now

            # Calculate age
            age_hours = (now - created_at).total_seconds() / 3600.0
            aging_status = "normal"
            if age_hours > 336:  # 14 days
                aging_status = "critical"
            elif age_hours > 168:  # 7 days
                aging_status = "warning"

            request_dict = get_dict(pending, "request", {})

            pending_list.append(
                {
                    "user_id": user_id,
                    "task_id": get_str(pending, "task_id", ""),
                    "created_at": created_at_str,
                    "age_hours": age_hours,
                    "aging_status": aging_status,
                    "channel_id": get_str(pending, "channel_id", "unknown"),
                    "categories": get_list(request_dict, "categories", []),
                    "reason": get_str(request_dict, "reason", ""),
                }
            )

        # Sort by age (oldest first) - cast to float for type safety
        pending_list.sort(
            key=lambda x: float(x["age_hours"]) if isinstance(x["age_hours"], (int, float)) else 0.0, reverse=True
        )

        return pending_list

    def get_partnership_metrics(self) -> Dict[str, object]:
        """
        Get partnership metrics.

        Returns:
            Dictionary with partnership statistics
        """
        total_requests = self._partnership_requests
        approval_rate = 0.0
        rejection_rate = 0.0
        deferral_rate = 0.0

        if total_requests > 0:
            approval_rate = (self._partnership_approvals / total_requests) * 100.0
            rejection_rate = (self._partnership_rejections / total_requests) * 100.0
            deferral_rate = (self._partnership_deferrals / total_requests) * 100.0

        # Calculate average approval time (from pending list)
        pending_list = self.list_pending_partnerships()
        avg_pending_hours = 0.0
        if pending_list:
            total_hours = sum(
                float(p["age_hours"]) if isinstance(p["age_hours"], (int, float)) else 0.0 for p in pending_list
            )
            avg_pending_hours = total_hours / len(pending_list)

        return {
            "total_requests": total_requests,
            "total_approvals": self._partnership_approvals,
            "total_rejections": self._partnership_rejections,
            "total_deferrals": self._partnership_deferrals,
            "pending_count": len(self._pending_partnerships),
            "approval_rate_percent": approval_rate,
            "rejection_rate_percent": rejection_rate,
            "deferral_rate_percent": deferral_rate,
            "avg_pending_hours": avg_pending_hours,
        }

    def get_pending_count(self) -> int:
        """Get count of pending partnerships."""
        return len(self._pending_partnerships)

    def get_request_counts(self) -> tuple[int, int, int]:
        """
        Get request counts for metrics.

        Returns:
            Tuple of (requests, approvals, rejections)
        """
        return (self._partnership_requests, self._partnership_approvals, self._partnership_rejections)

    def get_partnership_history(self, user_id: str) -> PartnershipHistory:
        """
        Get partnership history for a user.

        Args:
            user_id: User to get history for

        Returns:
            Partnership history with all outcomes
        """
        outcomes = self._partnership_history.get(user_id, [])

        # Determine current status
        current_status = "none"
        if user_id in self._pending_partnerships:
            current_status = "pending"
        elif outcomes:
            # Check if last outcome was approved
            last_outcome = outcomes[-1]
            if last_outcome.outcome_type == PartnershipOutcomeType.APPROVED:
                current_status = "approved"

        # Get timestamps
        last_request_at = None
        last_decision_at = None
        if user_id in self._pending_partnerships:
            pending = self._pending_partnerships[user_id]
            created_at_str = get_str(pending, "created_at", "")
            if created_at_str:
                last_request_at = datetime.fromisoformat(created_at_str)

        if outcomes:
            last_decision_at = outcomes[-1].decided_at
            # If we have outcomes but no last_request_at from pending, use earliest outcome time
            if not last_request_at:
                last_request_at = outcomes[0].decided_at

        return PartnershipHistory(
            user_id=user_id,
            total_requests=len(outcomes) + (1 if user_id in self._pending_partnerships else 0),
            outcomes=outcomes,
            current_status=current_status,
            last_request_at=last_request_at,
            last_decision_at=last_decision_at,
        )

    def list_pending_partnerships_typed(self) -> List[PartnershipRequest]:
        """
        Get all pending partnership requests (typed version).

        Returns:
            List of PartnershipRequest objects
        """
        pending_list = []
        now = self._now()

        for user_id, pending in self._pending_partnerships.items():
            created_at_str = get_str(pending, "created_at", "")
            created_at = datetime.fromisoformat(created_at_str) if created_at_str else now

            # Calculate age
            age_hours = (now - created_at).total_seconds() / 3600.0

            # Determine aging status
            if age_hours > 336:  # 14 days
                aging_status = PartnershipAgingStatus.CRITICAL
            elif age_hours > 168:  # 7 days
                aging_status = PartnershipAgingStatus.WARNING
            else:
                aging_status = PartnershipAgingStatus.NORMAL

            # Parse categories
            request_dict = get_dict(pending, "request", {})
            categories_data = get_list(request_dict, "categories", [])
            categories = [
                ConsentCategory(c) if isinstance(c, str) else ConsentCategory(c.get("value", "interaction"))
                for c in categories_data
            ]

            # Determine priority (could be enhanced with more logic)
            priority = PartnershipPriority.NORMAL
            if age_hours > 168:  # >7 days = high priority
                priority = PartnershipPriority.HIGH

            reason_str = get_str(request_dict, "reason", "")
            pending_list.append(
                PartnershipRequest(
                    user_id=user_id,
                    task_id=get_str(pending, "task_id", ""),
                    categories=categories,
                    reason=reason_str if reason_str else None,
                    channel_id=get_str(pending, "channel_id", "unknown"),
                    created_at=created_at,
                    age_hours=age_hours,
                    aging_status=aging_status,
                    priority=priority,
                )
            )

        # Sort by priority (HIGH first), then age (oldest first)
        pending_list.sort(key=lambda x: (x.priority.value != "high", -x.age_hours))

        return pending_list

    def get_partnership_metrics_typed(self) -> PartnershipMetrics:
        """
        Get partnership metrics (typed version).

        Returns:
            PartnershipMetrics object
        """
        total_requests = self._partnership_requests
        approval_rate = 0.0
        rejection_rate = 0.0
        deferral_rate = 0.0

        if total_requests > 0:
            approval_rate = (self._partnership_approvals / total_requests) * 100.0
            rejection_rate = (self._partnership_rejections / total_requests) * 100.0
            deferral_rate = (self._partnership_deferrals / total_requests) * 100.0

        # Calculate average and oldest pending
        pending_list = self.list_pending_partnerships_typed()
        avg_pending_hours = 0.0
        oldest_pending_hours = 0.0
        critical_count = 0

        if pending_list:
            total_hours = sum(p.age_hours for p in pending_list)
            avg_pending_hours = total_hours / len(pending_list)
            oldest_pending_hours = max(p.age_hours for p in pending_list)
            critical_count = sum(1 for p in pending_list if p.aging_status == PartnershipAgingStatus.CRITICAL)

        return PartnershipMetrics(
            total_requests=total_requests,
            total_approvals=self._partnership_approvals,
            total_rejections=self._partnership_rejections,
            total_deferrals=self._partnership_deferrals,
            pending_count=len(self._pending_partnerships),
            approval_rate_percent=approval_rate,
            rejection_rate_percent=rejection_rate,
            deferral_rate_percent=deferral_rate,
            avg_pending_hours=avg_pending_hours,
            oldest_pending_hours=oldest_pending_hours,
            critical_count=critical_count,
        )

    def cleanup_aged_requests(self, max_age_days: int = 30) -> int:
        """
        Auto-reject partnership requests older than threshold.

        Args:
            max_age_days: Maximum age in days before auto-rejection

        Returns:
            Number of requests auto-rejected
        """
        now = self._now()
        aged_users = []

        for user_id, pending in self._pending_partnerships.items():
            created_at_str = get_str(pending, "created_at", "")
            if not created_at_str:
                continue

            created_at = datetime.fromisoformat(created_at_str)
            age = now - created_at

            if age.days >= max_age_days:
                aged_users.append(user_id)
                task_id = get_str(pending, "task_id", "")

                # Create expired outcome
                outcome = PartnershipOutcome(
                    user_id=user_id,
                    task_id=task_id,
                    outcome_type=PartnershipOutcomeType.EXPIRED,
                    decided_by="system",
                    decided_at=now,
                    reason=f"Auto-rejected: pending for {age.days} days (max: {max_age_days})",
                    notes="Automatically expired due to age",
                )

                # Record in history
                if user_id not in self._partnership_history:
                    self._partnership_history[user_id] = []
                self._partnership_history[user_id].append(outcome)

                logger.warning(
                    f"Auto-rejecting partnership for {user_id}: pending for {age.days} days (max: {max_age_days})"
                )

        # Remove aged requests
        for user_id in aged_users:
            del self._pending_partnerships[user_id]
            self._partnership_rejections += 1

        return len(aged_users)
