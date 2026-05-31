"""Tests for GET /v1/federation/metrics."""

from __future__ import annotations


class TestFederationMetrics:
    def test_happy_path_wraps_snapshot(
        self, make_app, fake_edge, seeder, time_service
    ) -> None:
        fake_edge._inline_text_subscriber_count = 3
        fake_edge.set_metrics(
            {
                "envelopes_sent_total": {"InlineText": 42, "FederationAnnouncement": 7},
                "envelopes_received_total": {"InlineText": 10},
                "send_failures_total": {"reticulum-rs:unreachable": 1},
                "verify_failures_total": {"replay_detected": 3},
                "durable_queue_depth": {"durable": 5, "mandatory": 0},
                "transport_bytes_in_total": {"reticulum-rs": 24576},
                "transport_bytes_out_total": {"http": 1024},
                "peer_reachability_ratio": {"peer-x:reticulum-rs": 0.75},
            }
        )
        client = make_app(edge=fake_edge, seeder=seeder, time_service=time_service)
        resp = client.get("/v1/federation/metrics")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["envelopes_sent_total"]["InlineText"] == 42
        assert data["envelopes_received_total"]["InlineText"] == 10
        assert data["send_failures_total"]["reticulum-rs:unreachable"] == 1
        assert data["verify_failures_total"]["replay_detected"] == 3
        assert data["durable_queue_depth"]["durable"] == 5
        assert data["transport_bytes_in_total"]["reticulum-rs"] == 24576
        assert data["transport_bytes_out_total"]["http"] == 1024
        assert data["peer_reachability_ratio"]["peer-x:reticulum-rs"] == 0.75
        assert data["inline_text_subscriber_count"] == 3

    def test_edge_unavailable_returns_503(self, make_app, seeder, time_service) -> None:
        client = make_app(edge=None, seeder=seeder, time_service=time_service)
        resp = client.get("/v1/federation/metrics")
        assert resp.status_code == 503
        assert resp.json()["error"] == "EDGE_UNAVAILABLE"

    def test_metrics_call_raises_yields_503(
        self, make_app, fake_edge, seeder, time_service
    ) -> None:
        fake_edge.raise_metrics(RuntimeError("metrics offline"))
        client = make_app(edge=fake_edge, seeder=seeder, time_service=time_service)
        resp = client.get("/v1/federation/metrics")
        assert resp.status_code == 503

    def test_empty_snapshot_yields_empty_maps(
        self, make_app, fake_edge, seeder, time_service
    ) -> None:
        fake_edge.set_metrics({})
        client = make_app(edge=fake_edge, seeder=seeder, time_service=time_service)
        resp = client.get("/v1/federation/metrics")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["envelopes_sent_total"] == {}
        assert data["peer_reachability_ratio"] == {}
        assert data["inline_text_subscriber_count"] == 0

    def test_malformed_metric_entries_are_dropped(
        self, make_app, fake_edge, seeder, time_service
    ) -> None:
        fake_edge.set_metrics(
            {
                "envelopes_sent_total": {
                    "InlineText": 42,
                    "BadValue": "not-a-number",
                    123: 99,  # non-string key
                },
                "peer_reachability_ratio": {"ok": 0.5, "bad": "x"},
            }
        )
        client = make_app(edge=fake_edge, seeder=seeder, time_service=time_service)
        resp = client.get("/v1/federation/metrics")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["envelopes_sent_total"] == {"InlineText": 42}
        assert data["peer_reachability_ratio"] == {"ok": 0.5}
