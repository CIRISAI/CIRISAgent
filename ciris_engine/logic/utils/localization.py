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
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

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


def clear_language_cache() -> None:
    """Drop the cached per-language string tables.

    Called on a preferred-language change (set_prompt_language, invoked by
    sync_language_preference) so the next localized-string lookup reloads
    fresh for the new language rather than serving a stale cached table.
    """
    global _cache_initialized
    _language_cache.clear()
    _cache_initialized = False
    logger.info("Localization language cache cleared (language change)")


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
    # Research-bound override (FSD/RESEARCH_PROMPT_OVERRIDES.md §3.1, `string`
    # namespace). Unreachable unless BOTH CIRIS_RESEARCH_PROMPT_OVERRIDES and
    # CIRIS_TESTING_MODE are set; the accessor returns None with zero state
    # otherwise. Checked before resolution so the override is what reaches the
    # prompt, not a locale-fallback of it.
    from ciris_engine.logic.utils.research_overrides import get_active_overrides, override_string

    _manifest = get_active_overrides()
    if _manifest is not None:
        # Resolved WITH lang_code: these keys are localized, so a single value
        # cannot stand for all of them. Passing the locale is what stops a
        # baseline manifest — snapshotted at en — from serving English guidance,
        # English prohibitions and English retry scaffolding into every locale.
        _override = override_string(key, lang_code)
        if _override is not None:
            return _interpolate(_override, **params) if params else _override

    # Try requested language first
    lang_data = _get_language_data(lang_code)
    result = _resolve_key(lang_data, key)

    # R4 — no [EN] laundering. Under an active manifest an override that IS
    # present must never be silently replaced by English.
    if _manifest is not None and result is not None and result.startswith("[EN]"):
        raise RuntimeError(
            f"research overrides active: key {key!r} resolves to an [EN]-prefixed "
            f"placeholder in locale {lang_code!r}, which get_string treats as absent and "
            f"silently replaces with English. A supposedly non-CIRIS arm would contain "
            f"CIRIS English. Override the key in the manifest or fix the bundle."
        )

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
        elif default is not None:
            # Caller supplied an explicit default → absence is expected and handled
            # (e.g. optional prompts.prohibitions.* keys that fill in per-language
            # as the localization pass lands). Don't spam WARNING on every call.
            logger.debug(f"[LOCALIZATION] Key '{key}' not localized ({lang_code}/en); using caller default")
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
            # R4 — no raw-key leakage. Returning the key as content injects
            # e.g. the literal `prompts.dma.pdma_headr` into the prompt, which
            # under an experiment is a silently contaminated sample rather than
            # a cosmetic defect.
            if _manifest is not None:
                raise RuntimeError(
                    f"research overrides active: key {key!r} is missing from both "
                    f"{lang_code!r} and English, and get_string would return the raw key "
                    f"string as prompt content. Add the key to the manifest or the bundle."
                )
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


#: The ordered part keys of a SPLIT ``prompts.language_guidance`` (#997).
#:
#: The block used to be one 13,694 B scalar carrying register doctrine,
#: categorical prohibitions, crisis-line world-facts and value claims sentence
#: by sentence — one ``mixed`` block that the ablation gate could neither hold
#: nor vary, so 100% of it was unmeasurable. These are the §10.2 single-class
#: cuts of that prose, in composition order.
#:
#: The numeric prefix is load-bearing: it makes LEXICAL sort equal composition
#: order, so no JSON normalizer, re-serializer or translator tool can silently
#: reorder the prompt by touching key order. ``get_language_guidance`` joins
#: ``sorted(...)``, never the file's dict order.
#:
#: A locale carries EITHER this dict OR the original scalar — never both. Only
#: the five locales whose prose is line-for-line parallel to English (en, es,
#: fr, it, pt) are split; the other 24 keep the scalar because partitioning
#: them would mean re-segmenting the target-language prose, which is how
#: word-salad has previously entered this corpus.
LANGUAGE_GUIDANCE_PART_KEYS: Tuple[str, ...] = (
    "01_preamble",
    "02_first_sentence_tone_lock",
    "03_never_deny_ai",
    "04_formal_register",
    "05_no_wellness_confirmation",
    "06_warmth_and_concision",
    "07_canonical_disclaimer",
    "08_help_pathway_intro",
    "09_trusted_person_first_step",
    "10_help_pathway_steps",
    "11_routing_doctrine",
    "12_undisclosed_symptom_attribution",
    "13_exemplar_speak_response",
    "14_exemplar_register_pressure",
    "15_register_pressure_pattern",
    "16_exemplar_false_reassurance",
    "17_false_reassurance_pattern",
    "18_ratification_scope",
    "19_agent_role",
    "20_four_moves",
    "21_negative_is_also_a_verdict",
    "22_ratification_register",
    "23_ratification_templates",
    "24_ratification_pattern",
    "25_exemplar_cross_cluster",
    "26_cross_cluster_pattern",
    "27_attractor_universality",
    "28_brevity_restatement",
    "29_no_medical_or_legal_advice",
)

