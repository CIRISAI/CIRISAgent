"""The health check must be able to SEE that initialization finished.

THE OBSERVED FAILURE

A fully-booted agent reported `initializing` forever:

    status                  : initializing
    cognitive_state         : work            <- running, answering, sealing traces
    initialization_complete : False
    uptime_seconds          : 269
    warnings                : []              <- nothing to explain it

269 seconds after the log line "✓ CIRIS Agent Initialization Complete (9.6s)",
with every service group healthy.

WHY

`routes/system/helpers.py:119` probes the service like this:

    if init_service and hasattr(init_service, "is_initialized"):
        return init_service.is_initialized()
    return False        # fail closed (#943)

The service only defined `_is_initialized` — private. `hasattr` was False on
every poll, so the fail-closed branch fired every time. The class even
ADVERTISED "is_initialized" in `_get_actions()`, so the name was a promise it
did not keep, and the fail-closed design (correct on its own terms) turned the
mismatch into permanent silence rather than an error.

THE USER-VISIBLE COST

The mobile client sets `isConnected = status == "healthy"` and gates the whole
message composer on it. Text field, attach and send were all disabled on a
working agent, with nothing on screen explaining why — you simply could not type.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from ciris_engine.logic.adapters.api.routes.system.helpers import check_initialization_status
from ciris_engine.logic.services.lifecycle.initialization.service import InitializationService


def _request_with(init_service: Any) -> Any:
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(initialization_service=init_service)))


def test_the_advertised_action_actually_exists() -> None:
    """`_get_actions` promises "is_initialized"; the class must provide it."""
    service = InitializationService.__new__(InitializationService)
    advertised = InitializationService._get_actions(service)

    assert "is_initialized" in advertised
    assert hasattr(InitializationService, "is_initialized"), (
        "the service advertises an action it does not expose — this is exactly the "
        "mismatch that made the agent report 'initializing' forever"
    )


def test_health_probe_finds_the_method() -> None:
    """The literal `hasattr` the health check performs."""
    assert hasattr(InitializationService, "is_initialized"), (
        "hasattr(init_service, 'is_initialized') is False, so the health check takes "
        "its fail-closed branch on every poll regardless of boot state"
    )


def test_reports_complete_once_initialization_finished() -> None:
    service = InitializationService.__new__(InitializationService)
    service._initialization_complete = True

    assert service.is_initialized() is True
    assert check_initialization_status(_request_with(service)) is True, (
        "a finished boot still reported 'initializing'"
    )


def test_reports_incomplete_before_initialization_finishes() -> None:
    service = InitializationService.__new__(InitializationService)
    service._initialization_complete = False

    assert service.is_initialized() is False
    assert check_initialization_status(_request_with(service)) is False


def test_private_alias_still_works_for_existing_callers() -> None:
    service = InitializationService.__new__(InitializationService)
    service._initialization_complete = True
    assert service._is_initialized() is True
    assert InitializationService.is_initialized is InitializationService._is_initialized


def test_absent_service_still_fails_closed() -> None:
    """#943 is preserved: not knowing must not read as 'complete'."""
    assert check_initialization_status(_request_with(None)) is False


def test_service_without_the_method_still_fails_closed() -> None:
    assert check_initialization_status(_request_with(SimpleNamespace())) is False
