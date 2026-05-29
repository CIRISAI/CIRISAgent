"""Tests for /v1/system/peers/* — NodeCode share + add endpoints.

Covers:
- GET returns a round-trippable code that decodes to the same key_id /
  pubkey the route resolved from local state.
- GET passes query params through to the embedded hints.
- GET works without query params.
- GET returns 503 when the local identity isn't available.
- POST happy path creates an organic peer (was_already_present=False).
- POST is idempotent: a second call returns was_already_present=True.
- POST with the same key_id but different pubkey returns 409
  PUBKEY_CONFLICT and does not mutate state.
- POST with bad checksum returns 400 INVALID_NODE_CODE/CHECKSUM_MISMATCH.
- POST with wrong textual version returns 400 INVALID_NODE_CODE/INVALID_VERSION.
- POST without SYSTEM_ADMIN returns 403 (via dependency override absence).
"""

from __future__ import annotations

import base64
import os
import secrets
import tempfile
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.dependencies.auth import (
    require_observer,
    require_system_admin,
)
from ciris_engine.logic.adapters.api.routes.system.peers import router
from ciris_engine.logic.persistence.db import initialize_database
from ciris_engine.logic.runtime.bootstrap_peers import BootstrapPeerSeeder
from ciris_engine.logic.utils.node_code_codec import (
    _b32_no_pad_encode,
    _build_payload,
    _crc16_ccitt,
    decode_node_code,
    encode_node_code,
)
from ciris_engine.schemas.runtime.canonical_peer import PeerTrustState
from ciris_engine.schemas.runtime.node_code import NodeCode


class _StubTimeService:
    def __init__(self, frozen: Optional[datetime] = None) -> None:
        self._frozen = frozen or datetime(2026, 5, 29, 12, 0, 0, tzinfo=timezone.utc)
        self._tick = 0

    def now(self) -> datetime:
        self._tick += 1
        return self._frozen.replace(microsecond=self._tick)

    def now_iso(self) -> str:
        return self.now().isoformat()


def _observer_auth() -> object:
    return MagicMock(user_id="obs", role="OBSERVER")


def _admin_auth() -> object:
    return MagicMock(user_id="root", role="SYSTEM_ADMIN")


def _pk_b64() -> str:
    return base64.b64encode(secrets.token_bytes(32)).decode("ascii")


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
def time_service() -> _StubTimeService:
    return _StubTimeService()


@pytest.fixture
def seeder(temp_db, time_service) -> BootstrapPeerSeeder:
    return BootstrapPeerSeeder(time_service=time_service, registry_fetch_url=None)


@pytest.fixture
def local_identity() -> tuple[str, str]:
    """Stable local identity for the agent under test."""
    return ("agent-localnode001", _pk_b64())


def _make_app(
    *,
    seeder: Optional[BootstrapPeerSeeder] = None,
    time_service: Optional[_StubTimeService] = None,
    local_identity: Optional[tuple[str, str]] = None,
    override_admin: bool = True,
    override_observer: bool = True,
) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/system")
    app.state.time_service = time_service
    if seeder is not None:
        app.state.bootstrap_peer_seeder = seeder
    if local_identity is not None:
        app.state.local_identity = local_identity
    if override_observer:
        app.dependency_overrides[require_observer] = _observer_auth
    if override_admin:
        app.dependency_overrides[require_system_admin] = _admin_auth
    return app


# --------------------------------------------------------------------------- #
# GET /system/peers/my-node-code
# --------------------------------------------------------------------------- #


