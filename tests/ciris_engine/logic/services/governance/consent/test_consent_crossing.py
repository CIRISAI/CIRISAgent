"""attestation_promote is gone; consent rows enter the mesh and are widened by the ACTOR.

Persist v39/v40 (CIRISAgent#1134, #1144). The three traps the issue text
under-sells are each pinned: `awaiting_actor` is an Ok that did nothing; a
widening leaves two rows and the placed one has a new id; an axis refusal
names the axis and must reach the caller's log, not vanish.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import patch

import pytest

from ciris_engine.logic.services.governance.consent import attestation as att


class FakeEngine:
    """Records the v40 verbs exactly as persist exposes them to Python."""

    def __init__(self, enter: Dict[str, Any], widen: Optional[Dict[str, Any]] = None, refuse: Optional[str] = None):
        self.enter, self.widen, self.refuse = enter, widen, refuse
        self.calls: List[Tuple[str, tuple]] = []

    def describe_crossing(self, attestation_id: str, scope: str, cohort_target: Optional[str], basis: str) -> str:
        self.calls.append(("describe_crossing", (attestation_id, scope, cohort_target, basis)))
        if self.refuse:
            raise ValueError(f"contextual_integrity: axis {self.refuse} refused")
        return f'{{"ci_for": "{scope}"}}'

    def enter_mesh(self, attestation_id: str, ci: str) -> Dict[str, Any]:
        self.calls.append(("enter_mesh", (attestation_id, ci)))
        return dict(self.enter)

    def widen_audience(self, prior_id: str, ci: str, strip: List[str]) -> Dict[str, Any]:
        self.calls.append(("widen_audience", (prior_id, ci, list(strip))))
        return dict(self.widen or {})

    # the write door, unchanged
    def attestation_upsert_local(self, payload: str) -> str:
        self.calls.append(("attestation_upsert_local", (payload,)))
        return "att-local-1"


def test_crossed_then_widened_returns_the_placed_id_and_composes_like_the_server() -> None:
    eng = FakeEngine(enter={"outcome": "crossed", "attestation_id": "att-1"},
                     widen={"outcome": "crossed", "attestation_id": "att-1-widened"})
    outcome, placed = att.cross_to_mesh(eng, "att-1", label="t")
    assert (outcome, placed) == ("crossed", "att-1-widened")
    names = [c[0] for c in eng.calls]
    assert names == ["describe_crossing", "enter_mesh", "describe_crossing", "widen_audience"]
    # enter over the row's OWN placement (self), widen to federation, producer-authority basis, nothing stripped
    assert eng.calls[0][1][1:] == ("self", None, att._CROSSING_BASIS_PRODUCER_AUTHORITY)
    assert eng.calls[2][1][1:] == ("federation", None, att._CROSSING_BASIS_PRODUCER_AUTHORITY)
    assert eng.calls[3][1][2] == []


def test_awaiting_actor_is_read_by_name_and_nothing_is_widened() -> None:
    eng = FakeEngine(enter={"outcome": "awaiting_actor", "attesting_key_id": "k-user"})
    outcome, placed = att.cross_to_mesh(eng, "att-1", label="t")
    assert (outcome, placed) == ("awaiting_actor", None)
    assert [c[0] for c in eng.calls] == ["describe_crossing", "enter_mesh"]


def test_already_widened_places_nothing_new() -> None:
    eng = FakeEngine(enter={"outcome": "already_in_mesh", "attestation_id": "att-1"},
                     widen={"outcome": "already_widened", "attestation_id": "att-1-prior"})
    assert att.cross_to_mesh(eng, "att-1", label="t") == ("already_widened", None)


def test_an_axis_refusal_is_raised_with_the_axis_named() -> None:
    eng = FakeEngine(enter={"outcome": "crossed"}, refuse="audience")
    with pytest.raises(ValueError, match="axis audience refused"):
        att.cross_to_mesh(eng, "att-1", label="t")


# --- end to end through one emitting site ------------------------------------


def _revocation_with(engine: FakeEngine, caplog: Any) -> Optional[str]:
    with patch.object(att, "_resolve_engine", return_value=engine), \
         patch.object(att, "_resolve_attesting_key_id", return_value="fedaddr-node"), \
         patch.object(att, "build_consent_revocation_input") as build:
        build.return_value.model_dump_json.return_value = "{}"
        return att.emit_consent_revocation("user-1", "because", promote=True)


def test_revocation_returns_the_placed_id_when_widened(caplog: Any) -> None:
    eng = FakeEngine(enter={"outcome": "crossed", "attestation_id": "att-local-1"},
                     widen={"outcome": "crossed", "attestation_id": "att-fed-9"})
    assert _revocation_with(eng, caplog) == "att-fed-9"


def test_revocation_waiting_for_its_actor_returns_the_local_id_and_warns(caplog: Any) -> None:
    eng = FakeEngine(enter={"outcome": "awaiting_actor"})
    with caplog.at_level("WARNING"):
        assert _revocation_with(eng, caplog) == "att-local-1"
    assert any("waiting for its actor's signature" in r.getMessage() and "GRANTED" in r.getMessage() for r in caplog.records)


def test_revocation_survives_an_axis_refusal_and_names_it(caplog: Any) -> None:
    eng = FakeEngine(enter={"outcome": "crossed"}, refuse="temporal_lifecycle")
    with caplog.at_level("WARNING"):
        assert _revocation_with(eng, caplog) == "att-local-1"
    assert any("axis temporal_lifecycle refused" in r.getMessage() for r in caplog.records)


# --- the grant picker: a widening ties on the instant ------------------------


def test_picker_prefers_the_widest_placement_of_one_claim() -> None:
    original = {"attestation_id": "g-self", "asserted_at": "2026-09-04T10:00:00.123Z", "cohort_scope": "self"}
    widened = {"attestation_id": "g-fed", "asserted_at": "2026-09-04T10:00:00.123Z", "cohort_scope": "federation"}
    older_fed = {"attestation_id": "g-old", "asserted_at": "2026-09-04T09:00:00.000Z", "cohort_scope": "federation"}
    ordered = sorted([original, older_fed, widened], key=att._grant_sort_key, reverse=True)
    assert [r["attestation_id"] for r in ordered] == ["g-fed", "g-self", "g-old"]


# --- the other two crossing sites, end to end through the fake engine ----------


def _community_patches(engine: FakeEngine, community: Optional[str] = "community-1"):
    grant = patch.object(att, "build_community_consent_grant")
    structural = patch.object(att, "build_community_structural")
    return (
        patch.object(att, "consent_ceg_attestations_enabled", return_value=True),
        patch.object(att, "_resolve_engine", return_value=engine),
        patch.object(att, "_resolve_attesting_key_id", return_value="fedaddr-node"),
        patch.object(att, "canonical_community_key_id", return_value=community),
        patch.object(att, "_directed_payload", return_value="{}"),
        grant,
        structural,
    )


def test_directed_grant_adopts_the_widened_row_as_its_identity(caplog: Any) -> None:
    eng = FakeEngine(enter={"outcome": "crossed", "attestation_id": "att-local-1"},
                     widen={"outcome": "crossed", "attestation_id": "att-fed-7"})
    patches = _community_patches(eng)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5] as build, patches[6]:
        build.return_value.model_dump_json.return_value = "{}"
        assert att.emit_community_consent_grant() == "att-fed-7"
    assert [c[0] for c in eng.calls] == ["attestation_upsert_local", "describe_crossing", "enter_mesh", "describe_crossing", "widen_audience"]


def test_directed_grant_keeps_the_local_id_when_the_crossing_is_refused(caplog: Any) -> None:
    eng = FakeEngine(enter={"outcome": "crossed"}, refuse="audience")
    patches = _community_patches(eng)
    with caplog.at_level("WARNING"), patches[0], patches[1], patches[2], patches[3], patches[4], patches[5] as build, patches[6]:
        build.return_value.model_dump_json.return_value = "{}"
        assert att.emit_community_consent_grant() == "att-local-1"
    assert any("axis audience refused" in r.getMessage() for r in caplog.records)


def test_community_revocation_returns_the_placed_id(caplog: Any) -> None:
    intent = list(att.RevocationIntent)[0]

    class _Eng(FakeEngine):
        def attestation_insert_local(self, payload: str) -> str:
            self.calls.append(("attestation_insert_local", (payload,)))
            return "att-rev-1"

    eng = _Eng(enter={"outcome": "crossed", "attestation_id": "att-rev-1"},
               widen={"outcome": "crossed", "attestation_id": "att-rev-fed"})
    patches = _community_patches(eng)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6] as build:
        build.return_value.model_dump_json.return_value = "{}"
        assert att.emit_community_consent_revocation(intent, "att-fed-7", "user asked") == "att-rev-fed"
    assert eng.calls[0][0] == "attestation_insert_local"


def test_community_revocation_waiting_for_its_actor_keeps_the_local_id_and_warns(caplog: Any) -> None:
    intent = list(att.RevocationIntent)[0]

    class _Eng(FakeEngine):
        def attestation_insert_local(self, payload: str) -> str:
            return "att-rev-1"

    eng = _Eng(enter={"outcome": "awaiting_actor"})
    patches = _community_patches(eng)
    with caplog.at_level("WARNING"), patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6] as build:
        build.return_value.model_dump_json.return_value = "{}"
        assert att.emit_community_consent_revocation(intent, "att-fed-7", None) == "att-rev-1"
    assert any("waiting for its actor's signature" in r.getMessage() and "in force" in r.getMessage() for r in caplog.records)


def test_log_crossing_reports_a_no_op_outcome_by_name(caplog: Any) -> None:
    with caplog.at_level("INFO"):
        att._log_crossing("probe", "att-1", "already_widened", None, waiting_reads_as="n/a")
    assert any("crossing outcome: already_widened" in r.getMessage() for r in caplog.records)


def test_current_grant_picker_prefers_the_widened_copy_of_the_newest_claim() -> None:
    rows = {"items": [
        {"attestation_type": "scores", "attestation_id": "g-self", "asserted_at": "2026-09-04T10:00:00.123Z", "cohort_scope": "self"},
        {"attestation_type": "scores", "attestation_id": "g-fed", "asserted_at": "2026-09-04T10:00:00.123Z", "cohort_scope": "federation"},
        {"attestation_type": "withdraws", "attestation_id": "w-1", "asserted_at": "2026-09-04T11:00:00.000Z", "cohort_scope": "federation"},
    ]}

    class _Eng:
        def list_attestations(self, query: str, cursor: Any, limit: int, key_id: str) -> str:
            assert "consent" in query or "community" in query or query
            return json.dumps(rows)

    with patch.object(att, "_resolve_engine", return_value=_Eng()), patch.object(att, "_resolve_attesting_key_id", return_value="fedaddr-node"):
        assert att.current_community_grant_id() == "g-fed"


def test_grant_instant_picker_resolves_the_same_row_as_the_id_picker() -> None:
    rows = {"items": [
        {"attestation_type": "scores", "attestation_id": "g-self", "asserted_at": "2026-09-04T10:00:00.123Z", "cohort_scope": "self"},
        {"attestation_type": "scores", "attestation_id": "g-fed", "asserted_at": "2026-09-04T10:00:00.123Z", "cohort_scope": "federation"},
        {"attestation_type": "scores", "attestation_id": "g-old", "asserted_at": "2026-09-03T10:00:00.000Z", "cohort_scope": "federation"},
    ]}

    class _Eng:
        def list_attestations(self, query: str, cursor: Any, limit: int, key_id: str) -> str:
            return json.dumps(rows)

    with patch.object(att, "_resolve_engine", return_value=_Eng()), patch.object(att, "_resolve_attesting_key_id", return_value="fedaddr-node"):
        assert att.current_community_grant_asserted_at() == "2026-09-04T10:00:00.123Z"
