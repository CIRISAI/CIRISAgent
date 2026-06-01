"""CEG 0.9 attestation-intent schemas.

The agent authors the *semantic* portion of a CEG attestation — the "intent".
The CEG **envelope** (canonical bytes, ``attesting_key_id``, signature,
``valid_at``, federation transport) is constructed by the cohabiting LensCore
substrate (Rust, pinned to a Registry-published CEG version), not here. This
split is normative in CEG 0.9 §11.9 ("agent-intent / LensCore-envelope split")
and is what keeps CEG-version churn out of Python: when the envelope shape
changes (e.g. 0.9 -> 1.0), LensCore bumps its pin and the agent's intent is
unchanged.

Spec: ``CIRISRegistry/FSD/CEG`` @ **0.9**.
  - §4   envelope field set + required/optional/conditional + defaults
  - §2   grammar axes (epistemic_mode, stake, scope, witness_relation)
  - §8.1.8 cohort_scope semantics (self -> local_feed only; promotion widens)
  - §7.5 capacity:* self-emission ban (anti-Goodhart) — enforced client-side here
  - §11.9 agent-intent / LensCore-envelope split + capacity / reasoning-trace
          resolutions
  - §13.5 self-declaration discipline: richer state goes in ``context`` /
          ``evidence_refs`` — NOT new prefixes or envelope fields

Fields the substrate fills (NOT in this model, by design):
  ``attesting_key_id`` (always the signing federation key), ``valid_at``
  (signing time), the signature(s), and the canonical-bytes serialization.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator


class EpistemicMode(str, Enum):
    """CEG §2 epistemic-mode axis. Default ``direct``."""

    DIRECT = "direct"
    CRYPTO = "crypto"
    HEARSAY = "hearsay"
    DERIVATIVE = "derivative"
    APPEAL = "appeal"


class WitnessRelation(str, Enum):
    """CEG §2/§4 witness-relation axis. Envelope default is ``external``.

    The agent's own reasoning / audit / trace stream is direct self-knowledge
    and MUST set ``self`` explicitly (the default is not self).
    """

    SELF = "self"
    EXTERNAL = "external"
    DERIVED = "derived"


class OversightMode(str, Enum):
    """CEG §4 oversight-mode axis. Envelope default is null (unset)."""

    HITL = "HITL"  # human in the loop
    HOTL = "HOTL"  # human on the loop
    HOOTL = "HOOTL"  # human out of the loop


class Stake(str, Enum):
    """CEG §2 stake axis. Default ``reputational``."""

    FREE = "free"
    REPUTATIONAL = "reputational"
    CAPITAL = "capital"
    CRYPTOECONOMIC = "cryptoeconomic"


class CohortScope(str, Enum):
    """CEG §2 scope axis / §8.1.8 cohort_scope.

    Visibility/sharing tier, orthogonal to ``witness_relation`` (epistemic
    provenance). Per §8.1.8.1 a locally-produced attestation starts at
    ``self`` and appears only in the local feed; an opt-in share *promotes*
    it to a wider scope. ``community`` is the narrowest scope that federates
    (§8.1.13.3), so it is the floor for any trace shared to an external
    observer peer such as the CIRIS bootstrap lens.
    """

    SELF = "self"
    FAMILY = "family"
    COMMUNITY = "community"
    AFFILIATIONS = "affiliations"
    SPECIES = "species"
    BIOSPHERE = "biosphere"
    FEDERATION = "federation"


class OccurrenceRole(str, Enum):
    """CEG §4 occurrence-role axis. Default ``primary``."""

    PRIMARY = "primary"
    SHARED = "shared"
    REPLICA = "replica"


class AttestationIntent(BaseModel):
    """Agent-authored semantic content of a single CEG attestation.

    One ``AttestationIntent`` is produced at every emission point (an audit
    entry, a reasoning-trace verdict, a consent record, an observation about a
    user). LensCore consumes it and constructs the signed CEG envelope.

    Dimension authority: ``dimension`` is validated against the pinned CEG
    namespace (``dimensions.json``) at envelope-construction time in LensCore,
    NOT here — hard-coding the 0.9 namespace in Python would re-create the
    #842 version-lock trap. This model only checks shape + the one client-side
    invariant the agent owns (capacity self-emission, §7.5).
    """

    # --- required core (§4) ---
    dimension: str = Field(
        ...,
        min_length=1,
        description="Canonical namespace prefix + scoped leaf (e.g. 'conscience:coherence', "
        "'dma:pdma:beneficence', 'observed:user:<hash>'). Authoritative validation against "
        "the pinned CEG dimensions.json happens at envelope construction in LensCore.",
    )
    score: float = Field(..., ge=-1.0, le=1.0, description="§4 polarity scalar in [-1, +1].")
    confidence: float = Field(..., ge=0.0, le=1.0, description="§4 attester's own confidence in the score, [0, 1].")

    # --- subject / consent (§4, CEG 0.6 subject_key_ids) ---
    attested_key_id: Optional[str] = Field(
        default=None,
        description="Subject's federation key_id. None => self-attestation (substrate sets "
        "attested == attesting agent key). Set to another key/canonical-hash for claims about "
        "others (e.g. observed:user:*).",
    )
    subject_key_ids: List[str] = Field(
        default_factory=list,
        description="Consent-holder key_ids (CEG 0.6). Subject-bearing dimensions (observed:user:*, "
        "consent:*, anything naming a third party) MUST list that subject here so it retains "
        "wire-level revocation authority.",
    )

    # --- evidence / scoping (§4, §13.5) ---
    context: Optional[str] = Field(
        default=None,
        description="§4 free-form scoping detail; not parsed by substrate.",
    )
    evidence_refs: List[str] = Field(
        default_factory=list,
        description="§4 URIs / content-hashes for backing evidence. Reasoning traces decompose into "
        "dma:*/conscience:* score attestations whose raw reasoning blob is referenced here by "
        "content-hash (§11.9.2 / §13.5 — NO new reasoning:trace:* prefix family).",
    )
    valid_until: Optional[datetime] = Field(
        default=None, description="§4 ISO-8601; treated as stale after this point."
    )

    # --- grammar axes (§2), all defaulted to the envelope defaults ---
    epistemic_mode: EpistemicMode = Field(default=EpistemicMode.DIRECT, description="§2; default direct.")
    witness_relation: WitnessRelation = Field(
        default=WitnessRelation.EXTERNAL,
        description="§2/§4; envelope default external. Self-stream emissions must set SELF.",
    )
    oversight_mode: Optional[OversightMode] = Field(default=None, description="§4; default unset.")
    stake: Stake = Field(default=Stake.REPUTATIONAL, description="§2; default reputational.")

    # --- visibility / sharing (§8.1.8) ---
    cohort_scope: CohortScope = Field(
        default=CohortScope.SELF,
        description="§8.1.8; produced at self, promoted on opt-in share. community is the floor "
        "for federating a trace to an external observer peer.",
    )
    community_id: Optional[str] = Field(
        default=None, description="§4; REQUIRED iff cohort_scope == community."
    )
    family_id: Optional[str] = Field(default=None, description="§4; REQUIRED iff cohort_scope == family.")

    # --- multi-occurrence (§4) ---
    occurrence_id: Optional[str] = Field(
        default=None, description="§4 'occurrence-{n}'; None => occurrence-0. Maps from AGENT_OCCURRENCE_ID."
    )
    occurrence_count: Optional[int] = Field(default=None, ge=1, description="§4; None => 1.")
    occurrence_role: Optional[OccurrenceRole] = Field(default=None, description="§4; None => primary.")

    @model_validator(mode="after")
    def _check_cohort_and_capacity(self) -> "AttestationIntent":
        # §4 conditional requirements
        if self.cohort_scope == CohortScope.COMMUNITY and not self.community_id:
            raise ValueError("community_id is REQUIRED when cohort_scope == community (CEG §4)")
        if self.cohort_scope == CohortScope.FAMILY and not self.family_id:
            raise ValueError("family_id is REQUIRED when cohort_scope == family (CEG §4)")

        # §7.5 anti-Goodhart, enforced client-side (CEG-native adoption plan, CIRISAgent#834):
        # capacity:* is peer-conferred and MUST NOT be self-emitted. attested_key_id == None
        # means self-attestation, which the substrate would reject for capacity:*.
        if self.dimension.startswith("capacity:"):
            if self.attested_key_id is None:
                raise ValueError(
                    "capacity:* may not be self-emitted (CEG §7.5 anti-Goodhart): set attested_key_id "
                    "to a peer subject; capacity is peer-conferred, never self-scored."
                )
            if self.witness_relation == WitnessRelation.SELF:
                raise ValueError("capacity:* must not carry witness_relation=self (CEG §7.5).")
        return self
