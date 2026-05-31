"""Tests for /v1/federation/peers and /v1/federation/peers/{key_id}* routes."""

from __future__ import annotations

import asyncio

import pytest

from ciris_engine.schemas.runtime.canonical_peer import (
    CanonicalBootstrapPeer,
    PeerAppearance,
    PeerTrustState,
)


@pytest.fixture
def populated_seeder(seeder, pk_b64):
    """Seeder with one canonical + one organic peer."""
    seeder.seed_canonical_peers(
        [
            CanonicalBootstrapPeer(
                key_id="agent-canon1",
                alias="canon-alpha",
                pubkey_ed25519_base64=pk_b64(),
            )
        ]
    )
    asyncio.run(
        seeder.record_organic_peer(
            key_id="agent-organic1",
            pubkey_ed25519_base64=pk_b64(),
            alias="orgnametag",
        )
    )
    return seeder


class TestListPeers:
    def test_returns_all_peers_by_default(
        self, make_app, fake_edge, populated_seeder, time_service
    ) -> None:
        client = make_app(edge=fake_edge, seeder=populated_seeder, time_service=time_service)
        resp = client.get("/v1/federation/peers")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["total"] == 2
        keys = {p["key_id"] for p in data["peers"]}
        assert keys == {"agent-canon1", "agent-organic1"}

    def test_canonical_only_filters_organic(
        self, make_app, fake_edge, populated_seeder, time_service
    ) -> None:
        client = make_app(edge=fake_edge, seeder=populated_seeder, time_service=time_service)
        resp = client.get("/v1/federation/peers?canonical_only=true")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 1
        assert data["peers"][0]["key_id"] == "agent-canon1"

    def test_trust_filter(self, make_app, fake_edge, populated_seeder, time_service) -> None:
        # Canonical defaults to TRUSTED; organic defaults to UNKNOWN.
        client = make_app(edge=fake_edge, seeder=populated_seeder, time_service=time_service)
        resp = client.get("/v1/federation/peers?trust=trusted")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 1
        assert data["peers"][0]["key_id"] == "agent-canon1"

        resp2 = client.get("/v1/federation/peers?trust=unknown")
        data2 = resp2.json()["data"]
        assert data2["total"] == 1
        assert data2["peers"][0]["key_id"] == "agent-organic1"

    def test_returns_503_when_seeder_unavailable(self, make_app, fake_edge) -> None:
        client = make_app(edge=fake_edge, seeder=None, time_service=None)
        resp = client.get("/v1/federation/peers")
        assert resp.status_code == 503
        assert resp.json()["error"] == "BOOTSTRAP_SEEDER_UNAVAILABLE"


class TestGetPeerDetail:
    def test_returns_peer_with_reachability(
        self, make_app, fake_edge, populated_seeder, time_service
    ) -> None:
        fake_edge.set_reachability(
            "agent-canon1",
            {
                "reticulum-rs": {"ratio": 0.75, "last_ok_ts": 1716000000000},
                "http": {"ratio": 1.0, "last_ok_ts": 1716000005000},
            },
        )
        client = make_app(edge=fake_edge, seeder=populated_seeder, time_service=time_service)
        resp = client.get("/v1/federation/peers/agent-canon1")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["peer"]["key_id"] == "agent-canon1"
        assert data["reachability"]["by_medium"]["reticulum-rs"]["ratio"] == 0.75
        assert data["reachability"]["by_medium"]["http"]["last_ok_ts"] == 1716000005000

    def test_empty_reachability_yields_empty_by_medium(
        self, make_app, fake_edge, populated_seeder, time_service
    ) -> None:
        # No reachability configured → FakeEdge returns {} → empty by_medium.
        client = make_app(edge=fake_edge, seeder=populated_seeder, time_service=time_service)
        resp = client.get("/v1/federation/peers/agent-canon1")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["reachability"]["by_medium"] == {}

    def test_unknown_peer_returns_404(
        self, make_app, fake_edge, populated_seeder, time_service
    ) -> None:
        client = make_app(edge=fake_edge, seeder=populated_seeder, time_service=time_service)
        resp = client.get("/v1/federation/peers/agent-unknown")
        assert resp.status_code == 404
        assert resp.json()["error"] == "PEER_NOT_FOUND"

    def test_edge_unavailable_returns_503(
        self, make_app, populated_seeder, time_service
    ) -> None:
        client = make_app(edge=None, seeder=populated_seeder, time_service=time_service)
        resp = client.get("/v1/federation/peers/agent-canon1")
        assert resp.status_code == 503
        assert resp.json()["error"] == "EDGE_UNAVAILABLE"

    def test_reachability_call_raises_yields_503(
        self, make_app, fake_edge, populated_seeder, time_service
    ) -> None:
        fake_edge.set_reachability("agent-canon1", RuntimeError("transport down"))
        client = make_app(edge=fake_edge, seeder=populated_seeder, time_service=time_service)
        resp = client.get("/v1/federation/peers/agent-canon1")
        assert resp.status_code == 503

    def test_out_of_range_reachability_entries_dropped(
        self, make_app, fake_edge, populated_seeder, time_service
    ) -> None:
        fake_edge.set_reachability(
            "agent-canon1",
            {
                "ok": {"ratio": 0.5, "last_ok_ts": 100},
                "bad-ratio": {"ratio": 2.0, "last_ok_ts": 100},
                "bad-ts": {"ratio": 0.5, "last_ok_ts": -1},
                "bad-shape": "not-a-dict",
            },
        )
        client = make_app(edge=fake_edge, seeder=populated_seeder, time_service=time_service)
        resp = client.get("/v1/federation/peers/agent-canon1")
        assert resp.status_code == 200
        by_medium = resp.json()["data"]["reachability"]["by_medium"]
        assert set(by_medium.keys()) == {"ok"}


