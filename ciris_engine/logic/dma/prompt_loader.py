"""
Prompt Loader for DMA Systems

This module provides functionality to load prompts from YAML files,
separating prompt content from business logic for better maintainability.

Supports localized prompts by checking for language-specific versions in
prompts/localized/{lang}/ directories.
"""

import logging
import os
import re
from pathlib import Path
from typing import Any, Optional

import yaml

from ciris_engine.schemas.dma.prompts import PromptCollection

logger = logging.getLogger(__name__)


def _sanitize_for_log(value: str, max_length: int = 20) -> str:
    """Sanitize a value for safe inclusion in log messages."""
    sanitized = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", value)
    return sanitized[:max_length] + "..." if len(sanitized) > max_length else sanitized


# Default language for prompts
DEFAULT_LANGUAGE = "en"

# Polyglot block substitution: {{POLYGLOT_<NAME>}} on its own line is replaced
# at load time with the contents of data/localized/polyglot/<name_lowercase>.txt.
# The placeholder's leading indent is re-applied to every polyglot line so the
# substituted block stays inside its YAML block-scalar. See
# ciris_engine/data/localized/polyglot/CLAUDE.md for the polyglot doctrine.
POLYGLOT_PATTERN = re.compile(r"^(?P<indent>[ \t]*)\{\{POLYGLOT_(?P<name>[A-Z0-9_]+)\}\}[ \t]*$", re.MULTILINE)
POLYGLOT_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "localized" / "polyglot"

# Detects identifier-style placeholders that survived `.format()` — i.e. the
# template referenced a variable that was never passed to format(). Identifier-
# only intentionally: matches `{user_id}` and `{full_context_str}` but NOT JSON
# examples like `{"key": "val"}`, action-verb sets like `{speak, defer}`, or
# numeric values like `{0.5}`. Any match is a real bug, not a false positive.
UNEXPANDED_PLACEHOLDER_PATTERN = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}")


def safe_format(template: str, *, source: str, **kwargs: Any) -> str:
    """`.format(**kwargs)` with a post-pass that catches unexpanded placeholders.

    An unexpanded `{identifier}` in the rendered string means the template
    references a variable that was not passed — usually a stale field name
    after a schema reshape, a typo in the YAML, or a missing kwarg at the
    call site. The LLM would silently receive a malformed prompt with literal
    placeholder tokens; output quality degrades without any error signal.

    Behaviour:
      - PRODUCTION (default): leftovers logged at WARNING with `source` so
        ops can see which template/locale leaked which identifier.
      - STRICT (env `CIRIS_STRICT_PROMPT_FORMAT=1`): leftovers raise
        `ValueError` so test suites turn this into a hard failure.

    Args:
        template: The template string (typically loaded from a YAML field).
        source: Human-readable provenance for diagnostics (e.g.
            "pdma_ethical.system_guidance_header[en]"). Surfaces in both
            the warning log and the strict-mode exception message.
        **kwargs: Variables passed through to `str.format`.

    Returns:
        The formatted string. In production, returns even if leftovers
        exist (warning logged); in strict mode, raises before returning.

    Raises:
        ValueError: in strict mode if any unexpanded placeholders survive.
        KeyError: if `template.format(**kwargs)` itself raises (the
            "missing kwarg" failure mode is loud — this guard catches the
            silent "stale field name" mode where the kwarg simply isn't in
            kwargs but the template still references it via .format()'s
            permissive double-brace escape mishandling, etc.).
    """
    rendered = template.format(**kwargs)
    leftovers = sorted(set(UNEXPANDED_PLACEHOLDER_PATTERN.findall(rendered)))
    if leftovers:
        msg = (
            f"[PROMPT-FORMAT] Unexpanded placeholders in {source}: {leftovers}. "
            f"Template references variable(s) not passed to .format(). Likely "
            f"causes: stale field name after schema reshape, typo in YAML, or "
            f"missing kwarg at the call site."
        )
        if os.environ.get("CIRIS_STRICT_PROMPT_FORMAT", "").lower() in ("1", "true", "yes"):
            raise ValueError(msg)
        logger.warning(msg)
    return rendered


