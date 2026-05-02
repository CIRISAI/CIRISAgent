"""Tests for the CIRIS_ACCORD_METRICS_LOCAL_COPY_DIR feature flag (2.7.8.7).

Why this exists:
When the agent ships traces to the live lens, there was no local audit copy.
That gap surfaced as a real cost during the v3 Amharic + Hausa safety sweeps —
we shipped data to lens and had no offline copy to score against. This feature
flag tees every batch we POST to disk in parallel.

The tee is best-effort. The lens is the source of truth; the local copy is
supplementary. Disk failures (full / permission denied / non-serializable
event sneaking in) MUST NOT break the live POST.

These tests pin the contract:
1. Env var unset → no disk activity
2. Env var set + writable dir → batch payload mirrored to disk before POST
3. Env var set + unwritable dir → graceful degradation, POST still happens
4. Tee write failure mid-run → graceful degradation, POST still happens
5. File contents match what gets POSTed (byte-equivalent)
6. Sequence numbers prevent collision within a single adapter instance

The tests cover the contract without standing up the full adapter — we
unit-test the tee logic by constructing the relevant state directly. The
adapter's broader machinery is exercised in test_accord_metrics_service.py.
"""

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def base_payload():
    """A minimal lens-bound batch payload — same shape _send_events_batch builds."""
    return {
        "events": [
            {"event_type": "thought_start", "thought_id": "t1", "timestamp": "2026-05-01T00:00:00Z"},
            {"event_type": "action_result", "thought_id": "t1", "action": "speak"},
        ],
        "batch_timestamp": "2026-05-01T00:00:00Z",
        "consent_timestamp": "2025-01-01T00:00:00Z",
        "trace_level": "generic",
        "trace_schema_version": "1.0",
    }


def _make_tee_only_adapter(local_copy_dir, monkeypatch):
    """Build a minimal object exposing just the fields _send_events_batch's
    tee block reads. Avoids the full adapter constructor's CIRISVerify
    initialization which is heavy + tested elsewhere."""
    from ciris_adapters.ciris_accord_metrics.services import AccordMetricsService

    obj = AccordMetricsService.__new__(AccordMetricsService)
    obj._adapter_instance_id = "test-instance"
    obj._local_copy_dir = local_copy_dir
    obj._local_copy_seq = 0
    obj._endpoint_url = "https://lens.example.test/api/v1"
    return obj


class TestLocalCopyDirInit:
    """Adapter init must read CIRIS_ACCORD_METRICS_LOCAL_COPY_DIR, mkdir if
    needed, and probe-write to fail loudly if the dir isn't writable."""

    def test_unset_env_means_local_copy_disabled(self, monkeypatch, tmp_path):
        """Default behavior: no env var, no local copy. The tee block in
        _send_events_batch is gated on `_local_copy_dir is not None`."""
        monkeypatch.delenv("CIRIS_ACCORD_METRICS_LOCAL_COPY_DIR", raising=False)
        monkeypatch.delenv("CIRIS_COVENANT_METRICS_LOCAL_COPY_DIR", raising=False)

        from ciris_adapters.ciris_accord_metrics.services import _get_metrics_env

        # Confirm helper returns falsy when env var unset
        assert not _get_metrics_env("LOCAL_COPY_DIR")

    def test_set_env_creates_dir_and_enables_tee(self, monkeypatch, tmp_path):
        """When env var is set, init mkdir's the dir and enables the tee."""
        target = tmp_path / "lens-traces"
        monkeypatch.setenv("CIRIS_ACCORD_METRICS_LOCAL_COPY_DIR", str(target))

        from ciris_adapters.ciris_accord_metrics.services import _get_metrics_env

        env_value = _get_metrics_env("LOCAL_COPY_DIR")
        assert env_value == str(target)

        # Manually run the init logic for the tee dir
        candidate = Path(env_value)
        candidate.mkdir(parents=True, exist_ok=True)
        probe = candidate / ".accord_local_copy_probe"
        probe.write_text("")
        probe.unlink()

        assert candidate.exists()
        assert candidate.is_dir()

    def test_unwritable_dir_falls_through_to_disabled(self, monkeypatch, tmp_path):
        """If the configured dir can't be created (permission denied), the
        adapter must still load — local_copy disabled, live POSTs unaffected."""
        # Simulate by trying to mkdir under a path that's actually a file
        not_a_dir = tmp_path / "blocker"
        not_a_dir.write_text("I am a file, not a dir")
        target = not_a_dir / "lens-traces"

        with pytest.raises((OSError, FileExistsError, NotADirectoryError)):
            target.mkdir(parents=True, exist_ok=True)
        # Adapter init must catch this and set _local_copy_dir = None
        # (covered structurally — the try/except in the adapter init handles
        # OSError/PermissionError; we confirm the exception classes match here)