class TestSetTrust:
    def test_happy_path_updates_trust(
        self, make_app, fake_edge, populated_seeder, time_service
    ) -> None:
        client = make_app(edge=fake_edge, seeder=populated_seeder, time_service=time_service)
        resp = client.put(
            "/v1/federation/peers/agent-organic1/trust",
            json={"trust": "trusted"},
        )
        assert resp.status_code == 200, resp.text
        peer = resp.json()["data"]
        assert peer["trust"] == "trusted"
        # And the seeder reflects it.
        assert populated_seeder.get_local_state("agent-organic1").trust == PeerTrustState.TRUSTED

    def test_unknown_peer_returns_404(
        self, make_app, fake_edge, populated_seeder, time_service
    ) -> None:
        client = make_app(edge=fake_edge, seeder=populated_seeder, time_service=time_service)
        resp = client.put(
            "/v1/federation/peers/agent-nope/trust",
            json={"trust": "trusted"},
        )
        assert resp.status_code == 404
        assert resp.json()["error"] == "PEER_NOT_FOUND"

    def test_without_admin_role_refused(
        self, make_app, fake_edge, populated_seeder, time_service
    ) -> None:
        client = make_app(
            edge=fake_edge,
            seeder=populated_seeder,
            time_service=time_service,
            override_admin=False,
        )
        resp = client.put(
            "/v1/federation/peers/agent-organic1/trust",
            json={"trust": "blocked"},
        )
        assert resp.status_code >= 400
        # And nothing changed.
        assert populated_seeder.get_local_state("agent-organic1").trust == PeerTrustState.UNKNOWN

    def test_invalid_trust_value_returns_422(
        self, make_app, fake_edge, populated_seeder, time_service
    ) -> None:
        client = make_app(edge=fake_edge, seeder=populated_seeder, time_service=time_service)
        resp = client.put(
            "/v1/federation/peers/agent-organic1/trust",
            json={"trust": "wobbly"},
        )
        assert resp.status_code == 422


class TestSetAppearance:
    def test_happy_path_updates_appearance(
        self, make_app, fake_edge, populated_seeder, time_service
    ) -> None:
        client = make_app(edge=fake_edge, seeder=populated_seeder, time_service=time_service)
        body = {
            "appearance": {
                "icon": "🛡",
                "fg_color": "#ffffff",
                "bg_color": "#000000",
            }
        }
        resp = client.put("/v1/federation/peers/agent-canon1/appearance", json=body)
        assert resp.status_code == 200, resp.text
        peer = resp.json()["data"]
        assert peer["appearance"]["icon"] == "🛡"
        assert peer["appearance"]["bg_color"] == "#000000"

        # Persisted appearance survives a re-read.
        appearance = populated_seeder.get_local_state("agent-canon1").appearance
        assert isinstance(appearance, PeerAppearance)
        assert appearance.fg_color == "#ffffff"

    def test_unknown_peer_returns_404(
        self, make_app, fake_edge, populated_seeder, time_service
    ) -> None:
        client = make_app(edge=fake_edge, seeder=populated_seeder, time_service=time_service)
        resp = client.put(
            "/v1/federation/peers/agent-nope/appearance",
            json={"appearance": {"icon": "🛡"}},
        )
        assert resp.status_code == 404
        assert resp.json()["error"] == "PEER_NOT_FOUND"
