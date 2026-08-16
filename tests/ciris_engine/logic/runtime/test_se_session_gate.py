"""Tests for the macOS Secure Enclave session gate (CIRISServer#380).

The gate makes the federation keystore backend deterministic at boot so the
persist Engine and the node compose cannot seal two different keys (which the
substrate refuses as "TWO FEDERATION IDENTITIES IN ONE NODE"). The decision is
derived purely from the macOS console-session state, so it is fully unit-testable
by driving the classifier.
"""

from __future__ import annotations

import pytest

from ciris_engine.logic.runtime import se_session_gate as gate
from ciris_engine.logic.runtime.se_session_gate import (
    SESessionState,
    await_secure_enclave_session,
    secure_enclave_session_state,
)


@pytest.fixture
def force_macos(monkeypatch):
    """Pretend we are on macOS desktop regardless of the test host."""
    monkeypatch.setattr(gate, "_is_macos_desktop", lambda: True)


def _users(on_console: bool, locked: bool):
    return [
        {
            "kCGSSessionOnConsoleKey": on_console,
            "CGSSessionScreenIsLocked": locked,
        }
    ]


@pytest.mark.parametrize(
    "on_console,locked,expected",
    [
        (True, False, SESessionState.REACHABLE),  # attended, unlocked → use SE
        (True, True, SESessionState.LOCKED),  # attended but locked → divergence window
        (False, False, SESessionState.HEADLESS),  # no session → software deterministic
        (False, True, SESessionState.HEADLESS),  # no console user wins over stray lock flag
    ],
)
def test_classify_states(monkeypatch, force_macos, on_console, locked, expected):
    monkeypatch.setattr(gate, "_read_console_users", lambda: _users(on_console, locked))
    assert secure_enclave_session_state() is expected


def test_non_macos_is_noop(monkeypatch):
    monkeypatch.setattr(gate, "_is_macos_desktop", lambda: False)
    assert secure_enclave_session_state() is SESessionState.NOT_APPLICABLE
    # And the awaiter returns immediately without touching the session reader.
    assert await_secure_enclave_session(_sleep=lambda _s: None) is SESessionState.NOT_APPLICABLE


def test_unreadable_session_fails_open(monkeypatch, force_macos):
    """If IOConsoleUsers can't be read we must not hang the boot forever."""
    monkeypatch.setattr(gate, "_read_console_users", lambda: None)
    assert secure_enclave_session_state() is SESessionState.NOT_APPLICABLE


def test_reachable_and_headless_do_not_wait(monkeypatch, force_macos):
    for on_console, locked, expected in (
        (True, False, SESessionState.REACHABLE),
        (False, False, SESessionState.HEADLESS),
    ):
        monkeypatch.setattr(gate, "_read_console_users", lambda oc=on_console, lk=locked: _users(oc, lk))

        def _no_sleep(_s):  # pragma: no cover - must never be called
            raise AssertionError("gate slept on a non-locked session")

        assert await_secure_enclave_session(_sleep=_no_sleep) is expected


def test_locked_waits_then_resumes_on_unlock(monkeypatch, force_macos):
    """LOCKED blocks and emits status until the screen unlocks, then proceeds."""
    # Locked for the first two polls, then unlocked.
    seq = [_users(True, True), _users(True, True), _users(True, False)]
    calls = {"n": 0}

    def _reader():
        idx = min(calls["n"], len(seq) - 1)
        return seq[idx]

    def _sleep(_s):
        calls["n"] += 1

    monkeypatch.setattr(gate, "_read_console_users", _reader)

    surfaced = []
    result = await_secure_enclave_session(status_cb=surfaced.append, poll_secs=0.0, _sleep=_sleep)

    assert result is SESessionState.REACHABLE
    assert calls["n"] >= 2  # waited at least until the unlock
    assert surfaced, "status callback should have been invoked while waiting"
    assert all("Secure Enclave" in m for m in surfaced)


def test_locked_timeout_proceeds(monkeypatch, force_macos):
    """A stuck-locked session eventually returns LOCKED (safety valve), not hang."""
    monkeypatch.setattr(gate, "_read_console_users", lambda: _users(True, True))

    def _sleep(_s):
        pass

    result = await_secure_enclave_session(poll_secs=1.0, timeout_secs=3.0, _sleep=_sleep)
    assert result is SESessionState.LOCKED


def test_fast_user_switching_reads_the_console_user(monkeypatch, force_macos):
    """on-console + locked are per-user: the active console user's state wins.

    Regression for the split-any() bug: user A holds the console unlocked while a
    switched-out user B is locked. The gate must see REACHABLE, not LOCKED.
    """
    active_unlocked_switched_locked = [
        {"kCGSSessionOnConsoleKey": True, "CGSSessionScreenIsLocked": False},  # active
        {"kCGSSessionOnConsoleKey": False, "CGSSessionScreenIsLocked": True},  # switched out
    ]
    monkeypatch.setattr(gate, "_read_console_users", lambda: active_unlocked_switched_locked)
    assert secure_enclave_session_state() is SESessionState.REACHABLE

    # And the mirror: the console user IS locked; a switched-out user being
    # unlocked must not mask it.
    active_locked_switched_unlocked = [
        {"kCGSSessionOnConsoleKey": True, "CGSSessionScreenIsLocked": True},  # active
        {"kCGSSessionOnConsoleKey": False, "CGSSessionScreenIsLocked": False},  # switched out
    ]
    monkeypatch.setattr(gate, "_read_console_users", lambda: active_locked_switched_unlocked)
    assert secure_enclave_session_state() is SESessionState.LOCKED


def test_default_timeout_env_parsing(monkeypatch):
    monkeypatch.delenv(gate._TIMEOUT_ENV, raising=False)
    assert gate._resolve_default_timeout() == gate._DEFAULT_WAIT_TIMEOUT_SECS

    monkeypatch.setenv(gate._TIMEOUT_ENV, "90")
    assert gate._resolve_default_timeout() == 90.0

    monkeypatch.setenv(gate._TIMEOUT_ENV, "0")  # <=0 opts into indefinite
    assert gate._resolve_default_timeout() is None

    monkeypatch.setenv(gate._TIMEOUT_ENV, "not-a-number")
    assert gate._resolve_default_timeout() == gate._DEFAULT_WAIT_TIMEOUT_SECS


def test_bare_call_is_bounded_not_infinite(monkeypatch, force_macos):
    """The bare call site (no timeout arg) must be bounded via the env default,
    so a permanently-locked unattended host proceeds instead of hanging forever."""
    monkeypatch.setenv(gate._TIMEOUT_ENV, "1")  # tiny bound for the test
    monkeypatch.setattr(gate, "_read_console_users", lambda: _users(True, True))
    result = await_secure_enclave_session(poll_secs=1.0, _sleep=lambda _s: None)
    assert result is SESessionState.LOCKED
