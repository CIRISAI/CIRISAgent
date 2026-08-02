"""Substrate-backed integration tests for SecretsService (2.9.7, #896).

The SecretsStore / SecretsEncryption passthrough shims were inlined into
SecretsService and deleted — these tests prove the surviving facade drives
persist's `secrets_*` substrate correctly end-to-end: master-key bootstrap
probe, store/recall/forget, direct crypto, listing, and re-encryption.

Uses the shared `persist_engine` fixture (tests/fixtures/persist_engine.py,
registered in conftest) which wires a real sqlite-backed Engine into
`persistence.models.graph`.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from ciris_engine.logic.secrets.service import SecretsService
from ciris_engine.schemas.runtime.enums import SensitivityLevel
from ciris_engine.schemas.secrets.core import DetectedSecret
from ciris_engine.schemas.secrets.service import (
    DecapsulationContext,
    FilterUpdateRequest,
    PatternConfig,
)


@pytest.fixture
def time_service():
    mock = Mock()
    mock.now.return_value = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    return mock


@pytest.fixture
def secrets_service(persist_engine, time_service):
    """SecretsService against a real persist engine.

    Construction runs the master-key bootstrap probe (`secrets_test_encryption`
    → rotate-once on a fresh engine), so every test below starts with a
    ready crypto substrate.
    """
    return SecretsService(time_service=time_service)


@pytest.mark.asyncio
async def test_master_key_bootstrap_probe(persist_engine, secrets_service):
    """Constructing the service on a fresh engine initializes the master key."""
    assert persist_engine.secrets_test_encryption() is True


@pytest.mark.asyncio
async def test_encrypt_decrypt_round_trip(secrets_service):
    plaintext = "hunter2-round-trip"
    ciphertext = await secrets_service.encrypt(plaintext)
    assert ciphertext != plaintext
    assert await secrets_service.decrypt(ciphertext) == plaintext


@pytest.mark.asyncio
async def test_decrypt_garbage_returns_empty(secrets_service):
    assert await secrets_service.decrypt("not-a-valid-envelope") == ""


@pytest.mark.asyncio
async def test_store_retrieve_forget_round_trip(secrets_service):
    key = str(uuid.uuid4())
    await secrets_service.store_secret(key, "s3cr3t-value")

    assert await secrets_service.retrieve_secret(key) == "s3cr3t-value"

    refs = await secrets_service.list_all_secrets()
    assert key in [r.uuid for r in refs]

    assert await secrets_service.forget_secret(key) is True
    assert await secrets_service.retrieve_secret(key) is None


@pytest.mark.asyncio
async def test_recall_secret_metadata_and_decrypt(secrets_service):
    key = str(uuid.uuid4())
    detected = DetectedSecret(
        secret_uuid=key,
        original_value="tok-abc123",
        replacement_text=f"{{SECRET:{key}:test}}",
        pattern_name="api_key",
        description="Test API key",
        sensitivity=SensitivityLevel.HIGH,
        context_hint="unit test",
    )
    record = await secrets_service._store_detected_secret(detected, "msg-1")
    assert record.secret_uuid == key
    assert record.sensitivity_level == SensitivityLevel.HIGH
    # HIGH sensitivity persists tool-only auto-decapsulation
    assert record.auto_decapsulate_for_actions == ["tool"]

    result = await secrets_service.recall_secret(key, purpose="test", decrypt=False)
    assert result is not None and result.found is True and result.value is None

    result = await secrets_service.recall_secret(key, purpose="test", decrypt=True)
    assert result is not None and result.found is True and result.value == "tok-abc123"


@pytest.mark.asyncio
async def test_update_filter_config_seeds_substrate_catalog(persist_engine, secrets_service):
    """update_filter_config upserts patterns into persist's filter catalog.

    Persist's default catalog is EMPTY (gap filed upstream) — the seed is
    a precondition for any detection through the substrate.
    """
    result = await secrets_service.update_filter_config(
        FilterUpdateRequest(
            patterns=[
                PatternConfig(
                    name="test_api_key",
                    pattern="sk-[A-Za-z0-9]{10}",
                    sensitivity=SensitivityLevel.HIGH,
                    enabled=True,
                )
            ]
        ),
        accessor="test",
    )
    assert result.success is True
    assert result.stats is not None and result.stats.patterns_updated == 1

    config = await secrets_service.get_filter_config()
    patterns = config["config_value"]["patterns"]
    assert [p["pattern_id"] for p in patterns] == ["test_api_key"]
    # HIGH sensitivity → tool-only auto-decapsulation whitelist
    assert patterns[0]["auto_decapsulate_for_actions"] == ["tool"]

    # enabled=False removes the pattern from the catalog
    result = await secrets_service.update_filter_config(
        FilterUpdateRequest(
            patterns=[
                PatternConfig(
                    name="test_api_key",
                    pattern="sk-[A-Za-z0-9]{10}",
                    sensitivity=SensitivityLevel.HIGH,
                    enabled=False,
                )
            ]
        ),
        accessor="test",
    )
    assert result.success is True
    config = await secrets_service.get_filter_config()
    assert config["config_value"]["patterns"] == []


@pytest.mark.asyncio
async def test_process_incoming_text_detects_via_substrate(persist_engine, secrets_service):
    """Detection routes through persist's `secrets_process_incoming_text`."""
    await secrets_service.update_filter_config(
        FilterUpdateRequest(
            patterns=[
                PatternConfig(
                    name="test_api_key",
                    pattern="sk-[A-Za-z0-9]{10}",
                    sensitivity=SensitivityLevel.HIGH,
                    enabled=True,
                )
            ]
        ),
        accessor="test",
    )

    filtered, refs = await secrets_service.process_incoming_text("my key is sk-abcDEF1234 ok", "msg-1")
    assert len(refs) == 1
    ref = refs[0]
    assert ref.sensitivity == SensitivityLevel.HIGH
    assert f"{{SECRET:{ref.uuid}:" in filtered
    assert "sk-abcDEF1234" not in filtered
    # Detected secret is tracked for task-lifecycle auto-forget
    assert ref.uuid in secrets_service._current_task_secrets
    # And it round-trips through the substrate recall path
    assert await secrets_service.retrieve_secret(ref.uuid) == "sk-abcDEF1234"


