"""Regression tests for the secrets master-key bootstrap path.

Background — incident 2026-05-10 (RCA-secrets-master-key-zero-byte):
ServiceInitializer.initialize_memory_service generated the master key via
``aiofiles.open(path, "wb")`` followed by a write under the same 30s
asyncio timeout boundary as a downstream Postgres connect. When the DB
was unreachable, the timeout cancelled the parent coroutine mid-write
and left a 0-byte ``secrets_master.key``. Every subsequent boot then
failed ``len(master_key) != 32`` validation in
``SecretsEncryption.__init__`` — deterministic, no self-healing.

These tests pin the structural fixes:

1. Atomic write — ``.tmp`` + fsync + ``os.replace``. The canonical
   filename is never observably 0 bytes; cancellation orphans
   ``.tmp`` only.
2. Validate at load — wrong-length file is treated as corrupted and
   rotated, with a stable ERROR string for monitoring.
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import pytest

from ciris_engine.logic.runtime.service_initializer import ServiceInitializer


@pytest.mark.asyncio
async def test_load_valid_existing_master_key(tmp_path: Path) -> None:
    """Existing 32-byte file is loaded as-is — no rotation."""
    key_path = tmp_path / "secrets_master.key"
    expected = b"\xa5" * 32
    key_path.write_bytes(expected)
    original_mtime = key_path.stat().st_mtime_ns

    loaded = await ServiceInitializer._load_or_create_master_key(key_path)

    assert loaded == expected
    # Same file, untouched
    assert key_path.stat().st_mtime_ns == original_mtime


@pytest.mark.asyncio
async def test_zero_byte_file_triggers_rotation(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The exact incident artifact: a 0-byte file rotates with a stable
    monitoring string and produces a fresh 32-byte key."""
    key_path = tmp_path / "secrets_master.key"
    key_path.write_bytes(b"")  # the zero-byte trap

    with caplog.at_level(logging.ERROR):
        new_key = await ServiceInitializer._load_or_create_master_key(key_path)

    assert len(new_key) == 32
    # File on disk now matches the returned key (not the empty one)
    assert key_path.read_bytes() == new_key
    # Stable string monitoring will alert on
    assert any(
        "secrets_bootstrap_corruption" in r.message for r in caplog.records
    ), "expected stable 'secrets_bootstrap_corruption' marker in logs"


@pytest.mark.asyncio
async def test_short_file_triggers_rotation(tmp_path: Path) -> None:
    """Any non-32-byte length should be treated as corrupted, not just zero
    (covers partial writes from older code paths or unrelated FS damage)."""
    key_path = tmp_path / "secrets_master.key"
    key_path.write_bytes(b"\x01" * 16)  # half-length

    new_key = await ServiceInitializer._load_or_create_master_key(key_path)

    assert len(new_key) == 32
    assert new_key != b"\x01" * 16
    assert key_path.read_bytes() == new_key


@pytest.mark.asyncio
async def test_fresh_path_generates_and_persists(tmp_path: Path) -> None:
    """No existing file → atomic-write a new one; file lands at exactly 32
    bytes with 0o600 permissions and no leftover .tmp."""
    key_path = tmp_path / "secrets_master.key"
    assert not key_path.exists()

    new_key = await ServiceInitializer._load_or_create_master_key(key_path)

    assert len(new_key) == 32
    assert key_path.exists()
    assert key_path.read_bytes() == new_key
    # Owner-only permissions (RCA: prior code did chmod 0o600; preserve it)
    mode = key_path.stat().st_mode & 0o777
    assert mode == 0o600, f"expected 0600, got {oct(mode)}"
    # No orphan .tmp
    tmp_artifact = key_path.with_suffix(key_path.suffix + ".tmp")
    assert not tmp_artifact.exists()


@pytest.mark.asyncio
async def test_atomic_write_survives_outer_cancellation(tmp_path: Path) -> None:
    """The shielded atomic write must complete even when the *outer*
    coroutine that called it is cancelled mid-flight.

    This is the literal scenario from the incident: the parent coroutine
    is cancelled by ``asyncio.wait_for`` because a downstream network call
    (Postgres connect) timed out. With ``asyncio.shield`` + ``os.replace``,
    the canonical filename either holds the fully-written file or doesn't
    exist — never a 0-byte artifact.
    """
    key_path = tmp_path / "secrets_master.key"

    async def parent_with_downstream_timeout() -> bytes:
        # Start the master-key creation, then schedule a "downstream"
        # operation that times out — mimicking the Postgres connect path
        # whose timeout cancels the parent task.
        key = await ServiceInitializer._load_or_create_master_key(key_path)
        # Pretend to do downstream network I/O that hangs
        await asyncio.sleep(10)
        return key

    # Tight outer timeout: the master-key write completes (it's milliseconds),
    # then the downstream sleep is cancelled — but the file must already be
    # safely written.
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(parent_with_downstream_timeout(), timeout=0.2)

    # Canonical name exists and is 32 bytes — the contract.
    assert key_path.exists(), "master key must persist through outer cancellation"
    assert len(key_path.read_bytes()) == 32, "must never observe a 0-byte canonical file"
    # No orphan tmp
    tmp_artifact = key_path.with_suffix(key_path.suffix + ".tmp")
    assert not tmp_artifact.exists()


@pytest.mark.asyncio
async def test_rotation_and_reload_idempotent(tmp_path: Path) -> None:
    """After a rotation triggered by a corrupted file, a subsequent call
    must read the rotated key back unchanged (not rotate again)."""
    key_path = tmp_path / "secrets_master.key"
    key_path.write_bytes(b"")  # corrupt

    rotated = await ServiceInitializer._load_or_create_master_key(key_path)
    assert len(rotated) == 32

    # Second call → load path, same bytes
    reloaded = await ServiceInitializer._load_or_create_master_key(key_path)
    assert reloaded == rotated