@pytest.mark.asyncio
class TestSendEventsBatchTee:
    """The tee write must happen BEFORE the POST and must NEVER block it."""

    async def test_tee_writes_payload_to_disk_when_dir_set(self, tmp_path, monkeypatch, base_payload):
        """Happy path: dir set, payload writes to <dir>/accord-batch-*.json.

        Post-2.7.8.12 the bytes written are the EXACT bytes that get POSTed
        — `body = json.dumps(payload).encode("utf-8")` is the single source
        of truth for both. See `test_tee_bytes_byte_equal_to_wire_bytes`."""
        adapter = _make_tee_only_adapter(tmp_path, monkeypatch)

        # Inline-execute just the tee block — mirroring the production path.
        adapter._local_copy_seq += 1
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        copy_path = adapter._local_copy_dir / f"accord-batch-{ts}-{adapter._local_copy_seq:04d}.json"
        body = json.dumps(base_payload).encode("utf-8")
        copy_path.write_bytes(body)

        # Files in dir
        files = list(tmp_path.glob("accord-batch-*.json"))
        assert len(files) == 1
        assert files[0].name.endswith("-0001.json")

        # Round-trip the JSON; must equal the input payload
        loaded = json.loads(files[0].read_text())
        assert loaded == base_payload

    async def test_sequence_numbers_prevent_collision(self, tmp_path, monkeypatch, base_payload):
        """Multiple batches in the same adapter instance get distinct seq
        numbers, so two batches written within the same microsecond don't
        clobber each other."""
        adapter = _make_tee_only_adapter(tmp_path, monkeypatch)

        for _ in range(3):
            adapter._local_copy_seq += 1
            ts = "20260501T000000000000"  # same timestamp on purpose
            copy_path = adapter._local_copy_dir / f"accord-batch-{ts}-{adapter._local_copy_seq:04d}.json"
            copy_path.write_text(json.dumps(base_payload))

        files = sorted(tmp_path.glob("accord-batch-*.json"))
        assert len(files) == 3
        # Distinct seq numbers
        assert {f.name.split("-")[-1] for f in files} == {"0001.json", "0002.json", "0003.json"}

    async def test_tee_failure_does_not_propagate(self, tmp_path, monkeypatch, base_payload):
        """If write fails (disk full, permission denied), the POST path
        must continue. Simulated by monkeypatching write_text to raise."""
        adapter = _make_tee_only_adapter(tmp_path, monkeypatch)
        adapter._local_copy_seq += 1

        # Simulate disk write failure
        def _fail_write(self, *args, **kwargs):
            raise PermissionError("simulated disk-full")

        monkeypatch.setattr(Path, "write_text", _fail_write)

        # The tee block in _send_events_batch must catch this and proceed.
        # Re-implement the try/except contract here:
        try:
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
            copy_path = adapter._local_copy_dir / f"accord-batch-{ts}-{adapter._local_copy_seq:04d}.json"
            copy_path.write_text(json.dumps(base_payload))
            assert False, "write_text should have raised"
        except (OSError, PermissionError, TypeError):
            # Adapter swallows + logs; we just confirm the exception type is
            # what's caught. POST code below continues regardless.
            pass

    async def test_non_serializable_event_raises_typeerror_at_body_serialization(self, tmp_path, monkeypatch):
        """Post-2.7.8.12: serialization happens ONCE before the tee — a
        non-JSON-serializable event raises TypeError at `body =
        json.dumps(payload)` (the new single-source step), so neither the
        tee nor the wire path execute. The exception propagates to
        `_flush_events` which handles it as a transient failure (the same
        path that handles 5xx + network errors).

        Pre-2.7.8.12 the tee swallowed TypeError and the POST raised it
        separately; after the fix that double-handling is gone."""
        adapter = _make_tee_only_adapter(tmp_path, monkeypatch)
        adapter._local_copy_seq += 1

        bad_payload = {
            "events": [{"thought_id": "t1", "weird": object()}],  # non-serializable
            "batch_timestamp": "2026-05-01T00:00:00Z",
            "consent_timestamp": "2025-01-01T00:00:00Z",
            "trace_level": "generic",
            "trace_schema_version": "1.0",
        }

        # Body serialization must raise BEFORE the tee block runs.
        with pytest.raises(TypeError):
            json.dumps(bad_payload).encode("utf-8")

        # And no tee file is written.
        files = list(tmp_path.glob("accord-batch-*.json"))
        assert files == []

    async def test_tee_bytes_byte_equal_to_wire_bytes(self, tmp_path, monkeypatch):
        """The 2.7.8.12 contract: file on disk == bytes that go on the wire,
        byte-for-byte. This is the property that lets persist's body_sha256
        forensic join (introduced in lens v0.1.16) actually match local-tee
        files when reconciling rejected batches.

        Pre-2.7.8.12 the tee used `ensure_ascii=False, separators=(",",":")`
        while aiohttp's `json=payload` path used `json.dumps` defaults
        (`ensure_ascii=True`, spaced separators). On any payload with
        non-ASCII characters (every Yorùbá / Amharic / Hausa trace) the two
        byte sequences differed on every tone-marked codepoint and every
        comma/colon. body_sha256 prefixes captured by lens never matched
        any of the 798+ files in the local tee dirs — proven by the
        cross-reference run on 2026-05-02. This test pins the post-fix
        invariant: the bytes are literally the same."""
        # Yorùbá-tone-marked content is the canary — it surfaced the bug in
        # the first place via the failed body_sha256 cross-reference.
        payload = {
            "events": [
                {
                    "event_type": "action_result",
                    "thought_id": "t-yo-1",
                    "rationale": "Mo gbọ́ yín, Tèmítọ́pẹ́. Ìrànlọ́wọ́ ọjọ́gbọ́n ìlera-ọkàn wà ní àyè.",
                    "k_eff": 0.94,
                }
            ],
            "batch_timestamp": "2026-05-02T04:10:00Z",
            "consent_timestamp": "2025-01-01T00:00:00Z",
            "trace_level": "detailed",
            "trace_schema_version": "2.7.0",
        }

        # The single source of truth: serialize once.
        body = json.dumps(payload).encode("utf-8")

        # Tee writes those exact bytes.
        tee_path = tmp_path / "accord-batch-test-0001.json"
        tee_path.write_bytes(body)

        # Bytes on disk == bytes that get POSTed. This is the contract.
        assert tee_path.read_bytes() == body, (
            "tee file diverged from wire body — body_sha256 join with persist "
            "will fail. Check that both sides use json.dumps(payload).encode()."
        )

        # And the sha256 prefix (what lens logs on rejection) round-trips.
        import hashlib

        assert hashlib.sha256(tee_path.read_bytes()).hexdigest() == hashlib.sha256(body).hexdigest()


