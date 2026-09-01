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

import logging

import pytest

from ciris_engine.logic.runtime import node_fold
from ciris_engine.logic.utils.path_resolution import (
    get_federation_alias,
    get_node_alias,
    set_node_alias,
)


@pytest.fixture(autouse=True)
def _clean_alias():
    before = get_node_alias()
    yield
    set_node_alias(before)


def test_the_node_fold_uses_the_engine_alias(monkeypatch) -> None:
    """THE CONSTRAINT I BROKE AND RESTORED.

    The sealed keystore keys off (identity_dir, alias), so two spellings are two
    keys and CIRISServer#380 refuses to boot on a mismatch. Returning the
    provisioned NODE alias here — while the Engine still opened the federation
    one — turned a working first boot into

        RuntimeError: TWO FEDERATION IDENTITIES IN ONE NODE — refusing to start

    strictly worse than the bug it was meant to cure. This pins it shut.
    """
    monkeypatch.setenv("CIRIS_AGENT_ID", "ciris-agent-bootstrap")
    set_node_alias("ciris-node-bootstrap")

    assert node_fold._resolve_key_id() == get_federation_alias() == "ciris-agent-bootstrap"


def test_the_split_is_recorded_when_it_exists(monkeypatch, caplog) -> None:
    """Passing the engine alias is correct; being silent about the split is not.

    The substrate mints its own node key and the owner-binding then has to follow
    onto it. When that does not happen the install bricks on its SECOND boot, so
    the boot that creates the condition should say the two names differ.
    """
    monkeypatch.setenv("CIRIS_AGENT_ID", "ciris-agent-bootstrap")
    set_node_alias("ciris-node-bootstrap")

    with caplog.at_level(logging.INFO):
        node_fold._resolve_key_id()

    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "ciris-node-bootstrap" in joined and "CIRISServer#380" in joined


def test_no_split_no_noise(monkeypatch, caplog) -> None:
    """Nothing to report when the substrate has not minted a separate key."""
    monkeypatch.setenv("CIRIS_AGENT_ID", "ciris-agent-bootstrap")
    set_node_alias(None)

    with caplog.at_level(logging.INFO):
        assert node_fold._resolve_key_id() == "ciris-agent-bootstrap"

    assert not [r for r in caplog.records if "NODE-KEY" in r.getMessage()]
