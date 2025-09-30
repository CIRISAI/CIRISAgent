import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from ciris_engine.logic.adapters.api.api_observer import APIObserver
from ciris_engine.logic.adapters.api.routes.agent import (
    InteractRequest,
    interact,
    _message_responses,
    _response_events,
)
from ciris_engine.logic.adapters.api.services.auth_service import APIAuthService, User
from ciris_engine.schemas.api.auth import AuthContext, Permission, UserRole
from ciris_engine.schemas.runtime.api import APIRole
from ciris_engine.schemas.services.credit_gate import CreditCheckResult


class StubResourceMonitor:
    """Stub resource monitor that records credit checks."""

    def __init__(
        self,
        result: CreditCheckResult | None = None,
        exc: Exception | None = None,
        with_provider: bool = True,
    ) -> None:
        self._result = result
        self._exc = exc
        self.credit_provider = object() if with_provider else None
        self.calls = []

    async def check_credit(self, account, context):
        self.calls.append((account, context))
        if self._exc:
            raise self._exc
        assert self._result is not None
        return self._result


class StubSecretsService:
    async def process_incoming_text(self, content: str, message_id: str):
        return content, []


def _build_request(monitor: StubResourceMonitor) -> tuple[SimpleNamespace, AuthContext]:
    auth_service = APIAuthService()
    user = User(
        wa_id="wa-test",
        name="Test User",
        auth_type="password",
        api_role=APIRole.ADMIN,
        created_at=datetime.now(timezone.utc),
        is_active=True,
    )
    auth_service._users[user.wa_id] = user

    state = SimpleNamespace(
        api_config=SimpleNamespace(interaction_timeout=0.1),
        auth_service=auth_service,
        runtime=SimpleNamespace(agent_processor=None, agent_identity=SimpleNamespace(agent_id="agent-1")),
        resource_monitor=monitor,
        message_channel_map={},
    )

    observer = APIObserver(
        on_observe=lambda _: asyncio.sleep(0),
        secrets_service=StubSecretsService(),
        origin_service="api",
        resource_monitor=monitor,
    )

    async def on_message(msg):
        await observer._enforce_credit_policy(msg)
        _message_responses[msg.message_id] = "Acknowledged"
        state.message_channel_map[msg.channel_id] = msg.message_id
        event = _response_events.get(msg.message_id)
        if event:
            event.set()

    state.on_message = on_message
    app = SimpleNamespace(state=state)
    request = SimpleNamespace(app=app)

    auth_context = AuthContext(
        user_id=user.wa_id,
        role=UserRole.ADMIN,
        permissions={Permission.SEND_MESSAGES},
        api_key_id=None,
        session_id=None,
        authenticated_at=datetime.now(timezone.utc),
        request=None,
    )

    return request, auth_context


@pytest.mark.asyncio
async def test_interact_allows_when_credit_available() -> None:
    monitor = StubResourceMonitor(
        result=CreditCheckResult(
            has_credit=True,
            credits_remaining=5,
            expires_at=None,
            plan_name=None,
            reason=None,
            provider_metadata={},
        )
    )
    request, auth = _build_request(monitor)

    try:
        response = await interact(request, InteractRequest(message="hello"), auth)
    finally:
        _response_events.clear()
        _message_responses.clear()

    assert response.data.response == "Acknowledged"
    assert len(monitor.calls) == 1


@pytest.mark.asyncio
async def test_interact_blocks_when_credit_insufficient() -> None:
    monitor = StubResourceMonitor(
        result=CreditCheckResult(
            has_credit=False,
            credits_remaining=0,
            expires_at=None,
            plan_name=None,
            reason="insufficient",
            provider_metadata={},
        )
    )
    request, auth = _build_request(monitor)

    # Replace on_message to ensure downstream work happens only if credit passes
    called = {"value": False}

    observer = APIObserver(
        on_observe=lambda _: asyncio.sleep(0),
        secrets_service=StubSecretsService(),
        origin_service="api",
        resource_monitor=monitor,
    )

    async def failing_on_message(msg):
        await observer._enforce_credit_policy(msg)
        called["value"] = True

    request.app.state.on_message = failing_on_message

    with pytest.raises(HTTPException) as exc:
        await interact(request, InteractRequest(message="hello"), auth)

    _response_events.clear()
    _message_responses.clear()

    assert exc.value.status_code == 402
    assert called["value"] is False
    assert len(monitor.calls) == 1


@pytest.mark.asyncio
async def test_interact_returns_service_unavailable_on_provider_error() -> None:
    monitor = StubResourceMonitor(exc=RuntimeError("provider down"))
    request, auth = _build_request(monitor)

    with pytest.raises(HTTPException) as exc:
        await interact(request, InteractRequest(message="hello"), auth)

    _response_events.clear()
    _message_responses.clear()

    assert exc.value.status_code == 503
    assert len(monitor.calls) == 1


@pytest.mark.asyncio
async def test_interact_skips_credit_when_provider_missing() -> None:
    monitor = StubResourceMonitor(with_provider=False)
    request, auth = _build_request(monitor)

    try:
        response = await interact(request, InteractRequest(message="hello"), auth)
    finally:
        _response_events.clear()
        _message_responses.clear()

    assert response.data.response == "Acknowledged"
    # No credit calls recorded when provider absent
    assert len(monitor.calls) == 0
