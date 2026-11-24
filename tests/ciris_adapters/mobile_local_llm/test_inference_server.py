"""Tests for the inference server lifecycle manager."""

from __future__ import annotations

import asyncio
import signal
import sys
from unittest import mock

import pytest

from ciris_adapters.mobile_local_llm.config import MobileLocalLLMConfig
from ciris_adapters.mobile_local_llm.inference_server import InferenceServerError, InferenceServerManager


def _config(**overrides) -> MobileLocalLLMConfig:
    return MobileLocalLLMConfig(**overrides)


@pytest.mark.asyncio
class TestAttachMode:
    """When server_binary is None we attach to a pre-running server."""

    async def test_attach_becomes_ready_when_probe_succeeds(self):
        cfg = _config(server_binary=None, ready_timeout_seconds=1.0)
        mgr = InferenceServerManager(cfg)
        with mock.patch.object(mgr, "_probe_health", mock.AsyncMock(return_value=True)):
            await mgr.start()
        assert mgr.owns_process is False
        assert mgr.is_running is True
        assert mgr.process_id is None

    async def test_attach_raises_when_probe_never_succeeds(self):
        cfg = _config(server_binary=None, ready_timeout_seconds=0.2)
        mgr = InferenceServerManager(cfg)
        with mock.patch.object(mgr, "_probe_health", mock.AsyncMock(return_value=False)):
            with pytest.raises(InferenceServerError):
                await mgr.start()

    async def test_health_check_after_start(self):
        cfg = _config(server_binary=None, ready_timeout_seconds=1.0)
        mgr = InferenceServerManager(cfg)
        with mock.patch.object(mgr, "_probe_health", mock.AsyncMock(return_value=True)):
            await mgr.start()
            assert await mgr.health_check() is True
            mgr._probe_health.return_value = False  # type: ignore[attr-defined]
            assert await mgr.health_check() is False

    async def test_stop_is_safe_when_nothing_was_spawned(self):
        cfg = _config(server_binary=None)
        mgr = InferenceServerManager(cfg)
        await mgr.stop()  # should not raise


@pytest.mark.asyncio
class TestSpawnMode:
    """When server_binary is set we spawn and supervise a subprocess."""

    async def test_missing_binary_raises(self, tmp_path):
        missing = tmp_path / "does_not_exist"
        cfg = _config(server_binary=missing, ready_timeout_seconds=0.1)
        mgr = InferenceServerManager(cfg)
        with pytest.raises(InferenceServerError):
            await mgr.start()

    async def test_spawn_failure_is_wrapped(self, tmp_path):
        binary = tmp_path / "fake_server"
        binary.write_text("#!/bin/sh\nexit 0\n")
        binary.chmod(0o755)

        cfg = _config(server_binary=binary, ready_timeout_seconds=0.1)
        mgr = InferenceServerManager(cfg)

        async def boom(*_args, **_kwargs):
            raise OSError("exec fail")

        with mock.patch("asyncio.create_subprocess_exec", side_effect=boom):
            with pytest.raises(InferenceServerError):
                await mgr.start()

    async def test_build_argv_passes_host_port_and_model(self, tmp_path):
        binary = tmp_path / "srv"
        binary.write_text("#!/bin/sh\n")
        binary.chmod(0o755)
        model_path = tmp_path / "model.bin"
        cfg = _config(
            server_binary=binary,
            model_path=model_path,
            host="127.0.0.1",
            port=12345,
            server_extra_args=["--threads", "4"],
        )
        mgr = InferenceServerManager(cfg)
        argv = mgr._build_argv(binary)
        assert argv[0] == str(binary)
        assert "--host" in argv and "127.0.0.1" in argv
        assert "--port" in argv and "12345" in argv
        assert "--model" in argv and str(model_path) in argv
        assert argv[-2:] == ["--threads", "4"]

    async def test_process_death_during_startup_raises(self, tmp_path):
        binary = tmp_path / "srv"
        binary.write_text("#!/bin/sh\n")
        binary.chmod(0o755)

        fake_process = mock.MagicMock()
        fake_process.returncode = 42
        fake_process.pid = 1234

        async def fake_exec(*_args, **_kwargs):
            return fake_process

        cfg = _config(server_binary=binary, ready_timeout_seconds=0.5)
        mgr = InferenceServerManager(cfg)
        with mock.patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
            with mock.patch.object(mgr, "_probe_health", mock.AsyncMock(return_value=False)):
                with pytest.raises(InferenceServerError):
                    await mgr.start()
        assert mgr.last_exit_code == 42

    async def test_stop_sends_sigterm_and_reaps(self, tmp_path):
        binary = tmp_path / "srv"
        binary.write_text("#!/bin/sh\n")
        binary.chmod(0o755)

        fake_process = mock.MagicMock()
        fake_process.returncode = None
        fake_process.pid = 5678

        # Simulate "process exits after SIGTERM": await wait() flips
        # returncode to 0. Setting returncode before stop() would short-
        # circuit the already-exited path in InferenceServerManager.stop()
        # and skip the SIGTERM we're asserting on.
        async def _graceful_wait() -> int:
            fake_process.returncode = 0
            return 0

        fake_process.wait = mock.AsyncMock(side_effect=_graceful_wait)
        fake_process.send_signal = mock.MagicMock()

        async def fake_exec(*_args, **_kwargs):
            return fake_process

        cfg = _config(server_binary=binary, ready_timeout_seconds=0.5)
        mgr = InferenceServerManager(cfg)
        with mock.patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
            with mock.patch.object(mgr, "_probe_health", mock.AsyncMock(return_value=True)):
                await mgr.start()
        await mgr.stop()
        fake_process.send_signal.assert_called_once_with(signal.SIGTERM)
        fake_process.wait.assert_awaited()
        assert mgr.last_exit_code == 0