class DMAPromptLoader:
    """Loads and manages DMA prompts from YAML files.

    Supports localized prompts by checking for language-specific versions.
    """

    def __init__(self, prompts_dir: Optional[str] = None, language: str = DEFAULT_LANGUAGE):
        """
        Initialize the prompt loader.

        Args:
            prompts_dir: Optional custom prompts directory path.
                        If None, uses the default prompts/ directory relative to this file.
            language: ISO 639-1 language code (e.g., 'en', 'am', 'es').
                     If localized version exists, it will be used; otherwise falls back to English.
        """
        if prompts_dir is None:
            # Default to prompts/ directory in same location as this file
            self.prompts_dir = Path(__file__).parent / "prompts"
        else:
            self.prompts_dir = Path(prompts_dir)

        self.language = language
        self.localized_dir = self.prompts_dir / "localized" / language

        if not self.prompts_dir.exists():
            logger.warning(f"Prompts directory does not exist: {self.prompts_dir}")

    def set_language(self, language: str) -> None:
        """Update the language for prompt loading.

        Args:
            language: ISO 639-1 language code
        """
        self.language = language
        self.localized_dir = self.prompts_dir / "localized" / language
        logger.debug(f"DMA prompt language set to: {_sanitize_for_log(language)}")

    def _normalize_accord_mode(self, value: Any) -> str:
        """Normalize accord_header value to accord_mode string.

        Handles legacy boolean values and string modes:
        - True (bool) -> 'full'
        - False (bool) -> 'none'
        - 'full', 'compressed', 'none' (str) -> as-is
        - None -> 'full' (default)
        """
        if value is None:
            return "full"
        if isinstance(value, bool):
            return "full" if value else "none"
        str_value = str(value).lower()
        if str_value in ("true", "1", "yes"):
            return "full"
        if str_value in ("false", "0", "no"):
            return "none"
        if str_value in ("full", "compressed", "none"):
            return str_value
        # Default to full for unknown values
        return "full"

    def _substitute_polyglot_blocks(self, raw_content: str, template_path: Path) -> str:
        """Substitute ``{{POLYGLOT_<NAME>}}`` placeholders before YAML parsing.

        Each placeholder must occupy its own line. The placeholder's leading
        indent is re-applied to every non-empty line of the polyglot content
        so the substituted block stays inside its YAML block-scalar. Empty
        polyglot lines are emitted truly empty (matching YAML convention for
        blank lines inside a ``|`` scalar).
        """

        def _replace(m: "re.Match[str]") -> str:
            indent = m.group("indent")
            name = m.group("name")
            polyglot_path = POLYGLOT_DIR / f"{name.lower()}.txt"
            if not polyglot_path.exists():
                logger.error(
                    f"[DMA-PROMPT] Polyglot block not found: {polyglot_path} "
                    f"(referenced from {template_path})"
                )
                raise FileNotFoundError(
                    f"Polyglot block {{{{POLYGLOT_{name}}}}} not found at {polyglot_path}"
                )
            block_text = polyglot_path.read_text(encoding="utf-8").rstrip("\n")
            indented = "\n".join(f"{indent}{ln}" if ln else "" for ln in block_text.split("\n"))
            logger.debug(
                f"[DMA-PROMPT] Substituted {{{{POLYGLOT_{name}}}}} "
                f"({len(block_text)} chars) from {polyglot_path}"
            )
            return indented

        return POLYGLOT_PATTERN.sub(_replace, raw_content)

    def load_prompt_template(self, template_name: str) -> PromptCollection:
        """
        Load a prompt template from a YAML file.

        Checks for localized version first if language is not English.
        Falls back to English version if localized version not found.

        Args:
            template_name: Name of the template file (without .yml extension)

        Returns:
            PromptCollection containing the prompt template data

        Raises:
            FileNotFoundError: If the template file doesn't exist
            yaml.YAMLError: If the YAML file is malformed
        """
        template_path = None

        # Try localized version first if not English
        if self.language != DEFAULT_LANGUAGE and self.localized_dir.exists():
            localized_path = self.localized_dir / f"{template_name}.yml"
            if localized_path.exists():
                template_path = localized_path
                logger.debug(f"Using localized prompt template: {localized_path}")

        # Fall back to default (English) version
        if template_path is None:
            template_path = self.prompts_dir / f"{template_name}.yml"
            if self.language != DEFAULT_LANGUAGE:
                logger.debug(f"Localized prompt not found for {self.language}, using English: {template_path}")

        if not template_path.exists():
            logger.error(f"[DMA-PROMPT] Template file NOT FOUND: {template_path}")
            raise FileNotFoundError(f"Prompt template not found: {template_path}")

        try:
            logger.info(f"[DMA-PROMPT] Loading template from: {template_path}")
            with open(template_path, "r", encoding="utf-8") as f:
                raw_content = f.read()
                logger.info(f"[DMA-PROMPT] Read {len(raw_content)} chars from {template_name}.yml")
                raw_content = self._substitute_polyglot_blocks(raw_content, template_path)
                template_data = yaml.safe_load(raw_content)

            if not isinstance(template_data, dict):
                logger.error(f"[DMA-PROMPT] Invalid template format: expected dict, got {type(template_data)}")
                raise ValueError(
                    f"Invalid template format in {template_path}: expected dict, got {type(template_data)}"
                )

            logger.info(f"[DMA-PROMPT] Parsed template {template_name}: keys={list(template_data.keys())}")

            # Convert dict to PromptCollection
            prompt_collection = PromptCollection(
                component_name=template_name,
                description=template_data.get("description", f"Prompts for {template_name}"),
                version=template_data.get("version", "1.0"),
                system_header=template_data.get("system_header"),
                system_guidance_header=template_data.get("system_guidance_header"),
                domain_principles=template_data.get("domain_principles"),
                evaluation_steps=template_data.get("evaluation_steps"),
                evaluation_criteria=template_data.get("evaluation_criteria"),
                response_format=template_data.get("response_format"),
                response_guidance=template_data.get("response_guidance"),
                decision_format=template_data.get("decision_format"),
                action_parameter_schemas=template_data.get("action_parameter_schemas"),
                csdma_ambiguity_guidance=template_data.get("csdma_ambiguity_guidance"),
                action_params_speak_csdma_guidance=template_data.get("action_params_speak_csdma_guidance"),
                action_params_ponder_guidance=template_data.get("action_params_ponder_guidance"),
                action_params_observe_guidance=template_data.get("action_params_observe_guidance"),
                reasoning_csdma_guidance=template_data.get("reasoning_csdma_guidance"),
                final_ponder_advisory=template_data.get("final_ponder_advisory"),
                closing_reminder=template_data.get("closing_reminder"),
                context_integration=template_data.get("context_integration"),
                accord_mode=self._normalize_accord_mode(template_data.get("accord_header", "full")),
                supports_agent_modes=bool(template_data.get("supports_agent_modes", True)),
            )

            # Add any agent-specific variations
            for key, value in template_data.items():
                if "_mode_" in key and isinstance(value, str):
                    prompt_collection.agent_variations[key] = value
                elif key not in PromptCollection.model_fields and isinstance(value, str):
                    prompt_collection.custom_prompts[key] = value

            return prompt_collection

        except yaml.YAMLError as e:
            logger.error(f"Failed to parse YAML template {template_path}: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to load template {template_path}: {e}")
            raise

    def get_system_message(self, template_data: PromptCollection, **kwargs: Any) -> str:
        """
        Build a system message from template data and variables.

        Args:
            template_data: The loaded template data
            **kwargs: Variables to substitute in the template

        Returns:
            Formatted system message string
        """
        system_parts = []
        component = getattr(template_data, "component_name", "unknown")
        lang = self.language

        # Add main system guidance header
        if template_data.system_guidance_header:
            system_parts.append(
                safe_format(
                    template_data.system_guidance_header,
                    source=f"{component}.system_guidance_header[{lang}]",
                    **kwargs,
                )
            )

        # Add domain principles if present
        if template_data.domain_principles:
            system_parts.append(
                safe_format(
                    template_data.domain_principles,
                    source=f"{component}.domain_principles[{lang}]",
                    **kwargs,
                )
            )

        # Add evaluation steps if present
        if template_data.evaluation_steps:
            system_parts.append(
                safe_format(
                    template_data.evaluation_steps,
                    source=f"{component}.evaluation_steps[{lang}]",
                    **kwargs,
                )
            )

        # Add evaluation criteria if present
        if template_data.evaluation_criteria:
            system_parts.append(
                safe_format(
                    template_data.evaluation_criteria,
                    source=f"{component}.evaluation_criteria[{lang}]",
                    **kwargs,
                )
            )

        # Add response format guidance if present
        if template_data.response_format:
            system_parts.append(
                safe_format(
                    template_data.response_format,
                    source=f"{component}.response_format[{lang}]",
                    **kwargs,
                )
            )

        # Add response guidance if present
        if template_data.response_guidance:
            system_parts.append(
                safe_format(
                    template_data.response_guidance,
                    source=f"{component}.response_guidance[{lang}]",
                    **kwargs,
                )
            )

        return "\n\n".join(system_parts)

    def get_user_message(self, template_data: PromptCollection, **kwargs: Any) -> str:
        """
        Build a user message from template data and variables.

        Args:
            template_data: The loaded template data
            **kwargs: Variables to substitute in the template

        Returns:
            Formatted user message string
        """
        if template_data.context_integration:
            component = getattr(template_data, "component_name", "unknown")
            return safe_format(
                template_data.context_integration,
                source=f"{component}.context_integration[{self.language}]",
                **kwargs,
            )
        else:
            # Fallback for basic context integration
            return f"Thought to evaluate: {kwargs.get('original_thought_content', '')}"

    def get_accord_mode(self, template_data: PromptCollection) -> str:
        """
        Get the accord mode for this template.

        Args:
            template_data: The loaded template data

        Returns:
            Accord mode: 'full', 'compressed', or 'none'
        """
        return template_data.accord_mode

    def uses_accord_header(self, template_data: PromptCollection) -> bool:
        """
        Check if template requires accord text as system header.

        Args:
            template_data: The loaded template data

        Returns:
            True if accord header should be used (mode is 'full' or 'compressed')
        """
        return template_data.accord_mode in ("full", "compressed")