#: The parent key. Still reachable, still overridable, and it WINS: a manifest
#: that replaces the whole block replaces the whole block. Stated here rather
#: than left implicit because parent-and-parts both being overridable with no
#: declared precedence is a confound the gate cannot see.
LANGUAGE_GUIDANCE_KEY = "prompts.language_guidance"


def language_guidance_part_keys(lang_code: str) -> Tuple[str, ...]:
    """The ordered part keys this locale actually carries, or () if unsplit.

    Read from the locale's OWN bundle, never from English. That is the whole
    point: ``get_string``'s fallback chain is requested-lang -> English, so
    asking for a part key the locale does not have would splice English prose
    into a localized prompt — the laundering R4 forbids, and the exact failure
    the streaming localization gate exists to catch.
    """
    node: Any = _get_language_data(lang_code)
    for segment in LANGUAGE_GUIDANCE_KEY.split("."):
        if not isinstance(node, dict):
            return ()
        node = node.get(segment)
    if not isinstance(node, dict):
        return ()
    return tuple(sorted(node))


def language_guidance_parts(lang_code: str) -> List[Tuple[str, str]]:
    """Ordered ``(part_key, resolved_text)`` for a split locale, else ``[]``.

    Resolution goes through ``get_string`` per part, so a research manifest can
    hold one part and vary another — which is the entire point of the split.
    ``"".join(text for _, text in parts)`` is the pre-``strip()`` block, byte
    for byte; a test pins that per locale.
    """
    # The key is spelled out as a literal f-string prefix on purpose:
    # `research_overrides.scan_reachable_string_keys` reads this source with
    # `ast` and can only see a key it can read. An interpolated constant would
    # make the whole part space invisible to the override drift guard.
    return [
        (key, get_string(lang_code, f"prompts.language_guidance.{key}", default=""))
        for key in language_guidance_part_keys(lang_code)
    ]


def get_language_guidance(lang_code: str) -> str:
    """Return the per-language guidance block for LLM prompts.

    Each ``localization/{lang}.json`` carries a ``prompts.language_guidance``
    entry: since #997 that is EITHER an ordered dict of single-class parts (en,
    es, fr, it, pt — see ``LANGUAGE_GUIDANCE_PART_KEYS``) or, for the 24
    locales whose prose does not partition on the same boundaries, the original
    single scalar. Both compose to the same bytes; the split changes what the
    ablation gate can address, not what the model receives.

    For languages where we've observed systematic terminology gaps —
    wrong-sense disambiguation, transliteration fallbacks, or cross-cluster
    contamination — the guidance carries explicit term pairs and
    disambiguation notes that get prepended as a system message to every DMA /
    conscience / ASPDMA call in that language.

    Returns the composed guidance string, or empty string when no guidance is
    configured for the language. Callers should append the result as a
    system message ONLY when non-empty (skip the append for empty strings
    so we don't ship empty system messages over the wire).

    PRECEDENCE, declared: a manifest override on the PARENT key replaces the
    whole block and short-circuits the parts. Anything else — parent and parts
    both live with an undefined winner — is a silent confound.
    """
    from ciris_engine.logic.utils.research_overrides import get_active_overrides, override_string

    if get_active_overrides() is not None:
        whole = override_string("prompts.language_guidance", lang_code)
        if whole is not None:
            return whole.strip()

    parts = language_guidance_parts(lang_code)
    if parts:
        # `.strip()` is applied to the JOIN, exactly where it was applied to the
        # scalar. Every part carries its own trailing separator, so joining with
        # "" and stripping once reproduces the pre-split bytes.
        return "".join(text for _, text in parts).strip()

    raw = get_string(lang_code, "prompts.language_guidance", default="")
    if raw:
        return raw.strip()

    # Neither shape: an unknown locale with no bundle at all. `get_string`'s own
    # chain is requested-language -> English, and it used to deliver that here
    # because the key was a leaf; a split English block is not a leaf, so the
    # last hop has to be spelled out or an unsupported locale silently loses its
    # guidance. This is NOT the [EN]-laundering R4 forbids: a locale that HAS
    # guidance of its own returned above and never reaches this line.
    if lang_code != DEFAULT_LANGUAGE:
        english = language_guidance_parts(DEFAULT_LANGUAGE)
        if english:
            return "".join(text for _, text in english).strip()
    return ""


