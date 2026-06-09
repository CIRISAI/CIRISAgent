"""
Consent → CEG attestation mapper (CIRISAgent#869, 2.9.6 consent fold).

Converts the agent's consent objects (``ConsentStatus``) into the CEG
``LocalAttestationInput`` the persist substrate accepts via
``Engine.attestation_upsert_local`` (CIRISPersist#171, persist >= 4.9.0), and
provides flag-gated, best-effort emit helpers the consent service calls on
grant / modify / revoke.

This is the consent-domain slice of the CEG-native agent migration (#840):
each consent record becomes a ``witness_relation: self``, local-tier
attestation. The user identity lives in the **dimension** (per-user, so the
``(occurrence, dimension)`` upsert key gives one replaceable row per user) and
in the **claim** — NOT in ``subject_key_ids``, because end users are not
federation-key holders. Revocation/opt-out replaces the row with a score-0
state and (best-effort) promotes it to federation tier so the withdrawal is
announceable (CEG §10.1.3).

Shape verified against the persist 4.9.0 wheel: ``attestation_type: "scores"``
requires a ``:v<N>``-versioned dimension; the envelope is opaque JSON to
persist except ``dimension`` (the upsert key). See the round-trip test in
``tests/.../consent/test_consent_attestation.py``.

Default OFF: gated on ``CIRIS_CONSENT_CEG_ATTESTATIONS`` so the dual-write is
opt-in until the migration is validated end-to-end.
"""

from __future__ import annotations

import hashlib
import logging
import os
import uuid
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.consent.core import ConsentStatus, ConsentStream

logger = logging.getLogger(__name__)

# Dimension namespace. The `:v1` suffix is REQUIRED for attestation_type
# "scores" (persist's T3 version-pinning gate); `consent:*` clears the
# reserved-prefix admit check (§7.7 / AV rules).
_CONSENT_STREAM_DIM_PREFIX = "consent:stream"
_DIM_VERSION = "v1"

# attestation_type "scores" → persist gates the dimension version + stores the
# envelope verbatim. Structural CEG types (supersedes/withdraws) are exempt
# from the version rule but we keep consent on the scores axis for queryability.
_ATTESTATION_TYPE_SCORES = "scores"

# Stream → calibration score (1.0 = strongest standing grant). The full state
# travels in the claim; the score is the CEG-axis summary.
_STREAM_SCORE = {
    ConsentStream.PARTNERED.value: 1.0,
    ConsentStream.TEMPORARY.value: 0.5,
    ConsentStream.ANONYMOUS.value: 0.0,
}

_FEATURE_FLAG_ENV = "CIRIS_CONSENT_CEG_ATTESTATIONS"


def consent_ceg_attestations_enabled() -> bool:
    """True when the consent→CEG dual-write is opted in (default off)."""
    return os.environ.get(_FEATURE_FLAG_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def _user_dimension(user_id: str) -> str:
    """Per-user dimension so each user gets one replaceable upsert row.

    The user_id is hashed to a stable 16-hex token to keep the dimension a
    clean CEG identifier (and to avoid leaking raw user identifiers into the
    federation-visible dimension); the real user_id is carried in the claim.
    """
    user_token = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:16]
    return f"{_CONSENT_STREAM_DIM_PREFIX}:{user_token}:{_DIM_VERSION}"


def _stream_score(stream: str) -> float:
    return _STREAM_SCORE.get(stream, 0.0)


class ConsentClaim(BaseModel):
    """Agent-authored CEG claim body carried inside the attestation envelope."""

    model_config = ConfigDict(defer_build=True)

    user_id: str = Field(..., description="User whose consent this attests")
    stream: str = Field(..., description="Consent stream (temporary/partnered/anonymous)")
    categories: List[str] = Field(default_factory=list, description="Consented categories")
    state: str = Field("active", description="active | revoked")
    granted_at: Optional[str] = Field(None, description="ISO grant time")
    expires_at: Optional[str] = Field(None, description="ISO expiry (TEMPORARY)")
    reason: Optional[str] = Field(None, description="Reason for the change")


class ConsentAttestationEnvelope(BaseModel):
    """The CEG attestation envelope. Persist reads only ``dimension``."""

    model_config = ConfigDict(defer_build=True)

    dimension: str = Field(..., description="Versioned per-user consent dimension")
    id: str = Field(..., description="Envelope id (uuid4)")
    score: float = Field(..., ge=0.0, le=1.0, description="Calibration score for the stream")
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="Producer confidence")
    claim: ConsentClaim = Field(..., description="Agent-authored consent claim body")


