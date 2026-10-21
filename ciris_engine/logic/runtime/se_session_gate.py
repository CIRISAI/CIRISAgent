"""macOS Secure Enclave session gate — deterministic keystore backend at boot.

RCA (CIRISServer#380 "TWO FEDERATION IDENTITIES IN ONE NODE" on macOS)
---------------------------------------------------------------------
The node's ONE federation identity is sealed in a keystore that is opened more
than once during boot — first by the persist ``Engine`` (see
``persistence/db/core.py``), then by the node's compose inside
``ciris_server.serve_with_python_adapter``. On macOS the ``ciris_keyring``
factory selects the *Secure Enclave* signer. SE key operations return
``OSStatus -25308`` (``errSecInteractionNotAllowed``) when there is a console
login session whose screen is **locked** — the SE cannot be reached without an
active, attended user session. Critically this is **intermittent** across the
handful of keystore opens in one boot: one open lands on SE while the next falls
back to software. The two opens then seal the identity as *different* keys, and
the substrate's one-identity boot gate refuses to start:

    RuntimeError: TWO FEDERATION IDENTITIES IN ONE NODE — refusing to start.
    ... The persist Engine and this process sign as DIFFERENT keys ...

It "works everywhere else" because Linux/CI has no Secure Enclave (software-only,
deterministic) and iOS reaches its Secure Enclave reliably (foreground app on an
unlocked device). Only macOS with a **locked** console session flip-flops.

The gate
--------
Make the backend deterministic by refusing to proceed while SE is *present but
flaky*. The decision is made purely from the macOS console-session state, so it
needs no fragile "is this blob SE-backed?" probe:

  * **no console session** (headless daemon / ssh / CI): SE is consistently
    unavailable → every open falls back to software → deterministic → PROCEED.
  * **console session, screen unlocked**: SE consistently reachable → PROCEED.
  * **console session, screen LOCKED**: SE intermittent → the divergence window
    → WAIT until the screen is unlocked (an active user session can reach the
    Secure Enclave), surfacing status on the CLI and to the UI, then PROCEED.

This covers all three required scenarios: headless, headed (uses SE), and
"headed first (sealed with SE) then head goes away" — the last now waits for the
session to come back instead of minting a divergent second identity.

Non-macOS platforms (Linux / iOS / Android / Windows) are a no-op.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from enum import Enum
from typing import Any, Callable, Dict, Final, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# One place for the exact operator-facing wording (CLI console + UI console
# parser both latch this line). Keep the "Secure Enclave" + "active user session"
# vocabulary stable — clients may pattern-match it.
WAITING_MESSAGE = (
    "Waiting for an active user session to access key material in the Secure "
    "Enclave (the screen is locked; log in / unlock to continue)"
)

# How often to re-check the session and re-emit the waiting status.
_POLL_SECS = 2.0

# Default upper bound on the locked-session wait. This MUST stay under the
# desktop launcher's server health-wait (`_wait_for_server_health`, 60s in
# ciris_engine/cli.py) — with the ~5s post-gate boot on top — so that:
#   * an attended user who locked mid-boot has time to come back and unlock, but
#   * an UNATTENDED locked host (e.g. a Mac mini logged-in-but-locked overnight)
#     does not wait forever. On expiry the gate returns LOCKED and the caller
#     proceeds, preserving today's intermittent-boot behavior instead of turning
#     it into a permanent hang whose only signal is a log line every 2s, and
#     keeping the "screen is locked" status — not a generic launcher timeout —
#     as the thing the user sees.
_DEFAULT_WAIT_TIMEOUT_SECS = 45.0
_TIMEOUT_ENV = "CIRIS_SE_SESSION_GATE_TIMEOUT_SECONDS"

# Sentinel so callers can pass timeout_secs=None ("wait indefinitely") distinctly
# from "not supplied" (resolve the env-backed bounded default). A bare `object()`
# cannot type-check as a default for `Optional[float]`, so the sentinel gets its
# own type and joins the union — keeping all THREE states expressible.
class _EnvDefault:
    """Marker type for "caller did not supply a timeout"."""


_ENV_DEFAULT: Final[_EnvDefault] = _EnvDefault()


def _resolve_default_timeout() -> Optional[float]:
    """The bounded wait ceiling: ``CIRIS_SE_SESSION_GATE_TIMEOUT_SECONDS`` or the
    default. A value <= 0 opts into an indefinite wait (operator's explicit call)."""
    raw = os.environ.get(_TIMEOUT_ENV, "").strip()
    if not raw:
        return _DEFAULT_WAIT_TIMEOUT_SECS
    try:
        value = float(raw)
    except ValueError:
        logger.warning("%s=%r is not a number — using %.0fs", _TIMEOUT_ENV, raw, _DEFAULT_WAIT_TIMEOUT_SECS)
        return _DEFAULT_WAIT_TIMEOUT_SECS
    return value if value > 0 else None


class SESessionState(str, Enum):
    """Result of classifying the current macOS console session."""

    # SE is consistently reachable (unlocked, attended) — safe to use SE.
    REACHABLE = "reachable"
    # No console session at all — SE consistently unavailable, software-only is
    # deterministic, safe to proceed.
    HEADLESS = "headless"
    # A console session exists but its screen is locked — SE is intermittently
    # available, which is the two-identity divergence window. Must wait.
    LOCKED = "locked"
    # Not macOS, or state could not be determined — no-op / fail-open.
    NOT_APPLICABLE = "not_applicable"


def _is_macos_desktop() -> bool:
    """True on macOS proper, False on iOS (which reports darwin) and elsewhere."""
    if sys.platform != "darwin":
        return False
    # iOS also reports sys.platform == "darwin"; distinguish via the multiarch tag
    # the BeeWare/iOS CPython carries (same probe db/core.py uses for the stack fix).
    multiarch = getattr(getattr(sys, "implementation", None), "_multiarch", "") or ""
    return "iphoneos" not in multiarch.lower()


def _read_console_users() -> Optional[List[Dict[str, Any]]]:
    """Return the IOConsoleUsers array from IOKit, or None if unreadable.

    Uses ``ioreg -a`` (archived plist) + plistlib so there is no PyObjC/Quartz
    dependency and the parse is not regex-fragile across macOS versions.
    """
    import plistlib

    try:
        raw = subprocess.run(
            ["ioreg", "-n", "Root", "-d1", "-a"],
            capture_output=True,
            timeout=5,
        ).stdout
        if not raw:
            return None
        root = plistlib.loads(raw)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        logger.debug("SE gate: could not read IOConsoleUsers (%s)", exc)
        return None

    def _find(node: object) -> Optional[List[Dict[str, Any]]]:
        if isinstance(node, dict):
            if "IOConsoleUsers" in node:
                users = node["IOConsoleUsers"]
                return users if isinstance(users, list) else None
            for value in node.values():
                found = _find(value)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for value in node:
                found = _find(value)
                if found is not None:
                    return found
        return None

    return _find(root)


def _classify(users: Optional[List[Dict[str, Any]]]) -> Tuple[bool, bool]:
    """(on_console, screen_locked) for the user that actually holds the console.

    on-console and screen-locked are a PER-USER property. Two independent any()
    calls over the whole array mix users: with fast user switching (user A
    attended + unlocked on the console, user B switched out + locked), a split
    any() would report on_console=True AND screen_locked=True and the gate would
    wait despite an attended, unlocked session. Read both facts off the single
    user holding the console.
    """
    for user in users or []:
        if isinstance(user, dict) and user.get("kCGSSessionOnConsoleKey"):
            return (True, bool(user.get("CGSSessionScreenIsLocked")))
    return (False, False)


def secure_enclave_session_state() -> SESessionState:
    """Classify the current session for keystore-backend determinism."""
    if not _is_macos_desktop():
        return SESessionState.NOT_APPLICABLE

    users = _read_console_users()
    if users is None:
        # Fail-open: if we cannot read the session state we must not hang the
        # boot forever. Treat as reachable and let the substrate decide.
        return SESessionState.NOT_APPLICABLE

    on_console, screen_locked = _classify(users)
    if not on_console:
        return SESessionState.HEADLESS
    if screen_locked:
        return SESessionState.LOCKED
    return SESessionState.REACHABLE


def await_secure_enclave_session(
    status_cb: Optional[Callable[[str], None]] = None,
    poll_secs: float = _POLL_SECS,
    timeout_secs: Union[float, None, _EnvDefault] = _ENV_DEFAULT,
    _sleep: Callable[[float], None] = time.sleep,
) -> SESessionState:
    """Block until the Secure Enclave can be reached deterministically.

    Returns the state that unblocked the gate (REACHABLE / HEADLESS /
    NOT_APPLICABLE). While the console session is LOCKED it emits
    ``WAITING_MESSAGE`` on the CLI (print + logger) and via ``status_cb`` (for
    the UI) every ``poll_secs`` until the screen is unlocked.

    ``timeout_secs`` bounds the locked wait so an unattended locked host does not
    hang forever; on expiry it logs and returns LOCKED so the caller proceeds
    (preserving today's intermittent-boot behavior). Unset resolves the
    env-backed default (``_resolve_default_timeout``); pass ``None`` explicitly to
    wait indefinitely.
    """
    if isinstance(timeout_secs, _EnvDefault):
        timeout_secs = _resolve_default_timeout()

    state = secure_enclave_session_state()
    if state in (SESessionState.REACHABLE, SESessionState.HEADLESS, SESessionState.NOT_APPLICABLE):
        if state == SESessionState.HEADLESS:
            logger.info(
                "SE gate: no console session — Secure Enclave unavailable, "
                "software keystore is deterministic; proceeding headless."
            )
        return state

    # LOCKED: SE is present but flaky. Wait for an active/unlocked session.
    waited = 0.0
    first = True
    while True:
        line = WAITING_MESSAGE if first else f"{WAITING_MESSAGE} [{int(waited)}s]"
        # CLI console (also latched by the KMP UI stdout parser) + structured log.
        print(f"[SE-GATE] {line}", flush=True)
        logger.warning("SE gate: %s", line)
        if status_cb is not None:
            try:
                status_cb(WAITING_MESSAGE)
            except Exception as exc:  # noqa: BLE001 - status surfacing must never break boot
                logger.debug("SE gate: status_cb raised (non-fatal): %s", exc)
        first = False

        _sleep(poll_secs)
        waited += poll_secs

        state = secure_enclave_session_state()
        if state != SESessionState.LOCKED:
            logger.info(
                "SE gate: session is now '%s' — Secure Enclave reachable; proceeding.",
                state.value,
            )
            print("[SE-GATE] active session detected — resuming startup", flush=True)
            return state

        if timeout_secs is not None and waited >= timeout_secs:
            logger.warning(
                "SE gate: still locked after %.0fs (timeout) — proceeding anyway; "
                "the node may refuse with TWO FEDERATION IDENTITIES until an "
                "active session is available.",
                waited,
            )
            return SESessionState.LOCKED
