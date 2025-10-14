"""
Configuration Bootstrap for Graph-Based Config System.

Loads essential configuration from multiple sources in priority order,
then migrates to graph-based configuration for runtime management.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

import aiofiles
import yaml

from ciris_engine.schemas.config.essential import EssentialConfig
from ciris_engine.schemas.types import ConfigDict, JSONDict

from .env_utils import get_env_var

logger = logging.getLogger(__name__)


class ConfigBootstrap:
    """Load essential config from multiple sources in priority order."""

    @staticmethod
    def _deep_merge(base: ConfigDict, update: ConfigDict) -> ConfigDict:
        """Recursively merge two configuration dictionaries."""
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                base[key] = ConfigBootstrap._deep_merge(base[key], value)  # type: ignore[arg-type]
            else:
                base[key] = value
        return base

    @staticmethod
    def _apply_env_overrides(config_data: ConfigDict) -> ConfigDict:
        """Apply environment variable overrides to config data."""
        # Database paths
        db_path = get_env_var("CIRIS_DB_PATH")
        if db_path:
            config_data.setdefault("database", {})["main_db"] = db_path

        secrets_db = get_env_var("CIRIS_SECRETS_DB_PATH")
        if secrets_db:
            config_data.setdefault("database", {})["secrets_db"] = secrets_db

        audit_db = get_env_var("CIRIS_AUDIT_DB_PATH")
        if audit_db:
            config_data.setdefault("database", {})["audit_db"] = audit_db

        # Service endpoints
        llm_endpoint = get_env_var("OPENAI_API_BASE") or get_env_var("LLM_ENDPOINT")
        if llm_endpoint:
            config_data.setdefault("services", {})["llm_endpoint"] = llm_endpoint

        llm_model = get_env_var("OPENAI_MODEL_NAME") or get_env_var("OPENAI_MODEL") or get_env_var("LLM_MODEL")
        if llm_model:
            config_data.setdefault("services", {})["llm_model"] = llm_model

        # Security settings
        retention_days = get_env_var("AUDIT_RETENTION_DAYS")
        if retention_days:
            try:
                config_data.setdefault("security", {})["audit_retention_days"] = int(retention_days)
            except ValueError:
                logger.warning(f"Invalid AUDIT_RETENTION_DAYS value: {retention_days}")

        # Operational limits
        max_tasks = get_env_var("MAX_ACTIVE_TASKS")
        if max_tasks:
            try:
                config_data.setdefault("limits", {})["max_active_tasks"] = int(max_tasks)
            except ValueError:
                logger.warning(f"Invalid MAX_ACTIVE_TASKS value: {max_tasks}")

        max_depth = get_env_var("MAX_THOUGHT_DEPTH")
        if max_depth:
            try:
                config_data.setdefault("security", {})["max_thought_depth"] = int(max_depth)
            except ValueError:
                logger.warning(f"Invalid MAX_THOUGHT_DEPTH value: {max_depth}")

        # Runtime settings
        log_level = get_env_var("LOG_LEVEL")
        if log_level:
            config_data["log_level"] = log_level.upper()

        debug_mode = get_env_var("DEBUG_MODE")
        if debug_mode:
            config_data["debug_mode"] = debug_mode.lower() in ("true", "1", "yes", "on")

        return config_data

    @staticmethod
    async def load_essential_config(
        config_path: Optional[Path] = None, cli_overrides: Optional[ConfigDict] = None
    ) -> EssentialConfig:
        """
        Load essential configuration from multiple sources.

        Priority order (highest to lowest):
        1. CLI arguments (if provided)
        2. Environment variables
        3. Configuration file (YAML)
        4. Schema defaults

        Args:
            config_path: Optional path to YAML config file
            cli_overrides: Optional CLI argument overrides

        Returns:
            Validated EssentialConfig instance
        """
        # Start with empty config data
        config_data: ConfigDict = {}

        # Load from YAML file if exists
        yaml_path = config_path or Path("config/essential.yaml")
        if yaml_path.exists():
            try:
                async with aiofiles.open(yaml_path, "r") as f:
                    yaml_content = await f.read()
                    yaml_data = yaml.safe_load(yaml_content) or {}
                config_data = ConfigBootstrap._deep_merge(config_data, yaml_data)
                logger.info(f"Loaded configuration from {yaml_path}")
            except Exception as e:
                logger.warning(f"Failed to load YAML config from {yaml_path}: {e}")

        # Apply environment variable overrides
        config_data = ConfigBootstrap._apply_env_overrides(config_data)

        # Apply CLI overrides (highest priority)
        if cli_overrides:
            config_data = ConfigBootstrap._deep_merge(config_data, cli_overrides)

        # Create and validate config
        try:
            essential_config = EssentialConfig(**config_data)
            logger.info("Essential configuration loaded and validated")
            return essential_config
        except Exception as e:
            logger.error(f"Configuration validation failed: {e}")
            raise ValueError(f"Invalid configuration: {e}") from e

    @staticmethod
    def get_config_metadata(config: EssentialConfig, yaml_path: Optional[Path] = None) -> JSONDict:
        """
        Generate metadata about config sources for migration to graph.

        Returns dict mapping config keys to their source information
        (source, env_var/file, bootstrap_phase flag).
        """
        metadata: Dict[str, Any] = {}

        # Check which values came from environment
        env_sources = {
            "database.main_db": "CIRIS_DB_PATH",
            "database.secrets_db": "CIRIS_SECRETS_DB_PATH",
            "database.audit_db": "CIRIS_AUDIT_DB_PATH",
            "services.llm_endpoint": "OPENAI_API_BASE",
            "services.llm_model": "OPENAI_MODEL",
            "security.audit_retention_days": "AUDIT_RETENTION_DAYS",
            "limits.max_active_tasks": "MAX_ACTIVE_TASKS",
            "security.max_thought_depth": "MAX_THOUGHT_DEPTH",
            "log_level": "LOG_LEVEL",
            "debug_mode": "DEBUG_MODE",
        }

        for key, env_var in env_sources.items():
            if get_env_var(env_var):
                metadata[key] = {"source": "env_var", "env_var": env_var, "bootstrap_phase": True}

        # Mark file-sourced configs
        if yaml_path and yaml_path.exists():
            # Would need to track which specific values came from file
            # For now, mark all non-env values as file-sourced
            for key in ["database", "services", "security", "limits"]:
                if key not in metadata:
                    metadata[key] = {"source": "config_file", "file": str(yaml_path), "bootstrap_phase": True}

        # Everything else is from defaults
        return metadata
