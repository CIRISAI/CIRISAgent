"""
Lifecycle manager for a local OpenAI-compatible inference server.

The adapter runs the inference server *as part of the CIRIS runtime* so that
service health follows process health: if the binary crashes, the LLM bus
marks this provider unhealthy and falls back to a hosted LLM. If the binary
can't start (missing model, port in use, etc.) the adapter simply stays
unhealthy without tearing the whole runtime down.

The underlying binary is pluggable. Anything that speaks the OpenAI REST
surface on ``http://host:port/v1`` is fine: LiteRT-LM, llama.cpp's
``server``, Ollama, etc. The adapter only owns:

* spawning / terminating the subprocess
* polling the ``/health`` endpoint for readiness
* surfacing health and status for the LLM bus
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import signal
import subprocess
from pathlib import Path
from typing import List, Optional

from .config import MobileLocalLLMConfig

logger = logging.getLogger(__name__)


# Try to use httpx if available (it is already a transitive dependency on
# desktop + server), fall back to urllib so the adapter can still probe
# health on stripped-down Android builds.
try:  # pragma: no cover - import guard
    import httpx  # type: ignore[import-not-found]

    _HAVE_HTTPX = True
except ImportError:  # pragma: no cover - fallback path
    httpx = None  # type: ignore[assignment]
    _HAVE_HTTPX = False


class InferenceServerError(RuntimeError):
    """Raised when the local inference server cannot be managed."""


class InferenceServerManager:
    """Spawns and supervises the local inference server binary."""

    def __init__(self, config: MobileLocalLLMConfig) -> None:
        self._config = config
        self._process: Optional[asyncio.subprocess.Process] = None
        self._owned_process = False  # False when we attached to a pre-existing server
        self._last_exit_code: Optional[int] = None
        self._started = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def owns_process(self) -> bool:
        """True if we spawned the server ourselves (vs. attached to one)."""
        return self._owned_process

    @property
    def process_id(self) -> Optional[int]:
        """PID of the managed inference server, or None."""
        return self._process.pid if self._process else None

    @property
    def last_exit_code(self) -> Optional[int]:
        """Exit code from the last terminated inference server process."""
        return self._last_exit_code

    @property
    def is_running(self) -> bool:
        """True if our managed process is still alive."""
        if self._process is None:
            return not self._owned_process and self._started
        return self._process.returncode is None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start or attach to the local inference server.

        If ``config.server_binary`` is set we spawn the subprocess. If not,
        we assume the caller (or the Android app) has already started the
        server and we simply probe it for readiness. Either way we block
        until the ``/health`` endpoint responds successfully or
        ``ready_timeout_seconds`` elapses.
        """
        if self._started:
            logger.debug("Inference server already started; ignoring duplicate start()")
            return

        if self._config.server_binary is not None:
            await self._spawn_subprocess()
        else:
            logger.info(
                "No server_binary configured; attaching to existing inference server at %s",
                self._config.base_url(),
            )
            self._owned_process = False

        await self._wait_until_ready()
        self._started = True
        logger.info("Local inference server ready at %s", self._config.base_url())

    async def stop(self) -> None:
        """Stop the managed process gracefully, with a forced kill fallback."""
        self._started = False
        if self._process is None:
            return

        if self._process.returncode is not None:
            self._last_exit_code = self._process.returncode
            self._process = None
            return

        logger.info("Stopping local inference server (pid=%s)", self._process.pid)
        try:
            self._process.send_signal(signal.SIGTERM)
        except ProcessLookupError:
            self._process = None
            return

        try:
            await asyncio.wait_for(self._process.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning("Inference server did not exit in 10s; killing pid=%s", self._process.pid)
            try:
                self._process.kill()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.error("Inference server pid=%s did not die after SIGKILL", self._process.pid)

        self._last_exit_code = self._process.returncode
        self._process = None

    async def health_check(self) -> bool:
        """Return True if the server responds on /health within a short timeout."""
        # If we own the process and it has exited, we are definitely unhealthy.
        if self._owned_process and self._process is not None and self._process.returncode is not None:
            self._last_exit_code = self._process.returncode
            return False
        return await self._probe_health(timeout=2.0)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _spawn_subprocess(self) -> None:
        binary = self._config.server_binary
        assert binary is not None  # guarded by caller
        if not self._binary_available(binary):
            raise InferenceServerError(
                f"Inference server binary not found or not executable: {binary}"
            )

        argv = self._build_argv(binary)
        logger.info("Spawning local inference server: %s", " ".join(argv))
        try:
            self._process = await asyncio.create_subprocess_exec(
                *argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
            )
        except (OSError, FileNotFoundError) as exc:
            raise InferenceServerError(f"Failed to spawn inference server: {exc}") from exc
        self._owned_process = True

    def _build_argv(self, binary: Path) -> List[str]:
        argv: List[str] = [str(binary)]

        # Common args most OpenAI-compatible inference servers accept.
        # Unknown flags on a specific binary will be rejected at spawn time,
        # which surfaces clearly in the logs.
        argv += ["--host", self._config.host, "--port", str(self._config.port)]
        if self._config.model_path is not None:
            argv += ["--model", str(self._config.model_path)]
        argv += list(self._config.server_extra_args)
        return argv

    @staticmethod
    def _binary_available(binary: Path) -> bool:
        if binary.is_file():
            return True
        # Support bare binary names that resolve via PATH.
        return shutil.which(str(binary)) is not None

    async def _wait_until_ready(self) -> None:
        timeout = self._config.ready_timeout_seconds
        deadline = asyncio.get_event_loop().time() + timeout
        interval = 0.5
        last_error: Optional[str] = None
        while True:
            if self._owned_process and self._process is not None and self._process.returncode is not None:
                self._last_exit_code = self._process.returncode
                raise InferenceServerError(
                    f"Inference server exited during startup (code={self._process.returncode})"
                )
            if await self._probe_health(timeout=1.5):
                return
            if asyncio.get_event_loop().time() >= deadline:
                raise InferenceServerError(
                    f"Inference server did not become ready within {timeout:.1f}s"
                    + (f": {last_error}" if last_error else "")
                )
            await asyncio.sleep(interval)

    async def _probe_health(self, *, timeout: float) -> bool:
        url = self._config.health_url()
        if _HAVE_HTTPX:
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:  # type: ignore[union-attr]
                    response = await client.get(url)
                    return 200 <= response.status_code < 500
            except Exception as exc:  # pragma: no cover - network variability
                logger.debug("httpx health probe failed for %s: %s", url, exc)
                return False
        return await asyncio.to_thread(self._sync_probe_health, url, timeout)

    @staticmethod
    def _sync_probe_health(url: str, timeout: float) -> bool:
        from urllib.error import URLError
        from urllib.request import urlopen

        try:
            with urlopen(url, timeout=timeout) as response:  # noqa: S310 - loopback only
                status: int = response.status
                return 200 <= status < 500
        except URLError:
            return False
        except Exception:  # pragma: no cover - best-effort probe
            return False


__all__ = ["InferenceServerManager", "InferenceServerError"]
