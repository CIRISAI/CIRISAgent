"""Tests for the inference server lifecycle manager."""

from __future__ import annotations

import signal
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
