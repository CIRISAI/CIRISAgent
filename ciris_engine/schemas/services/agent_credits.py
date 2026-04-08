"""
Commons Credits: Off-chain signed attestation records of bilateral verified interactions.

Credits are NOT tokens, NOT currency, NOT on-chain. They are recognition —
"giving someone credit" not "credit card." They exist as dual-signed
(Ed25519 + ML-DSA-65) attestations stored via persistent HW-rooted agent
identities (CIRISVerify).

Credits function as governance weight: deferral routing priority, domain
certification, WA consensus voting weight, anti-sybil policy votes, dispute
resolution, luxury goods distribution, and discovery preference.

USDC (wallet adapter) is completely separate — for paying for services only.

See FSD/COMMONS_CREDITS.md for the full specification.
See CCA paper (Zenodo 18217688) for the k_eff quality measurement.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class InteractionOutcome(str, Enum):
    """Outcome of a bilateral agent interaction."""

    RESOLVED = "resolved"
    PARTIAL = "partial"
    UNRESOLVED = "unresolved"
    REJECTED = "rejected"


class DomainCategory(str, Enum):
    """Licensed domain categories that trigger auto-deferral via WiseBus.

    Maps to REQUIRES_SEPARATE_MODULE prohibitions in prohibitions.py.
    """

    MEDICAL = "MEDICAL"
    FINANCIAL = "FINANCIAL"
    LEGAL = "LEGAL"
    HOME_SECURITY = "HOME_SECURITY"
    IDENTITY_VERIFICATION = "IDENTITY_VERIFICATION"
    CONTENT_MODERATION = "CONTENT_MODERATION"
    RESEARCH = "RESEARCH"
    INFRASTRUCTURE_CONTROL = "INFRASTRUCTURE_CONTROL"


class DualSignature(BaseModel):
    """Ed25519 + ML-DSA-65 dual signature for quantum safety.

    Both signatures must verify for a record to be valid.
    Today Ed25519 provides security; ML-DSA-65 future-proofs.
    """

    model_config = ConfigDict(extra="forbid", defer_build=True)

    ed25519_signature: str = Field(..., description="Base64url-encoded Ed25519 signature")
    ed25519_key_id: str = Field(..., description="Signing key ID (agent-{hash[:12]})")
    ml_dsa_65_signature: Optional[str] = Field(
        None,
        description="Base64url-encoded ML-DSA-65 signature (when PQ available)",
    )
    ml_dsa_65_key_id: Optional[str] = Field(
        None,
        description="ML-DSA-65 key ID (when PQ available)",
    )


class GratitudeSignal(BaseModel):
    """The 'S' in CIRIS (Signalling Gratitude) made concrete.

    An explicit quality signal from one agent to another, dual-signed.
    Closes the bilateral verification loop as a cryptographic event.
    """

    model_config = ConfigDict(extra="forbid", defer_build=True)

    from_agent_id: str = Field(..., description="Ed25519 pubkey hash of signaling agent")
    to_agent_id: str = Field(..., description="Ed25519 pubkey hash of receiving agent")
    interaction_id: str = Field(..., description="ID of the interaction being acknowledged")
    quality_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Quality rating 0.0-1.0 of the interaction",
    )
    message: Optional[str] = Field(
        None,
        max_length=280,
        description="Optional gratitude message",
    )
    signature: DualSignature = Field(..., description="Dual signature of the signaling agent")
    timestamp: datetime = Field(..., description="When the signal was created")


class CreditRecord(BaseModel):
    """A signed attestation of a verified bilateral interaction.

    NOT a token. NOT currency. A self-authenticating record of mutual benefit
    verified against the coherence ratchet. Dual-signed by both parties plus
    node attestation. Verifiable offline.

    The interaction_id is deterministic from both trace IDs, preventing
    duplicate records for the same interaction.
    """

    model_config = ConfigDict(extra="forbid", defer_build=True)

    # Identity
    interaction_id: str = Field(
        ...,
        description="Deterministic ID from both trace IDs: sha256(sorted(trace_a, trace_b))[:16]",
    )
    requesting_agent_id: str = Field(..., description="Ed25519 pubkey hash of requesting agent")
    resolving_agent_id: str = Field(..., description="Ed25519 pubkey hash of resolving agent")

    # Traces
    requesting_trace_id: str = Field(..., description="ACCORD trace ID from requesting agent")
    resolving_trace_id: str = Field(..., description="ACCORD trace ID from resolving agent")

    # Outcome
    outcome: InteractionOutcome = Field(..., description="How the interaction was resolved")
    domain_category: Optional[DomainCategory] = Field(
        None,
        description="Licensed domain if applicable (MEDICAL, FINANCIAL, etc.)",
    )
    coherence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Coherence ratchet score from CIRISLens evaluation",
    )

    # Gratitude
    gratitude_signal: Optional[GratitudeSignal] = Field(
        None,
        description="Optional explicit gratitude from requesting agent",
    )

    # Dual signatures — both parties + node attestation
    requesting_agent_signature: DualSignature = Field(
        ...,
        description="Dual signature of the requesting agent over the record",
    )
    resolving_agent_signature: Optional[DualSignature] = Field(
        None,
        description="Dual signature of the resolving agent (populated when both sides confirmed)",
    )
    node_attestation: Optional[str] = Field(
        None,
        description="CIRISNode (or Veilid WA consensus) signature attesting the interaction",
    )
    node_attestation_key_id: Optional[str] = Field(
        None,
        description="Key ID of the attesting node",
    )

    # Timestamps
    created_at: datetime = Field(..., description="When the record was created")
    resolved_at: Optional[datetime] = Field(None, description="When the interaction was resolved")

    @staticmethod
    def compute_interaction_id(trace_id_a: str, trace_id_b: str) -> str:
        """Compute deterministic interaction ID from two trace IDs.

        Sorting ensures the same pair always produces the same ID
        regardless of which agent computes it.
        """
        sorted_ids = sorted([trace_id_a, trace_id_b])
        combined = f"{sorted_ids[0]}:{sorted_ids[1]}"
        return hashlib.sha256(combined.encode()).hexdigest()[:16]


class AgentCreditSummary(BaseModel):
    """Computed reputation summary from accumulated credit records.

    NOT a 'balance' — it's a governance weight summary derived from
    verified interactions. Determines voting power in WA consensus,
    routing priority, and domain access.

    k_eff (effective diversity) is the core quality measurement from
    CCA paper: k_eff = k / (1 + rho*(k-1)). High k_eff means diverse,
    independent interaction partners. Low k_eff (approaching 1) means
    correlated or repetitive interactions.
    """

    model_config = ConfigDict(extra="forbid", defer_build=True)

    agent_id: str = Field(..., description="Ed25519 pubkey hash")
    total_interactions: int = Field(0, ge=0, description="Total verified bilateral interactions")
    resolved_interactions: int = Field(0, ge=0, description="Successfully resolved interactions")
    average_coherence: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="Mean coherence score across all interactions",
    )
    k_eff: float = Field(
        1.0,
        ge=0.0,
        description="Effective diversity: k/(1+rho*(k-1)). Higher = more diverse partners.",
    )
    unique_partners: int = Field(0, ge=0, description="Number of distinct interaction partners")
    domain_expertise: Dict[str, int] = Field(
        default_factory=dict,
        description="Domain category -> count of resolved interactions",
    )
    governance_weight: float = Field(
        0.0,
        ge=0.0,
        description="Computed governance weight (interactions * k_eff * avg_coherence)",
    )
    last_interaction_at: Optional[datetime] = Field(
        None,
        description="When the most recent interaction occurred",
    )
    computed_at: datetime = Field(..., description="When this summary was computed")


class CreditGenerationPolicy(BaseModel):
    """Anti-gaming rules for credit record generation.

    Distributed via CIRISNode, signed by CIRIS L3C root key.
    Enforced locally by each agent. Code-level constants — cannot
    be modified by memory, learning, or runtime adaptation.

    These are the parameters that credit-weighted governance could
    vote to adjust (via signed policy updates from L3C).
    """

    model_config = ConfigDict(extra="forbid", defer_build=True)

    policy_version: str = Field(..., description="Policy version date string (YYYY-MM-DD)")

    # Rate limiting
    cooldown_seconds: int = Field(
        60,
        ge=0,
        description="Minimum seconds between credit records for the same agent pair",
    )
    max_daily_interactions_per_pair: int = Field(
        10,
        ge=1,
        description="Maximum credit records per unique agent pair per day",
    )

    # Quality thresholds
    coherence_threshold: float = Field(
        0.3,
        ge=0.0,
        le=1.0,
        description="Minimum coherence score for a record to be accepted",
    )

    # Circular detection
    circular_deferral_window_seconds: int = Field(
        300,
        ge=0,
        description="Window (seconds) to detect A->B->A circular deferrals",
    )

    # Identity requirements
    min_attestation_level: int = Field(
        2,
        ge=0,
        le=5,
        description="Minimum CIRISVerify attestation level to generate records",
    )

    # Policy authentication
    policy_signature: Optional[str] = Field(
        None,
        description="Ed25519 signature of the policy by CIRIS L3C root key",
    )
    policy_key_id: Optional[str] = Field(
        None,
        description="Key ID of the L3C root key that signed the policy",
    )


class DomainDeferralRequired(BaseModel):
    """Signal from WiseBus that a capability requires domain-specific deferral.

    Replaces the ValueError that was raised for REQUIRES_SEPARATE_MODULE.
    The caller auto-constructs a DeferralContext with domain_hint.
    """

    model_config = ConfigDict(extra="forbid", defer_build=True)

    category: DomainCategory = Field(
        ...,
        description="The licensed domain category (MEDICAL, FINANCIAL, etc.)",
    )
    capability: str = Field(..., description="The specific capability that triggered deferral")
    reason: str = Field(
        ...,
        description="Human-readable reason for deferral",
    )


class CreditRecordBatch(BaseModel):
    """Batch of credit records for CIRISNode submission or DHT replication."""

    model_config = ConfigDict(extra="forbid", defer_build=True)

    records: List[CreditRecord] = Field(..., description="Credit records to submit")
    agent_id: str = Field(..., description="Submitting agent's Ed25519 pubkey hash")
    batch_signature: DualSignature = Field(..., description="Dual signature over the batch")
    submitted_at: datetime = Field(..., description="When the batch was submitted")


__all__ = [
    "InteractionOutcome",
    "DomainCategory",
    "DualSignature",
    "GratitudeSignal",
    "CreditRecord",
    "AgentCreditSummary",
    "CreditGenerationPolicy",
    "DomainDeferralRequired",
    "CreditRecordBatch",
]
