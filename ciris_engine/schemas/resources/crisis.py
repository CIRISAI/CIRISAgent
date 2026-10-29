"""
Typed crisis resource management for CIRIS agents.

This module provides structured, validated crisis resources to ensure:
1. All crisis resources are actively maintained and validated
2. Resources are consistent across all templates
3. Legal disclaimers are properly included
4. Resources can be tested programmatically
5. Updates propagate to all agents automatically

Since CIRISAgent#971 the resource DATA lives in the localization corpus
(``ciris_engine/data/localized/crisis_resources_{lang}.json``) and this module
is a typed LOADER over it: the Pydantic models stay authoritative for shape,
the corpus is authoritative for content. The absolute rule for the corpus is
in each file's ``_meta.rule``: crisis phone numbers are NEVER machine-guessed —
see ``ciris_engine/data/localized/CRISIS_RESOURCES_VERIFICATION_NEEDED.md``.
"""

import json
import logging
import re
from datetime import date, datetime
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, Field, HttpUrl, ValidationError, field_validator

logger = logging.getLogger(__name__)


class CrisisResourceType(str, Enum):
    """Types of crisis resources available."""

    HOTLINE = "hotline"
    WEBSITE = "website"
    TEXT_LINE = "text_line"
    EMERGENCY = "emergency"
    DIRECTORY = "directory"
    SEARCH_TERM = "search_term"


class ResourceAvailability(str, Enum):
    """Geographic availability of resources.

    Every value that is not one of the four legacy region tokens is a
    lower-case ISO 3166-1 alpha-2 country code — the convention the original
    members ``us`` / ``ca`` / ``au`` / ``et`` already followed. The set is
    CLOSED on purpose: a typo'd or invented country in a crisis corpus file
    fails validation instead of silently matching nothing.

    Legacy non-ISO tokens, kept so existing corpus files and callers work:
    ``global``, ``regional``, ``eu`` (European Union), and ``uk`` — which
    means the United Kingdom (ISO ``GB``), NOT Ukraine (ISO ``UA``). Do not add
    a ``gb`` member: one country, one token.

    Country members (CIRISAgent#1248) are the countries whose national
    emergency numbers are staged in ``crisis_resources_{lang}.json``.
    """

    # Legacy region tokens (pre-#1248)
    GLOBAL = "global"
    US = "us"
    UK = "uk"
    EU = "eu"
    CANADA = "ca"
    AUSTRALIA = "au"
    ETHIOPIA = "et"
    REGIONAL = "regional"

    # ISO 3166-1 alpha-2 countries (CIRISAgent#1248), alphabetical by code
    AF = "af"  # Afghanistan
    AO = "ao"  # Angola
    AR = "ar"  # Argentina
    AT = "at"  # Austria
    BD = "bd"  # Bangladesh
    BE = "be"  # Belgium
    BR = "br"  # Brazil
    BY = "by"  # Belarus
    CD = "cd"  # DR Congo
    CH = "ch"  # Switzerland
    CI = "ci"  # Côte d'Ivoire
    CM = "cm"  # Cameroon
    CN = "cn"  # China
    CO = "co"  # Colombia
    DE = "de"  # Germany
    DZ = "dz"  # Algeria
    EG = "eg"  # Egypt
    ES = "es"  # Spain
    FR = "fr"  # France
    ID = "id"  # Indonesia
    IE = "ie"  # Ireland
    IN = "in"  # India
    IQ = "iq"  # Iraq
    IR = "ir"  # Iran
    IT = "it"  # Italy
    JP = "jp"  # Japan
    KE = "ke"  # Kenya
    KR = "kr"  # South Korea
    KZ = "kz"  # Kazakhstan
    LK = "lk"  # Sri Lanka
    MA = "ma"  # Morocco
    MM = "mm"  # Myanmar
    MX = "mx"  # Mexico
    MZ = "mz"  # Mozambique
    NE = "ne"  # Niger
    NG = "ng"  # Nigeria
    NZ = "nz"  # New Zealand
    PH = "ph"  # Philippines
    PK = "pk"  # Pakistan
    PT = "pt"  # Portugal
    RU = "ru"  # Russia
    SA = "sa"  # Saudi Arabia
    SG = "sg"  # Singapore
    SN = "sn"  # Senegal
    TH = "th"  # Thailand
    TJ = "tj"  # Tajikistan
    TR = "tr"  # Türkiye
    TZ = "tz"  # Tanzania
    UA = "ua"  # Ukraine
    UG = "ug"  # Uganda
    VN = "vn"  # Vietnam
    ZA = "za"  # South Africa


