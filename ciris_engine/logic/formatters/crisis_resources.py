"""
Crisis resource formatting for prompt templates.

This module provides functions to format crisis resources for inclusion
in prompts, ensuring consistent presentation and legal disclaimers.

Since CIRISAgent#971 the resource data lives in the localization corpus
(``ciris_engine/data/localized/crisis_resources_{lang}.json``); pass
``language`` to surface a locale's curated registry. en output is byte-frozen
by the golden test in ``tests/test_crisis_resources_corpus.py``.
"""

from typing import List, Optional

from ciris_engine.schemas.resources.crisis import (
    EMERGENCY_SECTION_LABEL,
    CrisisResource,
    ResourceAvailability,
    country_label,
    load_crisis_registry,
    resolve_location_country,
)

# FSD/RESEARCH_PROMPT_OVERRIDES.md §10.2: every line these blocks emit is class
# `empirical` — static world-facts (crisis numbers, URLs) checkable at compose
# time; they must hold across arms and are gate-checkable. Per-block
# (class, disposition) plumbing is CIRISAgent#973; this comment is the breadcrumb.


def _simplified_resource_line(resource: CrisisResource) -> str:
    """One bullet line for the simplified block.

    Contact info is appended only when the entry carries it. The en default
    path surfaces only URL/search-term directory entries, so this stays
    byte-identical at en; locale corpora with verified national numbers (am)
    surface the number deterministically instead of leaving the LLM to recall
    it parametrically.
    """
    line = f"• {resource.name}: {resource.description}"
    if resource.phone:
        line += f" — Phone: {resource.phone}"
    if resource.text_number:
        line += f" — Text: {resource.text_number}"
    return line


def format_crisis_resources_block(
    regions: Optional[List[ResourceAvailability]] = None,
    resource_ids: Optional[List[str]] = None,
    include_full_disclaimer: bool = True,
    language: Optional[str] = None,
    location: Optional[ResourceAvailability] = None,
) -> str:
    """
    Format crisis resources for inclusion in prompt templates.

    Args:
        regions: Geographic regions to filter resources by
        resource_ids: Specific resource IDs to include
        include_full_disclaimer: Whether to include the full legal disclaimer
        language: Locale whose corpus registry to use. None/'en'/unknown all
            resolve to the en base registry (fail-safe: never an empty block).
        location: The user's opted-in country (CIRISAgent#1248). Its emergency
            numbers render FIRST, labelled as the user's location. None (the
            default) = no location: only the language's countries render. This
            function never reads the environment; the system-block composer does.

    Returns:
        Formatted crisis resources block for prompt templates
    """
    registry = load_crisis_registry(language)

    if include_full_disclaimer:
        # Full format for templates that need complete crisis response
        return registry.format_crisis_response(resource_ids=resource_ids, regions=regions, location=location)

    # Simplified format for reference only
    lines = ["=== Crisis Resources ==="]

    # One gated selection path (CrisisResourceRegistry.select_resources): an
    # unverified number never reaches a prompt on ANY path. en keeps the legacy
    # global-3 cap (byte-frozen); a locale corpus is already curated, so its
    # full set is shown.
    support, groups = registry.emergency_render_groups(
        resource_ids=resource_ids, regions=regions, location=location, limit=3
    )

    for resource in support:
        lines.append(_simplified_resource_line(resource))

    # CIRISAgent#1248: emergency numbers under their own label, never in the
    # helpline list — an ambulance number listed beside crisis lines was
    # relayed to a user as a "mental-health helpline" — and every number
    # carries its country.
    if groups:
        lines.append(f"=== {EMERGENCY_SECTION_LABEL} ===")
        for country, is_location, entries in groups:
            for resource in entries:
                label = country_label(country, is_location, resource)
                lines.append(_simplified_resource_line(resource).replace("• ", f"• [{label}] ", 1))

    lines.append(f"• For immediate danger: {registry.immediate_danger_line('Call', groups_rendered=bool(groups))}")

    return "\n".join(lines)


def get_crisis_resources_system_block(language: Optional[str] = None) -> str:
    """The locale's crisis block as a standalone SYSTEM message.

    The one composer every DMA uses (CIRISAgent#1248, user ruling: crisis blocks
    load into context as part of the standard system prompt, like language
    guidance). Emitted right after per-language guidance at every site that
    carries language guidance — PDMA / CSDMA / DSDMA via
    ``append_round1_accord_blocks``, and ASPDMA / TSASPDMA (both modes) /
    DSASPDMA / MSASPDMA / IDMA directly.

    The block is the SIMPLIFIED format of the locale's own corpus registry
    (emittable entries only — :meth:`CrisisResourceRegistry.is_emittable`). A
    supported locale gets ITS registry, never the en one; only an unknown or
    unusable language resolves to en (fail-safe — never an empty block).

    Emergency numbers: the opted-in location country first (from
    ``resolve_location_country``: setup wizard / env), then the language's
    countries by speaker population, capped at ``LANGUAGE_COUNTRY_CAP`` —
    each labelled by country, under the emergency-services label.

    Before #1248 only DSDMA saw crisis resources, and only for identity
    templates carrying a ``{crisis_resources_block}`` placeholder — the ASPDMA
    that writes the user-facing SPEAK text never saw the curated numbers, so
    the model filled the slot itself.
    """
    return format_crisis_resources_block(
        include_full_disclaimer=False, language=language, location=resolve_location_country()
    )


def get_crisis_resources_guidance() -> str:
    """
    Get the standard crisis resources guidance text for Echo agents.

    Returns:
        Standard guidance text about crisis resources
    """
    return """
=== Crisis Resource Guidance ===

When users appear to be in crisis or express distress:

1. **DO NOT attempt to provide therapy or medical advice**
2. **DO share crisis resources with appropriate disclaimers**
3. **DO defer to human moderators when appropriate**
4. **DO encourage seeking professional help**

Remember: You are an AI moderator, not a healthcare provider. Your role is to:
- Share publicly available crisis resources
- Provide general information only
- Include clear disclaimers about the limitations of AI support
- Defer complex situations to human moderators

Maximum intervention: Provide crisis resources with disclaimers and defer to humans.
"""
