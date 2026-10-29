"""A node owner is never told "we forget about you in 14 days".

EVERY NODE IS CLAIMED, and claiming a node establishes the partnership with its
agent. Setup writes the founding PARTNERED record and the boot migration
backfills the owners it can see, but Eric's phone (its node owned by his fedID
from another device) reached its first interact without one. It got the
TEMPORARY default and the notice, and kept a TEMPORARY record that would have
forgotten him.

These tests hold the interact path: the owner gets the founding record, an
automatic TEMPORARY is repaired, a TEMPORARY the owner chose stays theirs, and
everyone else keeps the default and the notice.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Dict, List, Optional

import pytest

from ciris_engine.logic.adapters.api.routes import agent as A
from ciris_engine.logic.services.governance.consent import ConsentNotFoundError
from ciris_engine.schemas.api.auth import AuthContext, UserRole
from ciris_engine.schemas.consent.core import ConsentAuditEntry, ConsentStream

OWNER = "wa-root-owner-qGyw"
STRANGER = "wa-observer-1"


class FakeConsent:
    def __init__(self, streams: Dict[str, ConsentStream], reasons: Optional[Dict[str, List[str]]] = None) -> None:
        self.streams = dict(streams)
        self.reasons = reasons or {}
        self.granted: List[str] = []
        self.invalidated: List[str] = []

    async def get_consent(self, user_id: str):
        if user_id not in self.streams:
            raise ConsentNotFoundError(user_id)
        return SimpleNamespace(stream=self.streams[user_id])

    async def grant_consent(self, req, channel_id=None):
        self.granted.append(req.user_id)
        self.streams[req.user_id] = req.stream

    async def get_audit_trail(self, user_id: str, limit: int = 100):
        now = datetime.now(timezone.utc)
        return [
            ConsentAuditEntry(
                entry_id=f"e{i}", user_id=user_id, timestamp=now, previous_stream=ConsentStream.TEMPORARY,
                new_stream=ConsentStream.TEMPORARY, previous_categories=[], new_categories=[],
                initiated_by="user", reason=r,
            )
            for i, r in enumerate(self.reasons.get(user_id, []))
        ]

    def invalidate_cached(self, user_id: str) -> None:
        self.invalidated.append(user_id)


def _auth(uid: str) -> AuthContext:
    return AuthContext(user_id=uid, role=UserRole.ADMIN, permissions=set(), authenticated_at=datetime.now(timezone.utc))


def _request(cm: FakeConsent):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(consent_manager=cm)))


@pytest.fixture
def founded(monkeypatch: pytest.MonkeyPatch) -> List[str]:
    written: List[str] = []
    monkeypatch.setattr(
        "ciris_engine.logic.adapters.api.routes.setup.complete._create_founding_partnership",
        lambda wa_id, ingress_user_id=None: written.append(wa_id),
    )
    return written


def _owner_is(monkeypatch: pytest.MonkeyPatch, wa_id: Optional[str], fails: bool = False) -> None:
    async def read():
        if fails:
            raise TimeoutError("substrate did not answer")
        return SimpleNamespace(wa_id=wa_id) if wa_id else None

    monkeypatch.setattr("ciris_engine.logic.utils.node_ownership.read_owner_record", read)


@pytest.mark.asyncio
async def test_an_owner_with_no_record_gets_the_founding_partnership_and_no_notice(monkeypatch, founded):
    _owner_is(monkeypatch, OWNER)
    cm = FakeConsent({})
    assert await A._handle_consent_for_user(_auth(OWNER), "api_x", _request(cm)) == ""
    assert founded == [OWNER] and cm.granted == [] and cm.invalidated == [OWNER]


@pytest.mark.asyncio
async def test_an_owners_automatic_temporary_is_repaired(monkeypatch, founded):
    """Eric's phone: the first interact already minted TEMPORARY. It must not stand."""
    _owner_is(monkeypatch, OWNER)
    cm = FakeConsent({OWNER: ConsentStream.TEMPORARY}, {OWNER: [A._DEFAULT_TEMPORARY_REASON]})
    assert await A._handle_consent_for_user(_auth(OWNER), "api_x", _request(cm)) == ""
    assert founded == [OWNER]


@pytest.mark.asyncio
async def test_a_temporary_the_owner_chose_stays_theirs(monkeypatch, founded):
    _owner_is(monkeypatch, OWNER)
    cm = FakeConsent({OWNER: ConsentStream.TEMPORARY}, {OWNER: [A._DEFAULT_TEMPORARY_REASON, "I want to be forgotten"]})
    assert await A._handle_consent_for_user(_auth(OWNER), "api_x", _request(cm)) == ""
    assert founded == []


@pytest.mark.asyncio
async def test_a_partnered_owner_is_left_alone(monkeypatch, founded):
    _owner_is(monkeypatch, OWNER)
    cm = FakeConsent({OWNER: ConsentStream.PARTNERED})
    assert await A._handle_consent_for_user(_auth(OWNER), "api_x", _request(cm)) == ""
    assert founded == []


@pytest.mark.asyncio
async def test_anyone_else_keeps_the_temporary_default_and_the_notice(monkeypatch, founded):
    """The negative: the repair is the owner's alone."""
    _owner_is(monkeypatch, OWNER)
    cm = FakeConsent({})
    notice = await A._handle_consent_for_user(_auth(STRANGER), "api_x", _request(cm))
    assert "We forget about you in 14 days" in notice
    assert cm.granted == [STRANGER] and founded == []


@pytest.mark.asyncio
async def test_an_unreadable_owner_is_not_assumed_to_be_this_user(monkeypatch, founded):
    _owner_is(monkeypatch, OWNER, fails=True)
    cm = FakeConsent({})
    notice = await A._handle_consent_for_user(_auth(OWNER), "api_x", _request(cm))
    assert "14 days" in notice and founded == []
