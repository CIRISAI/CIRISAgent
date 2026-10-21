"""The health endpoint must not answer confidently about what it has not inspected (#943).

Three fail-open defaults let `/v1/system/health` report a system it never
checked, all the same shape — *absence of the authority that would answer is
treated as a yes*:

1. no initialization service on ``app.state`` → "initialization complete"
2. a provider exposing no ``is_healthy()`` → counted healthy
3. an empty registry → ``healthy == total == 0`` → "healthy"

Chained, they are worse than individually: ``determine_overall_status``
short-circuits on ``init_complete``, so (1) skipped the "initializing" branch
entirely and fell through into (3), and the endpoint reported **"healthy"** for
an agent that had not finished booting and had no services registered.

Every assertion here is in the negative direction. The positive-direction tests
that existed passed identically before and after the fix, which is precisely
why this survived to be found by hand.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict

import pytest

from ciris_engine.logic.adapters.api.routes.system.helpers import (
    check_initialization_status,
    check_provider_health,
    determine_overall_status,
)


def _request(**state: Any) -> Any:
    """Minimal stand-in for a Starlette Request carrying app.state."""
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(**state)))


class TestInitializationStatusFailsClosed:
    def test_missing_init_service_is_not_complete(self) -> None:
        assert check_initialization_status(_request()) is False

    def test_init_service_set_to_none_is_not_complete(self) -> None:
        """The real exposure window: app.py sets this attribute to None at app
        construction, so it EXISTS and is falsy until the service is attached."""
        assert check_initialization_status(_request(initialization_service=None)) is False

    def test_service_without_is_initialized_is_not_complete(self) -> None:
        assert check_initialization_status(_request(initialization_service=SimpleNamespace())) is False

    @pytest.mark.parametrize("initialized", [True, False])
    def test_a_real_service_is_still_believed(self, initialized: bool) -> None:
        """Failing closed must not stop a reachable authority from being heard."""
        svc = SimpleNamespace(is_initialized=lambda: initialized)
        assert check_initialization_status(_request(initialization_service=svc)) is initialized


class TestProviderHealthTriState:
    @pytest.mark.asyncio
    async def test_provider_without_is_healthy_is_unknown_not_healthy(self) -> None:
        assert await check_provider_health(SimpleNamespace()) is None

    @pytest.mark.asyncio
    async def test_raising_provider_is_unhealthy(self) -> None:
        def boom() -> bool:
            raise RuntimeError("down")

        assert await check_provider_health(SimpleNamespace(is_healthy=boom)) is False

    @pytest.mark.asyncio
    async def test_sync_and_async_healthy_providers_both_report_true(self) -> None:
        async def healthy_async() -> bool:
            return True

        assert await check_provider_health(SimpleNamespace(is_healthy=lambda: True)) is True
        assert await check_provider_health(SimpleNamespace(is_healthy=healthy_async)) is True

    @pytest.mark.asyncio
    async def test_unknown_is_distinguishable_from_unhealthy(self) -> None:
        """The caller has to tell these apart: unhealthy is a fact about the
        provider, unknown is a fact about our ability to ask. Both are excluded
        from the healthy count, but only one is a registration defect."""
        unknown = await check_provider_health(SimpleNamespace())
        unhealthy = await check_provider_health(SimpleNamespace(is_healthy=lambda: False))
        assert unknown is None
        assert unhealthy is False
        assert unknown is not unhealthy


class TestOverallStatus:
    def test_no_services_is_not_healthy(self) -> None:
        """`healthy == total` is satisfied vacuously at 0 == 0."""
        assert determine_overall_status(True, True, {}) == "critical"

    def test_incomplete_init_reports_initializing(self) -> None:
        services: Dict[str, Dict[str, int]] = {"llm": {"available": 1, "healthy": 1}}
        assert determine_overall_status(False, True, services) == "initializing"

    def test_the_full_chain_cannot_report_healthy(self) -> None:
        """The composed defect, end to end.

        No init service (→ False after the fix) and an empty registry is exactly
        the state an agent is in between ASGI app creation and service wiring.
        It previously reported "healthy"; the only two acceptable answers are
        "initializing" or "critical".
        """
        init_complete = check_initialization_status(_request(initialization_service=None))
        status = determine_overall_status(init_complete, True, {})
        assert status != "healthy"
        assert status == "initializing"

    def test_healthy_still_reachable_when_everything_is_actually_healthy(self) -> None:
        services: Dict[str, Dict[str, int]] = {"llm": {"available": 2, "healthy": 2}}
        assert determine_overall_status(True, True, services) == "healthy"

    def test_unknown_provider_cannot_manufacture_a_full_score(self) -> None:
        """One unaskable provider among two keeps the ratio below 100%."""
        services: Dict[str, Dict[str, int]] = {"llm": {"available": 2, "healthy": 1}}
        assert determine_overall_status(True, True, services) != "healthy"
