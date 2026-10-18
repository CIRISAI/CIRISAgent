"""One traces-consent grant, not one per opt-in path per tick (CIRISAgent#1289).

Live: a Windows 0.5.227 install wrote three `consent:community_trust:v1` grants
per boot (legacy_migration, node_fold, delivery_probe); a Linux 2.16.1 desktop
wrote one every ~15 s while persist refused each crossing for want of an owner
binding. Every one is a signed row that replicates to the canonical.

The fake corpus below behaves like persist where it matters: every
`attestation_upsert_local` mints a new row, and a crossing is refused while no
owner binding over the attesting key is held. No node, no :4243.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pytest

from ciris_engine.logic.services.governance.consent import attestation as att
from ciris_engine.logic.services.governance.consent import trace_sharing
from ciris_engine.schemas.consent.trace_sharing import TraceConsentSource, TraceSharingConsent

AGENT_KEY = "ciris-agent-bootstrap-test"
NODE_KEY = "ciris-node-test"
CANONICAL = "ciris-canonical-1-test"


class FakeCorpus:
    def __init__(self, owner: Optional[str] = "owner-1") -> None:
        # Whether persist's door admits the crossing. On an actor/node split install
        # the owner binding is over the NODE key, never the engine key.
        self.owner = owner
        self.crossing_attempts = 0
        self.rows: List[Dict[str, Any]] = []
        self._clock = datetime(2026, 10, 16, 15, 19, tzinfo=timezone.utc)

    def _now(self) -> str:
        self._clock += timedelta(seconds=15)
        return self._clock.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def _append(self, payload: str, attestation_type: str) -> str:
        data = json.loads(payload)
        row = {
            "attestation_id": str(uuid.uuid4()),
            "attestation_type": attestation_type,
            "asserted_at": self._now(),
            "cohort_scope": "self",
            "subject_key_ids": data.get("subject_key_ids", []),
            "attestation_envelope": data.get("attestation_envelope", {}),
        }
        self.rows.append(row)
        return str(row["attestation_id"])

    # writes
    def attestation_upsert_local(self, payload: str) -> str:
        return self._append(payload, "scores")

    def attestation_insert_local(self, payload: str) -> str:
        return self._append(payload, json.loads(payload)["attestation_type"])

    # reads
    def list_attestations(self, query: str, cursor: Optional[str], limit: int, key_id: str) -> str:
        return json.dumps({"items": list(self.rows)})

    def owner_of_json(self, key_id: str) -> str:
        """Split install (every install since 2.9.42): the engine key is never bound."""
        return json.dumps(self.owner if key_id == NODE_KEY else None)

    # v40 crossing — refused while unbound, exactly as persist refuses it
    def describe_crossing(self, attestation_id: str, scope: str, cohort: Optional[str], basis: str) -> str:
        self.crossing_attempts += 1
        if not self.owner:
            raise ValueError(f'federation_invalid_argument: no owner binding over "{AGENT_KEY}" is in force')
        return "{}"

    def enter_mesh(self, attestation_id: str, ci: str) -> Dict[str, Any]:
        return {"outcome": "crossed", "attestation_id": attestation_id}

    def widen_audience(self, prior_id: str, ci: str, strip: List[str]) -> Dict[str, Any]:
        prior = next(r for r in self.rows if r["attestation_id"] == prior_id)
        placed = dict(prior, attestation_id=f"{prior_id}-fed", cohort_scope="federation")
        self.rows.append(placed)
        return {"outcome": "crossed", "attestation_id": placed["attestation_id"]}

    # what the tests count
    def minted_grants(self) -> List[Dict[str, Any]]:
        """Signed grant CLAIMS — a widened placement of one claim is not a new claim."""
        return [r for r in self.rows if r["attestation_type"] == "scores" and r["cohort_scope"] == "self"]


@pytest.fixture
def corpus(monkeypatch: pytest.MonkeyPatch) -> FakeCorpus:
    eng = FakeCorpus()
    monkeypatch.delenv(att._FEATURE_FLAG_ENV, raising=False)
    monkeypatch.setattr(att, "_resolve_engine", lambda: eng)
    monkeypatch.setattr(att, "_resolve_attesting_key_id", lambda: AGENT_KEY)
    monkeypatch.setattr(att, "canonical_community_key_id", lambda: CANONICAL)
    # The ship half is the node's call and has its own tests; keep it out of the count.
    monkeypatch.setattr(trace_sharing, "_author_ship_grant", lambda r, analyze: r.peers_authored.append(CANONICAL))
    monkeypatch.setattr(trace_sharing, "trace_sharing_status", lambda: TraceSharingConsent())
    new_boot()
    return eng


def new_boot() -> None:
    """A process restart: forget everything held in memory; the corpus persists."""
    for name in ("_crossing_attempted",):
        held = getattr(att, name, None)
        if held is not None:
            held.clear()
    if hasattr(att, "_last_grant_decision"):
        att._last_grant_decision = None
    if hasattr(trace_sharing, "_last_incomplete"):
        trace_sharing._last_incomplete.clear()


def opt_in(source: TraceConsentSource) -> Optional[str]:
    return trace_sharing.grant_trace_sharing(source, require_opt_in=False).capture_grant_id


def test_two_boots_produce_one_grant(corpus: FakeCorpus) -> None:
    first = opt_in(TraceConsentSource.NODE_FOLD)
    new_boot()
    second = opt_in(TraceConsentSource.NODE_FOLD)

    assert len(corpus.minted_grants()) == 1
    assert first == second, "the second boot must name the grant already in force"


def test_every_path_in_one_boot_produces_one_grant(corpus: FakeCorpus) -> None:
    # The Windows sequence: legacy_migration runs before the node is claimed.
    corpus.owner = None
    opt_in(TraceConsentSource.LEGACY_MIGRATION)
    corpus.owner = "owner-1"
    opt_in(TraceConsentSource.NODE_FOLD)
    opt_in(TraceConsentSource.DELIVERY_PROBE)

    assert len(corpus.minted_grants()) == 1
    # and the one grant reached the community — the pre-bind path did not strand it
    assert [r for r in corpus.rows if r["cohort_scope"] == "federation"]


def test_unbound_owner_writes_one_local_grant_and_defers_only_the_crossing(
    corpus: FakeCorpus, caplog: pytest.LogCaptureFixture
) -> None:
    corpus.owner = None
    caplog.set_level(logging.DEBUG)

    first = opt_in(TraceConsentSource.DELIVERY_PROBE)  # emitted grant
    assert opt_in(TraceConsentSource.DELIVERY_PROBE) == first  # reusing grant: one new decision line
    first_tick = len([r for r in caplog.records if r.levelno >= logging.INFO])
    for _ in range(11):
        assert opt_in(TraceConsentSource.DELIVERY_PROBE) == first

    # The LOCAL capture row is what lens-core's capture gate reads: it is written,
    # once, whatever the binding. Only the crossing waits on persist's door.
    assert len(corpus.minted_grants()) == 1
    assert [r for r in corpus.rows if r["cohort_scope"] == "federation"] == []
    assert corpus.crossing_attempts == 1, "a refused crossing is not retried per tick"
    later = [r for r in caplog.records if r.levelno >= logging.INFO]
    assert len(later) == first_tick, "ticks 3..13 must add no INFO/WARN lines"

    # The binding landing, seen by the next lifecycle path, crosses the SAME row.
    corpus.owner = "owner-1"
    opt_in(TraceConsentSource.NODE_FOLD)
    assert len(corpus.minted_grants()) == 1
    assert [r for r in corpus.rows if r["cohort_scope"] == "federation"]


def test_split_install_writes_the_capture_grant_at_setup(corpus: FakeCorpus) -> None:
    """Regression for #1294: owner bound over the NODE key, engine key unbound.

    #1294 pre-checked owner_of_json(engine key), which is None on every split
    install, so the capture grant was never written and 0 traces were authored on
    all five platforms (run 39044230449).
    """
    result = trace_sharing.grant_trace_sharing(TraceConsentSource.SETUP_WIZARD, require_opt_in=False)
    assert result.capture_grant_id
    assert len(corpus.minted_grants()) == 1
    assert corpus.minted_grants()[0]["subject_key_ids"] == [CANONICAL]


@pytest.mark.parametrize("recant", [False, True], ids=["withdraw", "recant"])
def test_fresh_opt_in_after_revocation_emits_a_new_grant(corpus: FakeCorpus, recant: bool) -> None:
    original = opt_in(TraceConsentSource.SETUP_WIZARD)
    assert opt_in(TraceConsentSource.DATA_CARD) == original, "re-opting while in force reuses"
    assert len(corpus.minted_grants()) == 1

    assert trace_sharing.revoke_trace_sharing(TraceConsentSource.DATA_CARD, recant=recant)
    assert corpus.rows[-1]["attestation_type"] == ("recants" if recant else "withdraws")

    fresh = opt_in(TraceConsentSource.DATA_CARD)
    assert len(corpus.minted_grants()) == 2
    assert fresh and fresh != original
    assert opt_in(TraceConsentSource.DELIVERY_PROBE) == fresh, "and the fresh grant is then reused"


def test_interim_grant_is_directed_once_the_community_key_publishes(
    corpus: FakeCorpus, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(att, "canonical_community_key_id", lambda: None)
    opt_in(TraceConsentSource.LEGACY_MIGRATION)
    monkeypatch.setattr(att, "canonical_community_key_id", lambda: CANONICAL)
    opt_in(TraceConsentSource.NODE_FOLD)
    opt_in(TraceConsentSource.DELIVERY_PROBE)

    grants = corpus.minted_grants()
    assert len(grants) == 2, "interim, then exactly one directed upgrade"
    assert grants[0]["subject_key_ids"] == [] and grants[1]["subject_key_ids"] == [CANONICAL]


def test_unreadable_consent_state_mints_nothing(corpus: FakeCorpus, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_: Any) -> str:
        raise RuntimeError("substrate busy")

    monkeypatch.setattr(corpus, "list_attestations", boom)
    for _ in range(3):
        opt_in(TraceConsentSource.DELIVERY_PROBE)
    assert corpus.rows == []
