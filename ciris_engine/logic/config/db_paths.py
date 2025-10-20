"""
Database path utilities for the new config system.

Provides compatibility functions for getting database paths.
"""

from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urlunparse

from ciris_engine.schemas.config.essential import EssentialConfig


def _get_config_from_registry() -> Optional[EssentialConfig]:
    """Get EssentialConfig from the service registry.

    Returns:
        EssentialConfig instance or None if not available
    """
    try:
        from ciris_engine.logic.registries.base import ServiceRegistry
        from ciris_engine.schemas.runtime.enums import ServiceType

        registry = ServiceRegistry()
        config_services = registry.get_services_by_type(ServiceType.CONFIG)

        if config_services:
            config_service = config_services[0]
            if hasattr(config_service, "essential_config"):
                config: Optional[EssentialConfig] = getattr(config_service, "essential_config", None)
                return config
            elif hasattr(config_service, "_config"):
                config = getattr(config_service, "_config", None)
                return config

        return None
    except (ImportError, AttributeError):
        return None


def _modify_database_name_in_url(base_url: str, suffix: str) -> str:
    """Modify the database name in a PostgreSQL URL while preserving query parameters.

    Args:
        base_url: Original PostgreSQL URL (e.g., postgresql://user:pass@host:port/dbname?sslmode=require)
        suffix: Suffix to append to database name (e.g., "_secrets", "_auth")

    Returns:
        Modified URL with suffix added to database name, query params preserved

    Example:
        >>> _modify_database_name_in_url("postgresql://user:pass@host:5432/db?sslmode=require", "_secrets")
        "postgresql://user:pass@host:5432/db_secrets?sslmode=require"
    """
    parsed = urlparse(base_url)

    # Extract database name from path (remove leading /)
    db_name = parsed.path.lstrip("/")

    # Add suffix to database name
    new_db_name = f"{db_name}{suffix}"

    # Reconstruct path with leading /
    new_path = f"/{new_db_name}"

    # Reconstruct URL with new path, preserving all other components
    return urlunparse(
        (
            parsed.scheme,  # scheme (postgresql)
            parsed.netloc,  # netloc (user:pass@host:port)
            new_path,  # path (/db_secrets)
            parsed.params,  # params (empty for PostgreSQL URLs)
            parsed.query,  # query (sslmode=require)
            parsed.fragment,  # fragment (empty for PostgreSQL URLs)
        )
    )


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
        # Try to get config from the service registry
        try:
            from ciris_engine.logic.registries.base import get_global_registry
            from ciris_engine.schemas.runtime.enums import ServiceType

            # Use the global registry singleton
            registry = get_global_registry()
            config_services = registry.get_services_by_type(ServiceType.CONFIG)

            if config_services:
                config_service = config_services[0]
                if hasattr(config_service, "essential_config"):
                    config = config_service.essential_config
                elif hasattr(config_service, "_config"):
                    config = config_service._config

            if config is None:
                # FAIL FAST AND LOUD - no fallback to defaults
                raise RuntimeError(
                    "No configuration available from config service. "
                    "The system must be properly initialized with configuration."
                )
        except (ImportError, AttributeError) as e:
            # FAIL FAST AND LOUD - no fallback to defaults
            raise RuntimeError(
                f"Cannot access config service: {e}. " "The system must be properly initialized with configuration."
            )

    # Prefer database_url if set (supports PostgreSQL), otherwise use main_db path
    if config.database.database_url:
        return config.database.database_url

    db_path = Path(config.database.main_db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return str(db_path.resolve())


def get_secrets_db_full_path(config: Optional[EssentialConfig] = None) -> str:
    """
    Get the full path to the secrets database.

    For PostgreSQL: Modifies the database name in the URL (e.g., ciris_db -> ciris_db_secrets)
    For SQLite: Returns the configured secrets_db path

    Args:
        config: Optional EssentialConfig instance. If not provided, will attempt
                to get from the config service via ServiceRegistry.

    Returns:
        Full path to the secrets database file or modified PostgreSQL URL
    """
    if config is None:
        config = _get_config_from_registry()
        if config is None:
            # For secrets db, we can fall back to defaults as it's less critical
            config = EssentialConfig()

    # If using PostgreSQL (database_url is set), modify the database name
    if config.database.database_url:
        return _modify_database_name_in_url(config.database.database_url, "_secrets")

    # SQLite: use configured path
    db_path = Path(config.database.secrets_db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return str(db_path.resolve())


def get_audit_db_full_path(config: Optional[EssentialConfig] = None) -> str:
    """
    Get the full path to the audit database.

    For PostgreSQL: Modifies the database name in the URL (e.g., ciris_db -> ciris_db_auth)
    For SQLite: Returns the configured audit_db path

    Args:
        config: Optional EssentialConfig instance. If not provided, will attempt
                to get from the config service via ServiceRegistry.

    Returns:
        Full path to the audit database file or modified PostgreSQL URL
    """
    if config is None:
        config = _get_config_from_registry()
        if config is None:
            # For audit db, we can fall back to defaults as it's less critical
            config = EssentialConfig()

    # If using PostgreSQL (database_url is set), modify the database name
    if config.database.database_url:
        return _modify_database_name_in_url(config.database.database_url, "_auth")

    # SQLite: use configured path
    db_path = Path(config.database.audit_db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return str(db_path.resolve())


# For backward compatibility - uses defaults
def get_graph_memory_full_path() -> str:
    """Legacy function - graph memory is now in the main database."""
    return get_sqlite_db_full_path()
