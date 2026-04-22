"""
Crisis resource formatting for prompt templates.

This module provides functions to format crisis resources for inclusion
in prompts, ensuring consistent presentation and legal disclaimers.
"""

from typing import List, Optional

from ciris_engine.schemas.resources.crisis import DEFAULT_CRISIS_RESOURCES, ResourceAvailability


def format_crisis_resources_block(
    regions: Optional[List[ResourceAvailability]] = None,
    resource_ids: Optional[List[str]] = None,
    include_full_disclaimer: bool = True,
) -> str:
    """
    Format crisis resources for inclusion in prompt templates.

    Args:
        regions: Geographic regions to filter resources by
        resource_ids: Specific resource IDs to include
        include_full_disclaimer: Whether to include the full legal disclaimer

    Returns:
        Formatted crisis resources block for prompt templates
    """
    if include_full_disclaimer:
        # Full format for templates that need complete crisis response
        return DEFAULT_CRISIS_RESOURCES.format_crisis_response(resource_ids=resource_ids, regions=regions)

    # Simplified format for reference only
    lines = ["=== Crisis Resources ==="]

    # Get resources to display
    if resource_ids:
        resources = [
            DEFAULT_CRISIS_RESOURCES.resources[rid] for rid in resource_ids if rid in DEFAULT_CRISIS_RESOURCES.resources
        ]
    elif regions:
        resources = DEFAULT_CRISIS_RESOURCES.get_by_availability(regions)
    else:
        # Default to global resources
        resources = DEFAULT_CRISIS_RESOURCES.get_by_availability([ResourceAvailability.GLOBAL])

    # Add formatted resources
    for resource in resources[:3]:  # Limit to top 3 for space
        lines.append(f"• {resource.name}: {resource.description}")

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