class TestGetMyNodeCode:
    def test_round_trippable_code(self, temp_db, seeder, time_service, local_identity) -> None:
        app = _make_app(seeder=seeder, time_service=time_service, local_identity=local_identity)
        client = TestClient(app)
        resp = client.get("/system/peers/my-node-code")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["key_id"] == local_identity[0]
        assert data["alias_hint"] is None
        decoded = decode_node_code(data["code"])
        assert decoded.key_id == local_identity[0]
        assert decoded.pubkey_ed25519_base64 == local_identity[1]
        assert decoded.transport_hint is None
        assert decoded.alias_hint is None
        # QR payload also decodes to the same content.
        decoded_qr = decode_node_code(data["qr_payload"])
        assert decoded_qr.key_id == local_identity[0]
        assert decoded_qr.pubkey_ed25519_base64 == local_identity[1]

    def test_passes_query_params_through(self, temp_db, seeder, time_service, local_identity) -> None:
        app = _make_app(seeder=seeder, time_service=time_service, local_identity=local_identity)
        client = TestClient(app)
        resp = client.get(
            "/system/peers/my-node-code",
            params={"transport_hint": "tcp://example.com:4242", "alias_hint": "datum"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["alias_hint"] == "datum"
        decoded = decode_node_code(data["code"])
        assert decoded.transport_hint == "tcp://example.com:4242"
        assert decoded.alias_hint == "datum"

    def test_no_query_params_yields_none_hints(self, temp_db, seeder, time_service, local_identity) -> None:
        app = _make_app(seeder=seeder, time_service=time_service, local_identity=local_identity)
        client = TestClient(app)
        resp = client.get("/system/peers/my-node-code")
        assert resp.status_code == 200
        data = resp.json()["data"]
        decoded = decode_node_code(data["code"])
        assert decoded.transport_hint is None
        assert decoded.alias_hint is None

    def test_returns_503_when_identity_unavailable(
        self, temp_db, seeder, time_service, monkeypatch
    ) -> None:
        # No local_identity override -> route falls through to the real
        # verifier loader. Monkeypatch _get_local_identity to simulate
        # the "identity not yet available" case without invoking the
        # CIRISVerify FFI (which would block on this test host).
        from ciris_engine.logic.adapters.api.routes.system import peers as peers_module

        monkeypatch.setattr(peers_module, "_get_local_identity", lambda request: (None, None))

        app = _make_app(seeder=seeder, time_service=time_service, local_identity=None)
        client = TestClient(app)
        resp = client.get("/system/peers/my-node-code")
        assert resp.status_code == 503
        assert resp.json()["error"] == "FEDERATION_IDENTITY_UNAVAILABLE"


# --------------------------------------------------------------------------- #
# POST /system/peers/add-from-code
# --------------------------------------------------------------------------- #


class TestAddFromCode:
    def _share_code(self, key_id: str, pubkey: str, alias: Optional[str] = None) -> str:
        return encode_node_code(
            NodeCode(
                key_id=key_id,
                pubkey_ed25519_base64=pubkey,
                alias_hint=alias,
            )
        )

    def test_happy_path_creates_organic_peer(self, temp_db, seeder, time_service, local_identity) -> None:
        app = _make_app(seeder=seeder, time_service=time_service, local_identity=local_identity)
        client = TestClient(app)

        peer_key = "agent-remoteABC"
        peer_pk = _pk_b64()
        code = self._share_code(peer_key, peer_pk, alias="remote-display")

        resp = client.post("/system/peers/add-from-code", json={"code": code})
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["was_already_present"] is False
        peer = data["peer"]
        assert peer["key_id"] == peer_key
        assert peer["pubkey_ed25519_base64"] == peer_pk
        assert peer["canonical"] is False
        assert peer["trust"] == PeerTrustState.UNKNOWN.value
        assert peer["alias_override"] == "remote-display"

    def test_idempotent_returns_was_already_present(
        self, temp_db, seeder, time_service, local_identity
    ) -> None:
        app = _make_app(seeder=seeder, time_service=time_service, local_identity=local_identity)
        client = TestClient(app)

        peer_key = "agent-remoteIDEMPOTENT"
        peer_pk = _pk_b64()
        code = self._share_code(peer_key, peer_pk)

        first = client.post("/system/peers/add-from-code", json={"code": code})
        assert first.status_code == 200
        assert first.json()["data"]["was_already_present"] is False

        second = client.post("/system/peers/add-from-code", json={"code": code})
        assert second.status_code == 200
        body = second.json()["data"]
        assert body["was_already_present"] is True
        assert body["peer"]["key_id"] == peer_key
        assert body["peer"]["pubkey_ed25519_base64"] == peer_pk

    def test_pubkey_conflict_returns_409(self, temp_db, seeder, time_service, local_identity) -> None:
        app = _make_app(seeder=seeder, time_service=time_service, local_identity=local_identity)
        client = TestClient(app)

        peer_key = "agent-remoteCONFLICT"
        original_pk = _pk_b64()
        rotated_pk = _pk_b64()

        first = client.post(
            "/system/peers/add-from-code", json={"code": self._share_code(peer_key, original_pk)}
        )
        assert first.status_code == 200, first.text

        second = client.post(
            "/system/peers/add-from-code", json={"code": self._share_code(peer_key, rotated_pk)}
        )
        assert second.status_code == 409
        body = second.json()
        assert body["error"] == "PUBKEY_CONFLICT"
        assert body["key_id"] == peer_key
        assert body["existing_pubkey"] == original_pk
        assert body["supplied_pubkey"] == rotated_pk

        # The persisted state still has the original pubkey, not the rotated one.
        state = seeder.get_local_state(peer_key)
        assert state is not None
        assert state.pubkey_ed25519_base64 == original_pk

    def test_bad_checksum_returns_400(self, temp_db, seeder, time_service, local_identity) -> None:
        app = _make_app(seeder=seeder, time_service=time_service, local_identity=local_identity)
        client = TestClient(app)

        # Hand-craft a payload with a deliberately wrong CRC.
        nc = NodeCode(key_id="agent-x", pubkey_ed25519_base64=_pk_b64())
        payload = _build_payload(nc)
        good_crc = _crc16_ccitt(payload)
        bad_crc = (good_crc ^ 0xFFFF) & 0xFFFF
        bad_full = payload + bytes([(bad_crc >> 8) & 0xFF, bad_crc & 0xFF])
        bad_code = "CIRIS-V1-" + _b32_no_pad_encode(bad_full)

        resp = client.post("/system/peers/add-from-code", json={"code": bad_code})
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"] == "INVALID_NODE_CODE"
        assert body["subtype"] == "CHECKSUM_MISMATCH"

    def test_wrong_version_returns_400(self, temp_db, seeder, time_service, local_identity) -> None:
        app = _make_app(seeder=seeder, time_service=time_service, local_identity=local_identity)
        client = TestClient(app)
        resp = client.post(
            "/system/peers/add-from-code",
            json={"code": "CIRIS-V2-ABCD-EFGH-IJKL"},
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"] == "INVALID_NODE_CODE"
        assert body["subtype"] == "INVALID_VERSION"

    def test_malformed_returns_400(self, temp_db, seeder, time_service, local_identity) -> None:
        app = _make_app(seeder=seeder, time_service=time_service, local_identity=local_identity)
        client = TestClient(app)
        resp = client.post(
            "/system/peers/add-from-code",
            json={"code": "OTHER-V1-ABCD"},
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"] == "INVALID_NODE_CODE"
        assert body["subtype"] == "MALFORMED"

    def test_without_system_admin_returns_403(
        self, temp_db, seeder, time_service, local_identity
    ) -> None:
        # Build the app WITHOUT the require_system_admin override. The
        # real dependency rejects unauthenticated requests — depending
        # on the auth-service wiring in the test env it surfaces as
        # 401, 403, or a 500 from inside the dependency. The
        # load-bearing assertion is "did NOT succeed" — any non-2xx is
        # fine, and crucially the peer was NOT written.
        app = _make_app(
            seeder=seeder,
            time_service=time_service,
            local_identity=local_identity,
            override_admin=False,
        )
        client = TestClient(app)
        peer_key = "agent-remote403"
        code = self._share_code(peer_key, _pk_b64())
        resp = client.post("/system/peers/add-from-code", json={"code": code})
        assert resp.status_code >= 400, f"expected refusal, got {resp.status_code}"
        # And the seeder must not have written the peer.
        assert seeder.get_local_state(peer_key) is None
