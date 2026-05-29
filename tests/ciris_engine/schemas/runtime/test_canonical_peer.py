"""Schema-level tests for the canonical bootstrap peer / local peer state surface.

Covers model validation, enum vocabulary lock-in, and the field invariants
that the seeder relies on.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from ciris_engine.schemas.runtime.canonical_peer import (
    CanonicalBootstrapPeer,
    LocalPeerState,
    PeerAppearance,
    PeerTrustState,
)


class TestPeerTrustState:
    """The trust-state vocabulary is locked to Edge's EdgePeerTrust enum.

    If a value is added/removed/renamed here, the Edge crate (CIRISEdge#46)
    needs the same change — these are wire-bytes, not just internal.
    """

    def test_vocab_exact(self) -> None:
        assert {s.value for s in PeerTrustState} == {
            "trusted",
            "untrusted",
            "blocked",
            "unknown",
        }

    def test_str_round_trip(self) -> None:
        assert PeerTrustState("trusted") is PeerTrustState.TRUSTED
        assert PeerTrustState("unknown") is PeerTrustState.UNKNOWN


class TestCanonicalBootstrapPeer:
    def test_minimal_valid(self) -> None:
        peer = CanonicalBootstrapPeer(
            key_id="abc123",
            alias="datum @ agents.ciris.ai",
            pubkey_ed25519_base64="AAAA==",
        )
        assert peer.transport_hint is None
        assert peer.description is None

    def test_all_fields(self) -> None:
        peer = CanonicalBootstrapPeer(
            key_id="abc123",
            alias="datum",
            pubkey_ed25519_base64="AAAA==",
            transport_hint="tcp://agents.ciris.ai:4242",
            description="Production datum peer",
        )
        assert peer.transport_hint == "tcp://agents.ciris.ai:4242"
        assert peer.description == "Production datum peer"

    def test_empty_key_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CanonicalBootstrapPeer(key_id="", alias="x", pubkey_ed25519_base64="y")

    def test_empty_alias_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CanonicalBootstrapPeer(key_id="k", alias="", pubkey_ed25519_base64="y")

    def test_empty_pubkey_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CanonicalBootstrapPeer(key_id="k", alias="x", pubkey_ed25519_base64="")

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            CanonicalBootstrapPeer(
                key_id="k",
                alias="x",
                pubkey_ed25519_base64="y",
                bogus="nope",  # type: ignore[call-arg]
            )


class TestPeerAppearance:
    def test_all_none_is_valid(self) -> None:
        ap = PeerAppearance()
        assert ap.icon is None
        assert ap.fg_color is None
        assert ap.bg_color is None

    def test_full(self) -> None:
        ap = PeerAppearance(icon="🟢", fg_color="#ffffff", bg_color="#000000")
        assert ap.icon == "🟢"
        assert ap.fg_color == "#ffffff"
        assert ap.bg_color == "#000000"

    def test_extra_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            PeerAppearance(emoji="🟢")  # type: ignore[call-arg]


class TestLocalPeerState:
    def _now(self) -> datetime:
        return datetime(2026, 5, 29, 12, 0, 0, tzinfo=timezone.utc)

    def test_minimal_canonical(self) -> None:
        state = LocalPeerState(
            key_id="k1",
            canonical=True,
            trust=PeerTrustState.TRUSTED,
            first_seen=self._now(),
        )
        assert state.canonical is True
        assert state.trust is PeerTrustState.TRUSTED
        assert state.appearance is None
        assert state.alias_override is None
        assert state.notes is None
        assert state.last_seen is None

    def test_minimal_organic(self) -> None:
        state = LocalPeerState(
            key_id="k2",
            canonical=False,
            trust=PeerTrustState.UNKNOWN,
            first_seen=self._now(),
        )
        assert state.canonical is False
        assert state.trust is PeerTrustState.UNKNOWN

    def test_full(self) -> None:
        ap = PeerAppearance(icon="x", fg_color="#fff", bg_color="#000")
        state = LocalPeerState(
            key_id="k3",
            canonical=True,
            trust=PeerTrustState.BLOCKED,
            appearance=ap,
            alias_override="my-datum",
            notes="blocked by user 2026-05-29",
            first_seen=self._now(),
            last_seen=self._now(),
        )
        assert state.appearance is not None
        assert state.appearance.icon == "x"
        assert state.alias_override == "my-datum"

    def test_empty_key_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LocalPeerState(
                key_id="",
                canonical=True,
                trust=PeerTrustState.TRUSTED,
                first_seen=self._now(),
            )

    def test_round_trip_through_json(self) -> None:
        state = LocalPeerState(
            key_id="k4",
            canonical=True,
            trust=PeerTrustState.UNTRUSTED,
            first_seen=self._now(),
            last_seen=self._now(),
            appearance=PeerAppearance(icon="i"),
        )
        payload = state.model_dump(mode="json")
        restored = LocalPeerState.model_validate(payload)
        assert restored == state

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            LocalPeerState(
                key_id="k",
                canonical=True,
                trust=PeerTrustState.TRUSTED,
                first_seen=self._now(),
                bogus="nope",  # type: ignore[call-arg]
            )
