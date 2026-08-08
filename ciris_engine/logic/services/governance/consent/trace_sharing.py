"""THE handle for trace-sharing consent. Every opt-in path goes through here.

Before this module there were two half-grants living in different layers:

* session-ful paths (setup wizard, Data & Privacy card) called
  ``emit_community_consent_grant()`` — the CAPTURE gate only;
* session-less paths (node fold, delivery probe) called
  ``author_federation_consent()`` — the SHIP gate only.

Neither path granted both, so the common outcome was ``capture=True,
replication=False``: traces sealed perfectly, the node reported healthy, and
nothing ever left it. That is the exact drift ``log_federation_consent_drift``
was written to shout about — the detector existed while the writers stayed split.

So the rule this module enforces is: **granting trace sharing means granting all
of it.** One call authors the capture grant AND the ship/score grant, and reports
per-artifact what landed.

What it does NOT do is decide FOR the owner. Booting a node is not consenting to
replicate your reasoning off it, which is why the substrate stopped boot-authoring
in 0.5.146. Every path here is gated on an explicit owner act; the session-less
paths merely REPLAY an opt-in the owner already made (the wizard's choice, landed
in ``CIRIS_ACCORD_METRICS_CONSENT``). Unreadable signal ⇒ no consent authored.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from ciris_engine.schemas.consent.trace_sharing import (
    TraceConsentSource,
    TraceSharingConsent,
    TraceSharingGrantResult,
)

logger = logging.getLogger(__name__)

#: The legacy env var. It is where the first-run wizard's "Send traces" choice
#: lands and what the QA runner sets for a consented live capture, so it is the
#: import path into CEG consent state rather than a thing to be migrated away.
#: Read in exactly one place — here.
OPT_IN_ENV_VAR = "CIRIS_ACCORD_METRICS_CONSENT"
OPT_IN_TIMESTAMP_ENV_VAR = "CIRIS_ACCORD_METRICS_CONSENT_TIMESTAMP"


def owner_opted_into_trace_sharing() -> bool:
    """Did the OWNER opt in? Fails CLOSED — unreadable means no.

    Returns False when the signal cannot be read, so the failure mode is "no
    consent authored" and never "consented on the owner's behalf".
    """
    try:
        from ciris_engine.logic.config.env_utils import get_env_var  # noqa: PLC0415

        if str(get_env_var(OPT_IN_ENV_VAR, "")).lower() == "true":
            return True
    except Exception:  # noqa: BLE001 — config layer may not be up this early
        pass
    import os

    return os.environ.get(OPT_IN_ENV_VAR, "").lower() == "true"


def trace_sharing_status() -> TraceSharingConsent:
    """Resolve all three gates through the engine's own readers.

    Thin typed wrapper over ``federation_consent_status()``, which already does
    the resolution correctly (``list_consent_peers`` for the projection edge
    actually reads, the scoped resolver for analyze). This exists so callers get
    a model with a ``ships`` property instead of a dict they each interpret.
    """
    from ciris_engine.logic.services.governance.consent.attestation import (
        federation_consent_status,
    )

    try:
        raw = federation_consent_status()
    except Exception as exc:  # noqa: BLE001 — diagnostics must never raise
        logger.debug("trace-consent: status resolution failed: %s", exc)
        return TraceSharingConsent()

    def _tri(key: str) -> Optional[bool]:
        val = raw.get(key)
        return bool(val) if isinstance(val, bool) else None

    canonical = raw.get("canonical")
    return TraceSharingConsent(
        capture=_tri("capture"),
        replication=_tri("replication"),
        analyze=_tri("analyze"),
        canonical=str(canonical) if canonical else None,
        aligned=bool(raw.get("aligned")),
    )


def _canonical_targets() -> List[str]:
    """Canonical peers, discovered from live delivery status.

    Never a constant: ``CIRIS_CANONICAL_BOOTSTRAP_PEERS`` is empty by default and
    a hardcoded key_id is one more copy to drift.
    """
    try:
        import json as _json

        import ciris_server  # type: ignore[import-not-found, import-untyped, unused-ignore]

        ds = getattr(ciris_server, "delivery_status", None)
        if ds is None:
            return []
        status = ds()
        if isinstance(status, str):
            status = _json.loads(status)
        return [str(t) for t in ((status or {}).get("canonical_targets") or [])]
    except Exception as exc:  # noqa: BLE001
        logger.debug("trace-consent: delivery_status unreadable: %s", exc)
        return []


def _author_ship_grant(result: TraceSharingGrantResult) -> None:
    """Author the replication (+analyze) grant naming each canonical peer."""
    try:
        import ciris_server  # type: ignore[import-not-found, import-untyped, unused-ignore]

        author = getattr(ciris_server, "author_federation_consent", None)
        if author is None:
            result.errors.append("author_federation_consent unavailable (wheel <0.5.147)")
            return

        targets = _canonical_targets()
        if not targets:
            # Not an error: pre-root this is simply too early. The probe retries.
            result.errors.append("no canonical delivery target yet")
            return

        probe = getattr(ciris_server, "analyze_consent_stance", None)
        for peer in targets:
            try:
                # prefixes=None -> the build's own default, NEVER restated here.
                # A restated list is how ["capacity:"] shipped while the authority
                # said ["capacity:", "trace:"], stranding every trace it failed to
                # name. analyze=True is the consent to BE SCORED; without it the
                # grant is incomplete and the peer builds no reputation.
                author(peer, None, True)

                # ASSERT THE STANCE, NOT THE CALL. A row can exist and still fold
                # to `unspecified` — which reads as consented to anything counting
                # rows, while the serve gate goes on refusing.
                if probe is not None:
                    try:
                        stance = probe(peer)
                        if stance is not None and str(stance) != "granted":
                            result.errors.append(f"{peer}: authored but stance={stance!r}, not 'granted'")
                            continue
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("trace-consent: stance unreadable for %s: %s", peer, exc)
                result.peers_authored.append(peer)
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"{peer}: {exc}")
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"ship grant failed: {exc}")


def grant_trace_sharing(
    source: TraceConsentSource,
    *,
    granted_at: Optional[str] = None,
    require_opt_in: bool = True,
) -> TraceSharingGrantResult:
    """Grant trace sharing COMPLETELY — capture gate and ship/score gate.

    Args:
        source: which opt-in path is authoring, recorded on the result.
        granted_at: ISO timestamp for the capture grant; the build defaults it.
        require_opt_in: check the owner's opt-in signal first. Paths that carry
            the owner's act in-band (the wizard checkbox, the data card toggle)
            pass False — the click IS the consent, and the env var may not be
            written yet at that point. Session-less paths must leave this True.

    Never raises: a failed consent emit must not break setup completion or boot.
    """
    opted_in = True if not require_opt_in else owner_opted_into_trace_sharing()
    result = TraceSharingGrantResult(source=source, opted_in=opted_in)

    if not opted_in:
        logger.info(
            "trace-consent: owner has not opted into trace sharing (%s != true, source=%s) — "
            "nothing authored. Traces will seal locally and stay at (self, local), which is correct.",
            OPT_IN_ENV_VAR,
            source.value,
        )
        result.status = trace_sharing_status()
        return result

    # 1. CAPTURE — consent:community_trust:v1
    try:
        from ciris_engine.logic.services.governance.consent.attestation import (
            emit_community_consent_grant,
        )

        attestation_id = emit_community_consent_grant(granted_at=granted_at)
        if attestation_id:
            result.capture_grant_id = str(attestation_id)
        else:
            result.errors.append("capture grant returned None (engine/federation key not ready?)")
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"capture grant failed: {exc}")

    # 2. SHIP + SCORE — consent:replication:v1 (+ analyze)
    _author_ship_grant(result)

    result.status = trace_sharing_status()

    if result.complete:
        logger.info(
            "trace-consent: GRANTED via %s — capture=%s ship=%s. Sealed traces can now promote.",
            source.value,
            result.capture_grant_id,
            result.peers_authored,
        )
    else:
        # Loud: this is the difference between traces shipping and stranding, and
        # the half-granted state failed silently for a full day.
        logger.warning(
            "trace-consent: INCOMPLETE via %s — capture=%s ship=%s errors=%s. "
            "Traces will seal but may not replicate; the probe retries the ship "
            "grant once a canonical peer is rooted.",
            source.value,
            result.capture_grant_id or "MISSING",
            result.peers_authored or "MISSING",
            result.errors,
        )
    return result


def revoke_trace_sharing(
    source: TraceConsentSource,
    *,
    recant: bool = False,
) -> bool:
    """Withdraw (or recant) trace-sharing consent.

    ``recant=True`` disowns past traces as well as stopping future ones; the
    default withdraws going forward. Mirrors the grant path so revocation cannot
    drift from it. Returns True when a revocation was emitted.

    CAUTION — this writes the CEG structural row ONLY. ``RECANT`` additionally
    obliges the caller to run the DSAR deletion cascade
    (``INTENT_TRIGGERS_DELETION``). The data-deletion route owns that cascade and
    must keep calling ``emit_community_consent_revocation`` directly; do not
    route it through here and lose the second half.
    """
    try:
        from ciris_engine.logic.services.governance.consent.attestation import (
            RevocationIntent,
            current_community_grant_id,
            emit_community_consent_revocation,
        )

        target = current_community_grant_id()
        if not target:
            logger.info("trace-consent: nothing to revoke (no live capture grant), source=%s", source.value)
            return False
        intent = RevocationIntent.RECANT if recant else RevocationIntent.WITHDRAW
        emit_community_consent_revocation(intent, target, reason=f"revoked via {source.value}")
        logger.info("trace-consent: REVOKED (%s) via %s, target=%s", intent, source.value, target)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("trace-consent: revocation failed (non-fatal, source=%s): %s", source.value, exc)
        return False