#: English display name per country token — the label every emergency number is
#: rendered under (CIRISAgent#1248: a number is never emitted unlabelled by
#: country). Covers every country member of ResourceAvailability; enforced by
#: tests/test_crisis_resources_corpus.py.
COUNTRY_NAMES: Dict[ResourceAvailability, str] = {
    ResourceAvailability("af"): "Afghanistan",
    ResourceAvailability("ao"): "Angola",
    ResourceAvailability("ar"): "Argentina",
    ResourceAvailability("at"): "Austria",
    ResourceAvailability("au"): "Australia",
    ResourceAvailability("bd"): "Bangladesh",
    ResourceAvailability("be"): "Belgium",
    ResourceAvailability("br"): "Brazil",
    ResourceAvailability("by"): "Belarus",
    ResourceAvailability("ca"): "Canada",
    ResourceAvailability("cd"): "DR Congo",
    ResourceAvailability("ch"): "Switzerland",
    ResourceAvailability("ci"): "Côte d'Ivoire",
    ResourceAvailability("cm"): "Cameroon",
    ResourceAvailability("cn"): "China",
    ResourceAvailability("co"): "Colombia",
    ResourceAvailability("de"): "Germany",
    ResourceAvailability("dz"): "Algeria",
    ResourceAvailability("eg"): "Egypt",
    ResourceAvailability("es"): "Spain",
    ResourceAvailability("et"): "Ethiopia",
    ResourceAvailability("fr"): "France",
    ResourceAvailability("id"): "Indonesia",
    ResourceAvailability("ie"): "Ireland",
    ResourceAvailability("in"): "India",
    ResourceAvailability("iq"): "Iraq",
    ResourceAvailability("ir"): "Iran",
    ResourceAvailability("it"): "Italy",
    ResourceAvailability("jp"): "Japan",
    ResourceAvailability("ke"): "Kenya",
    ResourceAvailability("kr"): "South Korea",
    ResourceAvailability("kz"): "Kazakhstan",
    ResourceAvailability("lk"): "Sri Lanka",
    ResourceAvailability("ma"): "Morocco",
    ResourceAvailability("mm"): "Myanmar",
    ResourceAvailability("mx"): "Mexico",
    ResourceAvailability("mz"): "Mozambique",
    ResourceAvailability("ne"): "Niger",
    ResourceAvailability("ng"): "Nigeria",
    ResourceAvailability("nz"): "New Zealand",
    ResourceAvailability("ph"): "Philippines",
    ResourceAvailability("pk"): "Pakistan",
    ResourceAvailability("pt"): "Portugal",
    ResourceAvailability("ru"): "Russia",
    ResourceAvailability("sa"): "Saudi Arabia",
    ResourceAvailability("sg"): "Singapore",
    ResourceAvailability("sn"): "Senegal",
    ResourceAvailability("th"): "Thailand",
    ResourceAvailability("tj"): "Tajikistan",
    ResourceAvailability("tr"): "Türkiye",
    ResourceAvailability("tz"): "Tanzania",
    ResourceAvailability("ua"): "Ukraine",
    ResourceAvailability("ug"): "Uganda",
    ResourceAvailability("uk"): "United Kingdom",
    ResourceAvailability("us"): "United States",
    ResourceAvailability("vn"): "Vietnam",
    ResourceAvailability("za"): "South Africa",
}

#: Extra spellings a location string may use (setup wizard / env) beyond the
#: names above and the alpha-2 codes themselves. Lower-cased lookup keys.
_COUNTRY_ALIASES: Dict[str, str] = {
    "usa": "us", "united states of america": "us", "u.s.": "us", "u.s.a.": "us",
    "gb": "uk", "great britain": "uk", "britain": "uk", "england": "uk", "scotland": "uk", "wales": "uk",
    "northern ireland": "uk", "united kingdom of great britain and northern ireland": "uk",
    "turkey": "tr", "turkiye": "tr", "republic of korea": "kr", "korea, republic of": "kr", "korea": "kr",
    "ivory coast": "ci", "cote d'ivoire": "ci", "democratic republic of the congo": "cd",
    "congo, the democratic republic of the": "cd", "drc": "cd", "viet nam": "vn", "russian federation": "ru",
    "iran, islamic republic of": "ir", "tanzania, united republic of": "tz", "united republic of tanzania": "tz",
    "burma": "mm", "kingdom of saudi arabia": "sa", "people's republic of china": "cn", "prc": "cn",
}