class LocalAttestationInput(BaseModel):
    """Top-level input for ``Engine.attestation_upsert_local`` (persist #171).

    ``cohort_scope`` defaults to ``self`` and ``subject_key_ids`` to ``[]`` on
    the persist side, so the local self-witness row needs only these three
    fields. ``attested_key_id`` defaults to ``attesting_key_id``.
    """

    model_config = ConfigDict(defer_build=True)

    attesting_key_id: str = Field(..., description="Producing occurrence's federation key id")
    attestation_type: str = Field(_ATTESTATION_TYPE_SCORES, description="CEG attestation type")
    attestation_envelope: ConsentAttestationEnvelope = Field(..., description="The CEG envelope")


def build_consent_grant_input(status: ConsentStatus, attesting_key_id: str) -> LocalAttestationInput:
    """Map a ConsentStatus (grant/modify) to a local-tier attestation input."""
    claim = ConsentClaim(
        user_id=status.user_id,
        stream=str(status.stream),
        categories=[str(c) for c in status.categories],
        state="active",
        granted_at=status.granted_at.isoformat() if status.granted_at else None,
        expires_at=status.expires_at.isoformat() if status.expires_at else None,
    )
    envelope = ConsentAttestationEnvelope(
        dimension=_user_dimension(status.user_id),
        id=str(uuid.uuid4()),
        score=_stream_score(str(status.stream)),
        confidence=1.0,
        claim=claim,
    )
    return LocalAttestationInput(attesting_key_id=attesting_key_id, attestation_envelope=envelope)


def build_consent_revocation_input(
    user_id: str, attesting_key_id: str, reason: Optional[str] = None
) -> LocalAttestationInput:
    """Map a consent revocation/opt-out to a score-0 ``revoked`` attestation.

    Replaces the active row on the same per-user dimension; promotion (done by
    the caller) flips it to federation tier so the withdrawal is announceable.
    """
    claim = ConsentClaim(user_id=user_id, stream="", categories=[], state="revoked", reason=reason)
    envelope = ConsentAttestationEnvelope(
        dimension=_user_dimension(user_id),
        id=str(uuid.uuid4()),
        score=0.0,
        confidence=1.0,
        claim=claim,
    )
    return LocalAttestationInput(attesting_key_id=attesting_key_id, attestation_envelope=envelope)


def _resolve_attesting_key_id() -> Optional[str]:
    """The agent's federation signer key id (Edge), or None if unavailable."""
    try:
        from ciris_engine.logic.runtime.edge_runtime import get_federation_address

        return get_federation_address()
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("consent-CEG: federation address unavailable: %s", exc)
        return None


def _resolve_engine() -> Optional[object]:
    try:
        from ciris_engine.logic.persistence import get_persist_engine

        return get_persist_engine()
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("consent-CEG: persist engine unavailable: %s", exc)
        return None


def emit_consent_grant(status: ConsentStatus) -> Optional[str]:
    """Best-effort emit a local-tier CEG attestation for a consent grant/modify.

    No-op (returns None) when the flag is off, the engine/key is unavailable,
    or the write fails — emitting the attestation must NEVER break the consent
    write path. Returns the attestation_id on success.
    """
    if not consent_ceg_attestations_enabled():
        return None
    engine = _resolve_engine()
    key_id = _resolve_attesting_key_id()
    if engine is None or not key_id:
        logger.debug("consent-CEG: skip grant emit (engine=%s key=%s)", engine is not None, bool(key_id))
        return None
    try:
        payload = build_consent_grant_input(status, key_id).model_dump_json()
        attestation_id = engine.attestation_upsert_local(payload)  # type: ignore[attr-defined]
        logger.info("consent-CEG: emitted grant attestation %s for user %s", attestation_id, status.user_id)
        return str(attestation_id)
    except Exception as exc:
        logger.warning("consent-CEG: grant emit failed (non-fatal): %s", exc)
        return None


