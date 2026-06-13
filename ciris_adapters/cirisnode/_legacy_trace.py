"""Legacy trace pipeline types — PRIVATE to the cirisnode adapter.

Extracted verbatim from the pre-fold ciris_adapters/ciris_accord_metrics/
services.py (commit 2a228b4a4 — the coherent JCS + trace_schema_version
"3.0.0" state; persist's signed-epoch verify gate dispatches major >= 3 to
the JCS canonicalizer, so traces signed here verify against persist 5.x and
the prod lens).

WHY THIS EXISTS: the 2.9.6 LensCore fold (CIRISAgent#866) removed the
Python trace pipeline from accord_metrics — the substrate (ciris-lens-core
LensClient) owns capture/seal/sign/persist for the agent's reasoning
traces. The cirisnode adapter still builds + signs its OWN deferral-
resolution / commons-credit traces with the legacy Python pipeline and
ships them over the lens HTTP API. Folding cirisnode's emission onto the
substrate (DEFERRAL_RECEIVED / DEFERRAL_RESOLVED / CREDIT_GENERATED are in
the closed 15-variant taxonomy) is the follow-up — until then the types
live HERE so the fold's "no second shipping mechanism" applies to the
agent's reasoning-trace pipeline without breaking the node side.

Do not import these from new code.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)
# 3.0.0: bumped from "2.7.9" as part of the 2.9.6 HARD JCS cutover
# (CIRISAgent#871). The stamped trace_schema_version is the signed-bytes-bound
# discriminator a verifier uses to pick the canonicalizer that reproduces the
# signature: persist's gate is an era boundary — major >= 3 => JCS (RFC 8785),
# 2.x => legacy Python json.dumps (`canon_version_for_trace_schema`,
# persist src/verify/ed25519.rs). Leaving the stamp at "2.7.9" while signing
# JCS would gate the agent's JCS traces to the Python canonicalizer, failing
# every non-ASCII trace. The canonical FIELD LAYOUT is unchanged from 2.7.9
# (same 9-field envelope + deployment_profile §3.2); only the canonicalizer
# flipped, so persist's "3.0.0" dispatch arm reuses the 2.7.9 field builder.
# History: "2.7.9" (bumped from "2.7.0") signalled that LLM_CALL events carry
# the parent_event_type + parent_attempt_index fields per TRACE_WIRE_FORMAT.md
# §5.10; persistence MAY enforce field presence at a given schema version.
TRACE_SCHEMA_VERSION = "3.0.0"


def _strip_empty(obj: Any) -> Any:
    """Recursively strip None, empty strings, empty lists, empty dicts to reduce payload size."""
    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            stripped = _strip_empty(v)
            # Keep the value if it's not empty (0 and False are valid values)
            if stripped is not None and stripped != "" and stripped != [] and stripped != {}:
                result[k] = stripped
        return result
    elif isinstance(obj, list):
        return [_strip_empty(item) for item in obj if item is not None]
    return obj


@dataclass
class SimpleCapabilities:
    """Simple capabilities container for duck-typing with WiseBus.

    The supported_domains field declares which DomainCategory values this
    service can handle. WiseBus filters services by domain_hint when routing
    deferrals to ensure only qualified handlers receive domain-specific requests.
    """

    actions: List[str]
    scopes: List[str]
    supported_domains: List[str] = field(default_factory=list)  # DomainCategory values


@dataclass
class TraceComponent:
    """A single component of a reasoning trace.

    `agent_id_hash` is denormalized from the parent CompleteTrace onto every
    component as of trace_schema_version "2.7.9" (#712 item #1) — persistence
    layers read it directly from each row instead of propagating from the
    envelope. The wire representation carries the same value at both
    CompleteTrace and TraceComponent levels; agents MUST emit them equal,
    persistence MAY reject mismatches.
    """

    component_type: str  # observation, context, rationale, conscience, action, outcome
    event_type: str  # THOUGHT_START, SNAPSHOT_AND_CONTEXT, etc.
    timestamp: str
    data: Dict[str, Any]
    agent_id_hash: str = ""  # Denormalized from CompleteTrace.agent_id_hash; populated by build code.


@dataclass
class CompleteTrace:
    """A complete 6-component reasoning trace.

    `deployment_profile` (2.7.9+) carries the cohort-taxonomy block per
    FSD/TRACE_WIRE_FORMAT.md §3.2 — 6 agent-declared fields routed into
    the signed canonical bytes (§8) so cohort labels are non-forgeable
    post-emission. Agents MUST emit this block at trace_schema_version
    "2.7.9"; persistence MUST reject 2.7.9 traces missing it.
    Migration defaults populate when the operator hasn't configured
    explicit values (see `AccordMetricsService._build_deployment_profile`).
    """

    trace_id: str
    thought_id: str
    task_id: Optional[str]
    agent_id_hash: str
    started_at: str
    completed_at: Optional[str] = None
    components: List[TraceComponent] = field(default_factory=list)
    signature: Optional[str] = None
    signature_key_id: Optional[str] = None
    # Trace level determines what data is included - MUST be part of signature
    trace_level: Optional[str] = None
    trace_schema_version: str = TRACE_SCHEMA_VERSION
    # Cohort taxonomy block, 2.7.9+. Required-on-the-wire at
    # trace_schema_version "2.7.9" per FSD §3.2; absent at 2.7.0.
    deployment_profile: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization.

        Uses _strip_empty on component data to match what was signed.
        """
        out: Dict[str, Any] = {
            "trace_id": self.trace_id,
            "thought_id": self.thought_id,
            "task_id": self.task_id,
            "agent_id_hash": self.agent_id_hash,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "trace_level": self.trace_level,
            "trace_schema_version": self.trace_schema_version,
            "components": [
                {
                    "agent_id_hash": c.agent_id_hash or self.agent_id_hash,
                    "component_type": c.component_type,
                    "data": _strip_empty(c.data),
                    "event_type": c.event_type,
                    "timestamp": c.timestamp,
                }
                for c in self.components
            ],
            "signature": self.signature,
            "signature_key_id": self.signature_key_id,
        }
        if self.deployment_profile is not None:
            out["deployment_profile"] = dict(self.deployment_profile)
        return out

    def compute_hash(self) -> str:
        """Compute SHA-256 hash of trace content (excluding signature)."""
        # Build deterministic representation
        content: Dict[str, Any] = {
            "trace_id": self.trace_id,
            "thought_id": self.thought_id,
            "task_id": self.task_id,
            "agent_id_hash": self.agent_id_hash,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "trace_level": self.trace_level,
            "trace_schema_version": self.trace_schema_version,
            "components": [
                {
                    "component_type": c.component_type,
                    "event_type": c.event_type,
                    "timestamp": c.timestamp,
                    "data": c.data,
                }
                for c in self.components
            ],
        }
        if self.deployment_profile is not None:
            content["deployment_profile"] = dict(self.deployment_profile)
        json_str = json.dumps(content, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(json_str.encode()).hexdigest()


# CIRISVerify briefly blocks signing while a tree attestation runs (typically
# at startup); it raises a retryable AttestationInProgressError whose message


_TRACE_SIGN_MAX_RETRIES = 10
_TRACE_SIGN_RETRY_DELAY_S = 0.5


# 2.9.6 is the HARD JCS cutover (CEG §0.9 / the substrate triple persist 4.10 ·
# edge 1.5 · verify 5.0). Trace signing canonical bytes are produced by verify's
# RFC 8785 (JCS) canonicalizer — ciris_verify_core::jcs via the verify FFI — so
# they are byte-identical to what the Rust federation verifiers recompute on the
# wire. This replaces the pre-2.9.6 `json.dumps(sort_keys=True,
# separators=(",", ":"))` path, which was implicitly ensure_ascii=True and so
# diverged on EVERY non-ASCII byte (i.e. the entire multilingual trace corpus —
# signatures over Amharic/Arabic/Chinese/… traces verified locally but failed
# against any Rust verifier). verify 5.0.0 is a hard dependency of the 2.9.6
# triple (requirements.txt), so the binding is always present; we fail loud
# rather than silently fall back to the divergent json.dumps bytes.
_jcs_canon: Optional[Callable[[Any], bytes]] = None


def _get_jcs_canonicalize() -> Callable[[Any], bytes]:
    """Resolve verify's RFC 8785 (JCS) canonicalizer, cached process-wide.

    Both sources wrap the SAME Rust impl (ciris_verify_core::jcs), so output is
    byte-identical regardless of which loads:

    1. The pip-installed ``ciris_verify`` package — the dependency-declared
       source (``ciris-verify>=5.0.0`` in requirements.txt). Its wheel ships a
       loadable native lib for every platform, so this is the path that works
       in CI and any pip-based deploy.
    2. The in-repo ``ciris_adapters.ciris_verify`` adapter — its Linux/Windows
       native libs are build-time artifacts (bundled in the wheel / Android
       jniLibs), so this path covers bundled deploys where only it is present.

    Fails loud if neither resolves: a hard JCS cutover must never silently fall
    back to the divergent ``json.dumps`` bytes (that would mint signatures the
    Rust verifiers reject).
    """
    global _jcs_canon
    if _jcs_canon is not None:
        return _jcs_canon
    errors: List[str] = []
    for source in ("ciris_verify._jcs", "ciris_adapters.ciris_verify.ffi_bindings._jcs"):
        try:
            mod = __import__(source, fromlist=["jcs_canonicalize"])
            _jcs_canon = mod.jcs_canonicalize
            return _jcs_canon
        except Exception as exc:  # ImportError / RuntimeError (lib not loadable)
            errors.append(f"{source}: {exc}")
    raise RuntimeError(
        "2.9.6 JCS cutover: no RFC 8785 canonicalizer available from "
        "ciris_verify (>= 5.0.0). Trace signing cannot proceed without it. "
        "Tried: " + " | ".join(errors)
    )


def _attestation_in_progress_error() -> Optional[type]:
    """Return CIRISVerify's AttestationInProgressError type, if importable.

    ciris_verify is an optional adapter, so the type is resolved dynamically.
    """
    try:
        import ciris_adapters.ciris_verify as ciris_verify

        err = getattr(ciris_verify, "AttestationInProgressError", None)
        return err if isinstance(err, type) else None
    except ImportError:
        return None


class Ed25519TraceSigner:
    """Sign traces using the unified Ed25519 signing key.

    This class wraps the unified signing key from ciris_engine.logic.audit.signing_protocol,
    ensuring the same key is used for both audit trail signing and accord metrics traces.

    The unified key is stored at data/agent_signing.key and is shared with the audit service.
    """

    def __init__(self, seed_dir: Optional[Path] = None):
        """Initialize signer with optional seed directory for root public key."""
        self._unified_key: Optional[Any] = None
        self._root_pubkey: Optional[str] = None
        self._key_id: Optional[str] = None

        # Load root public key from seed directory (for verification only)
        if seed_dir is None:
            seed_dir = Path(__file__).parent.parent.parent / "seed"

        root_pub_file = seed_dir / "root_pub.json"
        if root_pub_file.exists():
            with open(root_pub_file) as f:
                root_data = json.load(f)
                self._root_pubkey = root_data.get("pubkey")
                logger.info(f"Loaded root public key: {root_data.get('wa_id', 'wa-unknown')}")

    def _ensure_unified_key(self) -> bool:
        """Ensure the unified signing key is loaded."""
        if self._unified_key is not None:
            return True

        try:
            from ciris_engine.logic.audit.signing_protocol import get_unified_signing_key

            self._unified_key = get_unified_signing_key()
            self._key_id = self._unified_key.key_id
            logger.info(f"Using unified signing key: {self._key_id}")
            return True
        except Exception as e:
            logger.warning(f"Could not load unified signing key: {e}")
            return False

    def _build_canonical_message(self, trace: CompleteTrace) -> bytes:
        """Build the canonical signing/verifying bytes per FSD/TRACE_WIRE_FORMAT.md §8.

        9-field canonical (post-2.7.8.9 / CIRISAgent#710):

            {
              "trace_id":            ...,
              "thought_id":          ...,
              "task_id":             ...,
              "agent_id_hash":       ...,
              "started_at":          ...,
              "completed_at":        ...,
              "trace_level":         ...,
              "trace_schema_version": ...,
              "components":          [strip_empty({component_type,data,event_type,timestamp}), ...]
            }

        Then RFC 8785 (JCS) canonicalized via verify — the 2.9.6 HARD cutover.
        Pre-2.9.6 used `json.dumps(canonical, sort_keys=True, separators=(",",
        ":"))`, which was ensure_ascii=True and diverged from the Rust verifiers
        on all non-ASCII (the multilingual corpus). See the module-level note.

        Migration history:
        - <= 2.7.8.8 used a 2-field legacy canonical {"components", "trace_level"}
          to match what `lens-legacy api/accord_api.py::verify_trace_signature`
          accepted. Persist v0.1.15 implements the spec's 9-field canonical;
          legacy 2-field signatures fail `verify_strict` with HTTP 422
          `verify_signature_mismatch` against the new typed verify path.
        - Persist's `try-both` fallback (CIRISPersist issue) accepts BOTH shapes
          during the migration window — so flipping the agent doesn't gate
          persist, and persist's fallback doesn't gate the agent.
        - Once the agent fleet has flipped to 9-field, persist drops the 2-field
          path on a future minor.

        The seven additional fields (vs the legacy 2-field) bind more provenance
        into the signed bytes — federation peers verify "this agent claims this
        thought_id at this time was signed under this schema version" without
        trusting the envelope wrapping.
        """
        # Per-component shape at trace_schema_version "2.7.9" (#712 item #1):
        # agent_id_hash is denormalized onto every TraceComponent so each
        # event row is self-contained — persist reads it directly from the
        # row instead of propagating from the envelope. The component's
        # value MUST equal the envelope's agent_id_hash; we copy here to
        # keep them locked.
        components_list = [
            _strip_empty(
                {
                    "agent_id_hash": c.agent_id_hash or trace.agent_id_hash,
                    "component_type": c.component_type,
                    "data": c.data,
                    "event_type": c.event_type,
                    "timestamp": c.timestamp.isoformat()
                    if hasattr(c.timestamp, "isoformat")
                    else str(c.timestamp),
                }
            )
            for c in trace.components
        ]
        # `started_at` / `completed_at` are typed as Optional[str|datetime] on
        # the trace envelope. Both mypy-narrow through an explicit None check
        # AND pass through unchanged if already a str. Persist's canonicalizer
        # does the same — the agreed-on shape is "ISO 8601 string or None".
        def _iso(value: Any) -> Any:
            if value is None:
                return None
            return value.isoformat() if hasattr(value, "isoformat") else str(value)

        canonical: Dict[str, Any] = {
            "trace_id": trace.trace_id,
            "thought_id": trace.thought_id,
            "task_id": trace.task_id,
            "agent_id_hash": trace.agent_id_hash,
            "started_at": _iso(trace.started_at),
            "completed_at": _iso(trace.completed_at),
            "trace_level": trace.trace_level,
            "trace_schema_version": trace.trace_schema_version,
            "components": components_list,
        }
        # 2.7.9+ deployment_profile block per FSD §3.2. The block is part of
        # the signed canonical bytes — federation peers verify the cohort
        # labels the agent declared at signing time so an intermediary
        # (or persist itself) cannot re-stamp them. Absent at 2.7.0;
        # present at 2.7.9 (with migration defaults if operator has not
        # configured explicit values).
        if trace.deployment_profile is not None:
            canonical["deployment_profile"] = dict(trace.deployment_profile)
        # 2.9.6 HARD JCS cutover: canonicalize via verify's RFC 8785 impl so the
        # signed bytes are byte-identical to what the Rust federation verifiers
        # recompute. The old `json.dumps(sort_keys=True, separators=(",", ":"))`
        # was ensure_ascii=True and diverged on all non-ASCII. See module note.
        return _get_jcs_canonicalize()(canonical)

    def sign_trace(self, trace: CompleteTrace) -> bool:
        """Sign a trace with the unified Ed25519 signing key.

        Canonical bytes are produced by _build_canonical_message — see that
        method's docstring for the 9-field shape per FSD/TRACE_WIRE_FORMAT.md §8
        and the 2.7.8.9 migration note.

        Returns True on success, False if the signing key isn't available.
        """
        if not self._ensure_unified_key() or self._unified_key is None:
            logger.warning("No unified signing key available for trace signing")
            return False

        attestation_in_progress = _attestation_in_progress_error()
        for attempt in range(_TRACE_SIGN_MAX_RETRIES):
            try:
                message = self._build_canonical_message(trace)
                message_hash = hashlib.sha256(message).hexdigest()
                logger.info(
                    f"[SIGN_TRACE] trace={trace.trace_id} level={trace.trace_level} "
                    f"len={len(message)} hash={message_hash[:16]} canonical=9-field"
                )
                trace.signature = self._unified_key.sign_base64(message)
                trace.signature_key_id = self._key_id
                logger.debug(f"Signed trace {trace.trace_id} with unified key {self._key_id}")
                return True
            except Exception as e:
                last_attempt = attempt >= _TRACE_SIGN_MAX_RETRIES - 1
                # The signing wrapper may re-raise CIRISVerify's
                # AttestationInProgressError as a generic exception that only
                # carries the message — so match the type OR the message.
                is_attestation = (
                    attestation_in_progress is not None
                    and isinstance(e, attestation_in_progress)
                ) or "attestation in progress" in str(e).lower()
                if is_attestation and not last_attempt:
                    logger.debug(
                        "trace signing deferred (attestation in progress); "
                        "retry %d/%d in %.1fs",
                        attempt + 1,
                        _TRACE_SIGN_MAX_RETRIES,
                        _TRACE_SIGN_RETRY_DELAY_S,
                    )
                    time.sleep(_TRACE_SIGN_RETRY_DELAY_S)
                    continue
                logger.error(f"Failed to sign trace: {e}")
                return False
        return False

    def verify_trace(self, trace: CompleteTrace) -> bool:
        """Verify a trace signature using the root public key.

        Uses the same _build_canonical_message helper as sign_trace, so the
        sign/verify paths can never drift out of sync at the canonicalization
        layer.
        """
        if not trace.signature or not self._root_pubkey:
            return False

        try:
            from cryptography.hazmat.primitives.asymmetric import ed25519

            pubkey_bytes = base64.urlsafe_b64decode(self._root_pubkey + "==")
            public_key = ed25519.Ed25519PublicKey.from_public_bytes(pubkey_bytes)
            sig_bytes = base64.urlsafe_b64decode(trace.signature + "==")
            message = self._build_canonical_message(trace)
            public_key.verify(sig_bytes, message)
            return True
        except Exception as e:
            logger.warning(f"Trace signature verification failed: {e}")
            return False

    @property
    def key_id(self) -> Optional[str]:
        """Get the key ID, loading unified key if needed."""
        if self._key_id is None:
            self._ensure_unified_key()
        return self._key_id

    @property
    def has_signing_key(self) -> bool:
        """Check if a signing key is available."""
        return self._ensure_unified_key()



