"""
Prompt Loader for DMA Systems

This module provides functionality to load prompts from YAML files,
separating prompt content from business logic for better maintainability.

Supports localized prompts by checking for language-specific versions in
prompts/localized/{lang}/ directories.
"""

import logging
from pathlib import Path
from typing import Any, Optional

import yaml

from ciris_engine.schemas.dma.prompts import PromptCollection

logger = logging.getLogger(__name__)

# Default language for prompts
DEFAULT_LANGUAGE = "en"


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
        logger.debug(f"DMA prompt language set to: {language}")

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
            raise FileNotFoundError(f"Prompt template not found: {template_path}")

        try:
            with open(template_path, "r", encoding="utf-8") as f:
                template_data = yaml.safe_load(f)

            if not isinstance(template_data, dict):
                raise ValueError(
                    f"Invalid template format in {template_path}: expected dict, got {type(template_data)}"
                )

            logger.debug(f"Loaded prompt template: {template_name}")

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
                rationale_csdma_guidance=template_data.get("rationale_csdma_guidance"),
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

        # Add main system guidance header
        if template_data.system_guidance_header:
            system_parts.append(template_data.system_guidance_header.format(**kwargs))

        # Add domain principles if present
        if template_data.domain_principles:
            system_parts.append(template_data.domain_principles.format(**kwargs))

        # Add evaluation steps if present
        if template_data.evaluation_steps:
            system_parts.append(template_data.evaluation_steps.format(**kwargs))

        # Add evaluation criteria if present
        if template_data.evaluation_criteria:
            system_parts.append(template_data.evaluation_criteria.format(**kwargs))

        # Add response format guidance if present
        if template_data.response_format:
            system_parts.append(template_data.response_format.format(**kwargs))

        # Add response guidance if present
        if template_data.response_guidance:
            system_parts.append(template_data.response_guidance.format(**kwargs))

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
            return template_data.context_integration.format(**kwargs)
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


# Global instance for convenience
_default_loader = None
_current_language = DEFAULT_LANGUAGE


def get_prompt_loader(language: Optional[str] = None) -> DMAPromptLoader:
    """Get the default prompt loader instance.

    Args:
        language: Optional language code. If provided and different from current,
                  updates the loader's language setting.

    Returns:
        DMAPromptLoader instance configured for the specified language.
    """
    global _default_loader, _current_language

    if _default_loader is None:
        lang = language or _current_language
        _default_loader = DMAPromptLoader(language=lang)
        _current_language = lang
    elif language and language != _current_language:
        _default_loader.set_language(language)
        _current_language = language

    return _default_loader


def set_prompt_language(language: str) -> None:
    """Set the language for DMA prompts globally.

    Args:
        language: ISO 639-1 language code (e.g., 'en', 'am', 'es')
    """
    global _default_loader, _current_language
    _current_language = language
    if _default_loader is not None:
        _default_loader.set_language(language)
    logger.info(f"DMA prompt language set to: {language}")
