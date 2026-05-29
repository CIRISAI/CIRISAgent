"""
Tests for BootstrapPeerSeeder (CIRISEdge#46 agent-side framework).

Covers the "rock-solid + organic" invariants:

  1. Canonical peers always present after reseed (even if mid-state deletion).
  2. User trust state on canonical peer survives reseed (TRUSTED->UNTRUSTED->reseed->UNTRUSTED).
  3. BLOCKED canonical peer stays BLOCKED across reseed.
  4. Organic peers accumulate with trust=UNKNOWN.
  5. Organic peer can be promoted to TRUSTED and persists.
  6. set_trust on unknown key_id raises ValueError (no silent insert).

Plus the registry-fetch fallback paths and concurrency safety.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock

import pytest

from ciris_engine.logic.persistence.db import initialize_database
from ciris_engine.logic.runtime.bootstrap_peers import BootstrapPeerSeeder
from ciris_engine.schemas.runtime.canonical_peer import (
    CanonicalBootstrapPeer,
    LocalPeerState,
    PeerAppearance,
    PeerTrustState,
)


class _StubTimeService:
    """Minimal TimeServiceProtocol stub: returns a frozen wall-clock now."""

    def __init__(self, frozen: Optional[datetime] = None) -> None:
        self._frozen = frozen or datetime(2026, 5, 29, 12, 0, 0, tzinfo=timezone.utc)
        self._tick = 0

    def now(self) -> datetime:
        # Advance by 1 second each call so first_seen / last_seen are
        # distinguishable in tests that care about ordering.
        self._tick += 1
        return self._frozen.replace(microsecond=self._tick)

    def now_iso(self) -> str:
        return self.now().isoformat()


@pytest.fixture
def temp_db():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    initialize_database(db_path)
    yield db_path
    if os.path.exists(db_path):
        try:
            os.unlink(db_path)
        except OSError:
            pass


@pytest.fixture
def time_service():
    return _StubTimeService()


@pytest.fixture
def seeder(temp_db, time_service):
    return BootstrapPeerSeeder(time_service=time_service, registry_fetch_url=None)


def _peer(key_id: str = "datum-001", alias: str = "datum", pubkey: str = "AAAA==") -> CanonicalBootstrapPeer:
    return CanonicalBootstrapPeer(
        key_id=key_id,
        alias=alias,
        pubkey_ed25519_base64=pubkey,
        transport_hint=None,
        description=None,
    )


# ---------------------------------------------------------------------------
# Invariant tests.
# ---------------------------------------------------------------------------


class TestCanonicalReseedInvariants:
    """Group the rock-solid invariants together so a regression in any one
    fails a clearly-named test."""

    def test_canonical_peer_present_after_first_seed(self, seeder):
        peer = _peer()
        seeder.seed_canonical_peers([peer])

        state = seeder.get_local_state(peer.key_id)
        assert state is not None
        assert state.canonical is True
        assert state.trust is PeerTrustState.TRUSTED

    def test_canonical_peer_always_present_after_reseed_when_deleted_midstate(self, seeder):
        """INVARIANT: canonical peers reappear on reseed even if a code path
        somehow deleted them in between."""
        peer = _peer()
        seeder.seed_canonical_peers([peer])
        assert seeder.get_local_state(peer.key_id) is not None

        # Simulate the "what if a code path deleted it" worst-case.
        seeder.delete_for_test(peer.key_id)
        assert seeder.get_local_state(peer.key_id) is None

        seeder.seed_canonical_peers([peer])
        restored = seeder.get_local_state(peer.key_id)
        assert restored is not None
        assert restored.canonical is True
        # Trust resets to default TRUSTED only because the row was destroyed —
        # that's the documented worst-case. The normal-path "survives reseed"
        # invariant is covered by the next test.
        assert restored.trust is PeerTrustState.TRUSTED

    @pytest.mark.asyncio
    async def test_user_set_trust_state_on_canonical_peer_survives_reseed(self, seeder):
        """INVARIANT: TRUSTED -> UNTRUSTED -> reseed -> still UNTRUSTED."""
        peer = _peer()
        seeder.seed_canonical_peers([peer])

        await seeder.set_trust(peer.key_id, PeerTrustState.UNTRUSTED)
        assert seeder.get_local_state(peer.key_id).trust is PeerTrustState.UNTRUSTED

        seeder.seed_canonical_peers([peer])
        after = seeder.get_local_state(peer.key_id)
        assert after is not None
        assert after.trust is PeerTrustState.UNTRUSTED, "user trust state must survive reseed"
        assert after.canonical is True

    @pytest.mark.asyncio
    async def test_blocked_canonical_peer_stays_blocked_across_reseed(self, seeder):
        """INVARIANT: BLOCKED canonical peer stays BLOCKED after reseed."""
        peer = _peer()
        seeder.seed_canonical_peers([peer])
        await seeder.set_trust(peer.key_id, PeerTrustState.BLOCKED)

        # Two reseeds back-to-back — mimics restart + cache warm.
        seeder.seed_canonical_peers([peer])
        seeder.seed_canonical_peers([peer])

        after = seeder.get_local_state(peer.key_id)
        assert after is not None
        assert after.trust is PeerTrustState.BLOCKED

    @pytest.mark.asyncio
    async def test_user_appearance_alias_notes_survive_reseed(self, seeder):
        """INVARIANT extension: user-owned annotations also survive reseed."""
        peer = _peer()
        seeder.seed_canonical_peers([peer])
        await seeder.set_appearance(peer.key_id, PeerAppearance(icon="🟢", fg_color="#fff", bg_color="#000"))

        seeder.seed_canonical_peers([peer])
        after = seeder.get_local_state(peer.key_id)
        assert after is not None
        assert after.appearance is not None
        assert after.appearance.icon == "🟢"
        assert after.appearance.fg_color == "#fff"


class TestOrganicPeerInvariants:
    @pytest.mark.asyncio
    async def test_organic_peer_accumulates_with_unknown_trust(self, seeder):
        """INVARIANT: organic peers default to UNKNOWN."""
        state = await seeder.record_organic_peer("k1", "PUBKEY1", alias="bob")
        assert state.canonical is False
        assert state.trust is PeerTrustState.UNKNOWN

        await seeder.record_organic_peer("k2", "PUBKEY2", alias="alice")

        all_peers = seeder.list_peers()
        keys = {p.key_id for p in all_peers}
        assert {"k1", "k2"} <= keys
        for p in all_peers:
            if p.key_id in {"k1", "k2"}:
                assert p.trust is PeerTrustState.UNKNOWN

    @pytest.mark.asyncio
    async def test_organic_peer_promoted_to_trusted_persists(self, seeder):
        """INVARIANT: promotion sticks across re-reads."""
        await seeder.record_organic_peer("k1", "PUBKEY1", alias="bob")
        await seeder.set_trust("k1", PeerTrustState.TRUSTED)

        # Re-read after set_trust completes.
        state = seeder.get_local_state("k1")
        assert state is not None
        assert state.trust is PeerTrustState.TRUSTED
        assert state.canonical is False

        # Re-recording the same key MUST NOT downgrade trust.
        await seeder.record_organic_peer("k1", "PUBKEY1", alias="bob")
        state_after = seeder.get_local_state("k1")
        assert state_after.trust is PeerTrustState.TRUSTED

    @pytest.mark.asyncio
    async def test_set_trust_on_unknown_keyid_raises_valueerror(self, seeder):
        """INVARIANT: no silent inserts via set_trust."""
        with pytest.raises(ValueError, match="unknown peer"):
            await seeder.set_trust("never-seen-key", PeerTrustState.TRUSTED)
        assert seeder.get_local_state("never-seen-key") is None

    @pytest.mark.asyncio
    async def test_record_organic_peer_idempotent(self, seeder):
        """INVARIANT: calling twice doesn't duplicate."""
        a = await seeder.record_organic_peer("k1", "PUBKEY1", alias="bob")
        b = await seeder.record_organic_peer("k1", "PUBKEY1", alias="bob")
        assert a.key_id == b.key_id

        peers = [p for p in seeder.list_peers() if p.key_id == "k1"]
        assert len(peers) == 1

    @pytest.mark.asyncio
    async def test_set_appearance_on_unknown_keyid_raises_valueerror(self, seeder):
        with pytest.raises(ValueError, match="unknown peer"):
            await seeder.set_appearance("never-seen-key", PeerAppearance(icon="x"))


