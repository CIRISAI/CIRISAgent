"""User extraction reads the task's own correlation, not the newest 100 of any.

`_extract_users_from_correlation_history` passed {"correlation_id": ...} to
`correlation_query`; it now reads the one correlation with `correlation_get`.
With other conversations' correlations present, only the task's own user may
come back -- and it must not page and decode a list per thought.
"""

from datetime import datetime, timezone
from unittest.mock import Mock

from ciris_engine.logic.context.system_snapshot_helpers import _extract_users_from_correlation_history
from ciris_engine.logic.persistence.models.correlations import add_correlation
from ciris_engine.schemas.telemetry.core import (
    CorrelationType,
    ServiceCorrelation,
    ServiceCorrelationStatus,
    ServiceRequestData,
    ServiceResponseData,
)


def _seed(correlation_id: str, user_id: str) -> None:
    now = datetime.now(timezone.utc)
    add_correlation(
        ServiceCorrelation(
            correlation_id=correlation_id,
            service_type="communication",
            handler_name="ObserveHandler",
            action_type="observe",
            request_data=ServiceRequestData(
                service_type="communication", method_name="observe", channel_id="c1", request_timestamp=now
            ),
            response_data=ServiceResponseData(
                success=True, execution_time_ms=1.0, error_message=None, response_timestamp=now
            ),
            status=ServiceCorrelationStatus.COMPLETED,
            correlation_type=CorrelationType.SERVICE_INTERACTION,
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
            timestamp=now,
            tags={"user_id": user_id},
            retention_policy="raw",
        )
    )


def _task(correlation_id: str) -> Mock:
    task = Mock()
    task.context = Mock()
    task.context.correlation_id = correlation_id
    return task


def test_only_the_tasks_own_correlation_is_read(persist_engine):
    _seed("corr_mine", "user_mine")
    for i in range(5):
        _seed(f"corr_other_{i}", f"user_other_{i}")  # other conversations, newer

    user_ids: set = set()
    _extract_users_from_correlation_history(_task("corr_mine"), user_ids)
    assert user_ids == {"user_mine"}


def test_unknown_correlation_adds_nobody(persist_engine):
    _seed("corr_other", "user_other")
    user_ids: set = set()
    _extract_users_from_correlation_history(_task("corr_missing"), user_ids)
    assert user_ids == set()
