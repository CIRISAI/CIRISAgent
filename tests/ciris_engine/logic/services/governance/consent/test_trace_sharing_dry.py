"""Every trace-sharing opt-in path goes through ONE handle.

The bug this locks down: session-ful paths (wizard, data card) authored only the
CAPTURE grant while session-less paths (node fold, delivery probe) authored only
the SHIP grant. Neither granted both, so nodes sat at
``capture=True, replication=False`` — sealing traces perfectly, reporting healthy,
and never shipping anything. The drift DETECTOR existed the whole time; the
writers were what had drifted.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from ciris_engine.logic.services.governance.consent import trace_sharing
from ciris_engine.schemas.consent.trace_sharing import (
    TraceConsentSource,
    TraceSharingConsent,
    TraceSharingGrantResult,
)

REPO = pathlib.Path(__file__).resolve().parents[6]

#: Paths that opt in to trace sharing. Each must route through the DRY handle
#: rather than calling a single-artifact emitter directly.
OPT_IN_SITES = [
    "ciris_engine/logic/adapters/api/routes/setup/complete.py",
    "ciris_engine/logic/adapters/api/routes/my_data.py",
    "ciris_engine/logic/runtime/node_fold.py",
    "ciris_engine/logic/runtime/edge_runtime.py",
    "ciris_adapters/ciris_accord_metrics/adapter.py",
]


def test_capture_only_never_counts_as_sharing() -> None:
    """The exact silent-failure state must not read as 'sharing works'."""
    assert TraceSharingConsent(capture=True, replication=False).ships is False
    assert TraceSharingConsent(capture=True, replication=None).ships is False
    assert TraceSharingConsent(capture=True, replication=True).ships is True


def test_unknown_gate_is_not_a_grant() -> None:
    """None means 'resolver unavailable' and must never collapse to granted."""
    st = TraceSharingConsent()
    assert st.capture is None and st.ships is False and st.aligned is False


def test_grant_result_incomplete_without_ship() -> None:
    r = TraceSharingGrantResult(
        source=TraceConsentSource.SETUP_WIZARD, opted_in=True, capture_grant_id="att-1"
    )
    assert r.complete is False, "capture alone is the bug, not a complete grant"
    r.peers_authored = ["canonical-1"]
    assert r.complete is True


def test_no_opt_in_authors_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fails CLOSED: session-less paths must never consent on the owner's behalf."""
    monkeypatch.delenv(trace_sharing.OPT_IN_ENV_VAR, raising=False)
    called: list[str] = []
    monkeypatch.setattr(
        trace_sharing, "_author_ship_grant", lambda r: called.append("ship")
    )
    result = trace_sharing.grant_trace_sharing(TraceConsentSource.NODE_FOLD)
    assert result.opted_in is False
    assert result.capture_grant_id is None
    assert called == [], "nothing may be authored without the owner's opt-in"


#: Session-less authors. These previously each carried their OWN read of the
#: opt-in signal, which is how one could fail-closed while another fails-open.
#: They must now gate purely through the handle.
#:
#: Deliberately excluded, with reasons:
#:   - my_data.py            WRITES the env var (_update_env_consent) — it is the
#:                           persistence of the owner's choice, not a gate on it.
#:   - setup/complete.py     mentions it in a docstring only.
#:   - accord_metrics/*      derives `_consent_given` from a BROADER set (env OR
#:                           adapter config graph OR a standing CEG grant, incl.
#:                           legacy COVENANT aliases) and then hands that
#:                           resolved answer to the handle via require_opt_in=
#:                           False. Collapsing it into this reader would LOSE the
#:                           config-graph and post-purge cases. Its three
#:                           `_get_metrics_env("CONSENT")` parses are a separate,
#:                           smaller DRY opportunity inside that adapter.
GATING_READ_SITES = [
    "ciris_engine/logic/runtime/node_fold.py",
    "ciris_engine/logic/runtime/edge_runtime.py",
]


@pytest.mark.parametrize("rel", GATING_READ_SITES)
def test_session_less_paths_gate_only_through_the_handle(rel: str) -> None:
    """A second interpretation of the signal is a second policy waiting to drift.

    Fails-open vs fails-closed, ``.lower()`` or not, ``get_env_var`` vs
    ``os.environ`` — each copy is a chance to disagree about whether the owner
    consented.
    """
    src = (REPO / rel).read_text(encoding="utf-8")
    assert trace_sharing.OPT_IN_ENV_VAR not in src, (
        f"{rel} reads {trace_sharing.OPT_IN_ENV_VAR} directly; call "
        "owner_opted_into_trace_sharing() instead"
    )


@pytest.mark.parametrize("rel", OPT_IN_SITES)
def test_opt_in_paths_do_not_call_single_artifact_emitters(rel: str) -> None:
    """No opt-in path may author one gate on its own.

    ``emit_community_consent_grant`` / ``author_federation_consent`` are the
    half-grants. Only the DRY handle may call them, so a future path cannot
    reintroduce the split by copying whichever neighbour it happened to read.
    """
    tree = ast.parse((REPO / rel).read_text(encoding="utf-8"))
    banned = {"emit_community_consent_grant", "author_federation_consent"}
    found = {
        n.func.id
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in banned
    }
    assert not found, f"{rel} calls {found} directly — route it through grant_trace_sharing()"
