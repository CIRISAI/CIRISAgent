"""Trace-sharing consent — the node-level decision to replicate reasoning traces.

Distinct from the user-relationship consent in :mod:`.core` (``ConsentStatus`` and
friends), which governs a *user's* data streams. This module is about ONE node's
owner deciding whether that node's sealed reasoning traces may leave it.

Three artifacts must align before a sealed trace is captured, shipped, and scored
(ciris-server 0.5.139+):

1. ``consent:community_trust:v1`` — the capture/seal gate
2. ``consent:replication:v1`` naming the canonical — the ship gate
3. ``consent:state:granted:v1`` scope=analyze — the CC#46 score gate

Granting only the first is the failure this schema exists to make visible: traces
seal perfectly, report healthy, and never leave (cohort_scope=self, tier=local).
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class TraceConsentSource(str, Enum):
    """Which opt-in path is asking. Recorded so a grant is traceable to the act
    that produced it — an owner's click, a migration, or a boot-time import of a
    choice the owner made earlier."""

    SETUP_WIZARD = "setup_wizard"
    """First-run wizard 'Send traces' checkbox — owner session present."""

    DATA_CARD = "data_card"
    """Post-wizard opt-in from the Data & Privacy / Manage Consent card."""

    LEGACY_ENV = "legacy_env"
    """``CIRIS_ACCORD_METRICS_CONSENT`` — where the wizard's choice lands, and
    what the QA runner sets. The import path into CEG consent state."""

    LEGACY_MIGRATION = "legacy_migration"
    """Adapter boot converting a pre-CEG consent record into the wire artifact."""

    NODE_FOLD = "node_fold"
    """Node bind/rebind, replaying an opt-in the owner already gave."""

    DELIVERY_PROBE = "delivery_probe"
    """The post-claim retry loop. The claim lands after bind, so the one moment
    a fixed-point attempt is guaranteed to fail is boot — hence the retry."""


class TraceSharingConsent(BaseModel):
    """Resolved state of all three gates, read through the engine's OWN resolvers.

    Every field is tri-state. ``None`` means "resolver unavailable" and must never
    be collapsed to ``False`` by a caller — an unknown is not a denial, and it is
    certainly not a grant. Row-existence is never used: a consent row can exist
    and still fold to ``unspecified``, which reads as consented to anything
    counting rows while the serve gate goes on refusing.
    """

    model_config = ConfigDict(defer_build=True)

    capture: Optional[bool] = Field(None, description="consent:community_trust:v1 — may traces be sealed at all")
    replication: Optional[bool] = Field(None, description="consent:replication:v1 naming the canonical — may they ship")
    analyze: Optional[bool] = Field(None, description="CC#46 analyze scope — may they be scored once they arrive")
    canonical: Optional[str] = Field(None, description="Canonical peer key_id the gates were resolved against")
    aligned: bool = Field(False, description="True only when every RESOLVABLE gate is granted")

    @property
    def ships(self) -> bool:
        """Traces can actually leave this node. Capture alone is the silent
        failure: sealed, healthy, and going nowhere."""
        return bool(self.capture) and bool(self.replication)


class TraceSharingGrantResult(BaseModel):
    """Outcome of one grant attempt, per artifact.

    Best-effort by construction: no opt-in path may be broken by a consent emit
    failing, so callers get a result to log rather than an exception to handle.
    """

    model_config = ConfigDict(defer_build=True)

    source: TraceConsentSource = Field(..., description="Which opt-in path authored this")
    opted_in: bool = Field(..., description="Whether the owner's opt-in signal was present at all")
    capture_grant_id: Optional[str] = Field(None, description="Attestation id of the community-trust grant")
    peers_authored: List[str] = Field(default_factory=list, description="Canonical peers the ship grant named")
    errors: List[str] = Field(default_factory=list, description="Per-artifact failures, for logging")
    status: Optional[TraceSharingConsent] = Field(None, description="Gate state resolved AFTER authoring")

    @property
    def complete(self) -> bool:
        """Both halves landed. Deliberately not derived from `status.aligned`:
        the analyze resolver may be unexposed, and a grant should not be reported
        incomplete because a gate could not be READ."""
        return bool(self.capture_grant_id) and bool(self.peers_authored)
