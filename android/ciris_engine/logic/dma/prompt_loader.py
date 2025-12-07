"""
Prompt Loader for DMA Systems

This module provides functionality to load prompts from YAML files,
separating prompt content from business logic for better maintainability.
"""

import logging
from pathlib import Path
from typing import Any, Optional

import yaml

from ciris_engine.schemas.dma.prompts import PromptCollection

logger = logging.getLogger(__name__)


class DMAPromptLoader:
    """Loads and manages DMA prompts from YAML files."""

    def __init__(self, prompts_dir: Optional[str] = None):
        """
        Initialize the prompt loader.

        Args:
            prompts_dir: Optional custom prompts directory path.
                        If None, uses the default prompts/ directory relative to this file.
        """
        if prompts_dir is None:
            # Default to prompts/ directory in same location as this file
            self.prompts_dir = Path(__file__).parent / "prompts"
        else:
            self.prompts_dir = Path(prompts_dir)

        if not self.prompts_dir.exists():
            logger.warning(f"Prompts directory does not exist: {self.prompts_dir}")

    def load_prompt_template(self, template_name: str) -> PromptCollection:
        """
        Load a prompt template from a YAML file.

        Args:
            template_name: Name of the template file (without .yml extension)

        Returns:
            PromptCollection containing the prompt template data

        Raises:
            FileNotFoundError: If the template file doesn't exist
            yaml.YAMLError: If the YAML file is malformed
        """
        template_path = self.prompts_dir / f"{template_name}.yml"

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
                uses_covenant_header=bool(template_data.get("covenant_header", False)),
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

    def uses_covenant_header(self, template_data: PromptCollection) -> bool:
        """
        Check if template requires COVENANT_TEXT as system header.

        Args:
            template_data: The loaded template data

        Returns:
            True if covenant header should be used
        """
        return template_data.uses_covenant_header


# Global instance for convenience
_default_loader = None


def get_prompt_loader() -> DMAPromptLoader:
    """Get the default prompt loader instance."""
    global _default_loader
    if _default_loader is None:
        _default_loader = DMAPromptLoader()
    return _default_loader
