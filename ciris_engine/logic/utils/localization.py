"""
Localization utility for CIRIS backend.

Provides string lookup with interpolation for the reasoning pipeline,
loading from /localization/*.json files. Not a service - just a utility
module that can be imported directly by DMA processors, handlers, formatters.

Usage:
    from ciris_engine.logic.utils.localization import get_string, get_localizer

    # Simple lookup with fallback to English
    text = get_string("am", "agent.greeting")

    # With parameter interpolation
    text = get_string("es", "mobile.startup_services_count", online=5, total=22)

    # Get a localizer bound to a specific language (for repeated lookups)
    loc = get_localizer("fr")
    text = loc("prompts.dma.pdma_header")
"""

import json
import logging
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

# Default language fallback
DEFAULT_LANGUAGE = "en"

# Cache for loaded language data
_language_cache: Dict[str, Dict[str, Any]] = {}

# Lock for thread-safe cache access (not strictly needed for dict but good practice)
_cache_initialized = False


def _get_localization_dir() -> Path:
    """Get the localization directory path.

    Uses platform-aware path resolution with fallback:
    1. CIRIS_LOCALIZATION_DIR env var if set (override)
    2. {CIRIS_HOME}/localization/ (standard location)
    3. Package data directory as fallback (for mobile/bundled deployments)

    Returns:
        Path to the localization directory
    """
    # Check environment variable first (test override)
    env_path = os.getenv("CIRIS_LOCALIZATION_DIR")
    if env_path:
        return Path(env_path)

    # Use centralized path resolution
    from ciris_engine.logic.utils.path_resolution import get_ciris_home

    ciris_home_loc = get_ciris_home() / "localization"

    # Check if CIRIS_HOME/localization exists and has JSON files
    if ciris_home_loc.exists() and any(ciris_home_loc.glob("*.json")):
        return ciris_home_loc

    # Fallback to package data directory (for mobile/bundled deployments)
    # The localization JSON files are bundled in ciris_engine/data/localized/
    package_loc = Path(__file__).parent.parent.parent / "data" / "localized"
    if package_loc.exists():
        logger.debug(f"Using package data localization directory: {package_loc}")
        return package_loc

    # Last resort: return CIRIS_HOME path even if empty (will trigger missing key warnings)
    return ciris_home_loc


def _load_language(lang_code: str) -> Optional[Dict[str, Any]]:
    """Load a language JSON file.

    Args:
        lang_code: ISO 639-1 language code (e.g., 'en', 'am', 'es')

    Returns:
        Parsed JSON data or None if file not found/invalid
    """
    loc_dir = _get_localization_dir()
    file_path = loc_dir / f"{lang_code}.json"

    if not file_path.exists():
        logger.warning(f"Localization file not found: {file_path}")
        return None

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data: Dict[str, Any] = json.load(f)
            logger.debug(f"Loaded localization for '{lang_code}': {len(data)} top-level keys")
            return data
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in localization file {file_path}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error loading localization file {file_path}: {e}")
        return None


def _get_language_data(lang_code: str) -> Dict[str, Any]:
    """Get language data, loading from file if not cached.

    Args:
        lang_code: ISO 639-1 language code

    Returns:
        Language data dict (empty dict if not found)
    """
    global _cache_initialized

    if lang_code not in _language_cache:
        data = _load_language(lang_code)
        _language_cache[lang_code] = data if data is not None else {}

    # Always ensure English is loaded for fallback
    if DEFAULT_LANGUAGE not in _language_cache and lang_code != DEFAULT_LANGUAGE:
        en_data = _load_language(DEFAULT_LANGUAGE)
        _language_cache[DEFAULT_LANGUAGE] = en_data if en_data is not None else {}

    _cache_initialized = True
    return _language_cache.get(lang_code, {})


