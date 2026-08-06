"""#1009 — the agent must present the FEDERATION key id, not the credits one.

For 71 hours canonical-server-1 answered every accord event with
``401 verify_unknown_key`` — 8,631 rejections a day from two agents, and trace
arrivals stopped entirely. The server was refusing correctly: the id being
presented had never been registered on the federation plane.

One Ed25519 key, two names for it:

    engine.local_derived_key_id()      ciris-agent-bootstrap-4zvq6c2q4t
    f"agent-{sha256(pubkey)[:12]}"     agent-e66b0f0b50e4

Only the first appears in ``federation_keys`` / ``accord_public_keys``. The
second is the CIRISVerify-managed second-signer id that
``ciris_engine/logic/audit/__init__.py`` records as REMOVED in 2.9.7, for
exactly this reason — "its keys were never federation-registered, so peer nodes
rejected them with verify_unknown_key". The removal missed
``AuthenticationService._register_agent_pubkey_with_persist``.

Why this is a unit test and not a rung on the mesh ladder: CIRISServer's
``harness/mesh-repro`` proves the full genesis-to-score chain, but its agent
role is ``agent_boot.py``, which *reproduces* the federation boot by calling
``Engine`` / ``init_edge_runtime`` / ``start_federation_delivery`` directly. It
contains no reference to ``AuthenticationService``. So the ladder can be green
end to end while this defect is live in production — which is precisely what
happened. The substrate signed correctly; the agent stamped the wrong name on
it.

The gate is therefore on the NAMESPACE, at the agent tier, offline: no docker,
no canonical node, no network. It reproduces in milliseconds what took a
71-hour soak to notice.
"""

from __future__ import annotations

import ast
import base64
import hashlib
import os
import pathlib
import tempfile

import pytest

SERVICE = pathlib.Path("ciris_engine/logic/services/infrastructure/authentication/service.py")

#: The federation ids the substrate actually verifies against are `derive_key_id`
#: output: the engine's configured alias plus a derived suffix. The credits ids
#: are `agent-` + 12 hex. The two are trivially distinguishable, which is the
#: whole point — nothing in either type system distinguished them, so the
#: substitution was invisible at every layer until a peer refused it.
CREDITS_SHAPE = "agent-"


def _engine_with_local_key(tmp: pathlib.Path):
    """A persist Engine carrying a real Ed25519 federation identity."""
    ciris_server = pytest.importorskip("ciris_server")
    seed_path = tmp / "local.key"
    seed_path.write_bytes(os.urandom(32))  # raw 32-byte Ed25519 seed
    return ciris_server.Engine(
        f"sqlite:///{tmp}/t.db",
        "ciris-agent-bootstrap",
        local_key_id="ciris-agent-bootstrap",
        local_key_path=str(seed_path),
    )


def test_the_two_namespaces_are_distinct_for_one_key() -> None:
    """The premise, proven rather than asserted.

    If these ever coincided the bug would be harmless and this file could go.
    They do not: same key material, two unrelated names.
    """
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        engine = _engine_with_local_key(tmp)

        federation_id = engine.local_derived_key_id()
        pubkey = base64.b64decode(engine.local_public_key_b64())
        credits_id = f"agent-{hashlib.sha256(pubkey).hexdigest()[:12]}"

        assert federation_id != credits_id
        assert not federation_id.startswith(CREDITS_SHAPE), (
            f"the federation id {federation_id!r} now has the credits shape; "
            f"if the substrate changed its derivation this whole gate needs rereading"
        )
        assert federation_id.startswith("ciris-agent-bootstrap"), (
            f"federation ids are derive_key_id output over the engine alias; got {federation_id!r}"
        )


def test_registration_uses_the_federation_key_id() -> None:
    """The regression guard.

    Asserted on the AST of the registering function rather than by running it,
    because reaching it needs a live CIRISVerify singleton and a wired persist
    engine — conditions under which the original defect silently `return`ed
    early and logged at debug. A test that needed all that to line up would have
    passed on a no-op, which is the failure mode this repo keeps finding.
    """
    tree = ast.parse(SERVICE.read_text(encoding="utf-8"), filename=str(SERVICE))
    fn = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == "_register_agent_pubkey_with_persist"
        ),
        None,
    )
    assert fn is not None, "_register_agent_pubkey_with_persist is gone — check this gate still tracks the code"

    # Any f-string building "agent-{...}" inside this function is the defect.
    minted = []
    for node in ast.walk(fn):
        if isinstance(node, ast.JoinedStr):
            head = node.values[0] if node.values else None
            if isinstance(head, ast.Constant) and isinstance(head.value, str):
                if head.value.startswith(CREDITS_SHAPE):
                    minted.append(ast.unparse(node))

    assert not minted, (
        f"_register_agent_pubkey_with_persist is minting credits-namespace ids {minted}. "
        f"The federation plane has never heard of them — peers answer 401 verify_unknown_key "
        f"and trace delivery stops silently. Register under engine.local_derived_key_id()."
    )

    src = ast.unparse(fn)
    assert "local_derived_key_id" in src, (
        "the registration no longer resolves the federation-derived key id. That id is the "
        "only one the substrate verifies against (see ciris_engine/logic/audit/__init__.py)."
    )


def test_the_removed_second_signer_stays_removed() -> None:
    """2.9.7 deleted the CIRISVerify second-signer identity. This asserts no new
    site reintroduces an `agent-{sha12}` signing id anywhere in the audit or
    federation paths.

    Scoped to id MINTING (an f-string whose literal head is `agent-`), so
    tenant partitioning — which legitimately uses `agent-default` and
    CIRIS_AGENT_ID — is not swept in.
    """
    roots = [
        pathlib.Path("ciris_engine/logic/audit"),
        pathlib.Path("ciris_engine/logic/services/infrastructure/authentication"),
        pathlib.Path("ciris_adapters/ciris_accord_metrics"),
    ]
    offenders: list[str] = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.JoinedStr) or not node.values:
                    continue
                head = node.values[0]
                if isinstance(head, ast.Constant) and isinstance(head.value, str):
                    if head.value.startswith(CREDITS_SHAPE) and "default" not in head.value:
                        offenders.append(f"{path}:{node.lineno} {ast.unparse(node)}")

    assert not offenders, (
        f"credits-namespace signing ids are back: {offenders}. 2.9.7 removed this identity "
        f"because peer nodes reject it; #1009 is what its survival cost."
    )
