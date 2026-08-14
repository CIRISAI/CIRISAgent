"""CIRISVerify thread runner for attestation.

This module handles running CIRISVerify on a separate thread with a larger
stack size, as required by Rust Tokio compatibility.
"""

import asyncio
import logging
import os
import sys
import threading
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Callable, Dict, Optional

from .hashes import load_python_hashes
from .platform import is_mobile
from .tree_verify import get_default_agent_version, run_tree_verify

# Python 3.10 compatibility: asyncio.timeout was added in Python 3.11
if sys.version_info >= (3, 11):
    _async_timeout = asyncio.timeout
else:

    @asynccontextmanager
    async def _async_timeout(delay: float) -> AsyncGenerator[None, None]:
        """Python 3.10 compatible timeout context manager."""
        loop = asyncio.get_event_loop()
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("No current task")

        timed_out = False

        def timeout_callback() -> None:
            nonlocal timed_out
            timed_out = True
            task.cancel()  # type: ignore[union-attr]

        handle = loop.call_later(delay, timeout_callback)
        try:
            yield
        except asyncio.CancelledError:  # noqa: ASYNC910  # NOSONAR
            # Cleanup: cancel the timeout callback
            handle.cancel()
            # Convert our own timeout-triggered cancellation to TimeoutError
            # (matches Python 3.11 asyncio.timeout behavior)
            if timed_out:
                raise asyncio.TimeoutError() from None
            # External cancellation - must re-raise per asyncio contract
            raise  # Re-raised for external cancellations (not our timeout)
        else:
            handle.cancel()


from .paths import find_audit_db_path, get_agent_root, get_ed25519_fingerprint
from .types import PythonHashesWrapper, VerifyThreadResult

logger = logging.getLogger(__name__)

# Absolute backstop for a wedged verifier thread. This is NOT the contract —
# see attestation_deadline_seconds() for that. It exists only so a thread that
# never returns cannot leak forever.
ATTESTATION_TIMEOUT = 90


def startup_attestation_budget_seconds() -> float:
    """The attestation contract, read at CALL time.

    An attestation is always produced within this many seconds. Not "usually",
    and not "unless the build is unregistered" — if it takes longer, that is a
    bug in the verifier, and the caller gets a degraded attestation rather than
    a hang.

    Read at call time on purpose. The equivalent constant in service.py is
    evaluated at import, which silently discarded the override: mobile_main sets
    CIRIS_STARTUP_ATTESTATION_BUDGET_SECONDS=45 at startup, but by then
    authentication.service had already been imported and frozen the value at
    20.0. The Android log proves it — "exceeded the 20s budget" on a runtime
    that had asked for 45.
    """
    raw = os.environ.get("CIRIS_STARTUP_ATTESTATION_BUDGET_SECONDS", "").strip()
    if raw:
        try:
            return max(1.0, float(raw))
        except ValueError:
            pass
    return 20.0


def attestation_deadline_seconds() -> float:
    """How long to wait for the verifier before degrading.

    The budget bounds the wait; ATTESTATION_TIMEOUT is only a ceiling for the
    case where someone sets an absurd budget. Waiting past the budget cannot
    help: the caller has already been told the run is a bug, and the result
    delivered late is the same degraded `level=0, binary=FAIL` the timeout path
    produces anyway.

    This is the whole defect on Android. The verifier blocked on an HTTPS
    source-availability check with no network (`https_ok=false`), the 90s
    backstop was what actually bounded it, and the processor gate arrived 65s
    in to find the budget long gone. The runtime never left the Setup cognitive
    state, so the agent sat in front of a typed question and never answered it.
    CIRIS_ATTESTATION_SKIP_REGISTRY did not save us: it removes the registry
    fetch (CIRISVerify#212), and this was a different network call. Bounding
    every path by the budget is what makes the promise hold regardless of which
    call is slow.
    """
    return min(float(ATTESTATION_TIMEOUT), startup_attestation_budget_seconds())


def _get_verifier_version(verifier: Any) -> str:
    """Get CIRISVerify version.

    Args:
        verifier: CIRISVerify verifier instance

    Returns:
        Version string or "unknown"
    """
    try:
        version = getattr(verifier, "version", None)
        if callable(version):
            version = version()
        if version is None:
            import ciris_adapters.ciris_verify as ciris_verify

            version = getattr(ciris_verify, "__version__", "unknown")
        return str(version) if version else "unknown"
    except Exception as e:
        logger.warning(f"[attestation] Version check failed: {e}")
        return "unknown"


