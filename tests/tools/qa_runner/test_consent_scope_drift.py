"""The client's replication-consent prefixes must match the substrate's default.

WHY THIS TEST EXISTS
--------------------
`consent:replication:v1` declares which attestation families a node will
replicate. `promote_consented_backlog` only lifts a row from
(cohort_scope=self, tier=local) to federation when its dimension is covered by a
live grant's prefixes. A grant that omits `trace:` therefore strands every
sealed trace permanently — and does so SILENTLY: the node converges to its
consent peer, reports healthy, seals traces successfully, and never offers them.

That shipped. Four client call sites carried three different lists; one declared
`["capacity:"]`. A live run produced four `trace:complete:v1` rows at self/local,
"converged to 1 consent peers", no envelopes_sent_total, and a canonical with
zero trace_events.

The client cannot call the substrate symbol directly — it posts the list over
HTTP — so its constant is a necessary mirror. A mirror with no drift guard is
how this bug happened, so this is the guard.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

KOTLIN = (
    Path(__file__).resolve().parents[3]
    / "client/shared/src/commonMain/kotlin/ai/ciris/mobile/shared/models/federation/FederationConsentScopes.kt"
)


def _kotlin_list(name: str) -> list[str]:
    src = KOTLIN.read_text()
    m = re.search(rf"val {name}:\s*List<String>\s*=\s*listOf\(([^)]*)\)", src)
    assert m, f"could not parse {name} from {KOTLIN.name} — the shape changed and this guard is blind"
    return re.findall(r'"([^"]+)"', m.group(1))


def test_client_to_canonical_matches_substrate_default():
    """TO_CANONICAL must equal ciris_server.default_attestation_prefixes()."""
    try:
        import ciris_server
    except ImportError:  # pragma: no cover
        pytest.skip("ciris_server not installed")

    fn = getattr(ciris_server, "default_attestation_prefixes", None)
    if fn is None:
        pytest.skip("ciris-server predates default_attestation_prefixes() (<0.5.146)")

    substrate = set(fn())
    client = set(_kotlin_list("TO_CANONICAL"))

    assert client == substrate, (
        f"DRIFT: client sends {sorted(client)}, substrate default is {sorted(substrate)}.\n"
        f"A prefix present in one and not the other silently strands every attestation "
        f"of the missing family at (cohort_scope=self, tier=local) — the node stays "
        f"healthy and ships nothing."
    )


def test_trace_prefix_is_present():
    """The one that actually broke: `trace:` must be in the client's send list.

    Pinned separately from the equality check so that if the substrate default
    ever regresses, BOTH tests fail rather than the equality test quietly
    agreeing with a broken value — which is how the original bug survived: three
    separate test fixtures all asserted the capacity-only list and all passed.
    """
    assert "trace:" in _kotlin_list("TO_CANONICAL"), (
        "TO_CANONICAL omits 'trace:' — sealed traces will never replicate to the canonical"
    )


def test_reverse_channel_is_narrower():
    """FROM_PEER is a health channel, not a trace channel — keep it distinct."""
    assert "trace:" not in _kotlin_list("FROM_PEER")
