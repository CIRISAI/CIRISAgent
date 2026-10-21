"""A provider without is_healthy() is reported ONCE, actionably (#935).

Whether a class implements a method is **static** — it cannot change between polls.
But `get_service_health_summary` runs on every `/v1/system/health` check, so it
re-reported the same fact hundreds of times an hour. Measured on `datum` running
2.9.13: 292 identical lines for `tool` and 146 for `wise_authority` in a 31-minute
window, contributing to an incident log that rotated in well under an hour against a
multi-week soak.

This is the same defect as the `AUTH_STEP_INFO` flood that 2.4.3 fixed, in a new
place: a constant, correct observation emitted at WARNING on a hot path.

The fix is NOT silence. The condition is a genuine registration defect and the
operator must see it — once, with what they need to resolve it.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any, List

import pytest

from ciris_engine.logic.adapters.api.routes.system import helpers
from ciris_engine.schemas.runtime.enums import ServiceType


class _NoHealthCheck:
    """A provider registered without going through base_service."""


class _Healthy:
    async def is_healthy(self) -> bool:
        return True


class _Registry:
    """Returns the SAME provider for every ServiceType, so one poll exercises the
    path once per type — which is exactly how datum produced 292 `tool` lines and
    146 `wise_authority` lines from one defect each."""

    def __init__(self, providers: List[Any]) -> None:
        self._providers = providers

    def get_services_by_type(self, _t: Any) -> List[Any]:
        return self._providers


class _Request:
    """Minimal stand-in for the FastAPI Request `collect_service_health` reads."""

    def __init__(self, registry: Any) -> None:
        self.app = SimpleNamespace(state=SimpleNamespace(service_registry=registry))


def _req(providers: List[Any]) -> Any:
    return _Request(_Registry(providers))


@pytest.fixture(autouse=True)
def _clear_report_state():
    helpers._REPORTED_UNHEALTHCHECKABLE.clear()
    yield
    helpers._REPORTED_UNHEALTHCHECKABLE.clear()


@pytest.mark.asyncio
async def test_reported_once_across_many_polls(caplog: pytest.LogCaptureFixture) -> None:
    req = _req([_NoHealthCheck()])
    with caplog.at_level(logging.WARNING):
        for _ in range(50):  # ~50 health polls
            await helpers.collect_service_health(req)

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warnings) <= len(list(ServiceType)), (
        f"{len(warnings)} warnings across 50 polls for a static property — this is "
        "the flood that rotated the incident log (292 lines in 31 min on datum)"
    )


@pytest.mark.asyncio
async def test_the_report_is_actionable(caplog: pytest.LogCaptureFixture) -> None:
    req = _req([_NoHealthCheck()])
    with caplog.at_level(logging.WARNING):
        await helpers.collect_service_health(req)

    msgs = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert msgs, "the defect must still be reported — silence is not the fix"
    msg = msgs[0]
    assert "_NoHealthCheck" in msg, "must name the offending class"
    assert "is_healthy" in msg, "must name what is missing"
    assert "FIX:" in msg, "must state the remedy"
    assert "registration defect" in msg, "must say it is a registration bug, not a runtime state"
    # An operator who reads this as transient will wait for it to clear. It never does.
    assert "NEVER WILL BE" in msg or "static" in msg


@pytest.mark.asyncio
async def test_a_healthy_provider_is_silent(caplog: pytest.LogCaptureFixture) -> None:
    req = _req([_Healthy()])
    with caplog.at_level(logging.WARNING):
        await helpers.collect_service_health(req)
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


@pytest.mark.asyncio
async def test_unknown_never_counts_as_healthy(caplog: pytest.LogCaptureFixture) -> None:
    """The #943 property must survive the noise fix.

    An unhealth-checkable provider stays in `available` but never in `healthy`, so it
    drags the ratio toward degraded rather than padding a quiet 100%.
    """
    req = _req([_NoHealthCheck()])
    summary = await helpers.collect_service_health(req)
    for _service, counts in summary.items():
        assert counts["available"] >= counts["healthy"]
        assert counts["healthy"] == 0, "an unknown provider must not be counted healthy"