def _resolve_key(data: Dict[str, Any], key: str) -> Optional[str]:
    """Resolve a dot-notation key from nested dict.

    Args:
        data: The language data dictionary
        key: Dot-notation key (e.g., 'prompts.dma.pdma_header')

    Returns:
        The string value or None if not found
    """
    parts = key.split(".")
    current: Any = data

    for part in parts:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
        if current is None:
            return None

    # Must be a string at the end
    if isinstance(current, str):
        return current
    return None


def _interpolate(template: str, **params: Any) -> str:
    """Interpolate parameters into a template string.

    Supports {param} syntax: "Hello {name}!" with name="World" -> "Hello World!"

    Args:
        template: The template string with {param} placeholders
        **params: Parameter values to substitute

    Returns:
        Interpolated string
    """
    result = template
    for name, value in params.items():
        result = result.replace(f"{{{name}}}", str(value))
    return result


def get_string(
    lang_code: str,
    key: str,
    default: Optional[str] = None,
    **params: Any,
) -> str:
    """Get a localized string with optional parameter interpolation.

    Fallback chain: requested language -> English -> default -> key itself

    Args:
        lang_code: ISO 639-1 language code (e.g., 'en', 'am', 'es', 'fr')
        key: Dot-notation key (e.g., 'agent.greeting', 'prompts.dma.pdma_header')
        default: Optional default value if key not found in any language
        **params: Parameters for interpolation (e.g., count=5, name="Alice")

    Returns:
        The localized, interpolated string

    Examples:
        >>> get_string("am", "agent.greeting")
        "ሰላም! ዛሬ እንዴት ልረዳዎ?"

        >>> get_string("es", "mobile.startup_services_count", online=5, total=22)
        "5/22 servicios en línea"

        >>> get_string("xx", "nonexistent.key", default="Fallback text")
        "Fallback text"
    """
    # Try requested language first
    lang_data = _get_language_data(lang_code)
    result = _resolve_key(lang_data, key)

    # Check for [EN] placeholder marker (indicates untranslated)
    if result is not None and result.startswith("[EN]"):
        logger.debug(f"[LOCALIZATION] Key '{key}' has [EN] placeholder, falling back to English (lang={lang_code})")
        result = None  # Treat as missing, fall back to English

    # Fall back to English if not found
    if result is None and lang_code != DEFAULT_LANGUAGE:
        en_data = _get_language_data(DEFAULT_LANGUAGE)
        result = _resolve_key(en_data, key)
        if result is not None:
            logger.info(f"[LOCALIZATION] Fallback to English for key '{key}' (requested lang={lang_code})")
        else:
            logger.warning(f"[LOCALIZATION] Key '{key}' not found in {lang_code} or English")

    # Fall back to default or key itself
    if result is None:
        if default is not None:
            logger.debug(
                f"[LOCALIZATION] Using default for key '{key}': {default[:50] if len(default) > 50 else default}"
            )
            result = default
        else:
            logger.warning(f"[LOCALIZATION] MISSING key: {key} (lang={lang_code}) - returning raw key")
            result = key
    else:
        # Successfully found the key - log at debug level
        preview = result[:50] if len(result) > 50 else result
        logger.debug(f"[LOCALIZATION] Found key '{key}' (lang={lang_code}): {preview}...")

    # Apply parameter interpolation
    if params:
        result = _interpolate(result, **params)

    return result


def get_localizer(lang_code: str) -> Callable[..., str]:
    """Get a localizer function bound to a specific language.

    Useful when you need to make many lookups in the same language.

    Args:
        lang_code: ISO 639-1 language code

    Returns:
        A function that takes (key, **params) and returns the localized string

    Example:
        >>> loc = get_localizer("fr")
        >>> loc("agent.greeting")
        "Bonjour ! Comment puis-je vous aider aujourd'hui ?"
        >>> loc("mobile.startup_services_count", online=5, total=22)
        "5/22 services en ligne"
    """

    def localizer(key: str, default: Optional[str] = None, **params: Any) -> str:
        return get_string(lang_code, key, default=default, **params)

    return localizer


