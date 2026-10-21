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
from typing import Any, Dict, List, Optional, Set

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
    """Geographic availability of resources."""

    GLOBAL = "global"
    US = "us"
    UK = "uk"
    EU = "eu"
    CANADA = "ca"
    AUSTRALIA = "au"
    ETHIOPIA = "et"
    REGIONAL = "regional"


class CrisisResourceSource(str, Enum):
    """Provenance of a crisis resource entry (CIRISAgent#971).

    BUILTIN — authored in-repo; carried over from the pre-corpus hardcoded registry.
    THROUGHLINE — cut from a ThroughLine (developer.throughlinecare.com) snapshot.
        Licensing evaluation pending; no such entries exist yet. The enum member
        exists so a future refresh tool (pattern: ``tools/update_ciris_verify.py``)
        can regenerate the corpus from a snapshot without a schema change.
    NATIONAL_VERIFIED — a national entry a human verified against an authoritative
        source (government page, national health service) cited in ``source_url``.
    """

    BUILTIN = "builtin"
    THROUGHLINE = "throughline"
    NATIONAL_VERIFIED = "national_verified"


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
        """Ensure at least one contact method is provided."""
        if not any([self.url, self.phone, self.text_number, self.search_term]):
            raise ValueError("At least one contact method must be provided")

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

    def default_prompt_resources(self, limit: Optional[int] = None) -> List[CrisisResource]:
        """The resource set surfaced when a caller asks for the default selection.

        en (the base corpus) keeps the legacy selection — GLOBAL entries only,
        optionally capped — byte-frozen by the golden test in
        ``tests/test_crisis_resources_corpus.py``. A locale corpus file is
        already curated for its locale (national entries first, then the
        international directories), so its full entry set in file order IS the
        default selection — EXCEPT entries carrying a phone/text number that no
        human has verified yet (``verified: false``, e.g. cut from a source
        snapshot awaiting review): those stay in the corpus but are never
        emitted. A wrong crisis number is catastrophically worse than the
        directory fallback.
        """
        if self.locale == "en":
            selected = self.get_by_availability([ResourceAvailability.GLOBAL])
            return selected[:limit] if limit is not None else selected
        return [r for r in self.resources.values() if r.verified or not (r.phone or r.text_number)]

    def format_crisis_response(
        self, resource_ids: Optional[List[str]] = None, regions: Optional[List[ResourceAvailability]] = None
    ) -> str:
        """Format a complete crisis response with disclaimer."""
        lines = [
            "The information shared suggests professional support may be helpful.",
            "",
            self.disclaimer,
            "",
            "**General Crisis Resources (not endorsements):**",
        ]

        # Get resources to display
        if resource_ids:
            resources = [self.resources[rid] for rid in resource_ids if rid in self.resources]
        elif regions:
            resources = self.get_by_availability(regions)
        else:
            # Default selection (en: global resources, byte-frozen; locale
            # corpora: the curated file's full entry set).
            resources = self.default_prompt_resources()

        # Add formatted resources
        for resource in resources:
            lines.append("")
            lines.append(resource.format_for_display(include_disclaimer=False))

        lines.extend(
            ["", "For immediate danger: Contact 911 or local emergency services", "", "[DEFER TO HUMAN MODERATOR]"]
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


# The default (en, base-corpus) registry. Import contract preserved from the
# pre-corpus era: this name is what formatters and tests build on.
DEFAULT_CRISIS_RESOURCES = load_crisis_registry("en")


def get_crisis_response_text(
    regions: Optional[List[ResourceAvailability]] = None,
    resource_ids: Optional[List[str]] = None,
    language: Optional[str] = None,
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
    return load_crisis_registry(language).format_crisis_response(resource_ids=resource_ids, regions=regions)