class TestCanonicalVsOrganicCollision:
    @pytest.mark.asyncio
    async def test_organic_announce_for_canonical_key_does_not_create_organic_row(self, seeder):
        """If we already have a canonical row, an ANNOUNCE for the same key
        does NOT create a competing organic row."""
        peer = _peer()
        seeder.seed_canonical_peers([peer])

        returned = await seeder.record_organic_peer(peer.key_id, "AAAA==", alias="datum")
        assert returned.canonical is True
        assert returned.trust is PeerTrustState.TRUSTED  # canonical default preserved

        # Only ONE row per key_id total.
        peers = [p for p in seeder.list_peers() if p.key_id == peer.key_id]
        assert len(peers) == 1
        assert peers[0].canonical is True


class TestListPeers:
    @pytest.mark.asyncio
    async def test_list_canonical_only(self, seeder):
        peer = _peer()
        seeder.seed_canonical_peers([peer])
        await seeder.record_organic_peer("k-organic", "PUB", alias="org")

        canonical_only = seeder.list_peers(canonical_only=True)
        all_peers = seeder.list_peers()

        assert len(canonical_only) == 1
        assert canonical_only[0].key_id == peer.key_id

        all_keys = {p.key_id for p in all_peers}
        assert {peer.key_id, "k-organic"} <= all_keys