@pytest.mark.asyncio
class TestHealthCheck:
    async def test_health_check_false_when_owned_process_exited(self, tmp_path):
        binary = tmp_path / "srv"
        binary.write_text("#!/bin/sh\n")
        binary.chmod(0o755)

        fake_process = mock.MagicMock()
        fake_process.returncode = 1

        cfg = _config(server_binary=binary)
        mgr = InferenceServerManager(cfg)
        mgr._process = fake_process  # type: ignore[assignment]
        mgr._owned_process = True

        assert await mgr.health_check() is False
        assert mgr.last_exit_code == 1

    async def test_startup_timeout_stops_spawned_subprocess(self, tmp_path):
        binary = tmp_path / "srv"
        binary.write_text("#!/bin/sh\n")
        binary.chmod(0o755)

        fake_process = mock.MagicMock()
        fake_process.returncode = None
        fake_process.pid = 9999

        async def _graceful_wait() -> int:
            fake_process.returncode = -signal.SIGTERM
            return -signal.SIGTERM

        fake_process.wait = mock.AsyncMock(side_effect=_graceful_wait)
        fake_process.send_signal = mock.MagicMock()

        async def fake_exec(*_args, **_kwargs):
            return fake_process

        cfg = _config(server_binary=binary, ready_timeout_seconds=0.1)
        mgr = InferenceServerManager(cfg)
        with mock.patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
            with mock.patch.object(mgr, "_probe_health", mock.AsyncMock(return_value=False)):
                with pytest.raises(InferenceServerError):
                    await mgr.start()

        fake_process.send_signal.assert_called_once_with(signal.SIGTERM)
        fake_process.wait.assert_awaited()
        assert mgr.process_id is None

    async def test_stdout_stream_is_drained_and_reported_on_startup_failure(self, tmp_path):
        binary = tmp_path / "srv"
        binary.write_text("#!/bin/sh\n")
        binary.chmod(0o755)

        stream = asyncio.StreamReader()
        stream.feed_data(b"loading model...\nfatal: invalid model header\n")
        stream.feed_eof()

        fake_process = mock.MagicMock()
        fake_process.returncode = 1
        fake_process.pid = 4321
        fake_process.stdout = stream

        async def fake_exec(*_args, **_kwargs):
            return fake_process

        cfg = _config(server_binary=binary, ready_timeout_seconds=0.5)
        mgr = InferenceServerManager(cfg)
        with mock.patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
            # Yield once so the stdout drain task reads the buffered lines before exit check.
            original_wait = mgr._wait_until_ready

            async def _wait_after_yield() -> None:
                await asyncio.sleep(0.02)
                await original_wait()

            with mock.patch.object(mgr, "_wait_until_ready", side_effect=_wait_after_yield):
                with pytest.raises(InferenceServerError, match="invalid model header"):
                    await mgr.start()

        assert mgr._stdout_task is None  # type: ignore[attr-defined]

    async def test_real_subprocess_heavy_output_does_not_deadlock(self):
        # Emit 128 KB (>64 KB OS pipe buffer) to stdout/stderr to verify draining prevents blocking.
        script = "import sys; sys.stdout.write(('x' * 1024 + '\\n') * 128); sys.stdout.flush()"
        cfg = _config(
            server_binary=None,
            ready_timeout_seconds=2.0,
        )
        mgr = InferenceServerManager(cfg)
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            stdin=asyncio.subprocess.DEVNULL,
        )
        mgr._process = proc  # type: ignore[attr-defined]
        mgr._owned_process = True  # type: ignore[attr-defined]
        assert isinstance(proc.stdout, asyncio.StreamReader)
        mgr._stdout_task = asyncio.create_task(mgr._drain_stdout(proc.stdout))  # type: ignore[attr-defined]
        try:
            rc = await asyncio.wait_for(proc.wait(), timeout=5.0)
            assert rc == 0
        finally:
            await mgr.stop()


class TestSyncHealthProbe:
    def test_sync_probe_health_accepts_only_2xx(self):
        from urllib.error import HTTPError

        class _Resp:
            def __init__(self, status: int) -> None:
                self.status = status

            def __enter__(self) -> _Resp:
                return self

            def __exit__(self, *_args: object) -> None:
                return None

        with mock.patch("urllib.request.urlopen", return_value=_Resp(200)):
            ok, err = InferenceServerManager._sync_probe_health("http://127.0.0.1:8091/health", 1.0)
            assert ok is True
            assert err is None

        with mock.patch("urllib.request.urlopen", return_value=_Resp(404)):
            ok, err = InferenceServerManager._sync_probe_health("http://127.0.0.1:8091/health", 1.0)
            assert ok is False
            assert err is not None and "404" in err

        http_err = HTTPError("http://127.0.0.1:8091/health", 503, "Service Unavailable", hdrs=None, fp=None)  # type: ignore[arg-type]
        with mock.patch("urllib.request.urlopen", side_effect=http_err):
            ok, err = InferenceServerManager._sync_probe_health("http://127.0.0.1:8091/health", 1.0)
            assert ok is False
            assert err is not None and "503" in err
