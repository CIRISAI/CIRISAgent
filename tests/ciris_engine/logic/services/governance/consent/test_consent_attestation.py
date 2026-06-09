"""Tests for the consent → CEG attestation mapper (CIRISAgent#869).

Pure mapper tests run anywhere. The round-trip test exercises the real
``ciris_persist`` Engine (persist >= 4.9.0, CIRISPersist#171) and self-skips on
older substrate pins that lack ``attestation_upsert_local``.
"""

import os
from datetime import datetime, timezone

import pytest

from ciris_engine.logic.services.governance.consent.attestation import (
    INTENT_TRIGGERS_DELETION,
    ConsentClaim,
    LocalAttestationInput,
    RevocationIntent,
    _directed_payload,
    build_community_consent_grant,
    build_community_structural,
    build_consent_grant_input,
    build_consent_revocation_input,
    consent_ceg_attestations_enabled,
)
from ciris_engine.schemas.consent.core import ConsentCategory, ConsentStatus, ConsentStream

_KID = "ciris-agent-bootstrap"
_COMMUNITY = "ciris-canonical-community"


def _status(stream: ConsentStream = ConsentStream.PARTNERED) -> ConsentStatus:
    now = datetime(2026, 6, 9, tzinfo=timezone.utc)
    return ConsentStatus(
        user_id="wa-2026-06-09-ABC",
        stream=stream,
        categories=[ConsentCategory.INTERACTION, ConsentCategory.PREFERENCE],
        granted_at=now,
        last_modified=now,
    )


# ---------------------------------------------------------------- pure mapper


def test_feature_flag_default_off(monkeypatch):
    monkeypatch.delenv("CIRIS_CONSENT_CEG_ATTESTATIONS", raising=False)
    assert consent_ceg_attestations_enabled() is False
    monkeypatch.setenv("CIRIS_CONSENT_CEG_ATTESTATIONS", "true")
    assert consent_ceg_attestations_enabled() is True


def test_grant_input_shape():
    inp = build_consent_grant_input(_status(), _KID)
    assert isinstance(inp, LocalAttestationInput)
    assert inp.attesting_key_id == _KID
    assert inp.attestation_type == "scores"
    env = inp.attestation_envelope
    # scores type requires a :v<N>-versioned dimension; consent:* namespace
    assert env.dimension.startswith("consent:stream:")
    assert env.dimension.endswith(":v1")
    assert env.score == 1.0  # PARTNERED
    assert isinstance(env.claim, ConsentClaim)
    assert env.claim.user_id == "wa-2026-06-09-ABC"
    assert env.claim.state == "active"
    assert env.claim.stream == "partnered"
    assert set(env.claim.categories) == {"interaction", "preference"}


def test_stream_score_mapping():
    assert build_consent_grant_input(_status(ConsentStream.PARTNERED), _KID).attestation_envelope.score == 1.0
    assert build_consent_grant_input(_status(ConsentStream.TEMPORARY), _KID).attestation_envelope.score == 0.5
    assert build_consent_grant_input(_status(ConsentStream.ANONYMOUS), _KID).attestation_envelope.score == 0.0


def test_same_user_same_dimension():
    """Replace-on-(occurrence, dimension): same user → identical dimension."""
    a = build_consent_grant_input(_status(ConsentStream.PARTNERED), _KID).attestation_envelope.dimension
    b = build_consent_grant_input(_status(ConsentStream.ANONYMOUS), _KID).attestation_envelope.dimension
    assert a == b


def test_revocation_input_shape():
    inp = build_consent_revocation_input("wa-2026-06-09-ABC", _KID, reason="user opted out")
    env = inp.attestation_envelope
    assert env.score == 0.0
    assert env.claim.state == "revoked"
    assert env.claim.reason == "user opted out"
    # opt-out replaces the active row → same per-user dimension
    grant_dim = build_consent_grant_input(_status(), _KID).attestation_envelope.dimension
    assert env.dimension == grant_dim


# ------------------------------------------------ community / CEG 1+4 (directed)


def test_only_recant_triggers_deletion():
    assert INTENT_TRIGGERS_DELETION[RevocationIntent.RECANT] is True
    assert INTENT_TRIGGERS_DELETION[RevocationIntent.WITHDRAW] is False
    assert INTENT_TRIGGERS_DELETION[RevocationIntent.SUPERSEDE] is False


