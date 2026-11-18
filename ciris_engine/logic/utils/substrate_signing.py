"""THE way this repo asks the substrate for a signature.

`Engine.local_sign` — the synchronous classical-only verb — cannot sign with a
sealed classical key, and since ciris-server 0.5.162 says so permanently:

    RuntimeError: local_sign cannot sign with a SEALED classical key — this is
    permanent, not transient, and the signature was NOT produced

Once a node holds ONE federation identity (CIRISServer#380 / CIRISPersist#616),
its classical half lives in the sealed keystore, whose `HardwareSigner::sign` is
async. So `local_sign` is not "usually fine, occasionally unavailable" — it is
unavailable for every production node, permanently.

**Why this module exists rather than a fix at each call site.** The same defect
appeared six times across four repositories, and every instance was *locally*
right: each site had a plausible reason to want a classical signature, and one
even fell back to `local_sign` only when no PQC signer was wired — which reads as
careful degradation until you know persist has since deleted the classical-only
state outright. Patching the sites one at a time is what let it survive six
reviews. The durable fix is that no site chooses a signing verb at all.

`local_sign_hybrid` is persist's single hybrid-sign verb (v17.7.0 /
CIRISPersist#470). It works for both custody models, and its `classical_sig` is
the same 64 raw Ed25519 bytes `local_sign` used to return — so callers that only
need the classical half get a byte-identical result and unchanged wire shape.

**persist v62 removes the PyO3 ``local_sign_hybrid``** (and ``verify_hybrid`` /
``verify_signed_*``); ``local_sign`` and ``local_pqc_sign`` stay. When the verb is
absent the hybrid is composed from those two exactly as persist's
``LocalSigner::sign_hybrid`` does: ``classical = local_sign(m)``,
``pqc = local_pqc_sign(m || classical)`` (persist test #470 pins the two as
byte-identical). The engine carries no single-key verifier, so verification has
no composition: without ``verify_hybrid`` it cannot be performed, and says so.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)

__all__ = ["sign_classical", "sign_hybrid", "sign_hybrid_required", "verify_hybrid_required"]


def sign_hybrid(engine: Any, canonical: bytes) -> Tuple[bytes, Optional[bytes]]:
    """Sign `canonical`, returning ``(classical_sig, pqc_sig)``.

    `pqc_sig` is None only when the build genuinely produced no PQC half. Callers
    that model a hybrid-pending row should key off that, never off catching an
    exception from a classical-only verb.

    Raises whatever the substrate raises. A signature that was not produced must
    not be papered over: the failure modes this replaces were silent, and a
    caller that swallows this writes an unsigned row that reads as signed.
    """
    if getattr(engine, "local_sign_hybrid", None) is not None:
        signatures = engine.local_sign_hybrid(canonical)
        classical = bytes(signatures["classical_sig"])
        raw_pqc = signatures.get("pqc_sig")
        return classical, (bytes(raw_pqc) if raw_pqc else None)
    return _compose_hybrid(engine, canonical)


def _compose_hybrid(engine: Any, canonical: bytes) -> Tuple[bytes, Optional[bytes]]:
    """The hybrid from the single-key verbs (persist v62): ``pqc = Sign_PQC(message || ed25519_sig)``."""
    classical = bytes(engine.local_sign(canonical))
    raw_pqc = engine.local_pqc_sign(canonical + classical) if getattr(engine, "local_pqc_sign", None) else None
    return classical, (bytes(raw_pqc) if raw_pqc else None)


def sign_classical(engine: Any, canonical: bytes) -> bytes:
    """The 64-byte Ed25519 signature, obtained the only way that still works.

    Drop-in for `engine.local_sign(canonical)` — same bytes, same length, same
    meaning — for call sites whose wire format carries a classical signature
    only. The PQC half is computed and discarded; that cost is deliberate,
    because the alternative is each site deciding for itself which verb to use,
    which is precisely how this defect reached six sites.
    """
    classical, _ = sign_hybrid(engine, canonical)
    return classical


#: The only verifier policy this repo passes (CC 5.3.2.4.3.1, CIRISAgent#1348):
#: both halves present and both verify. There is no classical-only posture to
#: select; when persist/edge drop the policy argument, this is the one line to go.
_HYBRID_REQUIRED = "strict"


def sign_hybrid_required(engine: Any, canonical: bytes) -> Tuple[bytes, bytes]:
    """Sign `canonical` with both halves, or raise: a classical-only signature is not produced.

    For records whose verifier is hybrid-required. A build with no PQC signer
    cannot make one, and saying so beats writing a row nothing will accept.
    """
    classical, pqc = sign_hybrid(engine, canonical)
    if not pqc:
        raise RuntimeError("no ML-DSA-65 half was produced; a hybrid-required record cannot be signed")
    return classical, pqc


def verify_hybrid_required(
    engine: Any,
    canonical: bytes,
    classical_sig_b64: str,
    pqc_sig_b64: Optional[str],
    ed25519_pubkey_b64: str,
    pqc_pubkey_b64: Optional[str],
) -> None:
    """Verify both halves of a hybrid signature. Raises ValueError on anything less.

    A missing PQC signature or key is a failure, never a reason to check the
    classical half alone.
    """
    if not pqc_sig_b64:
        raise ValueError("signature carries no ML-DSA-65 half (hybrid required)")
    if not pqc_pubkey_b64:
        raise ValueError("signer has no ML-DSA-65 public key (hybrid required)")
    if getattr(engine, "verify_hybrid", None) is None:
        # The engine exposes no single-key verifier to compose one from: the check cannot be performed.
        raise RuntimeError("the substrate exposes no hybrid verifier (verify_hybrid); the signature was NOT verified")
    engine.verify_hybrid(
        canonical, classical_sig_b64, pqc_sig_b64, ed25519_pubkey_b64, pqc_pubkey_b64, _HYBRID_REQUIRED
    )
