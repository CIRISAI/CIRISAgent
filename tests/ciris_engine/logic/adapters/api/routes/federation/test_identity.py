"""Tests for GET /v1/federation/identity."""

from __future__ import annotations

import asyncio


class TestFederationIdentity:
    def test_happy_path_returns_identity_with_zero_peers(
        self, make_app, fake_edge, seeder, time_service
    ) -> None:
        client = make_app(edge=fake_edge, seeder=seeder, time_service=time_service)
        resp = client.get("/v1/federation/identity")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["signer_key_id"] == "agent-localnode001"
        assert data["crate_version"] == "1.0.0"
        assert data["peer_count_total"] == 0
        assert data["peer_count_canonical"] == 0
        assert data["capabilities"] == [
            "sas",
            "fetch_content",
            "metrics",
            "subscribe_events",
            "inline_text",
        ]

    def test_identity_counts_canonical_and_organic_peers(
        self, make_app, fake_edge, seeder, time_service, pk_b64
    ) -> None:
        # Seed one canonical + add one organic.
        from ciris_engine.schemas.runtime.canonical_peer import CanonicalBootstrapPeer

        seeder.seed_canonical_peers(
            [
                CanonicalBootstrapPeer(
                    key_id="agent-canon1",
                    alias="canon",
                    pubkey_ed25519_base64=pk_b64(),
                ),
            ]
        )
        asyncio.run(
            seeder.record_organic_peer(
                key_id="agent-organic1",
                pubkey_ed25519_base64=pk_b64(),
            )
        )

        client = make_app(edge=fake_edge, seeder=seeder, time_service=time_service)
        resp = client.get("/v1/federation/identity")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["peer_count_total"] == 2
        assert data["peer_count_canonical"] == 1

    def test_returns_503_when_edge_unavailable(self, make_app, seeder, time_service) -> None:
        client = make_app(edge=None, seeder=seeder, time_service=time_service)
        resp = client.get("/v1/federation/identity")
        assert resp.status_code == 503
        assert resp.json()["error"] == "EDGE_UNAVAILABLE"

    def test_returns_503_when_edge_signer_call_raises(
        self, make_app, fake_edge, seeder, time_service
    ) -> None:
        fake_edge._signer_key_id_raises = RuntimeError("signer cold")
        client = make_app(edge=fake_edge, seeder=seeder, time_service=time_service)
        resp = client.get("/v1/federation/identity")
        assert resp.status_code == 503
        assert resp.json()["error"] == "EDGE_UNAVAILABLE"

    def test_seeder_unavailable_yields_zero_counts_not_503(
        self, make_app, fake_edge, time_service
    ) -> None:
        # No seeder + no time_service => seeder cannot be constructed.
        client = make_app(edge=fake_edge, seeder=None, time_service=None)
        resp = client.get("/v1/federation/identity")
        # Identity still surfaces; counts are zero per route contract.
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["peer_count_total"] == 0
        assert data["peer_count_canonical"] == 0
