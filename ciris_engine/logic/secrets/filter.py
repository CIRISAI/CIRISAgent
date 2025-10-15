"""
Secrets Detection and Filtering System for CIRIS Agent.

Automatically detects and protects sensitive information while maintaining
the agent's ability to reason about and use secrets safely.
"""

import logging
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from ciris_engine.schemas.secrets.core import ConfigExport, DetectedSecret, PatternStats
from ciris_engine.schemas.secrets.core import SecretPattern as ConfigSecretPattern
from ciris_engine.schemas.secrets.core import SecretsDetectionConfig, SecretsFilterResult
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


class SecretsFilter:
    """
    Automatic secrets detection and filtering system.

    Detects secrets in text and replaces them with secure UUID references
    while maintaining context for the agent.
    """

    def __init__(self, detection_config: Optional[SecretsDetectionConfig] = None) -> None:
        self.detection_config = detection_config or SecretsDetectionConfig()
        self._compiled_patterns: Dict[str, re.Pattern[str]] = {}
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Compile all active patterns for efficient matching."""
        self._compiled_patterns.clear()

        # Add all patterns from config
        if self.detection_config.enabled:
            for pattern in self.detection_config.patterns:
                try:
                    self._compiled_patterns[pattern.name] = re.compile(pattern.pattern)
                except re.error as e:
                    logger.error(f"Failed to compile pattern {pattern.name}: {e}")

    def detect_secrets(self, text: str, context_hint: str = "") -> List[DetectedSecret]:
        """
        Detect secrets in the given text.

        Args:
            text: Text to scan for secrets
            context_hint: Safe context description for logging

        Returns:
            List of detected secrets with metadata
        """
        detected_secrets = []

        for pattern_name, compiled_pattern in self._compiled_patterns.items():
            try:
                matches = compiled_pattern.finditer(text)
                for match in matches:
                    # Get pattern metadata
                    pattern_info = self._get_pattern_info(pattern_name)
                    if not pattern_info:
                        continue

                    # Generate UUID for this secret
                    secret_uuid = str(uuid.uuid4())

                    # Create replacement text
                    replacement_text = f"{{SECRET:{secret_uuid}:{pattern_info.description}}}"

                    # Create detected secret record
                    detected_secret = DetectedSecret(
                        secret_uuid=secret_uuid,
                        original_value=match.group(0),
                        replacement_text=replacement_text,
                        pattern_name=pattern_name,
                        description=pattern_info.description,
                        sensitivity=pattern_info.sensitivity,  # Use pattern sensitivity directly
                        context_hint=context_hint,
                    )

                    detected_secrets.append(detected_secret)

            except Exception as e:
                logger.error(f"Error processing pattern {pattern_name}: {e}")

        return detected_secrets

    def filter_text(self, text: str, context_hint: str = "") -> Tuple[str, List[DetectedSecret]]:
        """
        Filter text by detecting and replacing secrets with UUID references.

        Args:
            text: Original text containing potential secrets
            context_hint: Safe context description for logging

        Returns:
            Tuple of (filtered_text, detected_secrets_list)
        """
        detected_secrets = self.detect_secrets(text, context_hint)

        if not detected_secrets:
            return text, []

        # Replace secrets with UUID references using simple string replacement
        filtered_text = text
        for secret in detected_secrets:
            filtered_text = filtered_text.replace(secret.original_value, secret.replacement_text)

        logger.info(f"Filtered {len(detected_secrets)} secrets from text. Context: {context_hint}")

        return filtered_text, detected_secrets

    def _get_pattern_info(self, pattern_name: str) -> Optional[ConfigSecretPattern]:
        """Get pattern information by name."""
        for pattern in self.detection_config.patterns:
            if pattern.name == pattern_name:
                return pattern

        return None

    def add_custom_pattern(self, pattern: ConfigSecretPattern) -> None:
        """Add a new custom pattern."""
        # Remove existing pattern with same name
        self.detection_config.patterns = [p for p in self.detection_config.patterns if p.name != pattern.name]
        self.detection_config.patterns.append(pattern)
        self._compile_patterns()

        logger.info(f"Added custom secret pattern: {pattern.name}")

    def remove_custom_pattern(self, pattern_name: str) -> bool:
        """Remove a custom pattern by name."""
        original_count = len(self.detection_config.patterns)
        self.detection_config.patterns = [p for p in self.detection_config.patterns if p.name != pattern_name]

        if len(self.detection_config.patterns) < original_count:
            self._compile_patterns()
            logger.info(f"Removed custom secret pattern: {pattern_name}")
            return True
        return False

    def disable_pattern(self, pattern_name: str) -> None:
        """Disable a pattern (default or custom)."""
        # Remove pattern from active patterns
        self.detection_config.patterns = [p for p in self.detection_config.patterns if p.name != pattern_name]
        self._compile_patterns()
        logger.info(f"Disabled secret pattern: {pattern_name}")

    def enable_pattern(self, pattern_name: str) -> None:
        """Re-enable a previously disabled pattern."""
        # This method would need to store disabled patterns separately
        # For now, just log a warning
        logger.warning(f"Pattern re-enabling not supported without storage: {pattern_name}")

    def get_pattern_stats(self) -> PatternStats:
        """Get statistics about active patterns."""
        # Count patterns by type based on sensitivity level
        default_count = 0
        custom_count = 0
        for pattern in self.detection_config.patterns:
            # Assume patterns with standard sensitivity levels are defaults
            if pattern.sensitivity.value in ["low", "medium", "high"]:
                default_count += 1
            else:
                custom_count += 1

        return PatternStats(
            total_patterns=len(self._compiled_patterns),
            default_patterns=default_count,
            custom_patterns=custom_count,
            disabled_patterns=0,  # No disabled patterns in current schema
            builtin_patterns=True,  # Assume builtin patterns are always enabled
            filter_version="v1.0",
        )

    def export_config(self) -> ConfigExport:
        """Export current configuration for persistence."""
        # Convert patterns to appropriate categories
        custom_patterns = []
        default_patterns = []

        for pattern in self.detection_config.patterns:
            pattern_dict = pattern.model_dump()
            if pattern.sensitivity.value in ["low", "medium", "high"]:
                default_patterns.append(pattern_dict)
            else:
                custom_patterns.append(pattern_dict)

        return ConfigExport(
            filter_id="config_based",
            version=1,
            builtin_patterns_enabled=self.detection_config.enabled,
            custom_patterns=custom_patterns,
            disabled_patterns=[],  # No disabled patterns in current schema
            sensitivity_overrides={},
            require_confirmation_for=["CRITICAL"],
            auto_decrypt_for_actions=["speak", "tool"],
        )

    def import_config(self, config: ConfigExport) -> None:
        """Import configuration from dictionary."""
        # Convert from ConfigExport back to SecretsDetectionConfig
        patterns = []

        # Add custom patterns from config
        # Note: ConfigExport doesn't have default_patterns, only custom_patterns
        # The builtin patterns are controlled by builtin_patterns_enabled flag

        # Add custom patterns
        for pattern_obj in config.custom_patterns:
            # pattern_obj is already a SecretPattern (alias for ConfigSecretPattern)
            patterns.append(pattern_obj)

        # Create new config
        # Note: SecretsDetectionConfig only has 'enabled' and 'patterns' attributes
        self.detection_config = SecretsDetectionConfig(enabled=config.builtin_patterns_enabled, patterns=patterns)
        self._compile_patterns()
        logger.info(f"Imported secrets detection config with {len(patterns)} patterns")

    # Implement SecretsFilterInterface methods
    def filter_content(self, content: str, source_id: Optional[str] = None) -> SecretsFilterResult:
        """Filter content for secrets using the text filtering method."""
        filtered_text, detected_secrets = self.filter_text(content)

        schema_secrets = []
        for secret in detected_secrets:
            schema_secret = DetectedSecret(
                original_value=secret.original_value,
                secret_uuid=secret.secret_uuid,
                pattern_name=secret.pattern_name,
                description=secret.description,
                sensitivity=secret.sensitivity,
                context_hint=secret.context_hint,
                replacement_text=secret.replacement_text,
            )
            schema_secrets.append(schema_secret)

        return SecretsFilterResult(
            filtered_content=filtered_text,
            detected_secrets=schema_secrets,
            secrets_found=len(detected_secrets),
            patterns_matched=[s.pattern_name for s in detected_secrets],
        )

    def add_pattern(self, pattern: ConfigSecretPattern) -> bool:
        """Add a new secret detection pattern."""
        try:
            # Pattern is already a ConfigSecretPattern, just add it
            self.add_custom_pattern(pattern)
            return True
        except Exception as e:
            logger.error(f"Failed to add pattern: {e}")
            return False

    def remove_pattern(self, pattern_name: str) -> bool:
        """Remove a secret detection pattern."""
        return self.remove_custom_pattern(pattern_name)

    def get_filter_config(self) -> ConfigExport:  # pragma: no cover - thin wrapper
        """Get the current filter configuration."""
        # Convert detection config to schema format
        # Note: SecretsDetectionConfig just has 'patterns', not separate builtin/custom lists
        return ConfigExport(
            filter_id="config_based",
            version=1,
            builtin_patterns_enabled=self.detection_config.enabled,
            custom_patterns=[
                {
                    "name": p.name,
                    "pattern": p.pattern,
                    "description": p.description if hasattr(p, "description") else "",
                    "sensitivity": p.sensitivity.value if hasattr(p, "sensitivity") else "medium",
                    "enabled": True,  # All patterns in the list are considered enabled
                }
                for p in self.detection_config.patterns
            ],
            disabled_patterns=[],  # Not tracked separately in SecretsDetectionConfig
            sensitivity_overrides={},  # Not used in new system
            require_confirmation_for=["CRITICAL"],  # Default
            auto_decrypt_for_actions=["speak", "tool"],  # Default
        )

    def update_filter_config(self, updates: JSONDict) -> bool:  # pragma: no cover - rarely used
        """Update filter configuration settings."""
        try:
            for key, value in updates.items():
                if hasattr(self.detection_config, key):
                    setattr(self.detection_config, key, value)
            self._compile_patterns()
            return True
        except Exception:
            return False