def get_available_languages() -> list[str]:
    """Get list of available language codes.

    Returns:
        List of ISO 639-1 language codes with localization files
    """
    loc_dir = _get_localization_dir()
    if not loc_dir.exists():
        return [DEFAULT_LANGUAGE]

    languages = []
    for file_path in loc_dir.glob("*.json"):
        if file_path.stem != "manifest" and not file_path.stem.startswith("_"):
            languages.append(file_path.stem)

    return sorted(languages)


def get_language_meta(lang_code: str) -> Dict[str, str]:
    """Get metadata for a language (name, direction, etc.).

    Args:
        lang_code: ISO 639-1 language code

    Returns:
        Metadata dict with keys like 'language', 'language_name', 'direction'
    """
    lang_data = _get_language_data(lang_code)
    meta = lang_data.get("_meta", {})
    return {
        "language": meta.get("language", lang_code),
        "language_name": meta.get("language_name", lang_code.upper()),
        "direction": meta.get("direction", "ltr"),
    }


def preload_languages(lang_codes: Optional[list[str]] = None) -> None:
    """Preload language files into cache.

    Call this at startup to avoid lazy loading delays.

    Args:
        lang_codes: List of language codes to preload, or None for all available
    """
    if lang_codes is None:
        lang_codes = get_available_languages()

    for lang_code in lang_codes:
        _get_language_data(lang_code)
        logger.debug(f"Preloaded localization: {lang_code}")


def clear_cache() -> None:
    """Clear the language cache. Useful for testing or hot-reloading."""
    global _language_cache, _cache_initialized
    _language_cache = {}
    _cache_initialized = False
    logger.debug("Localization cache cleared")


def get_preferred_language() -> str:
    """Get the preferred language from environment.

    Checks CIRIS_PREFERRED_LANGUAGE environment variable.

    Returns:
        Language code (defaults to 'en')
    """
    return os.getenv("CIRIS_PREFERRED_LANGUAGE", DEFAULT_LANGUAGE)


def resolve_language_for_new_task(
    user_lang: Optional[str] = None,
    channel_lang: Optional[str] = None,
    explicit_lang: Optional[str] = None,
) -> str:
    """Resolve the preferred_language to set on a NEWLY CREATED task.

    Use this at any processor / handler / adapter site that creates a task
    where no incoming-message context provides the language directly. The
    priority chain follows BCP 47 / IETF localization best practice:

      1. **explicit_lang** — caller passed a specific value (e.g. inherited
         from a parent task in a deferral-resolution chain).
      2. **user_lang** — user's explicit preference (e.g. from a user
         profile, OAuth claim, or this-message override).
      3. **channel_lang** — the originating channel/community/server has a
         configured working language.
      4. **env (CIRIS_PREFERRED_LANGUAGE)** — agent's deployment-level
         default; ultimately English if unset.

    For SYSTEM-internal tasks (wakeup, dream, solitude, shutdown — no user,
    no real channel), pass all three args as None and the helper falls
    through to the env default.

    Returns the resolved ISO 639-1 language code (always a non-empty str).
    """
    for candidate in (explicit_lang, user_lang, channel_lang):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return get_preferred_language()


def _str_lang(obj: Any, attr: str) -> Optional[str]:
    """Read attr off obj only if it's a non-empty string.

    Mock objects return a MagicMock for any attribute access, so guarding
    against non-strings is required for tests that don't pre-stub attrs.
    Dict-shaped objects (commonly emitted by the SDK / API context blocks)
    are handled via ``.get`` so the chain works uniformly across attr-style
    dataclass contexts and dict-style payloads.
    """
    if isinstance(obj, dict):
        val = obj.get(attr)
    else:
        val = getattr(obj, attr, None)
    return val.strip() if isinstance(val, str) and val.strip() else None