def country_token(value: Optional[str]) -> Optional[ResourceAvailability]:
    """Map a country name or ISO 3166-1 alpha-2 code to its ResourceAvailability, or None.

    Accepts what the setup wizard writes (``CIRIS_USER_COUNTRY`` is an alpha-2 code,
    ``CIRIS_USER_LOCATION`` carries a name). Only countries the corpus knows map;
    anything else is None, which selects the language path — never a guess.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    key = value.strip().lower()
    key = _COUNTRY_ALIASES.get(key, key)
    for token, name in COUNTRY_NAMES.items():
        if key == token.value or key == name.lower():
            return token
    return None


class CrisisResourceSource(str, Enum):
    """Provenance of a crisis resource entry (CIRISAgent#971).

    BUILTIN — authored in-repo; carried over from the pre-corpus hardcoded registry.
    THROUGHLINE — cut from a ThroughLine (developer.throughlinecare.com) snapshot.
        Licensing evaluation pending; no such entries exist yet. The enum member
        exists so a future refresh tool (pattern: ``tools/update_ciris_verify.py``)
        can regenerate the corpus from a snapshot without a schema change.
    NATIONAL_VERIFIED — a national entry a human verified against an authoritative
        source (government page, national health service) cited in ``source_url``.
    MULTI_SOURCE_CITED — an EMERGENCY number (police / ambulance / fire, never a
        hotline) cross-checked against at least two independent cited sources that
        agree on the number and what it reaches, at least one of them official
        (``source_url``), the rest in ``source_urls``. No human checked it — this is
        the cited-sources standard the repo owner ruled for emergency numbers on
        2026-10-29 (CIRISAgent#1248). Hotlines stay NATIONAL_VERIFIED-only.
    """

    BUILTIN = "builtin"
    THROUGHLINE = "throughline"
    NATIONAL_VERIFIED = "national_verified"
    MULTI_SOURCE_CITED = "multi_source_cited"


class CrisisResource(BaseModel):
    """A validated crisis resource with metadata."""

    id: str = Field(..., description="Unique identifier for the resource")
    name: str = Field(..., description="Human-readable name")
    type: CrisisResourceType = Field(..., description="Type of resource")

    # Contact information (at least one required)
    url: Optional[HttpUrl] = Field(None, description="Website URL")
    phone: Optional[str] = Field(None, description="Phone number")
    text_number: Optional[str] = Field(None, description="SMS/text number")
    search_term: Optional[str] = Field(None, description="Search term for finding local resources")

    # Metadata
    description: str = Field(..., description="Brief description of the service")
    availability: List[ResourceAvailability] = Field(
        default_factory=lambda: [ResourceAvailability.GLOBAL], description="Geographic availability"
    )
    languages: List[str] = Field(default_factory=lambda: ["en"], description="Supported languages (ISO 639-1 codes)")

    # Validation metadata
    last_validated: datetime = Field(
        default_factory=datetime.now, description="When this resource was last validated as working"
    )
    validation_notes: Optional[str] = Field(None, description="Notes from last validation")

    # Legal/compliance
    is_endorsed: bool = Field(False, description="Whether CIRIS endorses this resource (always False for liability)")
    requires_disclaimer: bool = Field(True, description="Whether to show disclaimer when sharing")

    # Provenance (CIRISAgent#971). Sourcing from ThroughLine is deferred pending
    # licensing; these fields let a future refresh tool regenerate the corpus
    # without schema changes.
    source: CrisisResourceSource = Field(
        CrisisResourceSource.BUILTIN,
        description="Where this entry came from (builtin | throughline | national_verified)",
    )
    verified: bool = Field(
        False,
        description=(
            "True once a human has verified this entry against its source. "
            "NEVER machine-set to True for an entry carrying a phone/text number."
        ),
    )
    snapshot_date: Optional[date] = Field(None, description="Date the entry was cut from its source dataset")
    source_url: Optional[HttpUrl] = Field(None, description="Authoritative page this entry was sourced from")
    source_urls: List[HttpUrl] = Field(
        default_factory=list,
        description=(
            "Further independent sources that agree with source_url (CIRISAgent#1248). Structured, not "
            "prose, so the multi_source_cited bar (>=2 sources, >=1 official) is machine-checkable."
        ),
    )

    @field_validator("phone", "text_number")
    @classmethod
    def validate_phone_format(cls, v: Optional[str]) -> Optional[str]:
        """Basic phone number validation."""
        if v is None:
            return v
        # Remove common formatting characters
        cleaned = v.replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
        # Ensure it's numeric (except for + prefix)
        if cleaned.startswith("+"):
            cleaned = cleaned[1:]
        if not cleaned.isdigit():
            raise ValueError(f"Invalid phone number format: {v}")
        return v

    @field_validator("search_term")
    @classmethod
    def validate_search_term(cls, v: Optional[str]) -> Optional[str]:
        """Ensure search terms are safe and useful."""
        if v is None:
            return v
        # Should contain 'crisis' or 'hotline' or 'emergency'
        keywords = ["crisis", "hotline", "emergency", "help", "support"]
        if not any(keyword in v.lower() for keyword in keywords):
            raise ValueError(f"Search term should contain crisis-related keywords: {v}")
        return v

    def model_post_init(self, _context: Any) -> None:
        """Ensure at least one contact method is provided, and the sourcing bar holds."""
        if not any([self.url, self.phone, self.text_number, self.search_term]):
            raise ValueError("At least one contact method must be provided")
        if self.source == CrisisResourceSource.MULTI_SOURCE_CITED:
            # The cited-sources standard (owner ruling 2026-10-29) covers EMERGENCY
            # numbers only. A hotline is never emitted on citations alone.
            if self.type != CrisisResourceType.EMERGENCY:
                raise ValueError(f"{self.id}: multi_source_cited is for emergency numbers only, not {self.type.value}")
            if self.source_url is None or not self.source_urls:
                raise ValueError(f"{self.id}: multi_source_cited needs source_url (official) + >=1 source_urls")

    def format_for_display(self, include_disclaimer: bool = True) -> str:
        """Format resource for display in messages."""
        lines = [f"**{self.name}**"]

        if self.url:
            lines.append(f"• Website: {self.url}")
        if self.phone:
            lines.append(f"• Phone: {self.phone}")
        if self.text_number:
            lines.append(f"• Text: {self.text_number}")
        if self.search_term:
            lines.append(f"• Search: '{self.search_term}'")

        lines.append(f"• {self.description}")

        if include_disclaimer and self.requires_disclaimer:
            lines.append("• (Not an endorsement - information only)")

        return "\n".join(lines)


#: Label every emergency-services section carries (CIRISAgent#1248). Emergency
#: numbers (police / ambulance / fire) reach general emergency dispatch; they
#: are NOT mental-health or crisis helplines and must never be presented as one.
EMERGENCY_SECTION_LABEL = "Emergency services (police / ambulance / fire — NOT mental-health or crisis helplines)"


#: Sources whose ``verified: true`` entries may emit a number (see is_emittable).
_EMITTABLE_SOURCES = frozenset(
    {
        CrisisResourceSource.BUILTIN,
        CrisisResourceSource.NATIONAL_VERIFIED,
        CrisisResourceSource.MULTI_SOURCE_CITED,
        CrisisResourceSource.THROUGHLINE,
    }
)

#: Language-path cap: at most this many speaker countries per block, so the
#: block stays short (the location country, when opted in, rides on top).
LANGUAGE_COUNTRY_CAP = 6


def country_label(
    country: ResourceAvailability, is_location: bool = False, entry: Optional["CrisisResource"] = None
) -> str:
    """The country label an emergency number is rendered under.

    An entry valid in several countries (en's 911: US and Canada) is labelled with
    all of them, so a number is never attributed to only part of where it works.
    """
    countries = [country]
    if entry is not None and len(entry.availability) > 1:
        countries = [c for c in entry.availability if c in COUNTRY_NAMES] or countries
    name = " / ".join(COUNTRY_NAMES.get(c, c.value.upper()) for c in countries)
    return f"{name} — your location" if is_location else name


class CrisisResourceRegistry(BaseModel):
    """Registry of crisis resources for one locale, loaded from the corpus.

    One registry per corpus file (``crisis_resources_{locale}.json``). The en
    registry is the base corpus and carries the full builtin entry set; locale
    registries are curated per-locale (national entries first, then the
    international directories).
    """

    resources: Dict[str, CrisisResource] = Field(
        default_factory=dict, description="All registered crisis resources by ID"
    )

    # Per-locale corpus metadata (CIRISAgent#971)
    locale: str = Field("en", description="Primary language subtag this registry serves (corpus filename suffix)")
    needs_verified_entries: bool = Field(
        False,
        description=(
            "True while this locale still lacks human-verified national entries — the "
            "signal a human verifier works from; see CRISIS_RESOURCES_VERIFICATION_NEEDED.md"
        ),
    )
    verification_notes: Optional[str] = Field(
        None, description="Human notes on this locale's verification state (sources checked, known gaps)"
    )
    language_countries: List[ResourceAvailability] = Field(
        default_factory=list,
        description=(
            "Countries where this locale's language is spoken, ordered by (approximate) speaker "
            "population — the no-location emergency selection (CIRISAgent#1248). Capped at "
            "LANGUAGE_COUNTRY_CAP when rendered. Empty for en: the base registry is the fail-safe "
            "fallback for every unknown language, so it presumes no country."
        ),
    )
    emergency_line_ids: List[str] = Field(
        default_factory=list,
        description=(
            "LEGACY (en only): ordered ids of type=emergency entries whose numbers the 'For immediate "
            "danger' line names when no country-labelled emergency section is rendered — en's '911', "
            "byte-frozen by the golden test. Other locales leave it empty: their numbers render "
            "country-labelled in the emergency section (CIRISAgent#1248). Only emittable entries count."
        ),
    )

    # Legal disclaimer that MUST be included
    disclaimer: str = Field(
        default="""DISCLAIMER: I am an AI moderator, not a healthcare provider. The following
is general information only, not medical advice or crisis intervention:

This information is provided as-is without warranty. CIRIS L3C is not a
healthcare provider and does not endorse these resources. Please seek
qualified professional help.""",
        description="Required disclaimer text",
    )

    def add_resource(self, resource: CrisisResource) -> None:
        """Add a resource to the registry."""
        if resource.id in self.resources:
            raise ValueError(f"Resource with ID {resource.id} already exists")
        self.resources[resource.id] = resource

    def get_by_availability(self, regions: List[ResourceAvailability]) -> List[CrisisResource]:
        """Get resources available in specified regions."""
        results = []
        for resource in self.resources.values():
            if ResourceAvailability.GLOBAL in resource.availability:
                results.append(resource)
            elif any(region in resource.availability for region in regions):
                results.append(resource)
        return results

    def get_by_type(self, resource_type: CrisisResourceType) -> List[CrisisResource]:
        """Get all resources of a specific type."""
        return [r for r in self.resources.values() if r.type == resource_type]

    @staticmethod
    def is_emittable(resource: CrisisResource) -> bool:
        """THE anti-fabrication gate: may this entry reach a prompt?

        An entry carrying a phone/text number is emittable only when ``verified``
        is true — set by a human (``builtin`` / ``national_verified``) or, for
        EMERGENCY numbers only, by the cited-sources standard
        (``multi_source_cited``: >=2 agreeing sources, >=1 official — owner ruling
        2026-10-29, CIRISAgent#1248; the schema refuses it on a hotline). Entries
        awaiting either stay in the corpus but are never emitted. Applied on EVERY
        selection path (default, regions, resource_ids, emergency groups).
        """
        if not (resource.phone or resource.text_number):
            return True
        return resource.verified and resource.source in _EMITTABLE_SOURCES

    def default_prompt_resources(self, limit: Optional[int] = None) -> List[CrisisResource]:
        """The resource set surfaced when a caller asks for the default selection.

        en (the base corpus) keeps the legacy selection — GLOBAL entries only,
        optionally capped — byte-frozen by the golden test in
        ``tests/test_crisis_resources_corpus.py``. A locale corpus file is
        already curated for its locale (national entries first, then the
        international directories), so its full entry set in file order IS the
        default selection — EXCEPT entries that fail :meth:`is_emittable`.
        """
        if self.locale == "en":
            selected = [r for r in self.get_by_availability([ResourceAvailability.GLOBAL]) if self.is_emittable(r)]
            return selected[:limit] if limit is not None else selected
        return [r for r in self.resources.values() if self.is_emittable(r)]

    def select_resources(
        self,
        resource_ids: Optional[List[str]] = None,
        regions: Optional[List[ResourceAvailability]] = None,
        limit: Optional[int] = None,
    ) -> List[CrisisResource]:
        """One selection path for every formatter, gated by :meth:`is_emittable`.

        ``limit`` caps the explicit ``resource_ids`` / ``regions`` selections and
        is passed through to :meth:`default_prompt_resources` (which honours it at
        en only — a locale corpus is already curated).
        """
        if resource_ids:
            picked = [self.resources[rid] for rid in resource_ids if rid in self.resources]
        elif regions:
            picked = self.get_by_availability(regions)
        else:
            return self.default_prompt_resources(limit=limit)
        emitted = [r for r in picked if self.is_emittable(r)]
        return emitted[:limit] if limit is not None else emitted

    @staticmethod
    def split_emergency(resources: List[CrisisResource]) -> Tuple[List[CrisisResource], List[CrisisResource]]:
        """Split a selection into (helplines/directories, emergency services).

        CIRISAgent#1248: an ambulance number listed in the same bullet list as
        crisis helplines was presented to the user as a "mental-health
        helpline". Emergency entries are therefore always rendered under their
        own emergency-services label, never alongside the hotlines.
        """
        support = [r for r in resources if r.type != CrisisResourceType.EMERGENCY]
        emergency = [r for r in resources if r.type == CrisisResourceType.EMERGENCY]
        return support, emergency

    def emergency_groups(
        self, location: Optional[ResourceAvailability] = None, cap: int = LANGUAGE_COUNTRY_CAP
    ) -> List[Tuple[ResourceAvailability, bool, List[CrisisResource]]]:
        """The emergency numbers to render, grouped by country: ``(country, is_location, entries)``.

        Selection (CIRISAgent#1248):

        1. Location opted in and the corpus has emittable entries for it -> that
           country FIRST, flagged as the user's location — even when it is outside
           the language's countries (a Spanish speaker in Germany gets Germany).
        2. Then this locale's ``language_countries`` in speaker-population order,
           skipping the location country, capped at ``cap`` countries.
        3. Nothing for either -> no groups; the line says "local emergency
           services" with no number.

        Entries come from the cross-locale country index (every corpus file),
        preferring this locale's own copy; only :meth:`is_emittable` entries.
        """
        index = emergency_index()
        groups: List[Tuple[ResourceAvailability, bool, List[CrisisResource]]] = []

        def entries_for(country: ResourceAvailability) -> List[CrisisResource]:
            own = [
                r for r in self.resources.values()
                if r.type == CrisisResourceType.EMERGENCY and country in r.availability and self.is_emittable(r)
            ]
            if own:
                return own
            return list(index.get(country, []))

        if location is not None:
            found = entries_for(location)
            if found:
                groups.append((location, True, found))
        language_added = 0
        for country in self.language_countries:
            if language_added >= cap:
                break
            if location is not None and country == location:
                continue
            found = entries_for(country)
            if found:
                groups.append((country, False, found))
                language_added += 1
        return groups

    def emergency_line_numbers(self) -> List[str]:
        """Numbers the 'For immediate danger' line names: verified emergency entries only."""
        numbers: List[str] = []
        for rid in self.emergency_line_ids:
            entry = self.resources.get(rid)
            if (
                entry is not None
                and entry.type == CrisisResourceType.EMERGENCY
                and entry.phone
                and self.is_emittable(entry)
                and entry.phone not in numbers
            ):
                numbers.append(entry.phone)
        return numbers

    def immediate_danger_line(self, verb: str, groups_rendered: bool = False) -> str:
        """The 'For immediate danger' line (CIRISAgent#1248).

        - Country-labelled emergency numbers rendered above -> the line points at
          them and repeats none (no number is ever emitted without its country).
        - Otherwise the legacy ``emergency_line_ids`` (en only: "911", the
          human-verified US/Canada entry — byte-frozen by the golden test).
        - Otherwise NO number. The old hard-coded "911" told a Spanish speaker in
          Spain (112) or a Hausa speaker in Nigeria (112) to dial the US number.
        """
        if groups_rendered:
            # Every number is already listed above, labelled by country — the line
            # repeats none, so no number is ever emitted without its country.
            return f"{verb} the emergency number listed above for your country, or local emergency services"
        numbers = self.emergency_line_numbers()
        if numbers:
            # Legacy en line ("Call 911 ..."), byte-frozen by the golden test.
            return f"{verb} {' / '.join(numbers)} or local emergency services"
        return f"{verb} local emergency services"

    def emergency_render_groups(
        self,
        resource_ids: Optional[List[str]] = None,
        regions: Optional[List[ResourceAvailability]] = None,
        location: Optional[ResourceAvailability] = None,
        limit: Optional[int] = None,
    ) -> Tuple[List[CrisisResource], List[Tuple[ResourceAvailability, bool, List[CrisisResource]]]]:
        """(support entries, emergency groups) for one block — the shared selection for both formats."""
        selected = self.select_resources(resource_ids=resource_ids, regions=regions, limit=limit)
        support, explicit_emergency = self.split_emergency(selected)
        if resource_ids or regions:
            groups: List[Tuple[ResourceAvailability, bool, List[CrisisResource]]] = []
            for entry in explicit_emergency:
                country = entry.availability[0] if entry.availability else ResourceAvailability.GLOBAL
                for c, _, entries in groups:
                    if c == country:
                        entries.append(entry)
                        break
                else:
                    groups.append((country, location == country, [entry]))
            return support, groups
        return support, self.emergency_groups(location=location)

    def format_crisis_response(
        self,
        resource_ids: Optional[List[str]] = None,
        regions: Optional[List[ResourceAvailability]] = None,
        location: Optional[ResourceAvailability] = None,
    ) -> str:
        """Format a complete crisis response with disclaimer."""
        lines = [
            "The information shared suggests professional support may be helpful.",
            "",
            self.disclaimer,
            "",
            "**General Crisis Resources (not endorsements):**",
        ]

        # Default selection (en: global resources, byte-frozen; locale corpora:
        # the curated file's full entry set) — gated on every path.
        support, groups = self.emergency_render_groups(resource_ids=resource_ids, regions=regions, location=location)

        for resource in support:
            lines.append("")
            lines.append(resource.format_for_display(include_disclaimer=False))

        if groups:
            lines.extend(["", f"**{EMERGENCY_SECTION_LABEL}:**"])
            for country, is_location, entries in groups:
                for resource in entries:
                    label = country_label(country, is_location, resource)
                    lines.append("")
                    lines.append(f"[{label}] " + resource.format_for_display(include_disclaimer=False))

        lines.extend(
            [
                "",
                f"For immediate danger: {self.immediate_danger_line('Contact', groups_rendered=bool(groups))}",
                "",
                "[DEFER TO HUMAN MODERATOR]",
            ]
        )

        return "\n".join(lines)

    def validate_all_resources(self) -> Dict[str, bool]:
        """Validate all resources are properly formed."""
        results = {}
        for resource_id, resource in self.resources.items():
            try:
                # Re-validate the model
                resource.model_validate(resource.model_dump())
                results[resource_id] = True
            except Exception as e:
                results[resource_id] = False
        return results


# ---------------------------------------------------------------------------
# Corpus loader (CIRISAgent#971)
#
# The data formerly hardcoded here lives in the localization corpus:
#   ciris_engine/data/localized/crisis_resources_{lang}.json
# One file per manifest language. en is the base corpus (full builtin set);
# the other locales carry the international directory entries plus any
# human-verified national entries, and a needs_verified_entries marker while
# national entries are missing. See CRISIS_RESOURCES_VERIFICATION_NEEDED.md
# in that directory before touching the data — crisis numbers are NEVER
# machine-guessed.
# ---------------------------------------------------------------------------

_CRISIS_CORPUS_PACKAGE = "ciris_engine.data.localized"
_CRISIS_CORPUS_DIR = Path(__file__).resolve().parents[2] / "data" / "localized"
_LANG_SUBTAG = re.compile(r"^[a-z]{2,3}$")


def _normalize_language(language: Optional[str]) -> str:
    """Reduce a language tag to its primary subtag; anything unusable -> 'en'.

    'pt-BR' -> 'pt', 'EN' -> 'en'. The subtag regex also guards the corpus
    filename against path-injection through a hostile language string. This is
    a crisis surface: ANY unusable input (None, empty, non-str garbage) must
    fail safe to en rather than raise.
    """
    if not isinstance(language, str) or not language:
        return "en"
    subtag = language.strip().lower().replace("_", "-").split("-")[0]
    return subtag if _LANG_SUBTAG.fullmatch(subtag) else "en"


def _read_corpus_text(filename: str) -> Optional[str]:
    """Read a corpus file via importlib.resources, with a path fallback."""
    try:
        from importlib.resources import files

        return files(_CRISIS_CORPUS_PACKAGE).joinpath(filename).read_text(encoding="utf-8")
    except (ImportError, FileNotFoundError, ModuleNotFoundError):
        path = _CRISIS_CORPUS_DIR / filename
        if path.exists():
            return path.read_text(encoding="utf-8")
        return None


def _parse_registry(raw: str) -> CrisisResourceRegistry:
    """Validate corpus JSON into a typed registry (``_meta`` is bookkeeping)."""
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("crisis corpus file must contain a JSON object")
    data.pop("_meta", None)
    return CrisisResourceRegistry.model_validate(data)


@lru_cache(maxsize=None)
def _load_crisis_registry_cached(lang: str) -> CrisisResourceRegistry:
    """Load one locale's registry; unknown/broken locale files fail safe to en."""
    if lang != "en":
        raw = _read_corpus_text(f"crisis_resources_{lang}.json")
        if raw is not None:
            try:
                return _parse_registry(raw)
            except (ValueError, ValidationError) as exc:
                logger.warning("Crisis corpus for locale %r invalid (%s) — falling back to en", lang, exc)
        else:
            logger.debug("No crisis corpus for locale %r — falling back to en", lang)
        return _load_crisis_registry_cached("en")

    raw = _read_corpus_text("crisis_resources_en.json")
    if raw is None:
        # The en corpus is safety-critical packaged data; a missing file is a
        # broken install and must fail loudly at startup, not degrade to an
        # empty crisis block.
        raise RuntimeError("crisis_resources_en.json missing from ciris_engine/data/localized — broken install")
    return _parse_registry(raw)


def load_crisis_registry(language: Optional[str] = None) -> CrisisResourceRegistry:
    """Typed loader over the crisis-resource corpus.

    Fail-safe semantics: an unknown, unmapped, or corrupt locale always yields
    the en base registry (which carries the international directories) — never
    an empty registry, never a KeyError.
    """
    return _load_crisis_registry_cached(_normalize_language(language))


def _corpus_locales() -> List[str]:
    """Every locale with a crisis corpus file, sorted (en first is not assumed)."""
    names: List[str] = []
    try:
        from importlib.resources import files

        names = [p.name for p in files(_CRISIS_CORPUS_PACKAGE).iterdir()]
    except (ImportError, FileNotFoundError, ModuleNotFoundError, NotADirectoryError):
        names = [p.name for p in _CRISIS_CORPUS_DIR.glob("crisis_resources_*.json")]
    locales = []
    for name in names:
        m = re.fullmatch(r"crisis_resources_([a-z]{2,3})\.json", name)
        if m:
            locales.append(m.group(1))
    return sorted(locales)


@lru_cache(maxsize=1)
def emergency_index() -> Dict[ResourceAvailability, List[CrisisResource]]:
    """Cross-locale index: country -> its EMITTABLE emergency entries (CIRISAgent#1248).

    Emergency numbers belong to a country, not a language, but the corpus files
    are per language: Germany's numbers live in the de file. A location-opted-in
    user whose language is not spoken there (a Spanish speaker in Germany) still
    needs them, so the location path reads this index. Built from every corpus
    file; one entry per (country, number), first file in sorted order wins.
    Only :meth:`CrisisResourceRegistry.is_emittable` entries are indexed.
    """
    index: Dict[ResourceAvailability, List[CrisisResource]] = {}
    seen: Set[Tuple[ResourceAvailability, Optional[str]]] = set()
    non_country = {ResourceAvailability.GLOBAL, ResourceAvailability.REGIONAL, ResourceAvailability.EU}
    for lang in _corpus_locales():
        registry = load_crisis_registry(lang)
        for entry in registry.resources.values():
            if entry.type != CrisisResourceType.EMERGENCY or not CrisisResourceRegistry.is_emittable(entry):
                continue
            for country in entry.availability:
                if country in non_country or (country, entry.phone) in seen:
                    continue
                seen.add((country, entry.phone))
                index.setdefault(country, []).append(entry)
    return index


def resolve_location_country() -> Optional[ResourceAvailability]:
    """The user's opted-in location country, or None (CIRISAgent#1248).

    Location is opt-in at setup: ``CIRIS_USER_COUNTRY`` (ISO alpha-2, written by
    the setup wizard) wins; otherwise the country component of
    ``location_utils.get_user_location()``. Unknown / unset -> None, which
    selects the language path. Never raises — this is a crisis surface.
    """
    import os

    try:
        token = country_token(os.environ.get("CIRIS_USER_COUNTRY"))
        if token is not None:
            return token
        from ciris_engine.logic.utils.location_utils import get_user_location

        location = get_user_location()
        for candidate in (location.country, *(p.strip() for p in (location.location_string or "").split(","))):
            token = country_token(candidate)
            if token is not None:
                return token
    except Exception:  # noqa: BLE001 - location is best-effort; the language path still applies
        logger.debug("Crisis resources: location lookup failed; using the language path", exc_info=True)
    return None


# The default (en, base-corpus) registry. Import contract preserved from the
# pre-corpus era: this name is what formatters and tests build on.
DEFAULT_CRISIS_RESOURCES = load_crisis_registry("en")


def get_crisis_response_text(
    regions: Optional[List[ResourceAvailability]] = None,
    resource_ids: Optional[List[str]] = None,
    language: Optional[str] = None,
    location: Optional[ResourceAvailability] = None,
) -> str:
    """
    Get formatted crisis response text with appropriate resources.

    Args:
        regions: Geographic regions to filter resources by
        resource_ids: Specific resource IDs to include
        language: Locale whose corpus registry to use (None/'en'/unknown -> en)

    Returns:
        Formatted crisis response text with disclaimer
    """
    return load_crisis_registry(language).format_crisis_response(
        resource_ids=resource_ids, regions=regions, location=location
    )
