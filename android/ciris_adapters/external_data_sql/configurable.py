"""
External Data SQL ConfigurableAdapterProtocol implementation.

Provides interactive configuration workflow for SQL database connections:
1. Database Type - Select dialect (PostgreSQL, MySQL, SQLite, MSSQL)
2. Connection - Enter connection details (host, port, database, credentials)
3. Privacy Schema - Optional privacy schema for GDPR/DSAR compliance
4. Features - Select enabled features (read-only mode, etc.)
5. Confirm - Review and apply configuration
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .schemas import SQLConnectorConfig, SQLDialect

logger = logging.getLogger(__name__)


class SQLConfigurableAdapter:
    """SQL database configurable adapter.

    Implements ConfigurableAdapterProtocol for SQL database connections
    with support for multiple dialects and GDPR/DSAR compliance features.
    """

    # Supported SQL dialects
    SUPPORTED_DIALECTS = {
        "postgres": {
            "label": "PostgreSQL",
            "description": "PostgreSQL database",
            "default_port": 5432,
            "connection_template": "postgresql://{user}:{password}@{host}:{port}/{database}",
        },
        "mysql": {
            "label": "MySQL/MariaDB",
            "description": "MySQL or MariaDB database",
            "default_port": 3306,
            "connection_template": "mysql+pymysql://{user}:{password}@{host}:{port}/{database}",
        },
        "sqlite": {
            "label": "SQLite",
            "description": "SQLite database file",
            "default_port": None,
            "connection_template": "sqlite:///{path}",
        },
        "mssql": {
            "label": "Microsoft SQL Server",
            "description": "Microsoft SQL Server database",
            "default_port": 1433,
            "connection_template": "mssql+pyodbc://{user}:{password}@{host}:{port}/{database}?driver=ODBC+Driver+17+for+SQL+Server",
        },
    }

    # Available features
    AVAILABLE_FEATURES = {
        "read_only": {
            "label": "Read-Only Mode",
            "description": "Restrict to SELECT queries only (no modifications)",
            "default": True,
        },
        "dsar_operations": {
            "label": "DSAR Operations",
            "description": "Enable GDPR/DSAR operations (find, export, delete, anonymize)",
            "default": True,
        },
        "query_validation": {
            "label": "Query Validation",
            "description": "Validate queries against privacy schema",
            "default": True,
        },
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the SQL configurable adapter.

        Args:
            config: Optional existing configuration
        """
        self.config = config or {}
        self._applied_config: Optional[Dict[str, Any]] = None

        logger.info("SQLConfigurableAdapter initialized")

    async def get_config_options(self, step_id: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get options for a selection step.

        Args:
            step_id: ID of the configuration step
            context: Current configuration context

        Returns:
            List of available options
        """
        logger.info(f"Getting config options for step: {step_id}")

        if step_id == "select_dialect":
            # Return supported SQL dialects
            return [
                {
                    "id": dialect_id,
                    "label": dialect["label"],
                    "description": dialect["description"],
                    "metadata": {
                        "default_port": dialect["default_port"],
                        "connection_template": dialect["connection_template"],
                    },
                }
                for dialect_id, dialect in self.SUPPORTED_DIALECTS.items()
            ]

        elif step_id == "select_features":
            # Return available features
            return [
                {
                    "id": feature_id,
                    "label": feature["label"],
                    "description": feature["description"],
                    "metadata": {"default": feature["default"]},
                }
                for feature_id, feature in self.AVAILABLE_FEATURES.items()
            ]

        return []

    async def validate_config(self, config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate SQL configuration before applying.

        Performs:
        - Required field validation
        - Connection string format validation
        - Dialect validation
        - Optional connectivity test

        Args:
            config: Complete configuration to validate

        Returns:
            (is_valid, error_message) tuple
        """
        logger.info("Validating SQL configuration")

        if not config:
            return False, "Configuration is empty"

        # Check required fields
        dialect = config.get("dialect")
        if not dialect:
            return False, "dialect is required"

        if dialect not in self.SUPPORTED_DIALECTS:
            return False, f"Invalid dialect: {dialect}. Must be one of: {list(self.SUPPORTED_DIALECTS.keys())}"

        # Validate connection parameters based on dialect
        if dialect == "sqlite":
            # SQLite needs path
            db_path = config.get("database_path")
            if not db_path:
                return False, "database_path is required for SQLite"
        else:
            # Other databases need host, database, credentials
            host = config.get("host")
            database = config.get("database")
            user = config.get("user")
            password = config.get("password")

            if not host:
                return False, "host is required"
            if not database:
                return False, "database is required"
            if not user:
                return False, "user is required"
            if not password:
                return False, "password is required"

        # Optional: Test connection if requested
        test_connection = config.get("test_connection", False)
        if test_connection:
            connection_string = self._build_connection_string(config)
            if not connection_string:
                return False, "Failed to build connection string"

            try:
                from sqlalchemy import create_engine, text

                engine = create_engine(connection_string, connect_args={"timeout": 10})
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                engine.dispose()
                logger.info("SQL connection test successful")
            except Exception as e:
                return False, f"Connection test failed: {e}"

        logger.info("SQL configuration validated successfully")
        return True, None

    def _build_connection_string(self, config: Dict[str, Any]) -> Optional[str]:
        """Build SQLAlchemy connection string from config.

        Args:
            config: Configuration dictionary

        Returns:
            Connection string or None if invalid
        """
        dialect = config.get("dialect")
        if not dialect or dialect not in self.SUPPORTED_DIALECTS:
            return None

        template = self.SUPPORTED_DIALECTS[dialect]["connection_template"]

        try:
            if dialect == "sqlite":
                # SQLite uses path
                db_path = config.get("database_path", "")
                return template.format(path=db_path)
            else:
                # Other databases use host/port/user/password/database
                host = config.get("host", "localhost")
                port = config.get("port", self.SUPPORTED_DIALECTS[dialect]["default_port"])
                user = config.get("user", "")
                password = config.get("password", "")
                database = config.get("database", "")

                return template.format(
                    host=host,
                    port=port,
                    user=user,
                    password=password,
                    database=database,
                )
        except KeyError as e:
            logger.error(f"Missing template parameter: {e}")
            return None

    async def apply_config(self, config: Dict[str, Any]) -> bool:
        """Apply the configuration.

        Stores configuration and sets up environment for the service.

        Args:
            config: Validated configuration to apply

        Returns:
            True if applied successfully
        """
        logger.info("Applying SQL configuration")

        self._applied_config = config.copy()

        # Build connection string
        connection_string = self._build_connection_string(config)
        if not connection_string:
            logger.error("Failed to build connection string")
            return False

        # Create SQL connector config
        dialect = config.get("dialect", "sqlite")
        connector_id = config.get("connector_id", "sql")
        privacy_schema_path = config.get("privacy_schema_path")

        try:
            sql_dialect = SQLDialect(dialect)
        except ValueError:
            logger.error(f"Invalid dialect: {dialect}")
            return False

        # Build config dict for JSON serialization
        config_dict = {
            "connector_id": connector_id,
            "connection_string": connection_string,
            "dialect": sql_dialect.value,
            "privacy_schema_path": privacy_schema_path,
            "connection_timeout": config.get("connection_timeout", 30),
            "query_timeout": config.get("query_timeout", 60),
            "max_retries": config.get("max_retries", 3),
        }

        # Save config to file
        config_path = os.environ.get("CIRIS_DATA_DIR", "data")
        config_file = Path(config_path) / "sql_config.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(config_file, "w") as f:
                json.dump(config_dict, f, indent=2)
            logger.info(f"SQL configuration saved to {config_file}")
        except Exception as e:
            logger.error(f"Failed to save config file: {e}")
            return False

        # Set environment variable for the SQL service
        os.environ["CIRIS_SQL_EXTERNAL_DATA_CONFIG"] = str(config_file)

        # Set feature flags
        enabled_features = config.get("enabled_features", [])
        if enabled_features:
            os.environ["CIRIS_SQL_ENABLED_FEATURES"] = ",".join(enabled_features)

        # Log sanitized config
        safe_config = {k: ("***" if "password" in k.lower() or "token" in k.lower() else v) for k, v in config.items()}
        logger.info(f"SQL configuration applied: {safe_config}")

        return True

    def get_applied_config(self) -> Optional[Dict[str, Any]]:
        """Get the currently applied configuration.

        Returns:
            Applied configuration or None if not configured
        """
        return self._applied_config
