"""The node key must be provisioned BEFORE edge init, or the edge refuses.

ciris-server 0.5.189 / CC 3.4.7.3 (CIRISAgent#1119). Until that cut one key
answered two questions: the embedded fold handed the substrate CIRISAgent's own
bootstrap key (``identity_type = agent``) and it served as the node identity too,
so the Reticulum transport identity named a key carrying AGENCY.

The ordering here is load-bearing, not incidental. Edge resolves the node key
with ``open_existing`` and REFUSES when it is absent — correct, because a key
edge minted itself would be registered by no directory and owner-bound by nobody
(the CIRISAgent#1009 shape). Edge also inits before CIRISServer's compose folds
on, so without provisioning a first boot has nothing to open.

These tests pin the call ORDER and the version-skew behaviour, not the substrate's
own guarantees — those are proved upstream in
``tests/node_key_is_not_the_actor_key.rs`` and ``consent_survives_the_key_split.rs``.
"""

import os
from pathlib import Path
from typing import Any, Dict, Iterator, List

import pytest


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Any]:
    """A real persist Engine wired as the process engine — edge init refuses
    without one. Mirrors test_edge_runtime_self_key_registration's fixture."""
    import ciris_engine.logic.persistence.models.graph as graph_mod
    from ciris_engine.logic.persistence._substrate import Engine, reset_engine  # type: ignore[import-untyped]
    from ciris_engine.logic.persistence.models.graph import set_persist_engine

    (tmp_path / "local_signing.seed").write_bytes(os.urandom(32))
    (tmp_path / "local_pqc_signing.seed").write_bytes(os.urandom(32))

    prior_engine, prior_dsn = graph_mod._engine, graph_mod._engine_dsn
    reset_engine()
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


class _FakeEdge:
    def signer_key_id(self) -> str:
        # The NODE key: this is what the real edge returns once
        # use_node_identity is on, which is precisely why authorship must not
        # be read from here.
        return "ciris-agent-bootstrap-node"

    def local_addr(self) -> str:
        return "0.0.0.0:4242"


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Dict[str, Any]:
    """Record the order of provision vs edge-init, and the kwargs each got."""
    import ciris_engine.logic.persistence._substrate as substrate
    from ciris_engine.logic.runtime import edge_runtime

    order: List[str] = []
    seen: Dict[str, Any] = {"order": order, "edge_kwargs": None, "provision_args": None}

    def _fake_init(*args: Any, **kwargs: Any) -> _FakeEdge:
        order.append("init_edge_runtime")
        seen["edge_kwargs"] = kwargs
        return _FakeEdge()

    monkeypatch.setattr(edge_runtime, "_edge_disabled", lambda: False)
    monkeypatch.setattr(edge_runtime, "_edge", None)
    monkeypatch.setattr(substrate, "init_edge_runtime", _fake_init)
    monkeypatch.setenv("CIRIS_FEDERATION_DELIVERY", "false")
    monkeypatch.setenv("CIRIS_HOME", str(tmp_path))
    return seen


def _install_fake_substrate(monkeypatch: pytest.MonkeyPatch, seen: Dict[str, Any], provision: Any) -> None:
    """Put a stand-in `ciris_server` in sys.modules with the given provisioner."""
    import sys
    import types

    mod = types.ModuleType("ciris_server")
    if provision is not None:

        def _provision(alias: str, identity_dir: str) -> str:
            seen["order"].append("provision_node_identity")
            seen["provision_args"] = (alias, identity_dir)
            return provision

        mod.provision_node_identity = _provision  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ciris_server", mod)


def test_provisioning_runs_before_edge_init(
    monkeypatch: pytest.MonkeyPatch, calls: Dict[str, Any], engine: Any, tmp_path: Path
) -> None:
    """The whole defect in one assertion: edge cannot open what was never minted."""
    from ciris_engine.logic.runtime.edge_runtime import initialize_edge_runtime

    _install_fake_substrate(monkeypatch, calls, "ciris-agent-bootstrap-node")
    initialize_edge_runtime(tmp_path / "identity")

    assert calls["order"] == ["provision_node_identity", "init_edge_runtime"], (
        "edge resolves the node key with open_existing and refuses when absent — "
        "provisioning must precede it"
    )


@pytest.mark.asyncio
async def test_edge_carries_the_node_identity(
    monkeypatch: pytest.MonkeyPatch, calls: Dict[str, Any], engine: Any, tmp_path: Path
) -> None:
    """The last open item of the split: the wire identity is the node's.

    Edge takes its Reticulum transport identity from the engine's signer capsule,
    and in the embedded fold the edge is already running when compose folds onto
    it — so this call is the only place it can be set. With it, the lightnet door
    (`is_bootstrap()` kinds, attributed via the link's transport identity) is
    walked by a key with no agency to exercise.
    """
    from ciris_engine.logic.runtime.edge_runtime import initialize_edge_runtime

    _install_fake_substrate(monkeypatch, calls, "ciris-agent-bootstrap-node")
    initialize_edge_runtime(tmp_path / "identity")

    assert calls["order"] == ["provision_node_identity", "init_edge_runtime"]
    assert calls["edge_kwargs"].get("use_node_identity") is True


