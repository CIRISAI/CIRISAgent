"""GET /v1/system/runtime/delivery-receipt — the receiver's answer, tri-state.

`delivery_status()` carries the producer's preconditions: rooted, KEX present,
envelopes sent. All three can be green while nothing was stored at the far end.
The receipt is the other side's signed assertion, and the one rule that must
never bend is that `None` means UNKNOWN, not zero and not failure
(CIRISServer#487 / #592).
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.dependencies.auth import require_admin
from ciris_engine.logic.adapters.api.routes.system import runtime as runtime_routes


@pytest.fixture
def app(monkeypatch) -> FastAPI:
    app = FastAPI()
    app.include_router(runtime_routes.router, prefix="/system")
    app.dependency_overrides[require_admin] = lambda: MagicMock()
    monkeypatch.setattr(
        "ciris_engine.logic.adapters.api.routes.my_data._compute_agent_id_hash_from_signer",
        lambda: "abc123def4567890",
    )
    return app


def _serve(monkeypatch, payload) -> None:
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    monkeypatch.setattr(
        "ciris_engine.logic.runtime.edge_runtime.read_delivery_receipt",
        lambda agent_id_hash=None: raw,
    )


def test_delivered_reads_true(app, monkeypatch):
    _serve(
        monkeypatch,
        {
            "verdict": {"newest_authored_held_by_every_answering_canonical": True},
            "canonicals": [
                {"key_id": "canonical-1", "holds_newest": True, "url": "http://h:4243", "url_source": "ip_hint",
                 "agents": [{"agent_id_hash": "abc123def4567890", "shipped_any": True}]}
            ],
        },
    )
    d = TestClient(app).get("/system/runtime/delivery-receipt").json()["data"]
    assert d["held_by_every_answering_canonical"] is True
    assert d["agent_id_hash"] == "abc123def4567890", "the hash must be named, not discovered"
    assert d["canonicals"][0]["holds_newest"] is True
    assert d["canonicals"][0]["shipped_any"] is True


def test_behind_is_distinguished_from_never_landed(app, monkeypatch):
    """False + shipped_any True means the plane works and is behind. That is a
    different fault from nothing ever landing, and the gate must be able to say
    which without reading the raw payload."""
    _serve(
        monkeypatch,
        {
            "verdict": {"newest_authored_held_by_every_answering_canonical": False},
            "canonicals": [
                {"key_id": "c1", "holds_newest": False,
                 "agents": [{"agent_id_hash": "abc123def4567890", "shipped_any": True}]},
                {"key_id": "c2", "holds_newest": False,
                 "agents": [{"agent_id_hash": "abc123def4567890", "shipped_any": False}]},
            ],
        },
    )
    d = TestClient(app).get("/system/runtime/delivery-receipt").json()["data"]
    assert d["held_by_every_answering_canonical"] is False
    by_key = {c["key_id"]: c for c in d["canonicals"]}
    assert by_key["c1"]["shipped_any"] is True, "behind"
    assert by_key["c2"]["shipped_any"] is False, "never landed"


def test_unknown_is_none_and_never_false(app, monkeypatch):
    """THE RULE. An unreachable canonical is not a delivery failure."""
    _serve(
        monkeypatch,
        {
            "verdict": {
                "newest_authored_held_by_every_answering_canonical": None,
                "canonicals_unreachable": 1,
                "canonicals_unverified": 0,
                "canonicals_partial": 0,
                "discovery_incomplete": False,
                "identity_unavailable": False,
            },
            "canonicals": [{"key_id": "c1", "error": "connect timeout", "url": "http://h:4243"}],
        },
    )
    d = TestClient(app).get("/system/runtime/delivery-receipt").json()["data"]
    assert d["held_by_every_answering_canonical"] is None
    assert d["held_by_every_answering_canonical"] is not False
    assert d["canonicals_unreachable"] == 1
    assert d["canonicals"][0]["error"] == "connect timeout"


def test_accessor_refusal_surfaces_rather_than_reading_as_a_verdict(app, monkeypatch):
    """`{"error": ...}` is what the accessor returns off-node. It must not be
    mistaken for "not delivered"."""
    _serve(monkeypatch, {"error": "no engine handle — this node's own trace store is not readable here"})
    d = TestClient(app).get("/system/runtime/delivery-receipt").json()["data"]
    assert d["held_by_every_answering_canonical"] is None
    assert "no engine handle" in d["error"]


def test_an_older_wheel_is_503_not_a_failed_verdict(app, monkeypatch):
    monkeypatch.setattr(
        "ciris_engine.logic.runtime.edge_runtime.read_delivery_receipt",
        lambda agent_id_hash=None: None,
    )
    r = TestClient(app).get("/system/runtime/delivery-receipt")
    assert r.status_code == 503
    assert "0.5.208" in r.json()["detail"]


def test_the_raw_payload_is_preserved_verbatim(app, monkeypatch):
    payload = {"verdict": {"newest_authored_held_by_every_answering_canonical": True}, "extra_upstream_field": 7}
    _serve(monkeypatch, payload)
    d = TestClient(app).get("/system/runtime/delivery-receipt").json()["data"]
    assert json.loads(d["raw_json"])["extra_upstream_field"] == 7, "diagnosis wants what it said, not our projection"


def test_unknown_hash_falls_back_to_discovery(app, monkeypatch):
    """The helper answers 'unknown' when the engine is not wired. Passing that
    through would ask about an agent that does not exist."""
    monkeypatch.setattr(
        "ciris_engine.logic.adapters.api.routes.my_data._compute_agent_id_hash_from_signer",
        lambda: "unknown",
    )
    seen = {}

    def capture(agent_id_hash=None):
        seen["hash"] = agent_id_hash
        return json.dumps({"verdict": {"newest_authored_held_by_every_answering_canonical": None}})

    monkeypatch.setattr("ciris_engine.logic.runtime.edge_runtime.read_delivery_receipt", capture)
    TestClient(app).get("/system/runtime/delivery-receipt")
    assert seen["hash"] is None


def test_requires_admin():
    app = FastAPI()
    app.include_router(runtime_routes.router, prefix="/system")
    assert TestClient(app).get("/system/runtime/delivery-receipt").status_code != 200
