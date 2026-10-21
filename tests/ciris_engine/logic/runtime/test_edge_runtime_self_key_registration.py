"""Edge-init registers the agent's OWN signer in persist's federation directory.

The one call that makes the agent's signing identity resolvable by anything
that is not this process: lens `receive_and_persist` (a signer missing from
the directory rejects every trace with `verify_unknown_key`, #896) and the
#944 cross-occurrence WA-deferral verification (a sibling occurrence resolves
the signer via `lookup_public_key`, which fails CLOSED on an absent row — see
test_deferral_signing.TestCrossOccurrenceVerification for that half).

This exercises ``initialize_edge_runtime`` against a REAL persist Engine —
only the Edge transport itself is stubbed (its construction needs a live
Reticulum runtime; the registration under test is an ENGINE call, and that
engine is real). If a future change drops or silently breaks the registration
(the v10 regression was exactly that: a 2-arg call that no-op'd), the
directory row assertion here goes red.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterator, Optional

import pytest


class _FakeEdge:
    """Just enough Edge for the post-construction path: the signer key id."""

    def signer_key_id(self) -> str:
        return "test-key"


def _directory_row(engine: Any, key_id: str) -> Optional[dict]:
    """The federation-directory record for ``key_id``, or None when absent."""
    try:
        raw = engine.lookup_public_key(key_id)
    except Exception:
        return None
    if not raw:
        return None
    record = json.loads(raw)
    return record if isinstance(record, dict) else None


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Any]:
    """A real persist Engine with both signing seeds, wired as the process
    engine — WITHOUT the fixture-side self-registration `persist_engine` does,
    because the registration is exactly what this test must observe edge-init
    perform. Mirrors test_deferral_signing's fixture."""
    import ciris_engine.logic.persistence.models.graph as graph_mod
    from ciris_engine.logic.persistence._substrate import Engine, reset_engine  # type: ignore[import-untyped]
    from ciris_engine.logic.persistence.models.graph import set_persist_engine

    (tmp_path / "local_signing.seed").write_bytes(os.urandom(32))
    (tmp_path / "local_pqc_signing.seed").write_bytes(os.urandom(32))

    prior_engine, prior_dsn = graph_mod._engine, graph_mod._engine_dsn
    reset_engine()  # persist pins a process singleton; un-pin any prior fixture's
    dsn = f"sqlite:///{tmp_path}/t.db"
    real = Engine(
        dsn,
        "test-key",
        local_key_id="test-key",
        local_key_path=str(tmp_path / "local_signing.seed"),
        local_pqc_key_id="test-key",
        local_pqc_key_path=str(tmp_path / "local_pqc_signing.seed"),
    )
    set_persist_engine(real, dsn=dsn)
    try:
        yield real
    finally:
        graph_mod._engine, graph_mod._engine_dsn = prior_engine, prior_dsn


@pytest.fixture
def edge_init_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> _FakeEdge:
    """Drive initialize_edge_runtime for real, stubbing only the Edge transport.

    - `_edge_disabled` forced False (pytest normally short-circuits edge init);
    - `_substrate.init_edge_runtime` returns the fake edge (the runtime imports
      it at call time from that module);
    - delivery off (`start_federation_delivery` needs a real embedded edge, and
      the seam under test is the registration, not shipping);
    - CIRIS_HOME pinned to tmp so rust-tracing side effects land in the sandbox.
    """
    import ciris_engine.logic.persistence._substrate as substrate
    from ciris_engine.logic.runtime import edge_runtime

    fake = _FakeEdge()
    monkeypatch.setattr(edge_runtime, "_edge_disabled", lambda: False)
    monkeypatch.setattr(edge_runtime, "_edge", None)
    monkeypatch.setattr(substrate, "init_edge_runtime", lambda *args, **kwargs: fake)
    monkeypatch.setenv("CIRIS_FEDERATION_DELIVERY", "false")
    monkeypatch.setenv("CIRIS_HOME", str(tmp_path))
    return fake


def test_edge_init_registers_the_self_federation_key(engine: Any, edge_init_env: _FakeEdge, tmp_path: Path) -> None:
    """Boot edge-init: the engine's own signer must land in federation_keys.

    Before: no directory row for the derived key id (fail-closed world).
    After: the row exists and carries the engine's own Ed25519 pubkey —
    the same row `_signing_pubkeys` / lens admission resolve against.
    """
    from ciris_engine.logic.runtime.edge_runtime import get_edge, initialize_edge_runtime

    derived = engine.local_derived_key_id()
    assert _directory_row(engine, derived) is None, "self key registered before edge-init ran — test premise broken"

    initialize_edge_runtime(tmp_path / "identity")

    assert get_edge() is edge_init_env  # the runtime actually initialized
    row = _directory_row(engine, derived)
    assert row is not None, (
        "edge-init did not register the self federation key — cross-occurrence "
        "WA-deferral verification and lens trace admission fail closed (#944/#896)"
    )
    assert row.get("pubkey_ed25519_base64") == engine.local_public_key_b64()


def test_edge_init_registration_is_idempotent_across_reinit(
    engine: Any, edge_init_env: _FakeEdge, tmp_path: Path
) -> None:
    """A second boot against an already-registered key must not fail boot:
    re-registration raises federation_conflict, which edge-init treats as
    benign (the except-branch posture the call site documents)."""
    from ciris_engine.logic.runtime import edge_runtime
    from ciris_engine.logic.runtime.edge_runtime import initialize_edge_runtime

    initialize_edge_runtime(tmp_path / "identity")
    edge_runtime._edge = None  # simulate a fresh boot in the same process
    initialize_edge_runtime(tmp_path / "identity")  # must not raise

    assert _directory_row(engine, engine.local_derived_key_id()) is not None
