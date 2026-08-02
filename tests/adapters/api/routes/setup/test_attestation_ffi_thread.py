"""The attestation FFI handlers spawn their daemon worker thread and degrade
gracefully when the FFI is unavailable (#956 coverage + behaviour).

Each of the three CIRISVerify attestation handlers runs its FFI call on an
8MB-stack `threading.Thread(target=_inner, daemon=True)` (#956 — the thread must
be daemon so an FFI that blocks cannot wedge interpreter shutdown). The existing
route tests mock at a level that returns before the thread is reached, which is
why coverage of those exact lines was 0%. These call the handlers directly with
a verifier whose `_lib` is None: `_inner` takes the "FFI not available" branch
and returns fast, but the daemon thread is still started and joined — exercising
the daemonized path and asserting the handler surfaces a clean 502 rather than
hanging.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

import ciris_engine.logic.adapters.api.routes.setup.attestation as attestation


def _verifier_without_lib() -> MagicMock:
    """A verifier whose FFI library is absent — `_inner` returns immediately
    with an error, after the daemon thread has been started and joined."""
    v = MagicMock()
    v._lib = None
    v._handle = None
    return v


@pytest.fixture(autouse=True)
def _stub_verifier(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(attestation, "_get_verifier", lambda request: _verifier_without_lib())


def _run(coro):  # type: ignore[no-untyped-def]
    # asyncio.run() closes the loop it creates, which shuts down that loop's
    # default ThreadPoolExecutor (the one run_in_executor(None, ...) uses) — so
    # these tests do not leave a lingering non-daemon executor worker behind.
    return asyncio.run(coro)


# Each entry invokes one handler. verify_app_attest takes a body, but the
# FFI-unavailable branch returns before reading it, so a mock stands in.
_FFI_HANDLERS = {
    "app_attest_nonce": lambda: attestation.get_app_attest_nonce(MagicMock()),
    "play_integrity_nonce": lambda: attestation.get_play_integrity_nonce(MagicMock()),
    "verify_app_attest": lambda: attestation.verify_app_attest(MagicMock(), MagicMock()),
}


class TestAttestationFfiThreadPath:
    @pytest.mark.parametrize("handler", _FFI_HANDLERS.values(), ids=list(_FFI_HANDLERS))
    def test_handler_spawns_daemon_ffi_thread_and_502s(self, handler) -> None:  # type: ignore[no-untyped-def]
        # Executes the daemonized FFI-thread path (#956) and asserts the
        # FFI-unavailable case surfaces a clean 502 rather than hanging.
        with pytest.raises(HTTPException) as exc:
            _run(handler())
        assert exc.value.status_code == 502

    def test_verify_status_and_nonce_paths_do_not_leave_a_nondaemon_ffi_thread(self) -> None:
        """The #956 property, observed at runtime: after the handler returns,
        the FFI worker it spawned is not lingering as a non-daemon thread.

        (The daemon flag itself is pinned statically in
        test_no_nondaemon_threads.py; this confirms the running handler honours
        it — the FFI thread is daemon, so it does not survive as a straggler.)
        """
        import threading

        before = {t.ident for t in threading.enumerate()}
        with pytest.raises(HTTPException):
            _run(attestation.get_play_integrity_nonce(MagicMock()))
        leaked = [
            t
            for t in threading.enumerate()
            if t.ident not in before and t.is_alive() and not t.daemon and t.name.startswith(("Thread-", "ciris"))
        ]
        assert not leaked, f"non-daemon FFI thread leaked past the call: {leaked}"