@pytest.mark.asyncio
async def test_process_incoming_text_clean_with_empty_catalog(persist_engine, secrets_service):
    """Empty substrate catalog (persist's default) → no detections."""
    text = "my key is sk-abcDEF1234 ok"
    filtered, refs = await secrets_service.process_incoming_text(text, "msg-clean")
    assert filtered == text
    assert refs == []


@pytest.mark.asyncio
async def test_decapsulate_degrades_gracefully_on_sqlite_stub(persist_engine, secrets_service):
    """`secrets_decapsulate` is stubbed on SQLite (upstream gap) — the
    facade returns the params unchanged instead of raising."""
    key = str(uuid.uuid4())
    detected = DetectedSecret(
        secret_uuid=key,
        original_value="tok-decap",
        replacement_text=f"{{SECRET:{key}:gated}}",
        pattern_name="api_key",
        description="Gated secret",
        sensitivity=SensitivityLevel.HIGH,
        context_hint="unit test",
    )
    await secrets_service._store_detected_secret(detected, "msg-2")

    params = {"cmd": f"use {{SECRET:{key}:gated}} here"}
    ctx = DecapsulationContext(action_type="tool", thought_id="t1", user_id="system")
    result = await secrets_service.decapsulate_secrets_in_parameters("tool", params, ctx)
    assert result == params


@pytest.mark.asyncio
async def test_list_secrets_filters(secrets_service):
    key = str(uuid.uuid4())
    await secrets_service.store_secret(key, "listed-value")

    medium = await secrets_service.list_secrets(sensitivity_filter="medium")
    assert key in [r.uuid for r in medium]
    critical = await secrets_service.list_secrets(sensitivity_filter="critical")
    assert key not in [r.uuid for r in critical]


@pytest.mark.asyncio
async def test_reencrypt_all_preserves_values(secrets_service):
    key = str(uuid.uuid4())
    await secrets_service.store_secret(key, "survives-rotation")

    import secrets as secrets_module

    assert await secrets_service.reencrypt_all(secrets_module.token_bytes(32)) is True
    assert secrets_service._rotation_count == 1
    assert await secrets_service.retrieve_secret(key) == "survives-rotation"


@pytest.mark.asyncio
async def test_store_alias_is_service(secrets_service):
    """Back-compat: `.store` (ex-SecretsStore) aliases the service itself —
    external callers (`secrets_snapshot`, ciris_verify adapter) reach
    `list_all_secrets` / `migrate_to_hardware_key` through it."""
    assert secrets_service.store is secrets_service
    assert await secrets_service.store.list_all_secrets() == await secrets_service.list_all_secrets()
    # Hardware path pending upstream (CIRISPersist#87) — graceful False, no raise
    assert await secrets_service.store.migrate_to_hardware_key() in (True, False)
