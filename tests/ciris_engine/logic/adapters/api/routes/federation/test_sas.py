"""Tests for GET /v1/federation/peers/{key_id}/sas."""

from __future__ import annotations


class TestFederationSAS:
    def test_happy_path_returns_words_and_digits(
        self, make_app, fake_edge, seeder, time_service
    ) -> None:
        fake_edge.set_sas("agent-peer", ["alpha", "bravo", "charlie", "delta", "echo"], "234567")
        client = make_app(edge=fake_edge, seeder=seeder, time_service=time_service)
        resp = client.get("/v1/federation/peers/agent-peer/sas")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["key_id"] == "agent-peer"
        assert data["words"] == ["alpha", "bravo", "charlie", "delta", "echo"]
        assert data["digits"] == "234567"

    def test_unknown_peer_returns_404(self, make_app, fake_edge, seeder, time_service) -> None:
        client = make_app(edge=fake_edge, seeder=seeder, time_service=time_service)
        resp = client.get("/v1/federation/peers/agent-nope/sas")
        assert resp.status_code == 404
        assert resp.json()["error"] == "PEER_SAS_UNAVAILABLE"

    def test_edge_unavailable_returns_503(self, make_app, seeder, time_service) -> None:
        client = make_app(edge=None, seeder=seeder, time_service=time_service)
        resp = client.get("/v1/federation/peers/agent-peer/sas")
        assert resp.status_code == 503
        assert resp.json()["error"] == "EDGE_UNAVAILABLE"

    def test_tuple_words_get_normalized_to_list(
        self, make_app, fake_edge, seeder, time_service
    ) -> None:
        # If Edge ever returns a tuple, the route should coerce to list[str].
        fake_edge._sas_words["agent-peer"] = ("one", "two", "three")  # type: ignore[assignment]
        fake_edge._sas_digits["agent-peer"] = "987654"
        client = make_app(edge=fake_edge, seeder=seeder, time_service=time_service)
        resp = client.get("/v1/federation/peers/agent-peer/sas")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["words"] == ["one", "two", "three"]
