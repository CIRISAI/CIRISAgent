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

Default ON as of 2.9.6 (the LensCore fold, CIRISAgent#866): the CEG
attestation IS the consent wire artifact. In the SOVEREIGN LensClient path
(``engine=None``) lens-core's per-seal consent gate reads
`consent:community_trust:v1` by the agent's federation key directly. In the
agent's actual runtime — the COHABITATION path (``engine=`` passed
explicitly, see ciris_accord_metrics/services.py) — lens-core does NOT read
the CEG row (``consent_attesting_key_id`` has no effect there; the cross-wheel
directory accessor is the unwired CIRISEdge#85 follow-up). There the grant
gates INDIRECTLY: the accord adapter reads it at boot via
``current_community_grant_id()`` and derives ``_consent_given``, which feeds
the config-fallback consent the seal gate consults. Either way opt-in (grant)
and revocation (withdraws/recants) only function if these emits run.
``CIRIS_CONSENT_CEG_ATTESTATIONS=false`` remains as an emergency kill-switch.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import logging
import os
import uuid
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.logic.utils.log_sanitizer import sanitize_for_log

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
    """True unless explicitly disabled (default ON as of 2.9.6).

    The consent→CEG write is no longer a dual-write experiment: the CEG
    attestation IS the consent artifact. It drives emission either directly
    (sovereign LensClient path, ``engine=None`` — lens-core reads the
    `consent:community_trust:v1` dimension at seal) or indirectly (the agent's
    cohabitation path, ``engine=`` passed — the adapter reads the grant at boot
    and derives the config-fallback consent the seal gate consults; the direct
    CEG-read gate in cohabitation is the unwired CIRISEdge#85 follow-up).
    CIRISAgent#866 fold; opt-in = grant, revoke = withdraws/recants. The flag
    remains only as an emergency kill-switch (CIRIS_CONSENT_CEG_ATTESTATIONS=false).
    """
    return os.environ.get(_FEATURE_FLAG_ENV, "").strip().lower() not in ("0", "false", "no", "off")


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
        logger.info(
            "consent-CEG: emitted grant attestation %s for user %s",
            attestation_id,
            sanitize_for_log(status.user_id),
        )
        return str(attestation_id)
    except Exception as exc:
        logger.warning("consent-CEG: grant emit failed (non-fatal): %s", exc)
        return None


# --- v40 tier crossing --------------------------------------------------------
# `attestation_promote` is gone (persist v39, CIRISAgent#1134/#1144). It re-signed
# the row with THIS NODE's key and cleared the actor's scrub, so the node became
# the author of a claim it was only carrying -- and because peers verify against
# `attesting_key_id`, an agent-attested promoted row was refused at every peer
# while the call returned True here. Two verbs replace it: `enter_mesh` crosses
# local -> federation tier over the SAME bytes (the node may only co-scrub), and
# `widen_audience` writes a `supersedes` the ACTOR signs at a wider audience.
# The server composes them this way for its own consent, moderation, age and
# watchlist rows (CIRISServer src/attestation_crossing.rs): enter over the row's
# own placement, stop on `awaiting_actor`, else widen to `federation` with the
# producer-authority basis and no stripped members. Three things the issue text
# under-sells, each handled here: `awaiting_actor` is an Ok that did nothing
# (read the outcome by NAME); a widening leaves TWO rows and the placed one has
# a NEW id (return the placed id -- it is what peers can read); every axis of the
# crossing is cross-checked and refused by its name (let that surface).
_CROSSING_BASIS_PRODUCER_AUTHORITY = '{"kind": "producer_authority"}'
_CROSSING_TARGET_FEDERATION = "federation"
_OUTCOME_PLACED = frozenset({"crossed", "already_in_mesh"})


def cross_to_mesh(engine: object, attestation_id: str, *, label: str) -> "tuple[str, Optional[str]]":
    """Enter the mesh and widen to the federation audience. Returns (outcome, placed_id).

    `outcome` is the name persist reports for the LAST step taken (`crossed` |
    `already_in_mesh` | `already_widened` | `awaiting_actor`); `placed_id` is the
    row id peers can read, or None when nothing new was placed. Raises what
    persist raises: an axis refusal names the axis and must not be hidden.
    """
    aid = str(attestation_id)
    ci_self = engine.describe_crossing(aid, "self", None, _CROSSING_BASIS_PRODUCER_AUTHORITY)  # type: ignore[attr-defined]
    entered = engine.enter_mesh(aid, ci_self)  # type: ignore[attr-defined]
    outcome = str(entered.get("outcome", "unknown")) if isinstance(entered, dict) else "unknown"
    if outcome == "awaiting_actor":
        # Not an error: the row is attested by a key whose signer this engine does
        # not hold and it carries no signature from write time. Persist will not
        # sign it with the node's key. It WAITS; the callers say what that means.
        return outcome, None
    ci_fed = engine.describe_crossing(aid, _CROSSING_TARGET_FEDERATION, None, _CROSSING_BASIS_PRODUCER_AUTHORITY)  # type: ignore[attr-defined]
    widened = engine.widen_audience(aid, ci_fed, [])  # type: ignore[attr-defined]
    w_outcome = str(widened.get("outcome", "unknown")) if isinstance(widened, dict) else "unknown"
    placed_raw = widened.get("attestation_id") if isinstance(widened, dict) else None
    placed = str(placed_raw) if placed_raw and w_outcome in _OUTCOME_PLACED else None
    return w_outcome, placed


def _log_crossing(label: str, attestation_id: str, outcome: str, placed: Optional[str], *, waiting_reads_as: str) -> None:
    if outcome == "awaiting_actor":
        logger.warning(
            "consent-CEG: %s %s is waiting for its actor's signature -- it has NOT reached the mesh; %s",
            label, attestation_id, waiting_reads_as,
        )
    elif placed and placed != str(attestation_id):
        logger.info("consent-CEG: %s %s placed at federation as %s (%s)", label, attestation_id, placed, outcome)
    else:
        logger.info("consent-CEG: %s %s crossing outcome: %s", label, attestation_id, outcome)


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
        logger.info(
            "consent-CEG: emitted revocation attestation %s for user %s",
            attestation_id,
            sanitize_for_log(user_id),
        )
    except Exception as exc:
        logger.warning("consent-CEG: revocation emit failed (non-fatal): %s", exc)
        return None
    placed: Optional[str] = None
    if promote:
        try:
            outcome, placed = cross_to_mesh(engine, str(attestation_id), label="revocation")
            _log_crossing("revocation", str(attestation_id), outcome, placed,
                          waiting_reads_as='peers keep reading the consent as GRANTED until it does')
        except Exception as exc:  # noqa: BLE001
            # Expected in CLIENT mode (no PQC signer): the local row stands. An axis
            # refusal also lands here and its message names the axis -- keep it visible.
            logger.warning("consent-CEG: %s crossing deferred (non-fatal): %s", "revocation", exc)
    return placed or str(attestation_id)


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
    # Substrate fallback: persist v13.4.0+ genesis-bakes the canonical server
    # (ciris-canonical-1) into the CEG on node boot; when this engine carries
    # that row (post node-fold, or a seeded install), read it directly — the
    # fabric produced the record, the agent just consumes it. Bare agent
    # engines (no node boot) return [] here and we stay unpublished.
    try:
        import json as _json

        engine = _resolve_engine()
        if engine is not None:
            rows = _json.loads(engine.list_canonical_servers() or "[]")  # type: ignore[attr-defined]
            for row in rows:
                key = row.get("key_id") if isinstance(row, dict) else None
                if key:
                    return str(key)
    except Exception:  # pragma: no cover - defensive (engine absent / pre-v13 substrate)
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


def build_community_consent_grant(
    attesting_key_id: str, community_key_id: str, granted_at: Optional[str] = None
) -> LocalAttestationInput:
    """Build the directed traces-consent grant (scores, subject = community).

    ``granted_at`` carries the ORIGINAL consent time when migrating a legacy
    consent artifact (.env / adapter-config) — the CEG object must preserve
    when the human actually consented, not when the migration ran.
    """
    claim = ConsentClaim(
        user_id=community_key_id,  # the directed counterparty (the canonical community)
        stream="community_trust",
        categories=["accord_traces"],
        state="active",
        granted_at=granted_at,
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


_SCOPE_RANK = {"self": 0, "family": 1, "community": 2, "affiliations": 3, "species": 4, "biosphere": 5, "federation": 6}


def _grant_sort_key(row: "dict[str, object]") -> "tuple[datetime, int]":
    """Newest claim first; among rows of ONE claim, the widest placement.

    A widening (persist v40) is a `supersedes` at a wider audience that carries
    the claim's own `asserted_at` verbatim, so the original self-scoped row and
    its placed federation copy TIE on the instant. The one peers can read is the
    wider one, and it is the one `capture_grant_id` and a revocation target must
    name (CIRISAgent#1144). Persist#798 will fold this on their side; until then
    the tiebreak is ours.
    """
    return _instant(row), _SCOPE_RANK.get(str(row.get("cohort_scope") or "self"), 0)


def _instant(row: "dict[str, object]") -> "datetime":
    """Sort key for a persist row's ``asserted_at``: the INSTANT, never its rendering.

    Persist v39 moved signed instants from microsecond to millisecond resolution
    (CC 2.6.2), so a corpus that spans the upgrade carries both ``.049840Z`` and
    ``.049Z`` -- and lexically ``.049840Z`` < ``.049Z`` because ``'8'`` < ``'Z'``.
    Sorting the string picked a pre-v39 grant asserted LATER as older than a
    post-v39 grant in the same second (CIRISAgent#1136). Persist's own
    ``check_instant_binding`` parses tolerantly for the same reason; so do we.
    An unparseable value sorts last.
    """
    raw = str(row.get("asserted_at") or "")
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


def current_community_grant_id() -> Optional[str]:
    """attestation_id of the current community-trust grant, or None.

    The structural primitives (withdraws/recants/supersedes) reference this as
    their ``target``. Reads via ``list_attestations`` (dimension_exact-scoped)
    and picks the latest ``scores`` row on the community-trust dimension.

    Stays on ``list_attestations`` — NOT the ``list_scores`` seek that
    ``_newest_community_trust_row`` adopted in 2.9.7 — because this lookup must
    find the INTERIM grant (unpromoted, written while the canonical community
    key is unpublished) so a user's withdrawal can target it. ``list_scores``
    seeks the V106 ``subject_key_ids`` projection, and the interim grant is
    emitted UNDIRECTED (``subject_key_ids=[]`` so it can never federate) → it
    projects zero V106 rows → invisible to ``list_scores`` at EVERY tier
    (CIRISPersist#461: tier was a red herring, subject-presence is the axis).
    ``list_attestations`` sees all tiers AND subjectless rows, so it stays.

    CIRISPersist#461 seal-gate confirmation (empirically resolved 2026-07,
    ciris-server 0.5.118 / persist v17.5.2 wheel):

      * The subjectless interim grant is INVISIBLE to ``list_scores`` at every
        tier (Local/Any/Federation → 0 rows); ``list_attestations`` sees it
        (1 row, tier=local). Confirmed by a live throwaway-engine probe.
      * lens-core's per-seal consent gate does NOT read this CEG row in the
        agent's runtime path. The agent constructs ``LensClient`` with an
        explicit ``engine=`` (the COHABITATION path, services.py); the wheel's
        own ``LensClient`` docstring states ``consent_attesting_key_id`` "has
        no effect when ``engine=`` is provided" — cohabitation uses the
        CONFIG-FALLBACK consent path only. The CEG engine-read gate needs a
        cross-wheel ``federation_directory`` accessor that is NOT yet wired:
        upstream follow-up CIRISEdge#85.
      * So the interim grant DOES gate local emission today, but INDIRECTLY:
        the accord adapter reads it at boot via THIS function (list_attestations
        → ``_consent_given=True``), which then feeds the config-fallback
        ``consent_timestamp`` the seal gate actually consults. Migrating this
        lookup to ``list_scores`` would return None for the subjectless interim
        grant → ``_consent_given`` stays False → every seal resolves NoConsent
        → all traces blocked. list_attestations is therefore load-bearing here
        for BOTH revocation targeting AND boot consent-derivation.

    Deferred self-subject migration (only when CIRISEdge#85 lands the
    cohabitation CEG-read gate, OR the agent adopts the sovereign engine=None
    LensClient path): give the interim grant ``subject_key_ids=[self]`` (still
    ``attestation_upsert_local`` → tier=local, so no-federate is preserved by
    TIER per persist#461) and migrate this lookup to ``list_scores(tier="Any")``
    — the live probe confirms a self-subject local row IS visible there while
    staying invisible to Federation tier and to default-tier list_scores. Until
    then the emit stays subjectless and this dimension_exact-scoped
    list_attestations read is the correct one.
    """
    engine = _resolve_engine()
    key_id = _resolve_attesting_key_id()
    if engine is None or not key_id:
        return None
    try:
        import json as _json

        # dimension_exact is honored at the substrate as of persist v17.5.2
        # (CIRISPersist#461 — it was a silent no-op before), so the query is
        # dimension-scoped and the community-trust row can't fall off page 1 as
        # per-user consent rows accumulate. list_attestations (not list_scores)
        # is still required: it sees ALL tiers AND subjectless rows, so the
        # UNDIRECTED interim grant remains findable for revocation targeting.
        page = _json.loads(
            engine.list_attestations(_json.dumps({"dimension_exact": _COMMUNITY_TRUST_DIMENSION}), None, 100, key_id)  # type: ignore[attr-defined]
        )
        rows = page.get("items", [])
        grants = [r for r in rows if r.get("attestation_type") == "scores"]
        if not grants:
            return None
        grants.sort(key=_grant_sort_key, reverse=True)
        return str(grants[0].get("attestation_id"))
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("consent-CEG: grant lookup failed: %s", exc)
        return None


def current_community_grant_asserted_at() -> Optional[str]:
    """``asserted_at`` of the current community-trust grant, or None.

    Companion to :func:`current_community_grant_id`. The accord service derives
    its config-fallback consent from the CEG grant (the source of truth in the
    cohabitation seal path — see that adapter's boot/self-heal derivation), and
    needs the grant's timestamp so the fallback ``consent_timestamp`` is STABLE
    across restarts rather than stamping a fresh ``now()`` each boot (the
    warning at services.py where consent is set without a timestamp). Uses the
    SAME ``list_attestations`` read + newest-``scores`` selection as the id
    lookup so the two stay consistent (they resolve the same row).
    """
    engine = _resolve_engine()
    key_id = _resolve_attesting_key_id()
    if engine is None or not key_id:
        return None
    try:
        import json as _json

        page = _json.loads(
            engine.list_attestations(_json.dumps({"dimension_exact": _COMMUNITY_TRUST_DIMENSION}), None, 100, key_id)  # type: ignore[attr-defined]
        )
        rows = page.get("items", [])
        grants = [r for r in rows if r.get("attestation_type") == "scores"]
        if not grants:
            return None
        grants.sort(key=_grant_sort_key, reverse=True)
        asserted_at = grants[0].get("asserted_at")
        return str(asserted_at) if asserted_at else None
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("consent-CEG: grant timestamp lookup failed: %s", exc)
        return None


# Sentinel counterparty for the interim LOCAL-TIER grant emitted while the
# canonical community key is unpublished. A local-tier row (no promotion,
# subject_key_ids=[]) can never federate, so the "consent objects are
# directed, never broadcast" invariant is preserved by construction — the
# row is readable only by this occurrence's own substrate (which is exactly
# what lens-core's per-seal consent gate reads). When the canonical key
# publishes, the directed grant upserts over this row (same dimension).
_PENDING_COMMUNITY_SENTINEL = "ciris:canonical-community:pending"


def emit_community_consent_grant(granted_at: Optional[str] = None) -> Optional[str]:
    """Best-effort emit the traces-consent grant. Returns attestation_id.

    This is THE consent wire artifact (2.9.6 #866). In the sovereign LensClient
    path lens-core's consent gate resolves the newest row on
    ``consent:community_trust:v1`` by the agent's federation key at every trace
    seal; in the agent's cohabitation path the grant instead drives the
    config-fallback consent the seal gate reads, via the adapter's boot-time
    ``current_community_grant_id()`` derivation (see that function's docstring
    for the confirmed CIRISPersist#461 seal-gate finding). Two shapes:

    - Canonical community key published → the DIRECTED grant
      (subject_key_ids=[community]) — the CEG promotion event self→community.
    - Key unpublished (interim) → an UNDIRECTED LOCAL-TIER grant that gates
      local emission but cannot federate (never promoted, no subjects), so
      nothing undirected ever leaves the occurrence. NOTE: the interim grant is
      emitted subjectless deliberately — it is found by ``list_attestations``
      (which sees subjectless local rows), NOT ``list_scores`` (V106 subject
      seek, blind to it). See current_community_grant_id for why that read
      split must be preserved.

    No-op (None) when the kill-switch is set or engine/key are unavailable.
    """
    if not consent_ceg_attestations_enabled():
        return None
    engine = _resolve_engine()
    key_id = _resolve_attesting_key_id()
    if engine is None or not key_id:
        logger.debug("consent-CEG: skip community grant (engine=%s key=%s)", engine is not None, bool(key_id))
        return None
    community = canonical_community_key_id()
    try:
        grant = build_community_consent_grant(key_id, community or _PENDING_COMMUNITY_SENTINEL, granted_at=granted_at)
        if community:
            attestation_id = engine.attestation_upsert_local(_directed_payload(grant, community))  # type: ignore[attr-defined]
            logger.info(
                "consent-CEG: emitted directed traces-consent grant %s → community %s", attestation_id, community
            )
            # The directed grant IS the CEG promotion event self→community —
            # promote it to federation tier so the counterparty can actually
            # receive it (a local-tier row never leaves the occurrence).
            # Best-effort, mirroring the revocation path: deferred in CLIENT
            # mode (no PQC signer); the local row still gates the seal.
            try:
                outcome, placed = cross_to_mesh(engine, str(attestation_id), label="directed grant")
                _log_crossing("directed grant", str(attestation_id), outcome, placed,
                              waiting_reads_as='the community cannot see the grant, so traces will seal locally and not replicate')
                if placed:
                    # THE COMMUNITY IDENTITY OF THE GRANT IS THE WIDENED ROW'S ID: capture_grant_id
                    # and the revocation target carry it to peers; the self-scoped original is
                    # a row they cannot read (CIRISAgent#1144).
                    attestation_id = placed
            except Exception as exc:  # noqa: BLE001
                # Expected in CLIENT mode (no PQC signer): the local row stands. An axis
                # refusal also lands here and its message names the axis -- keep it visible.
                logger.warning("consent-CEG: %s crossing deferred (non-fatal): %s", "directed grant", exc)
        else:
            attestation_id = engine.attestation_upsert_local(grant.model_dump_json())  # type: ignore[attr-defined]
            logger.info(
                "consent-CEG: emitted INTERIM local-tier traces-consent grant %s "
                "(canonical community key unpublished — gates local emission only, "
                "directed grant supersedes when the key ships)",
                attestation_id,
            )
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
    if engine is None or not key_id:
        return None
    # A revocation MUST be writable even while the canonical community key is
    # unpublished — lens-core's gate hard-stops on the newest withdraws/recants
    # row regardless of direction, and a user's recant may never be blocked on
    # upstream key publication. Undirected structural rows stay local-tier
    # (no promotion), mirroring the interim grant.
    community = canonical_community_key_id()
    try:
        row = build_community_structural(intent, target_id, key_id, community or "", reason)
        if not community:
            row.subject_key_ids = []
        attestation_id = engine.attestation_insert_local(row.model_dump_json())  # type: ignore[attr-defined]
        logger.info(
            "consent-CEG: emitted %s on %s (%s)",
            intent.value,
            target_id,
            f"community {community}" if community else "interim local-tier",
        )
    except Exception as exc:
        logger.warning("consent-CEG: community revocation emit failed (non-fatal): %s", exc)
        return None
    placed: Optional[str] = None
    if community:
        try:
            outcome, placed = cross_to_mesh(engine, str(attestation_id), label=f"{intent.value} revocation")
            _log_crossing(f"{intent.value} revocation", str(attestation_id), outcome, placed,
                          waiting_reads_as='the community keeps reading the grant as in force')
        except Exception as exc:  # noqa: BLE001
            # Expected in CLIENT mode (no PQC signer): the local row stands. An axis
            # refusal also lands here and its message names the axis -- keep it visible.
            logger.warning("consent-CEG: %s crossing deferred (non-fatal): %s", f"{intent.value} revocation", exc)
    return placed or str(attestation_id)


def federation_consent_status() -> "dict[str, object]":
    """CONSENT DRY (all four opt-in paths): resolve the FULL trace-sharing
    consent set through the engine's OWN readers — never row-existence.

    v22 (ciris-server 0.5.139+) needs THREE aligned artifacts for a sealed
    trace to be captured, shipped, and scorable:

    1. ``consent:community_trust:v1`` — capture/seal gate (this module owns it)
    2. ``consent:replication:v1`` naming the canonical — ship gate; resolved
       via ``list_consent_peers`` (the projection edge actually reads — a row
       can exist while being invisible to edge, per the 0.5.139 consent DX)
    3. ``consent:state:granted:v1`` scope=analyze naming the canonical's
       DERIVED key — CC#46 score gate (resolver not yet py-exposed; reported
       "unknown" until it is — never guessed from rows)

    The four opt-in paths (wizard, data card, legacy-convert, env var) all
    reduce to: paths WITH an owner session author via the owner-gated
    ``POST /v1/federation/consent`` (the Kotlin client's
    ``authorFederationConsent``); paths WITHOUT one (boot/env) must never
    silently author an owner-tier grant — they call THIS to detect drift and
    surface "confirmation needed" on the Manage Consent card instead. That is
    the same explicit-consent principle that removed server auto-consent.

    Returns a dict: ``capture`` / ``replication`` / ``analyze`` each
    ``True``/``False``/``None`` (None = resolver unavailable), ``canonical``
    (the peer checked), and ``aligned`` (True only when every resolvable gate
    is green). Never raises.
    """
    status: "dict[str, object]" = {
        "capture": None,
        "replication": None,
        "analyze": None,
        "canonical": None,
        "aligned": False,
    }
    try:
        status["capture"] = current_community_grant_id() is not None
    except Exception as exc:  # noqa: BLE001
        logger.debug("consent-DRY: capture resolution failed: %s", exc)
    engine = _resolve_engine()
    key_id = _resolve_attesting_key_id()
    if engine is None or not key_id:
        return status
    try:
        import json as _json

        canon = _json.loads(engine.list_canonical_servers() or "[]")  # type: ignore[attr-defined]
        canonical = canon[0].get("key_id") if canon else None
        status["canonical"] = canonical
        if canonical:
            peers = engine.list_consent_peers(key_id)  # type: ignore[attr-defined]
            peer_ids = peers if isinstance(peers, list) else _json.loads(peers or "[]")
            status["replication"] = any(canonical in str(p) for p in peer_ids)
    except Exception as exc:  # noqa: BLE001
        logger.debug("consent-DRY: replication resolution failed: %s", exc)
    # CC#46 analyze: resolve through the engine's scoped-consent resolver the
    # moment it is py-exposed (assert-the-resolved-stance; a row that folds to
    # Unspecified is the silent false the DX doc warns about).
    resolver = getattr(engine, "resolve_scoped_consent", None)
    if resolver is not None and status["canonical"]:
        try:
            stance = resolver(str(status["canonical"]), "analyze")
            status["analyze"] = "granted" in str(stance).lower()
        except Exception as exc:  # noqa: BLE001
            logger.debug("consent-DRY: analyze resolution failed: %s", exc)
    resolvable = [v for v in (status["capture"], status["replication"], status["analyze"]) if v is not None]
    status["aligned"] = bool(resolvable) and all(resolvable)
    return status


def log_federation_consent_drift(reason: str) -> None:
    """Boot/env-path detector (opt-in paths 3+4): when capture consent says
    YES but the federation grants are missing, say so LOUDLY with the exact
    remedy — never silently author an owner-tier grant from a session-less
    path. The Manage Consent card completes it with one owner-session call
    (``authorFederationConsent``)."""
    try:
        st = federation_consent_status()
        if st["capture"] and st["replication"] is False:
            logger.warning(
                "[CONSENT-DRY] capture consent is ON (%s) but consent:replication for "
                "canonical %s is NOT resolved via list_consent_peers — sealed traces "
                "will NOT replicate. Remedy: confirm sharing on the Manage Consent "
                "card (owner session -> POST /v1/federation/consent).",
                reason,
                st["canonical"],
            )
        elif st["capture"] and st["analyze"] is False:
            logger.warning(
                "[CONSENT-DRY] capture+replication consents resolved but the CC#46 "
                "analyze grant for %s is NOT — traces will ship but never be scored. "
                "Remedy: re-confirm sharing on the Manage Consent card.",
                st["canonical"],
            )
        else:
            logger.info("[CONSENT-DRY] consent status (%s): %s", reason, st)
    except Exception as exc:  # noqa: BLE001
        logger.debug("[CONSENT-DRY] drift check failed (non-fatal): %s", exc)