def _lang_from_obj_or_inner_context(obj: Any) -> Optional[str]:
    """Try `obj.preferred_language`, then `obj.context.preferred_language`,
    then `obj.initial_context.preferred_language`.

    The third attribute exists because ProcessingQueueItem (the runtime
    processing-queue representation of a Thought) stores its inherited
    ThoughtContext on `initial_context` rather than `context` — so a
    helper that only walks `.context` silently misses every conscience
    check that runs against a ProcessingQueueItem rather than a raw
    Thought, falling through the rest of the resolution chain to the
    env-var default. This was the silent symptom that caused every
    non-Amharic agent's conscience to read its prompts in whatever
    CIRIS_PREFERRED_LANGUAGE was on the host.

    Handles dict-shaped objects via ``_str_lang``'s dict branch.
    """
    if obj is None:
        return None
    lang = _str_lang(obj, "preferred_language")
    if lang:
        return lang
    if isinstance(obj, dict):
        inner_ctx = obj.get("context")
        initial_ctx = obj.get("initial_context")
    else:
        inner_ctx = getattr(obj, "context", None)
        initial_ctx = getattr(obj, "initial_context", None)
    if inner_ctx is not None:
        lang = _str_lang(inner_ctx, "preferred_language")
        if lang:
            return lang
    if initial_ctx is not None:
        return _str_lang(initial_ctx, "preferred_language")
    return None


def _lang_from_thought_or_task(context: Any) -> Optional[str]:
    """Layer 1: task/thought-specific preferred_language.

    Checks context.thought (and its inner context), then context.task /
    context.current_task (and its inner context), in that order. Handles
    both attr-style and dict-style contexts.
    """
    if isinstance(context, dict):
        thought = context.get("thought")
        task = context.get("task") or context.get("current_task")
    else:
        thought = getattr(context, "thought", None)
        task = getattr(context, "task", None) or getattr(context, "current_task", None)
    thought_lang = _lang_from_obj_or_inner_context(thought)
    if thought_lang:
        return thought_lang
    return _lang_from_obj_or_inner_context(task)


def _lang_from_user_profiles(context: Any) -> Optional[str]:
    """Layer 2: first matching user profile's preferred_language (or
    legacy `language` alias). Looks under `context.system_snapshot` first,
    then treats `context` itself as the snapshot. Handles both attr-style
    and dict-style contexts uniformly."""
    if isinstance(context, dict):
        snapshot: Any = context.get("system_snapshot") or context
    else:
        snapshot = getattr(context, "system_snapshot", None) or context

    if isinstance(snapshot, dict):
        user_profiles = snapshot.get("user_profiles")
    else:
        user_profiles = getattr(snapshot, "user_profiles", None)

    if not isinstance(user_profiles, list):
        return None
    for profile in user_profiles:
        lang = _str_lang(profile, "preferred_language") or _str_lang(profile, "language")
        if lang:
            return lang
    return None


def get_user_language_from_context(context: Any) -> str:
    """Resolve the agent's working language for THIS thought.

    Walks the canonical localization chain in priority order:
      1. Task / thought specific (set by the originating channel/adapter):
         a. `context.thought.preferred_language`
         b. `context.thought.context.preferred_language`
         c. `context.task.preferred_language`
         d. `context.task.context.preferred_language`
      2. Channel / user preference: first matching
         `system_snapshot.user_profiles[*].preferred_language`
         (or `.language` legacy alias)
      3. System setting: `CIRIS_PREFERRED_LANGUAGE` env var
      4. English default

    Adapters and the QA runner set the language at task/thought creation
    time by populating the appropriate `preferred_language` field. This
    helper does NOT do script-based language detection — language is an
    explicit input, not something we infer from the bytes.
    """
    if context is None:
        logger.debug("get_user_language_from_context: context is None, using env fallback")
        return get_preferred_language()

    try:
        lang = _lang_from_thought_or_task(context)
        if lang:
            logger.debug(f"get_user_language_from_context: thought/task lang='{lang}'")
            return lang

        lang = _lang_from_user_profiles(context)
        if lang:
            logger.debug(f"get_user_language_from_context: profile lang='{lang}'")
            return lang

        logger.debug("get_user_language_from_context: no thought/task/profile signal — env fallback")
    except Exception as e:
        logger.debug(f"get_user_language_from_context: error walking chain: {e}")

    return get_preferred_language()
