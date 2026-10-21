"""
Canonical bootstrap peer + local peer state schemas.

This module defines the agent-side data model for the "rock-solid + organic"
peer discovery framework (CIRISAgent T-C / CIRISEdge#46):

- ``CanonicalBootstrapPeer``: a peer the agent knows about *intrinsically* via
  constants (or via a federation-directory pull from CIRISRegistry). These
  always appear in the local peer list and reseed on every boot. The user
  may flip their trust state but cannot permanently delete them.
- ``PeerTrustState``: the trust-state vocabulary. Mirrors the Edge crate's
  ``EdgePeerTrust`` enum (TRUSTED / UNTRUSTED / BLOCKED / UNKNOWN) so we
  never have to translate at the FFI boundary.
- ``PeerAppearance``: per-peer ``(icon, fg_color, bg_color)`` tuple owned
  by the *local* user, not by the peer. This is the Sideband convention
  from the Reticulum cribsheet — appearance is a local annotation, never
  trusted from the wire.
- ``LocalPeerState``: the persisted state for a single peer (canonical or
  organically discovered). User-set fields (trust, appearance, notes,
  alias_override) survive reseed; the immutable canonical metadata is
  refreshed from the seed source on each reseed.

No online/offline indicator is tracked here — only ``last_seen``
timestamp. Reticulum convention: presence is a property of an attempted
contact, not a polled status.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class PeerTrustState(str, Enum):
    """Trust state of a peer.

    Vocabulary is locked to the Edge crate's ``EdgePeerTrust`` enum so the
    agent and Edge agree on the wire. Don't add states here without an
    Edge counterpart change.
    """

    TRUSTED = "trusted"
    UNTRUSTED = "untrusted"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


class CanonicalBootstrapPeer(BaseModel):
    """A peer that ships with the agent — infrastructure, not contact.

    These are sourced either from the in-process constant
    ``CIRIS_CANONICAL_BOOTSTRAP_PEERS`` or from the published
    CIRISRegistry federation-directory endpoint. They are reseeded into
    local state on every boot — the user can change their trust state
    but cannot delete them.
    """

    key_id: str = Field(
        ...,
        description="Ed25519 signer_key_id (federation address) for the peer",
        min_length=1,
    )
    alias: str = Field(
        ...,
        description="Human-readable name for the peer (e.g. 'datum @ agents.ciris.ai')",
        min_length=1,
    )
    pubkey_ed25519_base64: str = Field(
        ...,
        description="Ed25519 public key, base64-encoded — used to verify wire signatures",
        min_length=1,
    )
    transport_hint: Optional[str] = Field(
        None,
        description="Optional transport hint (e.g. 'tcp://example.com:4242'); not authoritative — Edge resolves transport via its own discovery",
    )
    description: Optional[str] = Field(
        None,
        description="Optional human-readable description shown in UI peer-listings",
    )

    model_config = ConfigDict(defer_build=True, extra="forbid")


class PeerAppearance(BaseModel):
    """Per-peer ``(icon, fg, bg)`` appearance tuple — owned by the local user.

    This is local UI sugar, not trusted from the wire. The Sideband
    pattern from the Reticulum cribsheet: every peer entry in the local
    address book can be visually distinguished by the user without that
    being a property the peer announces.
    """

    icon: Optional[str] = Field(
        None,
        description="Icon identifier (e.g. emoji codepoint or named icon)",
    )
    fg_color: Optional[str] = Field(
        None,
        description="Foreground color (e.g. CSS hex '#ffffff')",
    )
    bg_color: Optional[str] = Field(
        None,
        description="Background color (e.g. CSS hex '#000000')",
    )

    model_config = ConfigDict(defer_build=True, extra="forbid")


class LocalPeerState(BaseModel):
    """The persisted local state for a single peer (canonical or organic).

    Lifecycle:

    - **Canonical peer**: ``canonical=True``. Created/refreshed on every
      reseed from ``CIRIS_CANONICAL_BOOTSTRAP_PEERS`` or the federation
      directory. The canonical metadata (alias, pubkey, transport_hint,
      description) is *overwritten* on reseed. User-set fields (trust,
      appearance, alias_override, notes) are *preserved* across reseed.
    - **Organic peer**: ``canonical=False``. Created by
      ``record_organic_peer()`` from an ANNOUNCE event (CIRISEdge#46 wire
      surface; mocked here). Trust defaults to ``UNKNOWN``. User can
      promote to TRUSTED via SAS verification (T-E5, separate task).

    ``first_seen`` is stamped at row creation and never changes.
    ``last_seen`` is updated by callers that observe the peer on the
    wire. No online/offline flag — caller decides freshness threshold.

    ``pubkey_ed25519_base64`` is required — every peer has a pubkey by
    definition, canonical or organic. This is the wire-verifiable
    identity bound to ``key_id``.
    """

    key_id: str = Field(..., min_length=1, description="Ed25519 signer_key_id")
    pubkey_ed25519_base64: str = Field(
        ...,
        min_length=1,
        description="Ed25519 public key, base64-encoded — bound to key_id, used to verify wire signatures",
    )
    canonical: bool = Field(
        ...,
        description="True if this peer was seeded from CIRIS_CANONICAL_BOOTSTRAP_PEERS or the federation directory",
    )
    trust: PeerTrustState = Field(
        ...,
        description="User-controlled trust state — defaults to TRUSTED for canonical, UNKNOWN for organic",
    )
    appearance: Optional[PeerAppearance] = Field(
        None,
        description="Local-user-owned visual annotation; None means the UI uses defaults",
    )
    alias_override: Optional[str] = Field(
        None,
        description="Local alias the user chose; takes precedence over the canonical alias in UI",
    )
    notes: Optional[str] = Field(
        None,
        description="Local-user notes attached to this peer",
    )
    first_seen: datetime = Field(
        ...,
        description="UTC timestamp when this peer was first added to local state",
    )
    last_seen: Optional[datetime] = Field(
        None,
        description="UTC timestamp of the most recent wire-level observation",
    )

    model_config = ConfigDict(defer_build=True, extra="forbid")
