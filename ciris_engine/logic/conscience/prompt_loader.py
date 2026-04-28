"""
Prompt Loader for Conscience Systems

This module provides functionality to load conscience prompts from YAML files,
separating prompt content from business logic for better maintainability.

Supports localized prompts by checking for language-specific versions in
prompts/localized/{lang}/ directories.
"""

import logging
import re
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


def _sanitize_for_log(value: str, max_length: int = 50) -> str:
    """Sanitize user input for safe logging.

    Prevents log injection attacks by:
    - Removing newlines and control characters
    - Truncating to max_length
    - Replacing non-printable characters
    """
    if not isinstance(value, str):
        value = str(value)
    # Remove control characters (includes \r=0x0d, \n=0x0a in 0x00-0x1f range)
    sanitized = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", value)
    # Truncate
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length] + "..."
    return sanitized


# Default language for prompts
DEFAULT_LANGUAGE = "en"


class ConsciencePrompts(BaseModel):
    """Container for conscience prompt data."""

    version: str = Field(default="1.0")
    description: str = Field(default="")
    language: str = Field(default="en")
    system_prompt: str = Field(default="")
    user_prompt_template: str = Field(default="")
    user_prompt_with_image_template: str = Field(default="")


class ConsciencePromptLoader:
    """Loads and manages conscience prompts from YAML files.

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
            self.prompts_dir = Path(__file__).parent / "prompts"
        else:
            self.prompts_dir = Path(prompts_dir)

        self.language = language
        self.localized_dir = self.prompts_dir / "localized" / language
        self._cache: dict[str, ConsciencePrompts] = {}

        if not self.prompts_dir.exists():
            logger.warning(f"Conscience prompts directory does not exist: {self.prompts_dir}")

    def set_language(self, language: str) -> None:
        """Update the language for prompt loading.

        Args:
            language: ISO 639-1 language code
        """
        if language != self.language:
            self.language = language
            self.localized_dir = self.prompts_dir / "localized" / language
            self._cache.clear()  # Clear cache when language changes
            logger.debug(f"Conscience prompt language set to: {language}")

    def load_prompts(self, conscience_type: str) -> ConsciencePrompts:
        """
        Load prompts for a specific conscience type from YAML file.

        Checks for localized version first if language is not English.
        Falls back to English version if localized version not found.

        Args:
            conscience_type: Name of the conscience (e.g., 'entropy_conscience', 'coherence_conscience')

        Returns:
            ConsciencePrompts containing the prompt data

        Raises:
            FileNotFoundError: If the prompt file doesn't exist
        """
        cache_key = f"{self.language}:{conscience_type}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        template_path = None

        # Try localized version first if not English
        if self.language != DEFAULT_LANGUAGE and self.localized_dir.exists():
            localized_path = self.localized_dir / f"{conscience_type}.yml"
            if localized_path.exists():
                template_path = localized_path
                logger.debug(f"Using localized conscience prompt: {localized_path}")

        # Fall back to default (English) version
        if template_path is None:
            template_path = self.prompts_dir / f"{conscience_type}.yml"
            if self.language != DEFAULT_LANGUAGE:
                logger.debug(
                    f"Localized conscience prompt not found for {self.language}, using English: {template_path}"
                )

        if not template_path.exists():
            raise FileNotFoundError(f"Conscience prompt file not found: {template_path}")

        try:
            with open(template_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not isinstance(data, dict):
                raise ValueError(f"Invalid prompt format in {template_path}: expected dict")

            prompts = ConsciencePrompts(
                version=data.get("version", "1.0"),
                description=data.get("description", ""),
                language=data.get("language", self.language),
                system_prompt=data.get("system_prompt", ""),
                user_prompt_template=data.get("user_prompt_template", ""),
                user_prompt_with_image_template=data.get("user_prompt_with_image_template", ""),
            )

            self._cache[cache_key] = prompts
            logger.debug(f"Loaded conscience prompts: {conscience_type}")
            return prompts

        except yaml.YAMLError as e:
            logger.error(f"Failed to parse YAML prompt {template_path}: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to load conscience prompts {template_path}: {e}")
            raise

    def get_system_prompt(self, conscience_type: str) -> str:
        """Get the system prompt for a conscience type."""
        prompts = self.load_prompts(conscience_type)
        return prompts.system_prompt

    def get_user_prompt(self, conscience_type: str, image_context: Optional[str] = None, **kwargs: str) -> str:
        """Build user prompt from template with optional image context.

        Args:
            conscience_type: Type of conscience (e.g., 'entropy_conscience')
            image_context: Optional image context metadata
            **kwargs: Variables to substitute in the template (e.g., text, action_description)

        Returns:
            Formatted user prompt string
        """
        prompts = self.load_prompts(conscience_type)

        if image_context:
            template = prompts.user_prompt_with_image_template or prompts.user_prompt_template
            kwargs["image_context"] = image_context
        else:
            template = prompts.user_prompt_template

        try:
            from ciris_engine.logic.dma.prompt_loader import safe_format

            return safe_format(template, source=f"conscience.{conscience_type}[{self.language}]", **kwargs)
        except KeyError as e:
            logger.warning(f"Missing template variable {e} in {conscience_type}")
            return template


# Per-language loader cache. Each language gets its own independent loader so
# concurrent thoughts in different languages never trample each other's state.
# The previous singleton + mutable-language design caused a real production bug:
# the first thought that ran (whatever language CIRIS_PREFERRED_LANGUAGE held)
# locked the loader, and every subsequent thought — regardless of its actual
# user — was evaluated with that language's conscience prompts. For a Spanish
# user whose response was being judged with Amharic instructions, the LLM
# judge over-scored entropy and forced spurious PONDERs.
_loader_cache: dict[str, ConsciencePromptLoader] = {}


def get_conscience_prompt_loader(language: Optional[str] = None) -> ConsciencePromptLoader:
    """Get a conscience prompt loader for the requested language.

    Returns a per-language loader (cached). The agent should always pass the
    language of the THOUGHT/USER being evaluated — not rely on a global env
    var — so multilingual deployments grade each thought in its own language.

    Args:
        language: Optional ISO 639-1 language code. If None, falls back to
            the env var via get_preferred_language() — but callers should
            normally pass an explicit language derived from the user profile.

    Returns:
        ConsciencePromptLoader instance for the requested language.
    """
    if language is None:
        try:
            from ciris_engine.logic.utils.localization import get_preferred_language

            language = get_preferred_language()
        except ImportError:
            language = DEFAULT_LANGUAGE

    loader = _loader_cache.get(language)
    if loader is None:
        loader = ConsciencePromptLoader(language=language)
        _loader_cache[language] = loader
        logger.info(f"Conscience prompt loader created for language: {_sanitize_for_log(language)}")
    return loader


def set_conscience_prompt_language(language: str) -> None:
    """Compatibility shim — no-op now that loaders are per-language.

    Previously this mutated a global singleton; with per-language caching
    each call site selects its own loader at request time. Kept as a no-op
    so existing callers don't break, but issues a one-time warning to help
    surface stale globals.
    """
    logger.warning(
        f"set_conscience_prompt_language({_sanitize_for_log(language)}) called — "
        "this is a no-op now; pass language to get_conscience_prompt_loader() per request"
    )
