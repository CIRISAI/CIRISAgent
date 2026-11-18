"""The identity profile's BASE link (rc21 section 3): opened once, approved by digest, written with no prev.

- an unanchored profile opens ONE base-link deferral (``context.proposed_base_link``);
- resolve takes ``base_link_digest`` (approve only, one subject, the proposed digest);
- the agent signs it as the response row's ``amendment_digest`` and writes the
  link with ``emit_identity_amendment(digest, authorized_by, request_id, prev=None)``;
- a node without ``prev`` records nothing; the profile stays unanchored;
- GET /v1/wa/deferrals reports the profile and the capabilities.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, List, Optional
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from ciris_engine.logic.adapters.api.routes import wa
from ciris_engine.logic.context import identity_profile as ip
from ciris_engine.logic.services.governance.wise_authority import deferral_rows
from ciris_engine.schemas.api.wa import (
    PROPOSED_BASE_LINK_KEY,
    ProfileAnchorStatus,
    ProposedBaseLink,
    ResolveDeferralRequest,
)
from ciris_engine.schemas.infrastructure.identity_variance import IdentityProfile, IdentityProfileStatus
from ciris_engine.schemas.services.authority.wise_authority import PendingDeferral
from ciris_engine.schemas.services.authority_core import AuthorizationDecision, DeferralResponse
from tests.ciris_engine.logic.services.governance.test_wise_authority_service import (  # noqa: F401 - fixtures
    _insert_task_via_persist,
    auth_service,
    temp_db,
    time_service,
    wise_authority_service,
)
from tests.fixtures.deferral_rows import FakeNode, FakeRow, install_fake_node

DIGEST = hashlib.sha256(b"the shipped template").hexdigest()
PROPOSAL = ProposedBaseLink(template_name="default", template_version="1.0", manifest_digest=DIGEST)
DEFERRAL_ID = "defer_BASE_LINK_x_1761134400.0"
SESSION = "sess:wa-2026-10-22-OWNER1:bWFj"


_NOT_PASSED = "<prev not passed>"


class PrevNode(FakeNode):
    """A node whose ``emit_identity_amendment`` writes ``refs.prev`` (persist v62 / verify 23)."""

    def emit_identity_amendment(  # type: ignore[override]
        self, amendment_digest: str, authorized_by: str, request_id: str, prev: Optional[str] = _NOT_PASSED
    ) -> str:
        row_id = super().emit_identity_amendment(amendment_digest, authorized_by, request_id)
        self.calls.append(("prev", (prev,)))
        return row_id


@pytest.fixture(autouse=True)
def _clean_profile_state() -> Any:
    ip.reset_base_link_state()
    ip.set_base_link_opener(None)
    yield
    ip.reset_base_link_state()
    ip.set_base_link_opener(None)


def _profile(status: IdentityProfileStatus, template: Optional[str] = "default") -> IdentityProfile:
    return IdentityProfile(
        profile_digest="ab" * 32,
        expected_profile_digest=None,
        status=status,
        reason="profile_unanchored",
        template=template,
        template_verified=True,
        base_digest=DIGEST,
    )


# ------------------------------------------------------------------ the opener


@pytest.mark.asyncio
async def test_an_unanchored_profile_asks_once_per_process() -> None:
    import asyncio

    asked: List[ProposedBaseLink] = []

    async def opener(proposal: ProposedBaseLink) -> Optional[str]:
        asked.append(proposal)
        return "defer_BASE_LINK"

    ip.set_base_link_opener(opener)
    ip.maybe_open_base_link(_profile(IdentityProfileStatus.UNANCHORED))
    ip.maybe_open_base_link(_profile(IdentityProfileStatus.UNANCHORED))
    ip.maybe_open_base_link(_profile(IdentityProfileStatus.VERIFIED))
    ip.maybe_open_base_link(_profile(IdentityProfileStatus.UNANCHORED, template=None))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert [p.manifest_digest for p in asked] == [DIGEST]
    assert asked[0].template_name == "default"


@pytest.mark.asyncio
async def test_a_failed_open_is_asked_again(caplog: pytest.LogCaptureFixture) -> None:
    async def opener(proposal: ProposedBaseLink) -> Optional[str]:
        raise RuntimeError("persist down")

    ip.set_base_link_opener(opener)
    assert await ip.request_base_link(PROPOSAL) is None
    assert DIGEST not in ip._base_link_requested


@pytest.mark.asyncio
async def test_the_service_opens_one_base_link_deferral(wise_authority_service: Any) -> None:
    await wise_authority_service.start()
    first = await wise_authority_service.open_base_link_deferral(PROPOSAL)
    second = await wise_authority_service.open_base_link_deferral(PROPOSAL)
    assert first and first == second, "a pending base-link deferral is not re-opened"
    pending = [d for d in await wise_authority_service.get_pending_deferrals() if PROPOSED_BASE_LINK_KEY in d.context]
    assert len(pending) == 1
    assert ProposedBaseLink.model_validate_json(pending[0].context[PROPOSED_BASE_LINK_KEY]) == PROPOSAL
    assert pending[0].task_id.startswith("BASE_LINK_")


# ---------------------------------------------------------- resolve: the service


async def _open_and_answer(service: Any, node: FakeNode, auth_service: Any, digest: str = DIGEST) -> tuple:
    await service.start()
    deferral_id = await service.open_base_link_deferral(PROPOSAL)
    (pending,) = [d for d in await service.get_pending_deferrals() if d.deferral_id == deferral_id]
    response_id = await deferral_rows.emit_deferral_response(
        str(pending.request_attestation_id), True, SESSION, amendment_sha256=digest
    )
    auth_service.verify_deferral_resolution = AsyncMock(return_value=True)
    response = DeferralResponse(
        approved=True,
        reason="base link approved",
        wa_id="wa-2025-06-24-AUTH01",
        signature="dmVyaWZpZWQ=",
        signed_at="2026-11-18T12:00:00+00:00",
        amendment_sha256=digest,
        response_attestation_id=response_id,
    )
    return deferral_id, pending, response


def _stored_deferral(task_id: str) -> dict:
    from ciris_engine.logic.persistence.models.graph import get_persist_engine

    row = json.loads(get_persist_engine().task_get(task_id))
    context = row["context"] if isinstance(row["context"], dict) else json.loads(row["context"])
    return {"status": row["status"], **context["deferral"]}


def _base_nodes() -> List[Any]:
    from ciris_engine.logic.persistence.models.graph import get_nodes_by_type
    from ciris_engine.schemas.services.graph_core import NodeType

    return [n for n in get_nodes_by_type(NodeType.IDENTITY_AMENDMENT) if "base_link" in n.id]


@pytest.mark.asyncio
async def test_an_approved_base_link_is_written_with_no_prev(
    wise_authority_service: Any, auth_service: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    node = install_fake_node(monkeypatch, PrevNode())
    deferral_id, pending, response = await _open_and_answer(wise_authority_service, node, auth_service)

    assert await wise_authority_service.resolve_deferral(deferral_id, response) is True

    (call,) = node.calls_to("emit_identity_amendment")
    assert call == (DIGEST, response.response_attestation_id, pending.request_attestation_id)
    assert node.calls_to("prev") == [(None,)], "the base link names no prev, explicitly"
    stored = _stored_deferral(pending.task_id)
    assert stored["status"] == "completed"
    assert stored["base_link"]["status"] == "recorded"
    (base,) = _base_nodes()
    from ciris_engine.logic.context.identity_amendments import amendment_from_node

    amendment = amendment_from_node(base)
    assert amendment is not None and amendment.base and amendment.approved_sha256 == DIGEST
    assert amendment.amendment_attestation_id == stored["base_link"]["amendment_attestation_id"]


@pytest.mark.asyncio
async def test_a_node_without_prev_records_nothing_and_says_so(
    wise_authority_service: Any, auth_service: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    node = install_fake_node(monkeypatch)  # FakeNode: emit_identity_amendment has no prev
    deferral_id, pending, response = await _open_and_answer(wise_authority_service, node, auth_service)

    assert await wise_authority_service.resolve_deferral(deferral_id, response) is True

    assert node.calls_to("emit_identity_amendment") == []
    assert _stored_deferral(pending.task_id)["base_link"] == {
        "status": "not_recorded",
        "reason_id": deferral_rows.REASON_PREV_UNSUPPORTED,
    }
    assert _base_nodes() == []


@pytest.mark.asyncio
async def test_a_digest_that_is_not_the_proposed_one_is_refused_before_any_change(
    wise_authority_service: Any, auth_service: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    node = install_fake_node(monkeypatch, PrevNode())
    other = hashlib.sha256(b"another template").hexdigest()
    deferral_id, pending, response = await _open_and_answer(wise_authority_service, node, auth_service, digest=other)

    assert await wise_authority_service.resolve_deferral(deferral_id, response) is False

    assert node.calls_to("emit_identity_amendment") == []
    assert _stored_deferral(pending.task_id)["status"] == "deferred"


# ------------------------------------------------------------- resolve: the route


def _pending(context: Optional[dict] = None) -> PendingDeferral:
    return PendingDeferral(
        deferral_id=DEFERRAL_ID,
        created_at=datetime.now(timezone.utc),
        deferred_by="ciris_agent",
        task_id="task-1",
        thought_id="",
        reason="base link",
        context=context if context is not None else {PROPOSED_BASE_LINK_KEY: PROPOSAL.model_dump_json()},
        request_attestation_id="att-req",
        request_row_status="emitted",
    )


class _Route:
    def __init__(self, pending: PendingDeferral) -> None:
        self.resolved: List[DeferralResponse] = []
        route = self

        async def resolve(deferral_id: str, response: DeferralResponse) -> bool:
            route.resolved.append(response)
            return True

        async def sign(deferral_id: str, response: DeferralResponse, signed_at: str) -> DeferralResponse:
            return response.model_copy(update={"signature": "c2ln", "signed_at": signed_at})

        wa_service = SimpleNamespace(
            get_pending_deferrals=AsyncMock(return_value=[pending]),
            resolve_deferral=resolve,
            authorize=AsyncMock(
                return_value=AuthorizationDecision(allowed=True, message="ok", wa_id="wa", action="resolve_deferral")
            ),
        )
        self.request = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    wise_authority_service=wa_service,
                    authentication_service=SimpleNamespace(sign_deferral_resolution=sign),
                )
            ),
            headers={"authorization": f"Bearer {SESSION}"},
        )

    async def resolve(self, resolution: str = "approve", **fields: Any) -> Any:
        return await wa.resolve_deferral(
            self.request,  # type: ignore[arg-type]
            DEFERRAL_ID,
            ResolveDeferralRequest(resolution=resolution, guidance="approve the base", **fields),
            SimpleNamespace(user_id="wa-owner"),  # type: ignore[arg-type]
        )


def _node_with_request() -> FakeNode:
    node = FakeNode()
    node.rows.append(FakeRow("att-req", "deferral:request:v1", ()))
    return node


@pytest.mark.asyncio
async def test_base_link_digest_is_signed_as_the_response_rows_amendment_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    node = install_fake_node(monkeypatch, _node_with_request())
    route = _Route(_pending())
    await route.resolve(base_link_digest=DIGEST)
    assert node.calls_to("emit_deferral_response") == [("att-req", True, SESSION, DIGEST)]
    (resolved,) = route.resolved
    assert resolved.amendment_sha256 == DIGEST and resolved.amendment_text is None


@pytest.mark.parametrize("resolution", ["reject", "modify"])
@pytest.mark.asyncio
async def test_base_link_digest_requires_approve(monkeypatch: pytest.MonkeyPatch, resolution: str) -> None:
    install_fake_node(monkeypatch, _node_with_request())
    with pytest.raises(HTTPException) as refused:
        await _Route(_pending()).resolve(resolution, base_link_digest=DIGEST)
    assert refused.value.status_code == 400
    assert refused.value.detail["error"]["details"]["reason_id"] == "wa.base_link_digest_requires_approve"


@pytest.mark.parametrize("other", [{"amendment_text": "I am kind."}, {"call_fingerprint": "-16:" + "00" * 32}])
@pytest.mark.asyncio
async def test_base_link_digest_is_one_subject(monkeypatch: pytest.MonkeyPatch, other: dict) -> None:
    install_fake_node(monkeypatch, _node_with_request())
    with pytest.raises(HTTPException) as refused:
        await _Route(_pending()).resolve(base_link_digest=DIGEST, **other)
    assert refused.value.detail["error"]["details"]["reason_id"] == "wa.resolve_one_subject"


@pytest.mark.parametrize("context", [None, {}])
@pytest.mark.asyncio
async def test_base_link_digest_must_be_the_proposed_one(monkeypatch: pytest.MonkeyPatch, context: Optional[dict]) -> None:
    install_fake_node(monkeypatch, _node_with_request())
    pending = _pending(context) if context is not None else _pending()
    digest = DIGEST if context is not None else hashlib.sha256(b"x").hexdigest()
    route = _Route(pending)
    with pytest.raises(HTTPException) as refused:
        await route.resolve(base_link_digest=digest)
    assert refused.value.detail["error"]["details"]["reason_id"] == "wa.base_link_digest_mismatch"
    assert route.resolved == []


# ------------------------------------------------------------ the deferral list


@pytest.mark.asyncio
async def test_the_deferral_list_reports_the_profile_and_capabilities() -> None:
    ip._latest_profile = _profile(IdentityProfileStatus.UNANCHORED)
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                wise_authority_service=SimpleNamespace(get_pending_deferrals=AsyncMock(return_value=[_pending()]))
            )
        )
    )
    response = await wa.get_deferrals(request, SimpleNamespace(user_id="observer"), None)  # type: ignore[arg-type]
    body = response.data.model_dump(mode="json")
    assert body["profile"] == {
        "status": "unanchored",
        "profile_digest": "ab" * 32,
        "proposed_base_link": {"template_name": "default", "template_version": "1.0", "manifest_digest": DIGEST},
    }
    assert body["capabilities"]["exact_call_approval"] is True
    assert body["capabilities"]["base_link_approval"] is True
    assert body["capabilities"]["exact_amendment_text"] is True


def test_an_anchored_profile_reads_anchored_and_before_any_check_unanchored() -> None:
    ip._latest_profile = _profile(IdentityProfileStatus.VERIFIED)
    assert wa.deferral_list_profile([]).status is ProfileAnchorStatus.ANCHORED
    ip._latest_profile = None
    view = wa.deferral_list_profile([])
    assert view.status is ProfileAnchorStatus.UNANCHORED and view.profile_digest is None
