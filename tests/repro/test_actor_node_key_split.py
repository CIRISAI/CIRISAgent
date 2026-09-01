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


@pytest.mark.xfail(
    strict=True,
    reason="node_fold._resolve_key_id() returns the AGENT alias; CC 3.4.7.3 requires a node key",
)
def test_node_fold_does_not_boot_the_node_on_the_agent_key(monkeypatch) -> None:
    """The alias handed to the node must not be the one the engine signs as.

    This is the whole defect in one assertion. `serve_with_python_adapter(key_id=...)`
    receives this value; when it is the agent's alias the substrate mints a
    separate node key behind our back, the owner-binding cannot follow it, and
    consent re-authoring is unsatisfiable from that boot onward.
    """
    from ciris_engine.logic.runtime import node_fold
    from ciris_engine.logic.utils.path_resolution import get_federation_alias

    monkeypatch.setenv("CIRIS_AGENT_ID", "ciris-agent-bootstrap")
    node_alias = node_fold._resolve_key_id()

    assert node_alias is not None
    assert node_alias != get_federation_alias(), (
        "the node is being booted on the agent's federation alias — this is the "
        "state the substrate reports as 'the configured key is an ACTOR' and then "
        "works around by minting a node key whose owner-binding cannot follow"
    )


@pytest.mark.xfail(
    strict=True,
    reason="no node-role alias is exposed to node_fold; only the agent's federation alias is",
)
def test_a_node_alias_is_actually_available_to_node_fold() -> None:
    """Fixing the above requires something to fix it WITH.

    `provision_node_identity()` already mints and returns a node key id for edge
    (CIRISAgent#1119). If node_fold cannot reach that value, the fix is not a
    one-line swap and the design gap is the finding.
    """
    from ciris_engine.logic.runtime import node_fold

    assert hasattr(node_fold, "_resolve_node_key_id") or hasattr(node_fold, "get_node_alias"), (
        "node_fold has no way to ask for the NODE's alias — it can only ask for "
        "the federation (agent) one, so the two call sites cannot agree"
    )