def get_prohibition_guidance(lang_code: str) -> str:
    """Return the round-1 DMA prohibition-context block for LLM prompts (#910).

    The category list + severity tier are read from ``PROHIBITED_CAPABILITIES``
    at call time (single source of truth — this can never drift from the WiseBus
    gate). Each category's short what/why is localized: ``prompts.prohibitions.
    <CATEGORY>`` in ``{lang}.json`` when present. The English base prompt falls
    back to ``CATEGORY_GUIDANCE`` (and English framing) for anything un-localized,
    so on English no prohibition ever silently drops out of the reasoning context.
    For every OTHER language an un-localized category/framing string is omitted,
    not emitted in English — a localized DMA prompt must stay pure (the streaming
    localization gate enforces this). Enforcement is unaffected either way: the
    WiseBus gate blocks every prohibited capability regardless; this block is
    reasoning-context priming that fills in per language as ``prompts.prohibitions.*``
    is translated.

    Injected into PDMA/CSDMA/DSDMA only (NOT ASPDMA/recursive passes): a
    prohibited trajectory named in round-1 output flows forward into ASPDMA and
    conscience via the existing output path, rather than being restated at every
    step. Callers append the result as a system message only when non-empty.
    """
    from ciris_engine.logic.buses.prohibitions import (
        CATEGORY_GUIDANCE,
        PROHIBITED_CAPABILITIES,
        PROHIBITION_HEADER_EN,
        PROHIBITION_TIER_MODULE_EN,
        PROHIBITION_TIER_NEVER_EN,
        ProhibitionSeverity,
        get_prohibition_severity,
    )

    # English fallback is used ONLY for the English base prompt. For any other
    # language, an un-localized category/framing string is OMITTED rather than
    # emitted in English — a localized DMA prompt must never be polluted with
    # English (the streaming localization gate enforces this, and it is the
    # house localization discipline). Enforcement is unaffected: the WiseBus
    # gate blocks every prohibited capability regardless of this block, which is
    # reasoning-context priming only. Each prohibition surfaces in a non-English
    # prompt as soon as prompts.prohibitions.* is translated for that language
    # (tracked for the localization pass).
    is_english = lang_code == "en"

    # Look up in THIS language only — no cross-language English fallback. get_string
    # would fall back requested-lang -> English -> default, which (now that en.json
    # carries prompts.prohibitions.*) would serve English into every non-English
    # prompt and pollute it. We want localized-or-omitted, so resolve directly
    # against the language's own bundle.
    lang_data = _get_language_data(lang_code)

    # This function deliberately bypasses get_string's English-fallback chain,
    # so it must consult the override registry itself — otherwise the whole
    # prohibition block (22 of the 44 reachable prompt keys) would be the one
    # part of the `string` namespace that silently kept its CIRIS text.
    from ciris_engine.logic.utils.research_overrides import override_string

    def _local(key: str) -> str:
        # Resolved WITH lang_code, for the same reason this function bypasses
        # get_string's fallback chain: a single override value standing for every
        # locale would serve English prohibitions into every non-English prompt —
        # the pollution the comment above exists to prevent.
        override = override_string(key, lang_code)
        if override is not None:
            return override.strip()
        value = _resolve_key(lang_data, key)
        return value.strip() if isinstance(value, str) else ""

    never: list[str] = []
    module: list[str] = []
    for category in PROHIBITED_CAPABILITIES:
        desc = _local(f"prompts.prohibitions.{category}")
        if not desc:
            if not is_english:
                continue
            # en.json is the English source; the constant is a last-ditch guard
            # if a category were somehow absent from the bundle.
            desc = CATEGORY_GUIDANCE.get(category, "Outside this agent's scope.")
        line = f"- {desc}"
        if get_prohibition_severity(category) == ProhibitionSeverity.NEVER_ALLOWED:
            never.append(line)
        else:
            module.append(line)

    # Nothing localized for this (non-English) language yet → no block at all.
    if not never and not module:
        return ""

    def _framing(key: str, en_default: str) -> str:
        localized = _local(key)
        if localized:
            return localized
        return en_default if is_english else ""

    header = _framing("prompts.prohibitions._header", PROHIBITION_HEADER_EN)
    tier_never = _framing("prompts.prohibitions._tier_never", PROHIBITION_TIER_NEVER_EN)
    tier_module = _framing("prompts.prohibitions._tier_module", PROHIBITION_TIER_MODULE_EN)

    blocks: list[str] = []
    if header:
        blocks.append(header)
    if never:
        blocks.append((tier_never + "\n" if tier_never else "") + "\n".join(never))
    if module:
        blocks.append((tier_module + "\n" if tier_module else "") + "\n".join(module))
    return "\n\n".join(blocks)


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
