"""Under the mock LLM no ship grant is ever authored (CIRISAgent#1244).

The ship grant (``consent:replication:v1`` naming a canonical peer) is what
lets sealed traces leave the node. Every opt-in path funnels into
``trace_sharing._author_ship_grant``: the wizard, the data card, the node
fold, the delivery probe and the legacy migration. A mock-LLM run with consent
on, which is exactly what the QA runner sets, must author nothing.
"""

import logging
import sys
import types
from typing import List, Optional, Tuple

import pytest

from ciris_engine.logic.services.governance.consent import trace_sharing
from ciris_engine.schemas.consent.trace_sharing import TraceConsentSource, TraceSharingGrantResult

CANONICAL = "ciris-canonical-1"


@pytest.fixture
def fake_server(monkeypatch: pytest.MonkeyPatch) -> List[Tuple[str, Optional[list], bool]]:
    """A ciris_server stand-in with one canonical target that records ship grants."""
    calls: List[Tuple[str, Optional[list], bool]] = []
    fake = types.ModuleType("ciris_server")
    fake.author_federation_consent = lambda peer, prefixes, analyze: calls.append((peer, prefixes, analyze))  # type: ignore[attr-defined]
    fake.delivery_status = lambda: {"canonical_targets": [CANONICAL]}  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ciris_server", fake)
    return calls


def test_mock_llm_with_consent_authors_no_ship_grant(
    mock_llm_mode: None,
    fake_server: List[Tuple[str, Optional[list], bool]],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("CIRIS_ACCORD_METRICS_CONSENT", "true")
    result = TraceSharingGrantResult(source=TraceConsentSource.DELIVERY_PROBE, opted_in=True)
    with caplog.at_level(logging.INFO):
        trace_sharing._author_ship_grant(result, analyze=True)

    assert fake_server == [], "a ship grant was authored under the mock LLM"
    assert result.peers_authored == []
    assert any("mock LLM active" in e for e in result.errors)
    assert any("REFUSED remote trace export" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize(
    "source",
    [
        TraceConsentSource.NODE_FOLD,
        TraceConsentSource.DELIVERY_PROBE,
        TraceConsentSource.LEGACY_MIGRATION,
        TraceConsentSource.DATA_CARD,
        TraceConsentSource.SETUP_WIZARD,
    ],
)
def test_every_opt_in_path_is_refused(
    mock_llm_mode: None,
    fake_server: List[Tuple[str, Optional[list], bool]],
    monkeypatch: pytest.MonkeyPatch,
    source: TraceConsentSource,
) -> None:
    monkeypatch.setenv("CIRIS_ACCORD_METRICS_CONSENT", "true")
    # The capture grant is local (seals into this node's persist); stub it.
    from ciris_engine.logic.services.governance.consent import attestation

    monkeypatch.setattr(attestation, "emit_community_consent_grant", lambda granted_at=None: "grant-1")
    result = trace_sharing.grant_trace_sharing(source, require_opt_in=False, analyze=True)
    assert fake_server == []
    assert result.peers_authored == []


def test_real_llm_still_authors_the_ship_grant(
    real_llm_mode: None, fake_server: List[Tuple[str, Optional[list], bool]]
) -> None:
    result = TraceSharingGrantResult(source=TraceConsentSource.DELIVERY_PROBE, opted_in=True)
    trace_sharing._author_ship_grant(result, analyze=True)
    assert fake_server == [(CANONICAL, None, True)]
    assert result.peers_authored == [CANONICAL]
