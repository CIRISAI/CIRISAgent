"""Tests for POST /v1/federation/content/{content_id}."""

from __future__ import annotations

import base64
import hashlib


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class TestFederationContent:
    def test_happy_path_returns_base64_payload(
        self, make_app, fake_edge, seeder, time_service
    ) -> None:
        payload = b"hello world"
        sha = _sha256_hex(payload)
        fake_edge.set_content("agent-peer", sha, {"kind": "bytes", "bytes": payload})
        client = make_app(edge=fake_edge, seeder=seeder, time_service=time_service)
        resp = client.post(
            f"/v1/federation/content/{sha}",
            json={"peer_key_id": "agent-peer", "timeout_ms": 5000},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["content_id"] == sha
        assert base64.b64decode(data["payload_base64"]) == payload
        assert data["size_bytes"] == len(payload)
        assert data["content_type"] is None
        # fake_edge recorded the call.
        assert any(
            c[0] == "fetch_content" and c[2]["timeout_ms"] == 5000
            for c in fake_edge.calls
        )

    def test_content_miss_returns_404(
        self, make_app, fake_edge, seeder, time_service
    ) -> None:
        sha = _sha256_hex(b"never-held")
        # No set_content → FakeEdge defaults to content_miss.
        client = make_app(edge=fake_edge, seeder=seeder, time_service=time_service)
        resp = client.post(
            f"/v1/federation/content/{sha}",
            json={"peer_key_id": "agent-peer"},
        )
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"] == "CONTENT_MISS"
        assert body["content_id"] == sha
        assert body["peer_key_id"] == "agent-peer"

    def test_invalid_content_id_returns_400(
        self, make_app, fake_edge, seeder, time_service
    ) -> None:
        client = make_app(edge=fake_edge, seeder=seeder, time_service=time_service)
        resp = client.post(
            "/v1/federation/content/not-a-sha",
            json={"peer_key_id": "agent-peer"},
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "INVALID_CONTENT_ID"

    def test_edge_unavailable_returns_503(self, make_app, seeder, time_service) -> None:
        sha = _sha256_hex(b"x")
        client = make_app(edge=None, seeder=seeder, time_service=time_service)
        resp = client.post(
            f"/v1/federation/content/{sha}",
            json={"peer_key_id": "agent-peer"},
        )
        assert resp.status_code == 503
        assert resp.json()["error"] == "EDGE_UNAVAILABLE"

    def test_fetch_raises_yields_503(
        self, make_app, fake_edge, seeder, time_service
    ) -> None:
        sha = _sha256_hex(b"x")
        fake_edge.raise_fetch(RuntimeError("timeout"))
        client = make_app(edge=fake_edge, seeder=seeder, time_service=time_service)
        resp = client.post(
            f"/v1/federation/content/{sha}",
            json={"peer_key_id": "agent-peer"},
        )
        assert resp.status_code == 503
        body = resp.json()
        assert body["error"] == "FETCH_FAILED"

    def test_unknown_kind_returns_503(
        self, make_app, fake_edge, seeder, time_service
    ) -> None:
        sha = _sha256_hex(b"surprise")
        fake_edge.set_content("agent-peer", sha, {"kind": "surprise"})
        client = make_app(edge=fake_edge, seeder=seeder, time_service=time_service)
        resp = client.post(
            f"/v1/federation/content/{sha}",
            json={"peer_key_id": "agent-peer"},
        )
        assert resp.status_code == 503
        assert resp.json()["error"] == "FETCH_FAILED"

    def test_non_bytes_payload_returns_503(
        self, make_app, fake_edge, seeder, time_service
    ) -> None:
        sha = _sha256_hex(b"x")
        fake_edge.set_content("agent-peer", sha, {"kind": "bytes", "bytes": "not-bytes"})
        client = make_app(edge=fake_edge, seeder=seeder, time_service=time_service)
        resp = client.post(
            f"/v1/federation/content/{sha}",
            json={"peer_key_id": "agent-peer"},
        )
        assert resp.status_code == 503

    def test_without_system_admin_refused(
        self, make_app, fake_edge, seeder, time_service
    ) -> None:
        payload = b"secret"
        sha = _sha256_hex(payload)
        fake_edge.set_content("agent-peer", sha, {"kind": "bytes", "bytes": payload})
        client = make_app(
            edge=fake_edge,
            seeder=seeder,
            time_service=time_service,
            override_admin=False,
        )
        resp = client.post(
            f"/v1/federation/content/{sha}",
            json={"peer_key_id": "agent-peer"},
        )
        assert resp.status_code >= 400

    def test_timeout_ms_bounds_enforced(
        self, make_app, fake_edge, seeder, time_service
    ) -> None:
        sha = _sha256_hex(b"x")
        client = make_app(edge=fake_edge, seeder=seeder, time_service=time_service)
        # Below min
        r1 = client.post(
            f"/v1/federation/content/{sha}",
            json={"peer_key_id": "agent-peer", "timeout_ms": 0},
        )
        assert r1.status_code == 422
        # Above max
        r2 = client.post(
            f"/v1/federation/content/{sha}",
            json={"peer_key_id": "agent-peer", "timeout_ms": 999_999},
        )
        assert r2.status_code == 422
