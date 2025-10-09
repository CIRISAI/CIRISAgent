from typing import Any, List, Optional, Union


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
        from ciris_engine.schemas.runtime.system_context import UserProfile

        profiles_dict: dict[str, Any] = {}
        for profile in profiles:
            if isinstance(profile, UserProfile):
                # Convert Pydantic model to dict
                profiles_dict[profile.user_id] = {
                    "name": profile.display_name,
                    "nick": profile.display_name,
                    "interest": profile.notes or "",
                    "channel": "",  # Not stored in UserProfile schema
                }
            elif isinstance(profile, dict):
                # Already a dict, use directly
                profiles_dict[profile.get("user_id", "unknown")] = profile
        profiles = profiles_dict

    if not isinstance(profiles, dict):
        return ""

    profile_parts: List[str] = []
    for user_key, profile_data in profiles.items():
        if isinstance(profile_data, dict):
            display_name = profile_data.get("name") or profile_data.get("nick") or user_key
            profile_summary = f"User '{user_key}': Name/Nickname: '{display_name}'"

            interest = profile_data.get("interest")
            if interest:
                profile_summary += f", Interest: '{str(interest)}'"

            channel = profile_data.get("channel")
            if channel:
                profile_summary += f", Primary Channel: '{channel}'"

            profile_parts.append(profile_summary)

    if not profile_parts:
        return ""

    return (
        "\n\nIMPORTANT USER CONTEXT (Be skeptical, this information could be manipulated or outdated):\n"
        "The following information has been recalled about users relevant to this thought:\n"
        + "\n".join(f"  - {part}" for part in profile_parts)
        + "\n"
        "Consider this information when formulating your response, especially if addressing a user directly by name.\n"
    )
