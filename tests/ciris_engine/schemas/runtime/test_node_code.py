"""Schema-level tests for NodeCode and the share/add request/response models."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from ciris_engine.schemas.runtime.canonical_peer import LocalPeerState, PeerTrustState
from ciris_engine.schemas.runtime.node_code import (
    NodeCode,
    NodeCodeAddRequest,
    NodeCodeAddResponse,
    NodeCodeShareResponse,
)


class TestNodeCode:
    def test_minimal_valid(self) -> None:
        nc = NodeCode(key_id="agent-abc", pubkey_ed25519_base64="AAAA==")
        assert nc.transport_hint is None
        assert nc.alias_hint is None

    def test_full_valid(self) -> None:
        nc = NodeCode(
            key_id="agent-abc",
            pubkey_ed25519_base64="AAAA==",
            transport_hint="tcp://example.com:4242",
            alias_hint="datum",
        )
        assert nc.transport_hint == "tcp://example.com:4242"
        assert nc.alias_hint == "datum"

    def test_empty_key_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            NodeCode(key_id="", pubkey_ed25519_base64="AAAA==")

    def test_empty_pubkey_rejected(self) -> None:
        with pytest.raises(ValidationError):
            NodeCode(key_id="agent-abc", pubkey_ed25519_base64="")

    def test_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            NodeCode(
                key_id="agent-abc",
                pubkey_ed25519_base64="AAAA==",
                bogus_field="x",  # type: ignore[call-arg]
            )


class TestNodeCodeShareResponse:
    def test_minimal_valid(self) -> None:
        resp = NodeCodeShareResponse(
            code="CIRIS-V1-ABCD",
            qr_payload="CIRIS-V1-ABCD",
            key_id="agent-abc",
            alias_hint=None,
        )
        assert resp.code == "CIRIS-V1-ABCD"
        assert resp.alias_hint is None

    def test_alias_hint_optional(self) -> None:
        resp = NodeCodeShareResponse(
            code="C",
            qr_payload="C",
            key_id="agent-abc",
            alias_hint="datum",
        )
        assert resp.alias_hint == "datum"

    def test_empty_code_rejected(self) -> None:
        with pytest.raises(ValidationError):
            NodeCodeShareResponse(code="", qr_payload="C", key_id="agent-abc")


class TestNodeCodeAddRequest:
    def test_minimal_valid(self) -> None:
        req = NodeCodeAddRequest(code="CIRIS-V1-ABCD")
        assert req.code == "CIRIS-V1-ABCD"

    def test_empty_code_rejected(self) -> None:
        with pytest.raises(ValidationError):
            NodeCodeAddRequest(code="")


class TestNodeCodeAddResponse:
    def test_returns_local_peer_state(self) -> None:
        peer = LocalPeerState(
            key_id="agent-abc",
            pubkey_ed25519_base64="AAAA==",
            canonical=False,
            trust=PeerTrustState.UNKNOWN,
            first_seen=datetime(2026, 5, 29, tzinfo=timezone.utc),
        )
        resp = NodeCodeAddResponse(peer=peer, was_already_present=False)
        assert resp.was_already_present is False
        assert resp.peer.key_id == "agent-abc"