def emit_consent_revocation(user_id: str, reason: Optional[str] = None, promote: bool = True) -> Optional[str]:
    """Best-effort emit + promote a revocation attestation for an opt-out.

    Promotion (local→federation) is itself best-effort: it requires a PQC local
    signer (PROXY/SERVER mode); in CLIENT mode the local revocation row stands
    and promotion is retried at federation-emit time. Never raises.
    """
    if not consent_ceg_attestations_enabled():
        return None
    engine = _resolve_engine()
    key_id = _resolve_attesting_key_id()
    if engine is None or not key_id:
        logger.debug("consent-CEG: skip revocation emit (engine=%s key=%s)", engine is not None, bool(key_id))
        return None
    try:
        payload = build_consent_revocation_input(user_id, key_id, reason).model_dump_json()
        attestation_id = engine.attestation_upsert_local(payload)  # type: ignore[attr-defined]
        logger.info("consent-CEG: emitted revocation attestation %s for user %s", attestation_id, user_id)
    except Exception as exc:
        logger.warning("consent-CEG: revocation emit failed (non-fatal): %s", exc)
        return None
    if promote:
        try:
            engine.attestation_promote(attestation_id)  # type: ignore[attr-defined]
            logger.info("consent-CEG: promoted revocation %s to federation tier", attestation_id)
        except Exception as exc:
            # Expected in CLIENT mode (no PQC signer); the local row is enough.
            logger.debug("consent-CEG: revocation promote deferred (non-fatal): %s", exc)
    return str(attestation_id)


# ===========================================================================
# Community / accord-traces consent — DIRECTED at the canonical CIRIS community
# ===========================================================================
#
# The accord-traces opt-in is the first CEG-native transport experiment: the
# agent consents to share its reasoning traces with the **canonical CIRIS
# community** (the lens). Two nuances are load-bearing:
#
# 1. **Directed, not broadcast.** The consent object carries
#    ``subject_key_ids = [canonical CIRIS community key]`` — it is a *bilateral*
#    trust relationship with that one community, NOT a public attestation that
#    binds or is visible to every other opted-in agent.
#
# 2. **Revocation is the real CEG 1+4 structural primitive, by intent:**
#      - RECANT    ("it was a mistake — delete my data")  → ``recants``  → DSAR deletion
#      - WITHDRAW  ("stop sharing going forward")         → ``withdraws`` → keep history
#      - SUPERSEDE ("change my consent")                  → ``supersedes`` → replace
#    The UI hides the distinction (one "stop / delete" affordance with intent),
#    but only RECANT triggers the DSAR data-deletion cascade. Each structural
#    row references the grant it acts on via ``envelope.target`` and is
#    appended (``attestation_insert_local``), preserving the consent chain.

_COMMUNITY_TRUST_DIMENSION = "consent:community_trust:v1"
_CANONICAL_COMMUNITY_ENV = "CIRIS_CANONICAL_COMMUNITY_KEY_ID"


class RevocationIntent(str, Enum):
    """Maps a user's revoke action to the CEG structural primitive + DSAR semantics."""

    RECANT = "recants"  # mistake / "delete my data" → triggers DSAR deletion
    WITHDRAW = "withdraws"  # stop going forward, retain historical
    SUPERSEDE = "supersedes"  # replaced by a new consent grant


#: Only RECANT invokes the DSAR data-deletion cascade.
INTENT_TRIGGERS_DELETION = {
    RevocationIntent.RECANT: True,
    RevocationIntent.WITHDRAW: False,
    RevocationIntent.SUPERSEDE: False,
}


def canonical_community_key_id() -> Optional[str]:
    """The canonical CIRIS community's federation key id, or None if unpublished.

    Sourced from ``CIRIS_CANONICAL_COMMUNITY_KEY_ID``; falls back to the first
    canonical bootstrap peer once those are published (currently empty — the
    canonical community key ships with lenscore 1.0 / the canonical-peer cut).
    Without it the community-consent object cannot be *directed*, so emit is a
    no-op (we never broadcast an undirected traces-consent attestation).
    """
    explicit = os.environ.get(_CANONICAL_COMMUNITY_ENV, "").strip()
    if explicit:
        return explicit
    try:
        from ciris_engine.constants import CIRIS_CANONICAL_BOOTSTRAP_PEERS

        for peer in CIRIS_CANONICAL_BOOTSTRAP_PEERS or []:
            key = getattr(peer, "key_id", None) or (peer.get("key_id") if isinstance(peer, dict) else None)
            if key:
                return str(key)
    except Exception:  # pragma: no cover - defensive
        pass
    return None


class StructuralAttestationEnvelope(BaseModel):
    """Envelope for a CEG structural primitive (withdraws/recants/supersedes)."""

    model_config = ConfigDict(defer_build=True)

    dimension: str = Field(_COMMUNITY_TRUST_DIMENSION, description="Consent dimension")
    id: str = Field(..., description="Envelope id (uuid4)")
    target: str = Field(..., description="attestation_id of the grant this acts on")
    intent: str = Field(..., description="recants | withdraws | supersedes")
    reason: Optional[str] = Field(None, description="User reason")


