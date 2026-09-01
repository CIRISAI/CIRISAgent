"""The node is booted on the AGENT's key, and the substrate refuses it.

FIELD FAILURE (2026-09-01, ciris-agent 2.9.44 / ciris-server 0.5.196, Windows).
A user completed setup successfully, then could never start the app again. Every
subsequent boot died in ~9s:

    Node fold: serve_with_python_adapter exited/failed: RuntimeError:
      re-author consent ciris-node-bootstrap-3nclwiulun -> ciris-canonical-1-d7bdeu223k:
      refusing to emit a consent grant naming "ciris-node-bootstrap-3nclwiulun":
      this engine signs as "ciris-agent-bootstrap-jbdibklyfz", and a consent
      grant is self-attested (CEG 1.0-RC29 §5.6.8.15)
    [FAIL] Start Adapters failed: node fold failed to start (node-fails ⇒ agent-fails)
    [FAIL] CIRIS Agent Initialization Failed (8.5s)

THE CAUSE IS ONE ALIAS, PASSED IN TWO PLACES, DISAGREEING.

    17:09:45  [NODE-KEY] passing node_keystore_alias='ciris-node-bootstrap'  ← edge
    17:09:49  Node fold: identity resolution — alias=ciris-agent-bootstrap    ← node

CIRISAgent#1119 adopted `provision_node_identity()` so EDGE carries a real node
key. `node_fold._resolve_key_id()` was not updated and still returns
`get_federation_alias()` — the AGENT alias. The substrate sees an actor key
offered as the node identity and says so on every boot:

    WARN ciris_server::node_key: the configured key is an ACTOR, so it is not
      this node's identity. Minted and registered a separate node key
      (CC 3.4.7.3 Clause A: `node` is non-cohabitable with `agent`/`user`).
      The node's owner-binding must be re-issued onto the node key
      — see `plan_owner_binding_move`.
      configured_key_id=ciris-agent-bootstrap-jbdibklyfz configured_roles=["agent"]
      node_key_id=ciris-node-bootstrap-3nclwiulun

    WARN ciris_server::compose: the node key was minted but no owner signer is on
      disk, so its owner-binding could not follow. `owner_of(node)` does not resolve

First boot survives because no consent row names the node yet. Setup writes one.
Every boot after that must re-author it, and cannot: the row names the node key,
the engine can only sign as the actor key, and a consent grant is self-attested.
"""

from __future__ import annotations

import pytest

from ciris_engine.logic.runtime import node_fold
from ciris_engine.logic.utils.path_resolution import (
    get_federation_alias,
    get_node_alias,
    set_node_alias,
)


@pytest.fixture(autouse=True)
def _clean_alias():
    """Module state — restore it, or one test decides the next one's answer."""
    before = get_node_alias()
    yield
    set_node_alias(before)


def test_the_node_boots_on_the_node_key_not_the_agent_key(monkeypatch) -> None:
    """THE FIX. Once provisioning publishes a node alias, node_fold uses THAT.

    `serve_with_python_adapter(key_id=...)` receives this value. When it was the
    agent's alias the substrate minted a node key behind our back, the
    owner-binding could not follow it, and consent re-authoring became
    unsatisfiable from the second boot onward.
    """
    monkeypatch.setenv("CIRIS_AGENT_ID", "ciris-agent-bootstrap")
    set_node_alias("ciris-node-bootstrap")

    resolved = node_fold._resolve_key_id()

    assert resolved == "ciris-node-bootstrap"
    assert resolved != get_federation_alias(), "the node must not be booted on the actor key"


def test_both_call_sites_settle_on_one_value(monkeypatch) -> None:
    """Edge and node fold must not derive the name independently.

    They did, and disagreed — 'ciris-node-bootstrap' on one side,
    'ciris-agent-bootstrap' on the other, four seconds apart in the same boot.
    provision_node_identity owns the name; a second derivation is a second
    source of truth, which is the bug.
    """
    monkeypatch.setenv("CIRIS_AGENT_ID", "ciris-agent-bootstrap")
    # What edge_runtime does with the id provisioning returned.
    provisioned_key_id = "ciris-node-bootstrap-3nclwiulun"
    set_node_alias(provisioned_key_id.rsplit("-", 1)[0])

    assert node_fold._resolve_key_id() == get_node_alias() == "ciris-node-bootstrap"


def test_an_unprovisioned_node_says_so_loudly(monkeypatch, caplog) -> None:
    """The dangerous state must not be silent.

    Falling back to the actor key is exactly what bricks the install on its
    SECOND boot, and it produced no agent-side signal at all — only a substrate
    warning nobody correlated. If we must fall back, the log has to name the
    consequence while the boot that causes it is still running.
    """
    import logging

    monkeypatch.setenv("CIRIS_AGENT_ID", "ciris-agent-bootstrap")
    set_node_alias(None)

    with caplog.at_level(logging.WARNING):
        resolved = node_fold._resolve_key_id()

    assert resolved == get_federation_alias()
    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "ACTOR" in joined and "owner-binding" in joined, (
        "the fallback must state what it will cost, not just that it happened"
    )
