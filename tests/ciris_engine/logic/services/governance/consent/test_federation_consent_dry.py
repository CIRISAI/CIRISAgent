"""CONSENT DRY contract (v22 / ciris-server 0.5.139): the four opt-in paths
(wizard, data card, legacy-convert, env var) converge on ONE resolved truth.

Paths WITH an owner session author via the owner-gated route (the Kotlin
client's ``authorFederationConsent`` — wizard + data card, both verified to
call it). Paths WITHOUT one (boot/env) must NEVER author owner-tier grants —
they resolve the actual state via ``federation_consent_status`` and surface
drift. These tests pin the resolver half: resolution goes through the
engine's OWN readers (list_consent_peers — the projection edge reads), the
CC#46 analyze stance is never guessed from rows (None until the resolver is
py-exposed), and the drift logger warns with the remedy instead of authoring.
"""

import logging
from unittest.mock import MagicMock, patch

from ciris_engine.logic.services.governance.consent import attestation as att

MOD = "ciris_engine.logic.services.governance.consent.attestation"


def _engine(peers=None, canonicals='[{"key_id": "ciris-canonical-1-test"}]'):
    eng = MagicMock()
    eng.list_canonical_servers.return_value = canonicals
    eng.list_consent_peers.return_value = peers or []
    # analyze resolver deliberately ABSENT (0.5.139 py surface), and no principal-union readers
    del eng.resolve_scoped_consent
    del eng.resolve_scoped_consent_by_principals
    del eng.consent_peers_by_principals
    return eng


def _wire(monkey, engine, key_id="ciris-agent-test", grant="g-1"):
    monkey.setattr(att, "_resolve_engine", lambda: engine)
    monkey.setattr(att, "_resolve_attesting_key_id", lambda: key_id)
    monkey.setattr(att, "community_grant_in_force", lambda: grant)


def test_aligned_when_capture_and_replication_resolve(monkeypatch):
    eng = _engine(peers=["ciris-canonical-1-test"])
    _wire(monkeypatch, eng)
    st = att.federation_consent_status()
    assert st["capture"] is True
    assert st["replication"] is True
    assert st["analyze"] is None  # resolver not py-exposed: unknown, NOT guessed
    assert st["aligned"] is True  # every RESOLVABLE gate green
    eng.list_consent_peers.assert_called_once()  # the projection, not row reads


def test_replication_gap_detected_via_projection(monkeypatch):
    _wire(monkeypatch, _engine(peers=[]))  # grant row may exist; projection empty
    st = att.federation_consent_status()
    assert st["replication"] is False and st["aligned"] is False


def test_drift_logger_warns_with_remedy_never_authors(monkeypatch, caplog):
    eng = _engine(peers=[])
    _wire(monkeypatch, eng)
    with caplog.at_level(logging.WARNING):
        att.log_federation_consent_drift("env")
    assert any("[CONSENT-DRY]" in r.message and "Manage Consent" in r.message for r in caplog.records)
    # the session-less path must never author owner-tier grants
    assert not any("upsert" in str(c) or "emit" in str(c) for c in eng.method_calls)


def test_status_never_raises_without_engine(monkeypatch):
    monkeypatch.setattr(att, "_resolve_engine", lambda: None)
    monkeypatch.setattr(att, "_resolve_attesting_key_id", lambda: None)
    monkeypatch.setattr(att, "community_grant_in_force", lambda: None)
    st = att.federation_consent_status()
    assert st["aligned"] is False and st["replication"] is None


def _owner_authored_engine():
    """A node whose replication + analyze grants were authored by its OWNER (#599/#601):
    its own key holds no consent peer; the principal union does."""
    eng = MagicMock()
    eng.list_canonical_servers.return_value = '[{"key_id": "ciris-canonical-1-test"}]'
    eng.list_consent_peers.return_value = []
    eng.consent_peers_by_principals.return_value = '["ciris-canonical-1-test"]'
    eng.resolve_scoped_consent_by_principals.return_value = "granted"
    return eng


def test_owner_authored_grant_resolves_through_the_principals(monkeypatch, caplog):
    """The false warning: every battery node's traces reached the canonical while
    [CONSENT-DRY] said they would not, because only the node's own key was asked."""
    eng = _owner_authored_engine()
    _wire(monkeypatch, eng)
    st = att.federation_consent_status()
    assert st["replication"] is True and st["analyze"] is True and st["aligned"] is True
    eng.consent_peers_by_principals.assert_called_once_with("ciris-agent-test")
    eng.resolve_scoped_consent_by_principals.assert_called_once_with(
        "ciris-canonical-1-test", "ciris-agent-test", "analyze"
    )
    with caplog.at_level(logging.WARNING):
        att.log_federation_consent_drift("boot")
    assert not any(r.levelno >= logging.WARNING and "[CONSENT-DRY]" in r.message for r in caplog.records)


def test_principal_union_without_the_canonical_still_warns(monkeypatch, caplog):
    """Not vacuous: an empty principal union is still a real gap."""
    eng = _owner_authored_engine()
    eng.consent_peers_by_principals.return_value = "[]"
    _wire(monkeypatch, eng)
    assert att.federation_consent_status()["replication"] is False
    with caplog.at_level(logging.WARNING):
        att.log_federation_consent_drift("boot")
    assert any("[CONSENT-DRY]" in r.message for r in caplog.records)


def test_a_withdrawn_capture_grant_is_not_capture_consent(monkeypatch):
    eng = _owner_authored_engine()
    _wire(monkeypatch, eng, grant=None)
    monkeypatch.setattr(att, "current_community_grant_id", lambda: "g-withdrawn")
    assert att.federation_consent_status()["capture"] is False