def test_community_grant_is_directed_not_broadcast():
    import json

    grant = build_community_consent_grant(_KID, _COMMUNITY)
    assert grant.attestation_envelope.dimension == "consent:community_trust:v1"
    payload = json.loads(_directed_payload(grant, _COMMUNITY))
    # the consent is DIRECTED at the canonical community — not a public broadcast
    assert payload["subject_key_ids"] == [_COMMUNITY]


def test_structural_primitive_carries_target_and_type():
    row = build_community_structural(RevocationIntent.RECANT, "grant-123", _KID, _COMMUNITY, reason="mistake")
    assert row.attestation_type == "recants"
    assert row.subject_key_ids == [_COMMUNITY]
    assert row.attestation_envelope.target == "grant-123"
    assert row.attestation_envelope.intent == "recants"


# ---------------------------------------------------------- real persist round-trip


@pytest.fixture()
def persist_engine(tmp_path, monkeypatch):
    """A real ciris_persist Engine with a generated Ed25519 local signer.

    Skips on older persist pins (no attestation_upsert_local) so the test only
    runs against the #171 substrate (persist >= 4.9.0).
    """
    ciris_persist = pytest.importorskip("ciris_persist")
    Engine = ciris_persist.Engine
    if not hasattr(Engine, "attestation_upsert_local"):
        pytest.skip("ciris_persist < 4.9.0 (no attestation_upsert_local / #171 surface)")

    # Run inside tmp_path with relative DSN/seed names — the persist sqlite DSN
    # parser mishandles an absolute path after `sqlite://`.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "ed.seed").write_bytes(os.urandom(32))
    engine = Engine(
        "sqlite://rt.db?mode=rwc",
        _KID,
        local_key_id=_KID,
        local_key_path="ed.seed",
    )
    engine.register_federation_key("agent", _KID)
    return engine


def test_grant_then_revoke_roundtrip(persist_engine):
    import json

    # grant → one local-tier row
    grant_id = persist_engine.attestation_upsert_local(build_consent_grant_input(_status(), _KID).model_dump_json())
    assert grant_id

    page = json.loads(persist_engine.list_attestations("{}", None, 10, _KID))
    assert len(page["items"]) == 1
    row = page["items"][0]
    assert row["attestation_type"] == "scores"
    assert row["attestation_envelope"]["claim"]["state"] == "active"
    assert row["attestation_envelope"]["claim"]["stream"] == "partnered"

    # revoke → replaces the same (occurrence, dimension) row (still one row)
    rev_payload = build_consent_revocation_input("wa-2026-06-09-ABC", _KID, "opt out").model_dump_json()
    persist_engine.attestation_upsert_local(rev_payload)

    page2 = json.loads(persist_engine.list_attestations("{}", None, 10, _KID))
    assert len(page2["items"]) == 1, "revoke must replace, not append, on the per-user dimension"
    assert page2["items"][0]["attestation_envelope"]["claim"]["state"] == "revoked"


def test_directed_community_grant_then_1plus4_chain(persist_engine):
    """Directed traces-consent grant + the CEG structural chain round-trips."""
    import json

    grant_id = persist_engine.attestation_upsert_local(
        _directed_payload(build_community_consent_grant(_KID, _COMMUNITY), _COMMUNITY)
    )
    assert grant_id

    # withdraws / recants / supersedes each reference the grant
    for intent in (RevocationIntent.WITHDRAW, RevocationIntent.RECANT, RevocationIntent.SUPERSEDE):
        row = build_community_structural(intent, grant_id, _KID, _COMMUNITY, reason="t")
        sid = persist_engine.attestation_insert_local(row.model_dump_json())
        assert sid

    page = json.loads(persist_engine.list_attestations("{}", None, 20, _KID))
    types = {r["attestation_type"] for r in page["items"]}
    assert {"scores", "withdraws", "recants", "supersedes"} <= types
    # the directed grant carries the community as subject
    grant_row = next(r for r in page["items"] if r["attestation_type"] == "scores")
    assert _COMMUNITY in grant_row.get("subject_key_ids", [])