def _run_attestation_sync(
    verifier: Any,
    spot_check_count: int,
    attestation_mode: str,
    python_hashes: Optional[PythonHashesWrapper],
    agent_version: Optional[str],
    agent_root: str,
    key_fingerprint: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Run synchronous attestation via CIRISVerify.

    Args:
        verifier: CIRISVerify verifier instance
        spot_check_count: Number of files to spot check (0 for full)
        attestation_mode: "full" or "partial"
        python_hashes: Python module hashes wrapper
        agent_version: Agent version string
        agent_root: Agent root directory path
        key_fingerprint: Ed25519 key fingerprint

    Returns:
        Attestation result dict or None
    """
    if not hasattr(verifier, "run_attestation_sync"):
        return None

    # Generate a random challenge nonce (required by CIRISVerify)
    challenge = os.urandom(32)

    # WORKAROUND (CIRISVerify#212): verify v10.5.0's "Agent build record fetch"
    # blocks ~27s on an HTTPS timeout when the build is NOT in the registry
    # (every dev/QA/unregistered build), exceeding the startup-attestation
    # budget and bricking the processor. Skipping the registry step degrades to
    # exactly the state an unregistered build already reaches (L4 registry check
    # skipped) — just FAST instead of after a 27s hang. Opt-in via
    # CIRIS_ATTESTATION_SKIP_REGISTRY so production (registered builds) keeps the
    # full registry-checked attestation by default. run_attestation_sync accepts
    # skip_registry on verify >=10.x; guarded with a fallback for FFIs that don't
    # (avoids TypeError on an older bundled verify).
    skip_registry = os.environ.get("CIRIS_ATTESTATION_SKIP_REGISTRY", "").strip().lower() in ("1", "true", "yes", "on")

    logger.info(
        f"[attestation] Calling run_attestation_sync with "
        f"agent_root={agent_root}, agent_version={agent_version}, "
        f"python_hashes_count={python_hashes.module_count if python_hashes else 0}, "
        f"skip_registry={skip_registry}"
    )

    kwargs: Dict[str, Any] = dict(
        challenge=challenge,
        spot_check_count=spot_check_count,
        partial_file_check=(attestation_mode == "partial"),
        python_hashes=python_hashes,
        agent_version=agent_version,
        agent_project="ciris-agent",  # CIRISVerify v1.12.0+ per-call project (#10); explicit, not defaulted
        agent_root=agent_root,
        key_fingerprint=key_fingerprint,
        portal_key_id=key_fingerprint,  # Same as key_fingerprint for signature verification
    )
    if skip_registry:
        kwargs["skip_registry"] = True

    try:
        attestation_data: Dict[str, Any] = verifier.run_attestation_sync(**kwargs)
    except TypeError as exc:
        # Bundled verify predates skip_registry — drop it and retry so we never
        # hard-fail on the workaround itself (the budget env-gate still covers
        # this build).
        if "skip_registry" in kwargs:
            logger.warning("[attestation] verifier does not accept skip_registry (%s) — retrying without it", exc)
            kwargs.pop("skip_registry", None)
            attestation_data = verifier.run_attestation_sync(**kwargs)
        else:
            raise

    logger.info("[attestation] run_attestation_sync completed")
    return attestation_data


def _verify_audit_trail(
    verifier: Any,
    audit_db_path: str,
    key_fingerprint: Optional[str],
    attestation_data: dict[str, Any],
) -> dict[str, Any]:
    """Verify audit trail and merge results.

    Args:
        verifier: CIRISVerify verifier instance
        audit_db_path: Path to audit database
        key_fingerprint: Ed25519 key fingerprint
        attestation_data: Existing attestation data to merge into

    Returns:
        Updated attestation data with audit trail results
    """
    if not hasattr(verifier, "verify_audit_trail_sync"):
        return attestation_data

    try:
        logger.info(f"[attestation] Calling verify_audit_trail_sync with db_path={audit_db_path}")
        audit_result = verifier.verify_audit_trail_sync(
            db_path=audit_db_path,
            portal_key_id=key_fingerprint,
        )
        logger.info(f"[attestation] Audit trail verification result: {audit_result}")

        if audit_result:
            attestation_data["audit_trail"] = audit_result

    except Exception as e:
        logger.warning(f"[attestation] verify_audit_trail_sync failed: {e}")

    return attestation_data


def _log_attestation_response(attestation_data: Optional[dict[str, Any]]) -> None:
    """Log raw attestation response for debugging.

    Args:
        attestation_data: Attestation response dict
    """
    logger.info(f"[attestation] Raw response keys: {list(attestation_data.keys()) if attestation_data else 'None'}")
    if attestation_data:
        logger.info(f"[attestation] level={attestation_data.get('level')}, valid={attestation_data.get('valid')}")
        logger.info(f"[attestation] sources={attestation_data.get('sources')}")
        logger.info(f"[attestation] key_attestation={attestation_data.get('key_attestation')}")
        logger.info(f"[attestation] python_integrity={attestation_data.get('python_integrity')}")
        logger.info(f"[attestation] self_verification={attestation_data.get('self_verification')}")
        logger.info(f"[attestation] file_integrity={attestation_data.get('file_integrity')}")
        logger.info(f"[attestation] audit_trail={attestation_data.get('audit_trail')}")


def create_verification_thread_target(
    get_verifier: Callable[[], Any],
    attestation_mode: str,
    result_container: VerifyThreadResult,
) -> Callable[[], None]:
    """Create the target function for the verification thread.

    Args:
        get_verifier: Function to get the verifier instance
        attestation_mode: "full" or "partial"
        result_container: Container to store results

    Returns:
        Thread target function
    """
    spot_check_count = 0 if attestation_mode == "full" else 10

    def _run_verify_on_large_stack() -> None:
        """Run CIRISVerify on a thread with larger stack (Rust Tokio compatibility)."""
        try:
            verifier = get_verifier()
            if verifier is None:
                result_container.error = "CIRISVerify singleton not available"
                return

            version = _get_verifier_version(verifier)

            # Algorithm selection (CIRISAgent#740 / CIRISVerify#9):
            #   Mobile (Chaquopy)  → Algorithm B: load_python_hashes() reads
            #     startup_python_hashes.json that mobile_main.py wrote at boot;
            #     pass python_hashes to run_attestation_sync. Caps at L3.
            #   Desktop / server  → Algorithm A: verify_tree() walks agent_root
            #     against the registered file_manifest_json directly. No JSON
            #     middleman. Reaches L4. Run BEFORE run_attestation_sync so we
            #     can overlay python_integrity onto its result regardless of
            #     what its built-in walker does.
            python_hashes: Optional[PythonHashesWrapper] = None
            agent_version: Optional[str] = None
            tree_verify_result: Optional[Dict[str, Any]] = None
            if is_mobile():
                python_hashes, agent_version = load_python_hashes()
            else:
                agent_version = get_default_agent_version()
                tree_verify_result = run_tree_verify(agent_version=agent_version)

            # Get paths and fingerprint
            agent_root = get_agent_root()
            key_fingerprint = get_ed25519_fingerprint(verifier)
            audit_db_path = find_audit_db_path()

            # Run attestation
            attestation_data = _run_attestation_sync(
                verifier=verifier,
                spot_check_count=spot_check_count,
                attestation_mode=attestation_mode,
                python_hashes=python_hashes,
                agent_version=agent_version,
                agent_root=agent_root,
                key_fingerprint=key_fingerprint,
            )

            if attestation_data is None:
                attestation_data = {"error": "run_attestation_sync not available"}

            # Algorithm A overlay (desktop/server only). When verify_tree
            # produced a result, it is authoritative for python_integrity.
            if tree_verify_result is not None and isinstance(attestation_data, dict):
                attestation_data["python_integrity"] = tree_verify_result

            # Verify audit trail if we have a DB path
            if audit_db_path and attestation_data:
                attestation_data = _verify_audit_trail(verifier, audit_db_path, key_fingerprint, attestation_data)

            _log_attestation_response(attestation_data)

            result_container.result = {
                "version": version,
                "attestation": attestation_data,
            }

        except ImportError as e:
            result_container.error = f"CIRISVerify not available: {e}"
        except Exception as e:
            result_container.error = f"Attestation error: {e}"

    return _run_verify_on_large_stack


async def run_verification_thread(
    get_verifier: Callable[[], Any],
    attestation_mode: str,
) -> VerifyThreadResult:
    """Run CIRISVerify attestation in a separate thread.

    This function runs attestation on a thread with a larger stack size
    (required by Rust Tokio) and polls for completion asynchronously.

    Args:
        get_verifier: Function to get the verifier instance
        attestation_mode: "full" or "partial"

    Returns:
        VerifyThreadResult with result or error
    """
    result = VerifyThreadResult()

    thread_target = create_verification_thread_target(get_verifier, attestation_mode, result)

    # Run on thread with 8MB stack (Rust Tokio requirement)
    thread = threading.Thread(target=thread_target, daemon=True)
    thread.start()

    # Non-blocking wait: poll thread status while yielding to event loop
    # Use _async_timeout for Python 3.10 compatibility
    deadline = attestation_deadline_seconds()
    try:
        async with _async_timeout(deadline):
            while thread.is_alive():
                await asyncio.sleep(0.1)  # Yield to event loop every 100ms
    except asyncio.TimeoutError:
        # Degrade AT the budget instead of past it. The thread is a daemon and
        # keeps running; we simply stop letting it hold up startup. The result
        # returned here is identical to the one the old 90s path produced —
        # only 70s earlier, which is the difference between a degraded boot and
        # a processor stuck in Setup with a question on screen.
        logger.warning(
            "[attestation] TIMEOUT: verifier still running after %.0fs (the startup "
            "attestation budget). Degrading to an unverified attestation so startup "
            "can proceed. An attestation that cannot be produced inside the budget is "
            "a verifier bug — file it rather than raising the budget.",
            deadline,
        )
        result.error = f"Attestation timed out after {deadline:.0f} seconds"

    return result
