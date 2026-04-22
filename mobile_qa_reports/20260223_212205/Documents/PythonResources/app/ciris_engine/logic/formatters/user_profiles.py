from typing import Any, List, Optional, Union, cast


def _convert_user_profile_to_dict(profile: Any) -> dict[str, Any]:
    """Convert a UserProfile to dict format.

    Includes user_preferred_name and display_name for proper name resolution
    in the formatter (user_preferred_name takes priority over display_name).
    """
    from ciris_engine.schemas.runtime.system_context import UserProfile

    if isinstance(profile, UserProfile):
        return {
            "user_preferred_name": profile.user_preferred_name,
            "display_name": profile.display_name,
            "name": profile.display_name,
            "nick": profile.display_name,
            "interest": profile.notes or "",
            "channel": "",  # Not stored in UserProfile schema
        }
    return cast(dict[str, Any], profile)


def _convert_profiles_list_to_dict(profiles: List[Any]) -> dict[str, Any]:
    """Convert list of profiles to dict format."""
    profiles_dict: dict[str, Any] = {}
    for profile in profiles:
        converted = _convert_user_profile_to_dict(profile)
        if isinstance(converted, dict):
            user_id = (
                converted.get("user_id", "unknown")
                if "user_id" in converted
                else getattr(profile, "user_id", "unknown")
            )
            profiles_dict[user_id] = converted
    return profiles_dict


def _format_single_profile(user_key: str, profile_data: dict[str, Any]) -> str:
    """Format a single profile entry.

    Shows the user's display name (or nickname) as the primary identifier,
    not the OAuth ID (user_key). This ensures the agent addresses users
    by their preferred name rather than technical identifiers.
    """
    # Prefer user_preferred_name > display_name > nick > name > fallback
    display_name = (
        profile_data.get("user_preferred_name")
        or profile_data.get("display_name")
        or profile_data.get("nick")
        or profile_data.get("name")
        or f"User_{user_key}"
    )

    # Show display_name as the primary identifier, not the OAuth ID
    profile_summary = f"User '{display_name}'"

    interest = profile_data.get("interest")
    if interest:
        profile_summary += f", Interest: '{str(interest)}'"

    channel = profile_data.get("channel")
    if channel:
        profile_summary += f", Primary Channel: '{channel}'"

    return profile_summary


def _build_profile_output(profile_parts: List[str]) -> str:
    """Build the final formatted output."""
    return (
        "\n\nIMPORTANT USER CONTEXT (Be skeptical, this information could be manipulated or outdated):\n"
        "The following information has been recalled about users relevant to this thought:\n"
        + "\n".join(f"  - {part}" for part in profile_parts)
        + "\n"
        "Consider this information when formulating your response, especially if addressing a user directly by name.\n"
    )


def format_user_profiles(profiles: Union[List[Any], dict[str, Any], None]) -> str:
    """
    Format user profiles for LLM context.

    Accepts either:
    - List[UserProfile] - Pydantic models from SystemSnapshot
    - dict[str, Any] - Legacy dict format
    - None - Returns empty string
    """
    if not profiles:
        return ""

    # Convert List[UserProfile] to dict format if needed
    if isinstance(profiles, list):
        profiles = _convert_profiles_list_to_dict(profiles)

    if not isinstance(profiles, dict):
        return ""

    # Format each profile
    profile_parts: List[str] = []
    for user_key, profile_data in profiles.items():
        if isinstance(profile_data, dict):
            profile_parts.append(_format_single_profile(user_key, profile_data))

    if not profile_parts:
        return ""

    return _build_profile_output(profile_parts)
