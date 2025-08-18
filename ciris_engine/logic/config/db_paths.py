"""
Database path utilities for the new config system.

Provides compatibility functions for getting database paths.
"""

from pathlib import Path
from typing import Optional

from ciris_engine.schemas.config.essential import EssentialConfig


def get_sqlite_db_full_path(config: Optional[EssentialConfig] = None) -> str:
    """
    Get the full path to the main SQLite database.

    Args:
        config: Optional EssentialConfig instance. If not provided, will attempt
                to get from the config service via ServiceRegistry.

    Returns:
        Full path to the SQLite database file

    Raises:
        RuntimeError: If no config is available from any source
    """
    if config is None:
        raise RuntimeError(
            "No configuration provided to get_sqlite_db_full_path(). "
            "Config must be explicitly passed - this function is only for initialization. "
            "After initialization, services should use ConfigAccessor."
        )

    db_path = Path(config.database.main_db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return str(db_path.resolve())


def get_secrets_db_full_path(config: Optional[EssentialConfig] = None) -> str:
    """
    Get the full path to the secrets database.

    Args:
        config: Optional EssentialConfig instance. If not provided, will attempt
                to get from the config service via ServiceRegistry.

    Returns:
        Full path to the secrets database file
    """
    if config is None:
        # Try to get config from the service registry
        try:
            from ciris_engine.logic.registries.base import ServiceRegistry
            from ciris_engine.schemas.runtime.enums import ServiceType

            registry = ServiceRegistry.get_instance()
            config_services = registry.get_services_by_type(ServiceType.CONFIG)

            if config_services:
                config_service = config_services[0]
                if hasattr(config_service, "essential_config"):
                    config = config_service.essential_config
                elif hasattr(config_service, "_config"):
                    config = config_service._config

            if config is None:
                # For secrets db, we can fall back to defaults as it's less critical
                config = EssentialConfig()
        except (ImportError, AttributeError):
            # Fall back to defaults for secrets db
            config = EssentialConfig()

    db_path = Path(config.database.secrets_db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return str(db_path.resolve())


def get_audit_db_full_path(config: Optional[EssentialConfig] = None) -> str:
    """
    Get the full path to the audit database.

    Args:
        config: Optional EssentialConfig instance. If not provided, will attempt
                to get from the config service via ServiceRegistry.

    Returns:
        Full path to the audit database file
    """
    if config is None:
        # Try to get config from the service registry
        try:
            from ciris_engine.logic.registries.base import ServiceRegistry
            from ciris_engine.schemas.runtime.enums import ServiceType

            registry = ServiceRegistry.get_instance()
            config_services = registry.get_services_by_type(ServiceType.CONFIG)

            if config_services:
                config_service = config_services[0]
                if hasattr(config_service, "essential_config"):
                    config = config_service.essential_config
                elif hasattr(config_service, "_config"):
                    config = config_service._config

            if config is None:
                # For audit db, we can fall back to defaults as it's less critical
                config = EssentialConfig()
        except (ImportError, AttributeError):
            # Fall back to defaults for audit db
            config = EssentialConfig()

    db_path = Path(config.database.audit_db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return str(db_path.resolve())


# For backward compatibility - uses defaults
def get_graph_memory_full_path() -> str:
    """Legacy function - graph memory is now in the main database."""
    return get_sqlite_db_full_path()
