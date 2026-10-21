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

from ciris_engine.schemas.resources.crisis import CrisisResource, ResourceAvailability, load_crisis_registry

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
) -> str:
    """
    Format crisis resources for inclusion in prompt templates.

    Args:
        regions: Geographic regions to filter resources by
        resource_ids: Specific resource IDs to include
        include_full_disclaimer: Whether to include the full legal disclaimer
        language: Locale whose corpus registry to use. None/'en'/unknown all
            resolve to the en base registry (fail-safe: never an empty block).

    Returns:
        Formatted crisis resources block for prompt templates
    """
    registry = load_crisis_registry(language)

    if include_full_disclaimer:
        # Full format for templates that need complete crisis response
        return registry.format_crisis_response(resource_ids=resource_ids, regions=regions)

    # Simplified format for reference only
    lines = ["=== Crisis Resources ==="]

    # Get resources to display
    if resource_ids:
        resources = [registry.resources[rid] for rid in resource_ids if rid in registry.resources][:3]
    elif regions:
        resources = registry.get_by_availability(regions)[:3]
    else:
        # Default selection: en keeps the legacy global-3 cap (byte-frozen);
        # a locale corpus is already curated, so its full set is shown.
        resources = registry.default_prompt_resources(limit=3)

    # Add formatted resources
    for resource in resources:
        lines.append(_simplified_resource_line(resource))

    lines.append("• For immediate danger: Call 911 or local emergency services")

    return "\n".join(lines)


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
