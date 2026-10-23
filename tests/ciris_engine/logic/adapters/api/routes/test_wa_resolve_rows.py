"""POST /v1/wa/deferrals/{id}/resolve signs the Wise Authority's answer as a row, and fails closed (#1316)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, List, Optional
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from ciris_engine.logic.adapters.api.routes import wa
from ciris_engine.schemas.api.wa import ResolveDeferralRequest
from ciris_engine.schemas.services.authority.wise_authority import PendingDeferral
from ciris_engine.schemas.services.authority_core import AuthorizationDecision, DeferralResponse
from tests.fixtures.deferral_rows import FakeNode, FakeRow, install_fake_node

DEFERRAL_ID = "defer_task-1_1761134400.0"
SESSION = "sess:wa-2026-10-22-OWNER1:bWFj"


def _pending(request_id: Optional[str], status: str = "emitted", domain: Optional[str] = None) -> PendingDeferral:
    return PendingDeferral(
        deferral_id=DEFERRAL_ID,
        created_at=datetime.now(timezone.utc),
        deferred_by="ciris_agent",
        task_id="task-1",
        thought_id="thought-1",
        reason="identity change",
        context={"domain_hint": domain} if domain else {},
        request_attestation_id=request_id,
        request_row_status=status,
    )


class _Harness:
    def __init__(self, pending: PendingDeferral, authorization: str = f"Bearer {SESSION}") -> None:
        self.order: List[str] = []
        self.resolved: List[DeferralResponse] = []
        harness = self

        async def resolve(deferral_id: str, response: DeferralResponse) -> bool:
            harness.order.append("resolve_deferral")
            harness.resolved.append(response)
            return True

        async def sign(deferral_id: str, response: DeferralResponse, signed_at: str) -> DeferralResponse:
            harness.order.append("sign")
            return response.model_copy(update={"signature": "c2ln", "signed_at": signed_at})

        self.wa_service = SimpleNamespace(
            get_pending_deferrals=AsyncMock(return_value=[pending]),
            resolve_deferral=resolve,
            authorize=AsyncMock(return_value=AuthorizationDecision(allowed=True, message="ok", wa_id="wa", action="resolve_deferral")),
        )
        self.auth_service = SimpleNamespace(sign_deferral_resolution=sign)
        self.request = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(wise_authority_service=self.wa_service, authentication_service=self.auth_service)
            ),
            headers={"authorization": authorization},
        )
        self.auth = SimpleNamespace(user_id="wa-2026-10-22-OWNER1")

    async def resolve(self, resolution: str = "approve") -> Any:
        return await wa.resolve_deferral(
            self.request,  # type: ignore[arg-type]
            DEFERRAL_ID,
            ResolveDeferralRequest(resolution=resolution, guidance="$memorize x CONCEPT IDENTITY"),
            self.auth,  # type: ignore[arg-type]
        )


def _node_with_request() -> FakeNode:
    node = FakeNode()
    node.rows.append(FakeRow("att-req", "deferral:request:v1", ()))
    return node


@pytest.mark.asyncio
async def test_an_approval_is_signed_by_the_resolver_before_it_is_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    node = install_fake_node(monkeypatch, _node_with_request())
    h = _Harness(_pending("att-req"))
    original_emit = wa.emit_deferral_response

    async def emit(*args: Any) -> str:
        h.order.append("emit_response")
        return await original_emit(*args)

    monkeypatch.setattr(wa, "emit_deferral_response", emit)

    result = await h.resolve()

    assert node.calls_to("emit_deferral_response") == [("att-req", True, SESSION)], "the resolver's raw sess: token"
    assert h.order == ["sign", "emit_response", "resolve_deferral"]
    response_row = node.rows[-1]
    assert response_row.attestation_type == "deferral:response:approved:v1"
    assert h.resolved[0].response_attestation_id == response_row.attestation_id
    assert h.resolved[0].signature == "c2ln", "the #944 signature is kept"
    assert result.data.response_attestation_id == response_row.attestation_id
    assert result.data.request_attestation_id == "att-req"


@pytest.mark.parametrize(
    ("exc", "status", "reason_id"),
    [
        (PermissionError("deferral.resolver_has_no_key: signed in, but not the owner"), 403, "deferral.resolver_has_no_key"),
        (PermissionError("deferral.not_signed_in: answering needs the WA's own session"), 403, "deferral.not_signed_in"),
        (PermissionError("deferral.delegated: a delegated session cannot answer"), 403, "deferral.delegated"),
        (PermissionError("deferral.no_identity: the owner has no federation ID yet"), 403, "deferral.no_identity"),
        (ValueError("deferral.unknown_request: att-req is not an admitted deferral:request:v1"), 409, "deferral.unknown_request"),
        (ValueError("deferral.bad_input: bad input: request_id is empty"), 400, "deferral.bad_input"),
        (RuntimeError("deferral.store: store: get_attestation failed"), 503, "deferral.store"),
    ],
)
@pytest.mark.asyncio
async def test_a_refused_response_row_records_no_resolution(
    monkeypatch: pytest.MonkeyPatch, exc: BaseException, status: int, reason_id: str
) -> None:
    install_fake_node(monkeypatch, FakeNode(fail={"emit_deferral_response": exc}))
    h = _Harness(_pending("att-req"))

    with pytest.raises(HTTPException) as caught:
        await h.resolve()

    assert caught.value.status_code == status
    assert caught.value.detail["error"]["details"]["reason_id"] == reason_id
    assert reason_id in caught.value.detail["error"]["message"]
    assert "resolve_deferral" not in h.order, "fail closed: the resolution is not recorded"


@pytest.mark.asyncio
async def test_a_service_token_is_never_handed_to_the_pen(monkeypatch: pytest.MonkeyPatch) -> None:
    node = install_fake_node(monkeypatch, _node_with_request())
    h = _Harness(_pending("att-req"), authorization="Bearer service:abc123")
    await h.resolve()
    assert node.calls_to("emit_deferral_response") == [("att-req", True, None)]


@pytest.mark.asyncio
async def test_modify_is_signed_as_not_approved(monkeypatch: pytest.MonkeyPatch) -> None:
    node = install_fake_node(monkeypatch, _node_with_request())
    h = _Harness(_pending("att-req"))
    await h.resolve("modify")
    assert node.calls_to("emit_deferral_response") == [("att-req", False, SESSION)]
    assert node.rows[-1].attestation_type == "deferral:response:rejected:v1"
    assert h.resolved[0].approved is False


@pytest.mark.asyncio
async def test_a_deferral_without_a_request_row_resolves_without_a_response_row(monkeypatch: pytest.MonkeyPatch) -> None:
    node = install_fake_node(monkeypatch, _node_with_request())
    h = _Harness(_pending(None, status="failed"))
    await h.resolve()
    assert node.calls_to("emit_deferral_response") == []
    assert h.resolved[0].response_attestation_id is None, "so an identity change it approves is not applied"


@pytest.mark.asyncio
async def test_a_node_without_rows_resolves_as_before(monkeypatch: pytest.MonkeyPatch) -> None:
    node = install_fake_node(
        monkeypatch, FakeNode(missing=("emit_deferral_request", "emit_deferral_response", "emit_identity_amendment"))
    )
    h = _Harness(_pending(None, status="unavailable"))
    result = await h.resolve()
    assert node.calls == []
    assert h.order == ["sign", "resolve_deferral"]
    assert h.resolved[0].response_attestation_id is None
    assert result.data.success is True


@pytest.mark.asyncio
async def test_jurisdiction_is_checked_before_the_wa_signs(monkeypatch: pytest.MonkeyPatch) -> None:
    node = install_fake_node(monkeypatch, _node_with_request())
    h = _Harness(_pending("att-req", domain="financial"))
    h.wa_service.authorize = AsyncMock(
        return_value=AuthorizationDecision(allowed=False, message="no jurisdiction", wa_id="wa", action="resolve_deferral")
    )
    with pytest.raises(HTTPException) as caught:
        await h.resolve()
    assert caught.value.status_code == 403
    assert node.calls == [], "no row is signed for a resolution the caller has no jurisdiction over"