# ---------------------------------------------------------------------------
# Registry fetch fallback.
# ---------------------------------------------------------------------------


class _StubResponse:
    def __init__(self, status_code: int, body: object) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> object:
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class _StubAsyncClient:
    def __init__(self, resp: _StubResponse) -> None:
        self._resp = resp
        self.calls: List[Tuple[str, float]] = []

    async def get(self, url: str, timeout: float = 5.0) -> _StubResponse:
        self.calls.append((url, timeout))
        return self._resp


class TestRegistryFetch:
    @pytest.mark.asyncio
    async def test_no_url_returns_constants_list(self, temp_db, time_service):
        # The constants list is empty by spec — that's what we should get.
        from ciris_engine.constants import CIRIS_CANONICAL_BOOTSTRAP_PEERS

        seeder = BootstrapPeerSeeder(time_service=time_service, registry_fetch_url=None)
        peers = await seeder.fetch_from_registry()
        assert peers == list(CIRIS_CANONICAL_BOOTSTRAP_PEERS)

    @pytest.mark.asyncio
    async def test_http_500_falls_back_to_constants(self, temp_db, time_service):
        stub = _StubAsyncClient(_StubResponse(500, {"peers": []}))
        seeder = BootstrapPeerSeeder(
            time_service=time_service,
            registry_fetch_url="http://example.invalid/directory",
            http_client=stub,
        )
        peers = await seeder.fetch_from_registry()
        # constants list is empty -> we get [].
        assert peers == []
        assert len(stub.calls) == 1

    @pytest.mark.asyncio
    async def test_http_transport_failure_falls_back_to_constants(self, temp_db, time_service):
        boom_client = MagicMock()
        boom_client.get = AsyncMock(side_effect=RuntimeError("connection refused"))
        seeder = BootstrapPeerSeeder(
            time_service=time_service,
            registry_fetch_url="http://example.invalid/directory",
            http_client=boom_client,
        )
        peers = await seeder.fetch_from_registry()
        assert peers == []  # falls back to empty constants list

    @pytest.mark.asyncio
    async def test_invalid_json_falls_back_to_constants(self, temp_db, time_service):
        stub = _StubAsyncClient(_StubResponse(200, ValueError("garbage")))
        seeder = BootstrapPeerSeeder(
            time_service=time_service,
            registry_fetch_url="http://example.invalid/directory",
            http_client=stub,
        )
        peers = await seeder.fetch_from_registry()
        assert peers == []

    @pytest.mark.asyncio
    async def test_successful_fetch_returns_validated_peers(self, temp_db, time_service):
        body = {
            "peers": [
                {
                    "key_id": "datum-001",
                    "alias": "datum",
                    "pubkey_ed25519_base64": "AAAA==",
                },
                {
                    "key_id": "datum-002",
                    "alias": "datum-2",
                    "pubkey_ed25519_base64": "BBBB==",
                    "transport_hint": "tcp://x:4242",
                },
            ],
        }
        stub = _StubAsyncClient(_StubResponse(200, body))
        seeder = BootstrapPeerSeeder(
            time_service=time_service,
            registry_fetch_url="http://example.invalid/directory",
            http_client=stub,
        )
        peers = await seeder.fetch_from_registry()
        assert len(peers) == 2
        assert peers[0].key_id == "datum-001"
        assert peers[1].transport_hint == "tcp://x:4242"

    @pytest.mark.asyncio
    async def test_bare_list_body_accepted(self, temp_db, time_service):
        body = [
            {"key_id": "datum-001", "alias": "datum", "pubkey_ed25519_base64": "AAAA=="},
        ]
        stub = _StubAsyncClient(_StubResponse(200, body))
        seeder = BootstrapPeerSeeder(
            time_service=time_service,
            registry_fetch_url="http://example.invalid/directory",
            http_client=stub,
        )
        peers = await seeder.fetch_from_registry()
        assert len(peers) == 1

    @pytest.mark.asyncio
    async def test_unexpected_shape_falls_back(self, temp_db, time_service):
        stub = _StubAsyncClient(_StubResponse(200, "not a peer list"))
        seeder = BootstrapPeerSeeder(
            time_service=time_service,
            registry_fetch_url="http://example.invalid/directory",
            http_client=stub,
        )
        peers = await seeder.fetch_from_registry()
        assert peers == []

    @pytest.mark.asyncio
    async def test_malformed_entries_skipped(self, temp_db, time_service):
        body = {
            "peers": [
                {"key_id": "good", "alias": "x", "pubkey_ed25519_base64": "y"},
                {"key_id": ""},  # invalid - empty key_id
                "not-a-dict",
            ],
        }
        stub = _StubAsyncClient(_StubResponse(200, body))
        seeder = BootstrapPeerSeeder(
            time_service=time_service,
            registry_fetch_url="http://example.invalid/directory",
            http_client=stub,
        )
        peers = await seeder.fetch_from_registry()
        assert len(peers) == 1
        assert peers[0].key_id == "good"