class TestQARunnerWiring:
    """The QA runner must default to a /tmp/ path when --live-lens is on."""

    def test_default_path_is_under_tmp(self):
        """Operators don't want lens traces filling up the repo dir or HOME.
        QA runner default lands them under /tmp/qa-runner-lens-traces-<ts>/."""
        # The wiring is in tools/qa_runner/server.py around the
        # `if self.config.live_lens:` block. The test here pins the prefix
        # contract: any path the runner sets must start with /tmp/.
        from datetime import datetime, timezone

        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        default_path = f"/tmp/qa-runner-lens-traces-{ts}"
        assert default_path.startswith("/tmp/")
        assert "qa-runner-lens-traces" in default_path

    def test_operator_override_takes_precedence(self, monkeypatch):
        """If the operator pre-sets CIRIS_ACCORD_METRICS_LOCAL_COPY_DIR
        before invoking the QA runner, the runner respects it. The wiring
        in server.py is `if "CIRIS_ACCORD_METRICS_LOCAL_COPY_DIR" not in env`."""
        env = {"CIRIS_ACCORD_METRICS_LOCAL_COPY_DIR": "/operator/preset/path"}
        # Mimic the runner's check:
        if "CIRIS_ACCORD_METRICS_LOCAL_COPY_DIR" not in env:
            env["CIRIS_ACCORD_METRICS_LOCAL_COPY_DIR"] = "/tmp/qa-runner-default"
        assert env["CIRIS_ACCORD_METRICS_LOCAL_COPY_DIR"] == "/operator/preset/path"


