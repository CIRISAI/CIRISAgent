"""Identity-change deferrals as the Wise Authority sees and answers them (#1366).

- every identity-change deferral carries ``context.identity_change`` (kind, what
  changes, exact text or template, M-1 justification): amendment, base_link,
  reapproval;
- each held amendment approved before exact-text binding gets ONE re-approval
  deferral (kind=reapproval, its text unchanged, a justification), and does not
  count until approved;
- an approval hands the guidance task the proposal and its justification, so
  the write the consciences review carries them.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any, List, Optional
from unittest.mock import AsyncMock

import pytest

from ciris_engine.logic.context import identity_profile as ip
from ciris_engine.logic.services.governance.wise_authority import deferral_rows
from ciris_engine.schemas.actions.parameters import (
    IDENTITY_CHANGE_CONTEXT_KEY,
    M1_JUSTIFICATION_CONTEXT_KEY,
    PROPOSED_AMENDMENT_CONTEXT_KEY,
)
from ciris_engine.schemas.api.wa import IdentityChangeKind, IdentityChangeProposal, ProposedBaseLink
from ciris_engine.schemas.infrastructure.identity_variance import (
    IdentityAmendment,
    IdentityProfile,
    IdentityProfileStatus,
)
from ciris_engine.schemas.services.authority_core import DeferralResponse
from tests.ciris_engine.logic.services.governance.test_wise_authority_service import (  # noqa: F401 - fixtures
    auth_service,
    temp_db,
    time_service,
    wise_authority_service,
)
from tests.fixtures.deferral_rows import install_fake_node

LEGACY_TEXT = "I mentor new moderators"
SESSION = "sess:wa-2026-10-22-OWNER1:bWFj"


@pytest.fixture(autouse=True)
def _clean_profile_state() -> Any:
    ip.reset_base_link_state()
    ip.set_base_link_opener(None)
    ip.set_reapproval_opener(None)
    yield
    ip.reset_base_link_state()
    ip.set_base_link_opener(None)
    ip.set_reapproval_opener(None)


def _amendment(node_id: str, *, verified: bool, prev: Optional[str] = None, base: bool = False) -> IdentityAmendment:
    return IdentityAmendment(
        node_id=node_id,
        content="" if base else f"text of {node_id}",
        wa_id="wa-old",
        deferral_id=f"defer_{node_id}",
        granted_at="2026-10-01T00:00:00+00:00",
        verified=verified,
        amendment_row_prev=prev,
        base=base,
        amendment_attestation_id=f"att-{node_id}",
        approved_sha256="ab" * 32,
    )


def _profile(status: IdentityProfileStatus) -> IdentityProfile:
    return IdentityProfile(
        profile_digest="ab" * 32,
        status=status,
        reason="profile_match" if status is IdentityProfileStatus.VERIFIED else "profile_unanchored",
        base_digest="cd" * 32,
        base_row_id="att-base" if status is IdentityProfileStatus.VERIFIED else None,
    )


# ------------------------------------------------------------- which amendments


def test_each_amendment_that_cannot_count_needs_reapproval() -> None:
    per_row = [
        _amendment("base", verified=True, base=True),
        _amendment("legacy", verified=False),  # approved before exact-text binding
        _amendment("unchained", verified=True),  # verified row, but written before the chain: no prev
        _amendment("chained", verified=True, prev="att-base"),
    ]
    assert [a.node_id for a in ip.amendments_needing_reapproval(per_row)] == ["legacy", "unchained"]


def test_an_amendment_already_reapproved_is_not_asked_again() -> None:
    legacy = _amendment("legacy", verified=False)
    reapproved = _amendment("new", verified=True, prev="att-base").model_copy(update={"content": legacy.content})
    assert ip.amendments_needing_reapproval([legacy, reapproved]) == []


def test_an_unverified_amendment_does_not_apply_until_reapproved() -> None:
    """Already enforced by the profile check: nothing that did not verify counts."""
    base = ip.IdentityBase(agent_id="a", description="d", role="r")
    amendments, _ = ip.check_identity_profile(base, [_amendment("legacy", verified=False)])
    assert [a.verified for a in amendments] == [False]


@pytest.mark.asyncio
async def test_one_reapproval_deferral_opens_per_amendment_once_the_profile_is_anchored() -> None:
    asked: List[IdentityChangeProposal] = []

    async def opener(proposal: IdentityChangeProposal) -> Optional[str]:
        asked.append(proposal)
        return f"defer_{proposal.supersedes_node_id}"

    ip.set_reapproval_opener(opener)
    per_row = [_amendment("legacy", verified=False), _amendment("other", verified=False)]
    ip.maybe_open_reapprovals(per_row, _profile(IdentityProfileStatus.UNANCHORED))
    await asyncio.sleep(0)
    assert asked == [], "before the base link there is no chain head to write a re-approved link after"

    for _ in range(3):
        ip.maybe_open_reapprovals(per_row, _profile(IdentityProfileStatus.VERIFIED))
    for _ in range(3):
        await asyncio.sleep(0)
    assert sorted(p.supersedes_node_id or "" for p in asked) == ["legacy", "other"], "once per amendment"
    proposal = next(p for p in asked if p.supersedes_node_id == "legacy")
    assert proposal.kind is IdentityChangeKind.REAPPROVAL
    assert proposal.proposed_text == "text of legacy", "the held text, unchanged"
    assert proposal.m1_justification and "M-1" in proposal.m1_justification


@pytest.mark.asyncio
async def test_the_service_opens_one_reapproval_deferral_per_amendment(wise_authority_service: Any) -> None:
    await wise_authority_service.start()
    proposal = ip.reapproval_proposal(_amendment("legacy", verified=False))
    first = await wise_authority_service.open_reapproval_deferral(proposal)
    second = await wise_authority_service.open_reapproval_deferral(proposal)
    assert first and first == second, "a pending re-approval of the same amendment is not re-opened"

    (pending,) = [d for d in await wise_authority_service.get_pending_deferrals() if d.deferral_id == first]
    change = IdentityChangeProposal.model_validate_json(pending.context[IDENTITY_CHANGE_CONTEXT_KEY])
    assert change.kind is IdentityChangeKind.REAPPROVAL and change.supersedes_node_id == "legacy"
    assert pending.context[PROPOSED_AMENDMENT_CONTEXT_KEY] == "text of legacy"
    assert pending.context[M1_JUSTIFICATION_CONTEXT_KEY] == ip.REAPPROVAL_M1_JUSTIFICATION


@pytest.mark.asyncio
async def test_the_base_link_deferral_carries_its_identity_change_and_justification(wise_authority_service: Any) -> None:
    await wise_authority_service.start()
    link = ProposedBaseLink(template_name="default", manifest_digest=hashlib.sha256(b"t").hexdigest())
    deferral_id = await wise_authority_service.open_base_link_deferral(link)
    (pending,) = [d for d in await wise_authority_service.get_pending_deferrals() if d.deferral_id == deferral_id]
    change = IdentityChangeProposal.model_validate_json(pending.context[IDENTITY_CHANGE_CONTEXT_KEY])
    assert change.kind is IdentityChangeKind.BASE_LINK
    assert change.template == link
    assert change.m1_justification and "M-1" in change.m1_justification
    assert pending.context[M1_JUSTIFICATION_CONTEXT_KEY] == change.m1_justification


# ------------------------------------------------------------- the approval


@pytest.mark.asyncio
async def test_an_approved_reapproval_hands_its_proposal_and_justification_to_the_guidance_task(
    wise_authority_service: Any, auth_service: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    node = install_fake_node(monkeypatch)
    await wise_authority_service.start()
    proposal = ip.reapproval_proposal(_amendment("legacy", verified=False))
    deferral_id = await wise_authority_service.open_reapproval_deferral(proposal)
    (pending,) = [d for d in await wise_authority_service.get_pending_deferrals() if d.deferral_id == deferral_id]
    text = str(proposal.proposed_text)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    response_id = await deferral_rows.emit_deferral_response(
        str(pending.request_attestation_id), True, SESSION, amendment_sha256=digest
    )
    auth_service.verify_deferral_resolution = AsyncMock(return_value=True)
    response = DeferralResponse(
        approved=True,
        reason="re-approved",
        wa_id="wa-2025-06-24-AUTH01",
        signature="dmVyaWZpZWQ=",
        signed_at="2026-11-18T12:00:00+00:00",
        amendment_text=text,
        amendment_sha256=digest,
        response_attestation_id=response_id,
    )
    assert await wise_authority_service.resolve_deferral(deferral_id, response) is True
    assert node.calls_to("emit_identity_amendment") == [], "approval alone writes nothing: the guidance task applies it"

    from ciris_engine.logic.persistence.models.graph import get_persist_engine
    from ciris_engine.logic.persistence.models.tasks import _list_with_filter

    engine = get_persist_engine()
    guidance = [t for t in _list_with_filter({"status": "pending", "agent_occurrence_id": "default"}) if t.parent_task_id == pending.task_id]
    assert len(guidance) == 1, "the shared re-approval is applied by this occurrence"
    row = json.loads(engine.task_get(guidance[0].task_id))
    context = row["context"] if isinstance(row["context"], dict) else json.loads(row["context"])
    grant = context["wa_authorization"]
    assert grant["amendment_text"] == text
    assert grant["proposed_amendment"] == text
    assert grant["m1_justification"] == ip.REAPPROVAL_M1_JUSTIFICATION
    assert grant["identity_change_kind"] == "reapproval"
    assert "M-1" in guidance[0].description