# ---------------------------------------------------------------------------
# Concurrency.
# ---------------------------------------------------------------------------


class TestConcurrentMutations:
    @pytest.mark.asyncio
    async def test_concurrent_set_trust_calls_safe(self, seeder):
        """INVARIANT: parallel mutations don't corrupt state."""
        peer = _peer()
        seeder.seed_canonical_peers([peer])

        # Fire several set_trust calls in parallel — last one wins, but
        # the row must remain readable and valid throughout.
        await asyncio.gather(
            seeder.set_trust(peer.key_id, PeerTrustState.UNTRUSTED),
            seeder.set_trust(peer.key_id, PeerTrustState.TRUSTED),
            seeder.set_trust(peer.key_id, PeerTrustState.BLOCKED),
            seeder.set_trust(peer.key_id, PeerTrustState.UNTRUSTED),
        )

        state = seeder.get_local_state(peer.key_id)
        assert state is not None
        assert state.trust in {
            PeerTrustState.UNTRUSTED,
            PeerTrustState.TRUSTED,
            PeerTrustState.BLOCKED,
        }
        # Single row only — no duplicates from races.
        peers = [p for p in seeder.list_peers() if p.key_id == peer.key_id]
        assert len(peers) == 1

    @pytest.mark.asyncio
    async def test_concurrent_record_organic_peer_idempotent(self, seeder):
        """INVARIANT: parallel ANNOUNCE handling for the same key doesn't duplicate."""
        await asyncio.gather(
            seeder.record_organic_peer("k1", "PUB", alias="x"),
            seeder.record_organic_peer("k1", "PUB", alias="x"),
            seeder.record_organic_peer("k1", "PUB", alias="x"),
        )

        peers = [p for p in seeder.list_peers() if p.key_id == "k1"]
        assert len(peers) == 1
