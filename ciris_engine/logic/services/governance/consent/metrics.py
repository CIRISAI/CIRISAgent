"""
Consent Metrics Collection - REAL DATA ONLY.

Metrics collector for consent service operations.
Philosophy: No fake data, calculate from actual state.
"""

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Dict

from ciris_engine.schemas.consent.core import ConsentStream, DecayCounters, OperationalCounters, PartnershipCounters

if TYPE_CHECKING:
    from ciris_engine.schemas.consent.core import ConsentStatus

logger = logging.getLogger(__name__)


class ConsentMetricsCollector:
    """
    Collect consent-specific metrics from real service state.

    Top 5 Most Important Metrics:
    1. consent_active_users - Number of users with active consent
    2. consent_stream_distribution - Breakdown by stream type
    3. consent_partnership_success_rate - Approval rate for partnership requests
    4. consent_average_age_days - Average age of active consents
    5. consent_decay_completion_rate - Percentage of decays completed vs initiated
    """

    def __init__(self) -> None:
        """Initialize metrics collector."""
        pass

    def collect_stream_distribution(self, consent_cache: Dict[str, "ConsentStatus"], now: datetime) -> Dict[str, float]:
        """
        Calculate stream distribution metrics from consent cache.

        Args:
            consent_cache: Current consent cache
            now: Current timestamp

        Returns:
            Dictionary with stream distribution metrics
        """
        temporary_count = 0
        partnered_count = 0
        anonymous_count = 0
        total_age_seconds = 0.0
        consent_count = 0

        for user_id, status in consent_cache.items():
            consent_count += 1

            # Count by stream type
            if status.stream == ConsentStream.TEMPORARY:
                temporary_count += 1
            elif status.stream == ConsentStream.PARTNERED:
                partnered_count += 1
            elif status.stream == ConsentStream.ANONYMOUS:
                anonymous_count += 1

            # Calculate age for average
            if status.granted_at:
                age = (now - status.granted_at).total_seconds()
                total_age_seconds += age

        # Calculate average age in days
        avg_age_days = (total_age_seconds / consent_count / 86400.0) if consent_count > 0 else 0.0

        return {
            "consent_active_users": float(len(consent_cache)),
            "consent_temporary_percent": (temporary_count / consent_count * 100.0) if consent_count > 0 else 0.0,
            "consent_partnered_percent": (partnered_count / consent_count * 100.0) if consent_count > 0 else 0.0,
            "consent_anonymous_percent": (anonymous_count / consent_count * 100.0) if consent_count > 0 else 0.0,
            "consent_average_age_days": avg_age_days,
        }

    def collect_partnership_metrics(
        self,
        partnership_requests: int,
        partnership_approvals: int,
        partnership_rejections: int,
        pending_partnerships_count: int,
    ) -> Dict[str, float]:
        """
        Calculate partnership-related metrics.

        Args:
            partnership_requests: Total partnership requests
            partnership_approvals: Total approvals
            partnership_rejections: Total rejections
            pending_partnerships_count: Current pending count

        Returns:
            Dictionary with partnership metrics
        """
        partnership_success_rate = 0.0
        if partnership_requests > 0:
            partnership_success_rate = (partnership_approvals / partnership_requests) * 100.0

        return {
            "consent_partnership_success_rate": partnership_success_rate,
            "consent_partnership_requests_total": float(partnership_requests),
            "consent_partnership_approvals_total": float(partnership_approvals),
            "consent_partnership_rejections_total": float(partnership_rejections),
            "consent_pending_partnerships": float(pending_partnerships_count),
        }

    def collect_decay_metrics(
        self, total_decays_initiated: int, decays_completed: int, active_decays_count: int
    ) -> Dict[str, float]:
        """
        Calculate decay protocol metrics.

        Args:
            total_decays_initiated: Total decays started
            decays_completed: Total decays finished
            active_decays_count: Currently active decays

        Returns:
            Dictionary with decay metrics
        """
        decay_completion_rate = 0.0
        if total_decays_initiated > 0:
            decay_completion_rate = (decays_completed / total_decays_initiated) * 100.0

        return {
            "consent_decay_completion_rate": decay_completion_rate,
            "consent_active_decays": float(active_decays_count),
            "consent_total_decays_initiated": float(total_decays_initiated),
            "consent_decays_completed_total": float(decays_completed),
        }

    def collect_operational_metrics(
        self,
        consent_checks: int,
        consent_grants: int,
        consent_revokes: int,
        expired_cleanups: int,
        tool_executions: int,
        tool_failures: int,
    ) -> Dict[str, float]:
        """
        Calculate operational metrics.

        Args:
            consent_checks: Total consent status checks
            consent_grants: Total consent grants/updates
            consent_revokes: Total consent revocations
            expired_cleanups: Total cleanup operations
            tool_executions: Total tool executions
            tool_failures: Total tool failures

        Returns:
            Dictionary with operational metrics
        """
        return {
            "consent_checks_total": float(consent_checks),
            "consent_grants_total": float(consent_grants),
            "consent_revokes_total": float(consent_revokes),
            "consent_expired_cleanups_total": float(expired_cleanups),
            "consent_tool_executions_total": float(tool_executions),
            "consent_tool_failures_total": float(tool_failures),
        }

    def collect_all_metrics(
        self,
        consent_cache: Dict[str, "ConsentStatus"],
        now: datetime,
        partnership_counters: PartnershipCounters,
        decay_counters: DecayCounters,
        operational_counters: OperationalCounters,
        uptime_calculator: object = None,
    ) -> Dict[str, float]:
        """
        Collect all consent metrics in one call.

        Args:
            consent_cache: Current consent cache
            now: Current timestamp
            partnership_counters: Partnership-related counters
            decay_counters: Decay protocol counters
            operational_counters: Operational counters
            uptime_calculator: Optional uptime calculator

        Returns:
            Dictionary with all metrics
        """
        metrics: Dict[str, float] = {}

        # Collect stream distribution metrics
        metrics.update(self.collect_stream_distribution(consent_cache, now))

        # Collect partnership metrics
        metrics.update(
            self.collect_partnership_metrics(
                partnership_counters.requests,
                partnership_counters.approvals,
                partnership_counters.rejections,
                partnership_counters.pending_count,
            )
        )

        # Collect decay metrics
        metrics.update(
            self.collect_decay_metrics(
                decay_counters.total_initiated, decay_counters.completed, decay_counters.active_count
            )
        )

        # Collect operational metrics
        metrics.update(
            self.collect_operational_metrics(
                operational_counters.consent_checks,
                operational_counters.consent_grants,
                operational_counters.consent_revokes,
                operational_counters.expired_cleanups,
                operational_counters.tool_executions,
                operational_counters.tool_failures,
            )
        )

        # Add service health metric
        if uptime_calculator and hasattr(uptime_calculator, "_calculate_uptime"):
            metrics["consent_service_uptime_seconds"] = uptime_calculator._calculate_uptime()
        else:
            metrics["consent_service_uptime_seconds"] = 0.0

        return metrics

    def calculate_health_score(self, metrics: Dict[str, float]) -> float:
        """
        Calculate overall consent service health score (0-100).

        Factors:
        - Partnership success rate (weight: 0.3)
        - Decay completion rate (weight: 0.3)
        - Tool success rate (weight: 0.2)
        - Active users (weight: 0.2)

        Args:
            metrics: Current metrics dictionary

        Returns:
            Health score between 0 and 100
        """
        # Partnership health (0-30 points)
        partnership_health = metrics.get("consent_partnership_success_rate", 0.0) * 0.3

        # Decay health (0-30 points)
        decay_health = metrics.get("consent_decay_completion_rate", 0.0) * 0.3

        # Tool success health (0-20 points)
        tool_executions = metrics.get("consent_tool_executions_total", 0.0)
        tool_failures = metrics.get("consent_tool_failures_total", 0.0)
        tool_success_rate = (
            ((tool_executions - tool_failures) / tool_executions * 100.0) if tool_executions > 0 else 100.0
        )
        tool_health = tool_success_rate * 0.2

        # Active users health (0-20 points)
        # More users = healthier service (cap at 100 users = full points)
        active_users = min(metrics.get("consent_active_users", 0.0), 100.0)
        user_health = active_users * 0.2

        total_health = partnership_health + decay_health + tool_health + user_health

        return min(total_health, 100.0)