# Per-language DMA loader cache. Each language gets its own independent loader
# so concurrent thoughts in different languages never trample each other's
# state. The previous singleton + mutable-language design caused the same bug
# the conscience loader had: a Spanish thought could end up using Amharic
# prompts because some other thread mutated the global between selection
# and the actual DMA call.
_loader_cache: dict[str, DMAPromptLoader] = {}


def get_prompt_loader(language: Optional[str] = None) -> DMAPromptLoader:
    """Get a DMA prompt loader for the requested language.

    Returns a per-language loader (cached). The agent should always pass the
    language of the THOUGHT/USER being evaluated — not rely on a global env
    var — so multilingual deployments build prompts per thought in its own
    language.

    Args:
        language: Optional ISO 639-1 language code. If None, falls back to
            the env var via get_preferred_language() — but callers should
            normally pass an explicit language derived from the user profile.

    Returns:
        DMAPromptLoader instance for the requested language.
    """
    if language is None:
        try:
            from ciris_engine.logic.utils.localization import get_preferred_language

            language = get_preferred_language()
        except ImportError:
            language = DEFAULT_LANGUAGE

    loader = _loader_cache.get(language)
    if loader is None:
        loader = DMAPromptLoader(language=language)
        _loader_cache[language] = loader
        logger.info(f"DMA prompt loader created for language: {_sanitize_for_log(language)}")
    return loader


def set_prompt_language(language: str) -> None:
    """Compatibility shim — no-op now that loaders are per-language.

    Previously this mutated a global singleton; with per-language caching
    each call site selects its own loader at request time. Kept as a no-op
    so existing callers don't break, but issues a one-time warning to help
    surface stale globals.
    """
    logger.warning(
        f"set_prompt_language({_sanitize_for_log(language)}) called — "
        "this is a no-op now; pass language to get_prompt_loader() per request"
    )