@pytest.mark.asyncio
async def test_authorship_does_not_follow_the_transport(
    monkeypatch: pytest.MonkeyPatch, calls: Dict[str, Any], engine: Any, tmp_path: Path
) -> None:
    """The invariant that makes carrying the node key safe.

    Edge exposes ONE key accessor, `signer_key_id()`, returning whatever the
    transport carries. Everything asking "who authored this" — consent
    attestation, AccordMetrics' consent_attesting_key_id, the self-key
    registration, health, my_data — goes through `get_federation_address()`.

    If that still read the edge, enabling use_node_identity would register the
    NODE key as an `agent` and stamp actor-authored rows with the node identity:
    re-fusing the two roles CC 3.4.7.3 Clause A separates, while looking like
    adoption. Authorship therefore comes from the engine, whose derived key id
    the transport cannot move.
    """
    from ciris_engine.logic.runtime import edge_runtime
    from ciris_engine.logic.runtime.edge_runtime import (
        get_federation_address,
        get_node_key_id,
        initialize_edge_runtime,
    )

    _install_fake_substrate(monkeypatch, calls, "ciris-agent-bootstrap-node")
    initialize_edge_runtime(tmp_path / "identity")

    actor = get_federation_address()
    node = get_node_key_id()

    assert edge_runtime._edge is not None
    assert (
        edge_runtime._edge.signer_key_id() != actor
    ), "get_federation_address() must not return the transport identity"
    assert node == "ciris-agent-bootstrap-node"
    assert actor is not None and actor != node, "actor and node must be distinct ids"



def test_older_wheel_does_not_pass_unknown_kwargs(
    monkeypatch: pytest.MonkeyPatch, calls: Dict[str, Any], engine: Any, tmp_path: Path
) -> None:
    """<0.5.189 has no provisioner and no such kwargs — passing them TypeErrors
    the whole boot. Degrade to pre-split behaviour instead, loudly."""
    from ciris_engine.logic.runtime.edge_runtime import initialize_edge_runtime

    _install_fake_substrate(monkeypatch, calls, None)  # no provision_node_identity
    initialize_edge_runtime(tmp_path / "identity")

    assert calls["order"] == ["init_edge_runtime"]
    kwargs = calls["edge_kwargs"]
    assert "use_node_identity" not in kwargs
    assert "node_identity_dir" not in kwargs


def test_provisioning_failure_is_not_swallowed(
    monkeypatch: pytest.MonkeyPatch, calls: Dict[str, Any], engine: Any, tmp_path: Path
) -> None:
    """Fail-closed. CC 3.4.7.3 Clause D: `owner_of` unresolved is a refusal, never
    an unknown that reads as permission. Swallowing is precisely how the fused key
    survived — persist raised a Conflict and it was logged at debug as benign."""
    import sys
    import types

    from ciris_engine.logic.runtime.edge_runtime import initialize_edge_runtime

    mod = types.ModuleType("ciris_server")

    def _boom(alias: str, identity_dir: str) -> str:
        raise RuntimeError("actor key is not registered in federation_keys")

    mod.provision_node_identity = _boom  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ciris_server", mod)

    with pytest.raises(Exception, match="not registered in federation_keys"):
        initialize_edge_runtime(tmp_path / "identity")

    assert calls["order"] == [], "edge must not init when provisioning failed"


@pytest.mark.asyncio
async def test_reset_clears_the_cached_identities(
    monkeypatch: pytest.MonkeyPatch, calls: Dict[str, Any], engine: Any, tmp_path: Path
) -> None:
    """A reset runtime must not keep answering with the previous run's actor id.

    `get_federation_address()` returns `_actor_key_id` BEFORE it checks `_edge`,
    so clearing only `_edge` left a stale identity surviving the teardown meant
    to remove it — visible only as cross-test bleed, which is the kind of thing
    that gets blamed on the test that observes it rather than the reset that
    caused it.
    """
    from ciris_engine.logic.runtime.edge_runtime import (
        get_federation_address,
        get_node_key_id,
        initialize_edge_runtime,
        reset_edge_runtime,
    )

    _install_fake_substrate(monkeypatch, calls, "ciris-agent-bootstrap-node")
    initialize_edge_runtime(tmp_path / "identity")
    assert get_node_key_id() is not None

    reset_edge_runtime()

    assert get_federation_address() is None, "actor id survived the reset"
    assert get_node_key_id() is None, "node id survived the reset"
