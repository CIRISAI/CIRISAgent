"""The consent surface the wizard RENDERS — structure only, never copy.

``ciris_server.consent_disclosure()`` is exported to Python precisely so a client
can render the substrate's own words: "a wizard that writes its own version of
that paragraph drifts from the substrate the moment either changes" (peer.rs).
These models therefore describe the SHAPE of that payload and carry no strings of
their own. Every piece of text arrives with a stable ``id`` — a dot-notation key
into the 29-locale catalogue — so a client renders the localized string and falls
back to the substrate's ``text`` when a locale has no entry yet.

Adding a field here is how new substrate copy reaches the UI;
``test_consent_disclosure_contract`` fails when the substrate publishes something
these models do not carry, so new copy surfaces loudly instead of being dropped.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class DisclosureString(BaseModel):
    """One piece of substrate-authored copy plus its localization key."""

    id: str = Field(..., description="Dot-notation key into the locale catalogue")
    text: str = Field(..., description="The substrate's own wording, in source_locale")


class ConsentGrantDisclosure(BaseModel):
    """One consent dimension the owner is being asked to grant."""

    id: str = Field(..., description="Stable grant id ('replication', 'analyze')")
    title: DisclosureString
    permits: DisclosureString
    dimension: str = Field(..., description="CEG consent dimension, e.g. consent:replication:v1")
    required: bool = Field(
        ...,
        description=(
            "Whether declining is a misconfiguration. The substrate is explicit that "
            "marking an optional grant required misrepresents a legitimate choice."
        ),
    )
    covers: Optional[List[str]] = Field(None, description="Attestation prefixes this grant covers")
    scope: Optional[str] = Field(None, description="Scoped-resolver key, when the grant is scoped")
    parameter: Optional[str] = Field(None, description="How the grant is expressed at the call site")


class DecliningDisclosure(BaseModel):
    """Whether a grant may be declined, and what declining actually costs."""

    allowed: bool
    summary: Optional[DisclosureString] = None
    costs: List[DisclosureString] = Field(default_factory=list)


class LocationDisclosure(BaseModel):
    """The location envelope field — purpose first, then the bound."""

    title: DisclosureString
    purpose: DisclosureString
    permits: DisclosureString
    kind: str = Field(..., description="How location travels, e.g. 'envelope_field'")
    carrier: str = Field(..., description="The artifact that carries it, e.g. 'location_proof'")
    cell_format: str = Field(..., description="Cell system, e.g. 'h3'")
    max_resolution: int = Field(
        ...,
        description="The substrate's own coarseness bound. READ from here, never restated.",
    )
    required: bool
    declining: DecliningDisclosure


class ConsentDisclosure(BaseModel):
    """The whole consent screen, as the substrate publishes it."""

    primary_action: DisclosureString
    announce_requirement: DisclosureString = Field(
        ...,
        description=(
            "Not a consent choice — the floor for service. A node that does not "
            "announce gets no service access on the mesh and no agent services."
        ),
    )
    independent: DisclosureString
    details_expandable: bool
    grants: List[ConsentGrantDisclosure]
    declining_analyze: DecliningDisclosure
    location: LocationDisclosure
    source_locale: str = Field(..., description="Locale of the `text` fields as published")

    def grant(self, grant_id: str) -> Optional[ConsentGrantDisclosure]:
        """The named grant, or None when this build does not publish it."""
        return next((g for g in self.grants if g.id == grant_id), None)