class StructuralAttestationInput(BaseModel):
    """Input for a structural primitive via ``attestation_insert_local``."""

    model_config = ConfigDict(defer_build=True)

    attesting_key_id: str = Field(..., description="Producing occurrence's federation key id")
    attestation_type: str = Field(..., description="recants | withdraws | supersedes | delegates_to")
    subject_key_ids: List[str] = Field(default_factory=list, description="Directed-at community key(s)")
    attestation_envelope: StructuralAttestationEnvelope = Field(..., description="Structural envelope")


def build_community_consent_grant(attesting_key_id: str, community_key_id: str) -> LocalAttestationInput:
    """Build the directed traces-consent grant (scores, subject = community)."""
    claim = ConsentClaim(
        user_id=community_key_id,  # the directed counterparty (the canonical community)
        stream="community_trust",
        categories=["accord_traces"],
        state="active",
    )
    envelope = ConsentAttestationEnvelope(
        dimension=_COMMUNITY_TRUST_DIMENSION,
        id=str(uuid.uuid4()),
        score=1.0,
        confidence=1.0,
        claim=claim,
    )
    # Returns the base input; the directed subject_key_ids=[community] is added
    # at serialization time by _directed_payload (not broadcast — bilateral).
    return LocalAttestationInput(attesting_key_id=attesting_key_id, attestation_envelope=envelope)


def _directed_payload(inp: LocalAttestationInput, community_key_id: str) -> str:
    """Serialize a LocalAttestationInput with subject_key_ids=[community]."""
    import json as _json

    data = _json.loads(inp.model_dump_json())
    data["subject_key_ids"] = [community_key_id]
    return _json.dumps(data)


def build_community_structural(
    intent: RevocationIntent, target_id: str, attesting_key_id: str, community_key_id: str, reason: Optional[str] = None
) -> StructuralAttestationInput:
    """Build a withdraws/recants/supersedes row that acts on a prior grant."""
    return StructuralAttestationInput(
        attesting_key_id=attesting_key_id,
        attestation_type=intent.value,
        subject_key_ids=[community_key_id],
        attestation_envelope=StructuralAttestationEnvelope(
            id=str(uuid.uuid4()), target=target_id, intent=intent.value, reason=reason
        ),
    )


def emit_community_consent_grant() -> Optional[str]:
    """Best-effort emit the directed traces-consent grant. Returns attestation_id.

    No-op (None) unless the flag is on, the engine + agent key are available,
    AND the canonical community key is published (we never emit an undirected
    traces-consent object).
    """
    if not consent_ceg_attestations_enabled():
        return None
    engine = _resolve_engine()
    key_id = _resolve_attesting_key_id()
    community = canonical_community_key_id()
    if engine is None or not key_id or not community:
        logger.debug(
            "consent-CEG: skip community grant (engine=%s key=%s community=%s)",
            engine is not None,
            bool(key_id),
            bool(community),
        )
        return None
    try:
        grant = build_community_consent_grant(key_id, community)
        attestation_id = engine.attestation_upsert_local(_directed_payload(grant, community))  # type: ignore[attr-defined]
        logger.info("consent-CEG: emitted directed traces-consent grant %s → community %s", attestation_id, community)
        return str(attestation_id)
    except Exception as exc:
        logger.warning("consent-CEG: community grant emit failed (non-fatal): %s", exc)
        return None


def emit_community_consent_revocation(
    intent: RevocationIntent, target_id: str, reason: Optional[str] = None
) -> Optional[str]:
    """Best-effort emit the structural revocation (recant/withdraw/supersede).

    Returns the structural attestation_id. The caller is responsible for the
    DSAR deletion cascade when ``INTENT_TRIGGERS_DELETION[intent]`` is True
    (RECANT) — this function only writes the CEG structural row + promotes it.
    """
    if not consent_ceg_attestations_enabled():
        return None
    engine = _resolve_engine()
    key_id = _resolve_attesting_key_id()
    community = canonical_community_key_id()
    if engine is None or not key_id or not community:
        return None
    try:
        row = build_community_structural(intent, target_id, key_id, community, reason)
        attestation_id = engine.attestation_insert_local(row.model_dump_json())  # type: ignore[attr-defined]
        logger.info("consent-CEG: emitted %s on %s (community %s)", intent.value, target_id, community)
    except Exception as exc:
        logger.warning("consent-CEG: community revocation emit failed (non-fatal): %s", exc)
        return None
    try:
        engine.attestation_promote(attestation_id)  # type: ignore[attr-defined]
    except Exception as exc:
        logger.debug("consent-CEG: structural promote deferred (non-fatal): %s", exc)
    return str(attestation_id)
