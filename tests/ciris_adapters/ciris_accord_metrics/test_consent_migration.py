"""Legacy consent → CEG grant migration (adapter start hook).

The legacy consent artifacts (CIRIS_ACCORD_METRICS_CONSENT[_TIMESTAMP] env,
the persistent .env lines, the adapter-config graph fields) are MIGRATED, not
dual-written: the emitted CEG grant carries the ORIGINAL consent timestamp,
and on confirmed success the legacy sources are deleted. Post-migration boots
derive consent from the standing CEG grant.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ciris_adapters.ciris_accord_metrics.adapter import AccordMetricsAdapter

_TS = "2025-01-01T00:00:00Z"


def _mk_adapter(monkeypatch, tmp_path: Path, env_consent: bool = True):
    if env_consent:
        monkeypatch.setenv("CIRIS_ACCORD_METRICS_CONSENT", "true")
        monkeypatch.setenv("CIRIS_ACCORD_METRICS_CONSENT_TIMESTAMP", _TS)
    else:
        monkeypatch.delenv("CIRIS_ACCORD_METRICS_CONSENT", raising=False)
        monkeypatch.delenv("CIRIS_ACCORD_METRICS_CONSENT_TIMESTAMP", raising=False)
    monkeypatch.setenv("CIRIS_CONFIG_DIR", str(tmp_path))
    (tmp_path / ".env").write_text(
        "FOO=bar\n"
        f"CIRIS_ACCORD_METRICS_CONSENT=true\n"
        f"CIRIS_ACCORD_METRICS_CONSENT_TIMESTAMP={_TS}\n"
        "BAZ=1\n",
        encoding="utf-8",
    )
    runtime = MagicMock()
    runtime.agent_identity = None
    runtime.agent_id = "test-agent"
    runtime.config_service = None
    return AccordMetricsAdapter(runtime, adapter_config={"adapter_id": "accord_test"})


def test_grant_carries_original_timestamp(monkeypatch, tmp_path):
    """The migrated grant's granted_at is the LEGACY consent time, not now()."""
    adapter = _mk_adapter(monkeypatch, tmp_path)
    assert adapter._consent_timestamp == _TS

    captured = {}

    def fake_emit(granted_at=None):
        captured["granted_at"] = granted_at
        return "att-123"

    with patch(
        "ciris_engine.logic.services.governance.consent.attestation.emit_community_consent_grant",
        side_effect=fake_emit,
    ):
        with patch.object(adapter.metrics_service, "start", return_value=asyncio.sleep(0)):
            asyncio.run(adapter.start())

    assert captured["granted_at"] == _TS


def test_successful_migration_deletes_legacy_sources(monkeypatch, tmp_path):
    """On confirmed emit, env vars + .env lines + config fields are removed."""
    import os

    adapter = _mk_adapter(monkeypatch, tmp_path)
    with patch(
        "ciris_engine.logic.services.governance.consent.attestation.emit_community_consent_grant",
        return_value="att-123",
    ):
        with patch.object(adapter.metrics_service, "start", return_value=asyncio.sleep(0)):
            asyncio.run(adapter.start())

    # 1. process env purged
    assert "CIRIS_ACCORD_METRICS_CONSENT" not in os.environ
    assert "CIRIS_ACCORD_METRICS_CONSENT_TIMESTAMP" not in os.environ
    # 2. persistent .env purged, other lines intact
    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "CIRIS_ACCORD_METRICS_CONSENT" not in env_text
    assert "FOO=bar" in env_text and "BAZ=1" in env_text
    # 3. adapter-config graph fields cleared
    assert "consent_given" not in adapter._adapter_config
    assert "consent_timestamp" not in adapter._adapter_config


def test_failed_emit_preserves_legacy_sources(monkeypatch, tmp_path):
    """A no-op emit (engine/key unavailable) must NOT delete the sources."""
    import os

    adapter = _mk_adapter(monkeypatch, tmp_path)
    with patch(
        "ciris_engine.logic.services.governance.consent.attestation.emit_community_consent_grant",
        return_value=None,
    ):
        with patch.object(adapter.metrics_service, "start", return_value=asyncio.sleep(0)):
            asyncio.run(adapter.start())

    assert os.environ.get("CIRIS_ACCORD_METRICS_CONSENT") == "true"
    assert "CIRIS_ACCORD_METRICS_CONSENT=true" in (tmp_path / ".env").read_text(encoding="utf-8")


def test_post_migration_boot_derives_consent_from_ceg(monkeypatch, tmp_path):
    """No legacy sources + standing CEG grant → consenting boot."""
    adapter = _mk_adapter(monkeypatch, tmp_path, env_consent=False)
    assert adapter._consent_given is False

    with patch(
        "ciris_engine.logic.services.governance.consent.attestation.current_community_grant_id",
        return_value="att-123",
    ):
        with patch(
            "ciris_engine.logic.services.governance.consent.attestation.emit_community_consent_grant",
            return_value="att-123",
        ):
            with patch.object(adapter.metrics_service, "start", return_value=asyncio.sleep(0)):
                asyncio.run(adapter.start())

    assert adapter._consent_given is True


def test_granted_at_threads_into_claim():
    """build_community_consent_grant carries granted_at into the CEG claim."""
    from ciris_engine.logic.services.governance.consent.attestation import (
        build_community_consent_grant,
    )

    grant = build_community_consent_grant("key-1", "community-1", granted_at=_TS)
    assert grant.attestation_envelope.claim.granted_at == _TS
    # default stays None (fresh opt-in stamps nothing retroactive)
    grant2 = build_community_consent_grant("key-1", "community-1")
    assert grant2.attestation_envelope.claim.granted_at is None
