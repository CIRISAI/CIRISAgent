"""Tests for the /v1/federation/peers/{key_id}/trust and /appearance routes.

The peer list + detail reads moved to the local ciris-server node
(port 4243); only the trust/appearance mutations remain on the brain.
"""

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
