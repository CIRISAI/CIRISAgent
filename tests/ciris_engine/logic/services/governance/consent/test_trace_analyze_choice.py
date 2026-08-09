"""``analyze`` is the owner's answer, not a constant.

CC#46's be-scored dimension shipped hardcoded ``True`` — ``author(peer, None, True)``
with no UI anywhere. The substrate marks it ``required: false`` with two named
costs and ``fold_consent_surface.rs`` is explicit that "marking it required
misrepresents a legitimate choice as a misconfiguration". So the wizard collects
it and it must arrive, unchanged, at ``author_federation_consent`` — in BOTH
directions, which is the half that a default-True implementation gets wrong
silently.
"""

from __future__ import annotations

import sys
import types
from typing import List, Optional, Tuple

import pytest

from ciris_engine.logic.services.governance.consent import trace_sharing
from ciris_engine.schemas.consent.trace_sharing import (
    TraceConsentSource,
    TraceSharingConsent,
    TraceSharingGrantResult,
)


@pytest.fixture
def authored(monkeypatch: pytest.MonkeyPatch) -> List[Tuple[str, Optional[list], bool]]:
    """Capture every ``author_federation_consent(peer, prefixes, analyze)`` call."""
    calls: List[Tuple[str, Optional[list], bool]] = []

    fake = types.ModuleType("ciris_server")
    fake.author_federation_consent = lambda peer, prefixes, analyze: calls.append(  # type: ignore[attr-defined]
        (peer, prefixes, analyze)
    )
    fake.delivery_status = lambda: {"canonical_targets": ["canonical-1"]}  # type: ignore[attr-defined]
    fake.analyze_consent_stance = lambda peer: "granted"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ciris_server", fake)

    # Keep the capture half and the status resolver out of the way — this module
    # is about the ship grant's third argument.
    monkeypatch.setattr(
        "ciris_engine.logic.services.governance.consent.attestation.emit_community_consent_grant",
        lambda granted_at=None: "att-capture-1",
    )
    monkeypatch.setattr(trace_sharing, "trace_sharing_status", lambda: TraceSharingConsent())
    return calls


class TestAnalyzeReachesTheSubstrate:
    @pytest.mark.parametrize("analyze", [True, False])
    def test_the_toggle_value_is_what_is_authored(
        self, authored: List[Tuple[str, Optional[list], bool]], analyze: bool
    ) -> None:
        result = trace_sharing.grant_trace_sharing(
            TraceConsentSource.SETUP_WIZARD, require_opt_in=False, analyze=analyze
        )
        assert authored == [("canonical-1", None, analyze)]
        assert result.peers_authored == ["canonical-1"]

    def test_declining_analyze_still_ships(
        self, authored: List[Tuple[str, Optional[list], bool]]
    ) -> None:
        """Declining to be scored is not declining to share — the grant still lands."""
        result = trace_sharing.grant_trace_sharing(
            TraceConsentSource.SETUP_WIZARD, require_opt_in=False, analyze=False
        )
        assert result.capture_grant_id == "att-capture-1"
        assert result.complete is True

    def test_prefixes_are_still_never_restated(
        self, authored: List[Tuple[str, Optional[list], bool]]
    ) -> None:
        """Guard the neighbouring invariant: prefixes stay None (the build's default)."""
        trace_sharing.grant_trace_sharing(
            TraceConsentSource.SETUP_WIZARD, require_opt_in=False, analyze=True
        )
        assert authored[0][1] is None


class TestReplayHonoursTheRecordedChoice:
    """Session-less paths REPLAY a decision; they must not re-grant a declined one."""

    def test_replay_reuses_a_recorded_decline(
        self, authored: List[Tuple[str, Optional[list], bool]], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            trace_sharing, "trace_sharing_status", lambda: TraceSharingConsent(analyze=False)
        )
        trace_sharing.grant_trace_sharing(TraceConsentSource.NODE_FOLD, require_opt_in=False)
        assert authored == [("canonical-1", None, False)]

    def test_replay_reuses_a_recorded_grant(
        self, authored: List[Tuple[str, Optional[list], bool]], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            trace_sharing, "trace_sharing_status", lambda: TraceSharingConsent(analyze=True)
        )
        trace_sharing.grant_trace_sharing(TraceConsentSource.NODE_FOLD, require_opt_in=False)
        assert authored == [("canonical-1", None, True)]

    def test_unrecorded_stance_keeps_the_pre_2_9_14_default(
        self, authored: List[Tuple[str, Optional[list], bool]]
    ) -> None:
        """No row yet (the first authoring) must not silently become a decline."""
        trace_sharing.grant_trace_sharing(TraceConsentSource.NODE_FOLD, require_opt_in=False)
        assert authored == [("canonical-1", None, True)]

    def test_recorded_analyze_stance_never_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom() -> TraceSharingConsent:
            raise RuntimeError("substrate down")

        monkeypatch.setattr(trace_sharing, "trace_sharing_status", boom)
        assert trace_sharing.recorded_analyze_stance() is True
        assert trace_sharing.recorded_analyze_stance(default=False) is False


def test_an_explicit_argument_beats_the_recorded_stance(
    authored: List[Tuple[str, Optional[list], bool]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The owner changing their mind in the UI must win over the stored row."""
    monkeypatch.setattr(
        trace_sharing, "trace_sharing_status", lambda: TraceSharingConsent(analyze=True)
    )
    trace_sharing.grant_trace_sharing(
        TraceConsentSource.SETUP_WIZARD, require_opt_in=False, analyze=False
    )
    assert authored == [("canonical-1", None, False)]


def test_no_opt_in_authors_nothing_regardless_of_analyze(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The opt-in gate still comes first — analyze cannot smuggle a grant through."""
    monkeypatch.delenv(trace_sharing.OPT_IN_ENV_VAR, raising=False)
    calls: List[bool] = []
    monkeypatch.setattr(
        trace_sharing, "_author_ship_grant", lambda r, analyze: calls.append(analyze)
    )
    result: TraceSharingGrantResult = trace_sharing.grant_trace_sharing(
        TraceConsentSource.NODE_FOLD, analyze=True
    )
    assert result.opted_in is False
    assert calls == []