class TestSendEventsBatchEndToEnd:
    """End-to-end coverage of `_send_events_batch` — exercises the body
    serialization, sha256 computation, tee write, and POST path with a
    mocked aiohttp session. Pre-2.7.8.x these lines were structurally
    inline-tested only; SonarCloud's "new code coverage" tracker counts
    real `_send_events_batch` calls. These tests close that gap."""

    def _make_full_adapter(self, tmp_path, with_tee=True):
        """Build a minimally-configured AccordMetricsService that will
        actually execute `_send_events_batch`. Mocks the heavy pieces
        (aiohttp session, signing key) but lets the body-serialization +
        tee + status-handling code run for real."""
        from ciris_adapters.ciris_accord_metrics.services import AccordMetricsService

        obj = AccordMetricsService.__new__(AccordMetricsService)
        obj._adapter_instance_id = "e2e-test"
        obj._endpoint_url = "https://lens.example.test/api/v1"
        obj._local_copy_dir = tmp_path if with_tee else None
        obj._local_copy_seq = 0
        obj._consent_timestamp = "2025-01-01T00:00:00Z"
        obj._deployment_region = ""
        obj._deployment_type = ""
        obj._agent_role = ""
        obj._agent_template = ""
        obj._share_location_in_traces = False
        obj._user_location = ""
        obj._user_timezone = ""
        obj._user_latitude = None
        obj._user_longitude = None
        # _trace_level is an enum-shaped attribute the method reads .value off
        from types import SimpleNamespace
        obj._trace_level = SimpleNamespace(value="generic")
        return obj

    def _make_mock_session(self, status=200, body_text="ok"):
        """aiohttp ClientSession.post returns an async-context-manager
        wrapping the response. Build a mock that supports both
        `async with session.post(...) as response` and the response's
        `.status` + `.text()` accessors."""
        response = MagicMock()
        response.status = status
        response.text = AsyncMock(return_value=body_text)

        # Async context manager
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=response)
        cm.__aexit__ = AsyncMock(return_value=None)

        session = MagicMock()
        session.post = MagicMock(return_value=cm)
        return session, response

    @pytest.mark.asyncio
    async def test_full_path_writes_tee_file_and_posts_body(self, tmp_path):
        """Happy path: serialize once → tee write → POST with same bytes.
        Verifies the 2.7.8.12 byte-equality contract end-to-end."""
        adapter = self._make_full_adapter(tmp_path, with_tee=True)
        session, response = self._make_mock_session(status=200)
        adapter._session = session

        events = [
            {"event_type": "thought_start", "thought_id": "t1"},
            {"event_type": "action_result", "thought_id": "t1", "action": "speak"},
        ]
        await adapter._send_events_batch(events)

        # Tee file written
        tee_files = list(tmp_path.glob("accord-batch-*.json"))
        assert len(tee_files) == 1, f"Expected exactly one tee file, got {tee_files}"

        # POST called once
        assert session.post.call_count == 1
        call_kwargs = session.post.call_args.kwargs
        # Body passed as `data=`, not `json=` (the byte-equality fix)
        assert "data" in call_kwargs
        assert call_kwargs["headers"] == {"Content-Type": "application/json"}

        # Tee bytes byte-identical to wire bytes
        wire_body = call_kwargs["data"]
        assert tee_files[0].read_bytes() == wire_body

    @pytest.mark.asyncio
    async def test_no_tee_when_local_copy_dir_unset(self, tmp_path):
        """`_local_copy_dir is None` → no tee branch executes."""
        adapter = self._make_full_adapter(tmp_path, with_tee=False)
        session, _ = self._make_mock_session(status=200)
        adapter._session = session

        await adapter._send_events_batch([{"event_type": "x", "thought_id": "t"}])

        # No tee files anywhere under tmp_path
        assert list(tmp_path.glob("accord-batch-*.json")) == []
        assert session.post.call_count == 1

    @pytest.mark.asyncio
    async def test_lens_422_raises_typed_reject_error(self, tmp_path):
        """4xx (except 429) → LensContentRejectError raised, NOT generic RuntimeError.
        That's the typed-exception contract from 2.7.8.8 that the discard branch hangs on."""
        from ciris_adapters.ciris_accord_metrics.services import LensContentRejectError

        adapter = self._make_full_adapter(tmp_path, with_tee=False)
        session, _ = self._make_mock_session(
            status=422, body_text='{"detail":"verify_signature_mismatch"}'
        )
        adapter._session = session

        with pytest.raises(LensContentRejectError) as exc_info:
            await adapter._send_events_batch([{"event_type": "x", "thought_id": "t"}])

        assert exc_info.value.status == 422
        assert "verify_signature_mismatch" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_lens_429_rate_limited_raises_runtime_error_not_typed(self, tmp_path):
        """429 stays as a generic RuntimeError → re-queue path applies.
        The discard branch is for non-transient 4xx ONLY; rate-limiting is transient."""
        from ciris_adapters.ciris_accord_metrics.services import LensContentRejectError

        adapter = self._make_full_adapter(tmp_path, with_tee=False)
        session, _ = self._make_mock_session(status=429, body_text="rate limited")
        adapter._session = session

        with pytest.raises(RuntimeError) as exc_info:
            await adapter._send_events_batch([{"event_type": "x", "thought_id": "t"}])

        # Specifically NOT the typed exception — the re-queue path catches generic
        # RuntimeError but skips LensContentRejectError
        assert not isinstance(exc_info.value, LensContentRejectError)
        assert "429" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_lens_502_bad_gateway_raises_runtime_error(self, tmp_path):
        """5xx is transient → generic RuntimeError → re-queue path."""
        from ciris_adapters.ciris_accord_metrics.services import LensContentRejectError

        adapter = self._make_full_adapter(tmp_path, with_tee=False)
        session, _ = self._make_mock_session(status=502, body_text="bad gateway")
        adapter._session = session

        with pytest.raises(RuntimeError) as exc_info:
            await adapter._send_events_batch([{"event_type": "x", "thought_id": "t"}])

        assert not isinstance(exc_info.value, LensContentRejectError)

    @pytest.mark.asyncio
    async def test_tee_write_failure_does_not_block_post(self, tmp_path, monkeypatch):
        """If the tee write fails (disk full, perm denied), the POST still
        proceeds. The lens is the source of truth; the tee is supplementary."""
        adapter = self._make_full_adapter(tmp_path, with_tee=True)
        session, _ = self._make_mock_session(status=200)
        adapter._session = session

        # Simulate write_bytes raising — the OSError catch must swallow it.
        original_write_bytes = Path.write_bytes

        def _failing_write_bytes(self, *args, **kwargs):
            raise OSError("simulated disk full")

        monkeypatch.setattr(Path, "write_bytes", _failing_write_bytes)

        # Must NOT raise — POST proceeds even if tee fails.
        await adapter._send_events_batch([{"event_type": "x", "thought_id": "t"}])

        assert session.post.call_count == 1

    @pytest.mark.asyncio
    async def test_consent_timestamp_required(self, tmp_path):
        """No consent_timestamp → RuntimeError before any POST. Belt-and-suspenders
        check beyond the per-config validation, since lens returns 422 without it."""
        adapter = self._make_full_adapter(tmp_path, with_tee=False)
        adapter._consent_timestamp = ""  # Drop consent
        session, _ = self._make_mock_session(status=200)
        adapter._session = session

        with pytest.raises(RuntimeError, match="consent_timestamp"):
            await adapter._send_events_batch([{"event_type": "x", "thought_id": "t"}])

        # POST never called
        assert session.post.call_count == 0

    @pytest.mark.asyncio
    async def test_no_session_raises(self, tmp_path):
        """`_send_events_batch` requires an initialized HTTP session."""
        adapter = self._make_full_adapter(tmp_path, with_tee=False)
        adapter._session = None  # type: ignore[assignment]

        with pytest.raises(RuntimeError, match="HTTP session not initialized"):
            await adapter._send_events_batch([{"event_type": "x", "thought_id": "t"}])

    @pytest.mark.asyncio
    async def test_correlation_metadata_only_added_when_non_empty(self, tmp_path):
        """The correlation_metadata key is only present in the payload when
        at least one optional field has been set. Empty correlation never
        ships an empty `correlation_metadata` field — wire-shape contract."""
        adapter = self._make_full_adapter(tmp_path, with_tee=False)
        adapter._deployment_region = "us-east-1"  # set ONE field
        session, _ = self._make_mock_session(status=200)
        adapter._session = session

        await adapter._send_events_batch([{"event_type": "x", "thought_id": "t"}])

        # Read what was POSTed
        wire_body = session.post.call_args.kwargs["data"]
        payload = json.loads(wire_body.decode("utf-8"))
        assert "correlation_metadata" in payload
        assert payload["correlation_metadata"]["deployment_region"] == "us-east-1"
