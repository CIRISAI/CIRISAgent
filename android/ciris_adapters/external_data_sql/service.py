"""SQL Tool Service for external data access - Refactored with dialects."""

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from ciris_engine.logic.audit.signature_manager import AuditSignatureManager
from ciris_engine.logic.services.base_service import BaseService
from ciris_engine.protocols.services import TimeServiceProtocol, ToolService
from ciris_engine.schemas.adapters.tools import ToolExecutionResult, ToolExecutionStatus, ToolInfo, ToolParameterSchema
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.types import JSONDict

from .dialects import BaseSQLDialect, get_dialect
from .privacy_schema_loader import PrivacySchemaLoader
from .schemas import (
    DataLocation,
    PrivacySchemaConfig,
    SQLAnonymizationResult,
    SQLConnectorConfig,
    SQLDeletionResult,
    SQLDialect,
    SQLExportResult,
    SQLQueryResult,
    SQLStatsResult,
    SQLVerificationResult,
)

logger = logging.getLogger(__name__)


class SQLToolService(BaseService, ToolService):
    """Tool service for SQL database access and DSAR automation.

    Provides dialect-aware SQL operations for SQLite, MySQL, and PostgreSQL.
    Follows organic architecture: external data sources as tools.

    Refactored features:
    - Dialect separation for maintainability
    - Hybrid YAML/graph privacy schema storage
    - Cleaner service implementation
    """

    def __init__(
        self,
        config: Optional[SQLConnectorConfig] = None,
        privacy_schema_path: Optional[str] = None,
        *,
        time_service: Optional[TimeServiceProtocol] = None,
        **kwargs: Any,  # Accept additional kwargs from service loader
    ):
        """Initialize SQL tool service.

        Args:
            config: Optional connector configuration
            privacy_schema_path: Optional path to YAML/JSON privacy schema file
            time_service: Time service for timestamps (injected by framework)
            **kwargs: Additional keyword arguments (ignored, for framework compatibility)
        """
        super().__init__(time_service=time_service, service_name="SQLToolService")

        # Load config from environment variable if not provided
        if config is None:
            config_path = os.environ.get("CIRIS_SQL_EXTERNAL_DATA_CONFIG")
            if config_path:
                config = self._load_config_from_file(config_path)
                # Extract privacy schema path from config if provided
                if config and hasattr(config, "privacy_schema_path"):
                    privacy_schema_path = config.privacy_schema_path

        self._config = config
        self._engine: Optional[Engine] = None
        self._connector_id = config.connector_id if config else "sql"
        self._dialect: Optional[BaseSQLDialect] = None
        self._schema_loader = PrivacySchemaLoader()
        self._privacy_schema_path = privacy_schema_path

        # Signature manager for GDPR deletion verification (RSA-PSS signatures)
        self._signature_manager: Optional[AuditSignatureManager] = None
        self._signature_key_path = Path(os.environ.get("CIRIS_DATA_DIR", "data")) / "sql_deletion_keys"
        self._signature_db_path = str(Path(os.environ.get("CIRIS_DATA_DIR", "data")) / "ciris.db")

        # Result tracking and tool metadata
        self._results: Dict[str, ToolExecutionResult] = {}
        self._tool_schemas: Dict[str, ToolParameterSchema] = {}
        self._tool_info: Dict[str, ToolInfo] = {}

        # Build tool metadata after initialization
        self._tool_schemas = self._build_tool_schemas()
        self._tool_info = self._build_tool_info()

    def _load_config_from_file(self, config_path: str) -> Optional[SQLConnectorConfig]:
        """Load SQL connector configuration from JSON file.

        Args:
            config_path: Path to JSON configuration file

        Returns:
            SQLConnectorConfig if successful, None otherwise
        """
        try:
            with open(config_path, "r") as f:
                config_data = json.load(f)
            return SQLConnectorConfig(**config_data)
        except Exception as e:
            # Can't use self.log_error here - base class not initialized yet
            print(f"ERROR: Failed to load SQL config from {config_path}: {e}")
            return None

    async def initialize(self) -> None:
        """Initialize the service and database connection."""
        # Note: BaseService doesn't have initialize(), but this is required by framework
        # await super().initialize()  # Skip if not implemented

        # TODO: Move to debug level after tool registration is confirmed working
        self._logger.info(
            f"SQLToolService initializing with config: {self._config.connector_id if self._config else 'None'}"
        )
        self._logger.info(f"SQLToolService has {len(self._tool_schemas)} tool schemas ready")
        self._logger.info(f"SQLToolService has {len(self._tool_info)} tool info objects ready")

        # Initialize signature manager for GDPR deletion verification
        if self._time_service:
            try:
                self._signature_manager = AuditSignatureManager(
                    key_path=str(self._signature_key_path),
                    db_path=self._signature_db_path,
                    time_service=self._time_service,
                )
                self._signature_manager.initialize()
                logger.info(f"Initialized deletion signature manager with key ID: {self._signature_manager.key_id}")
            except Exception as e:
                logger.warning(f"Failed to initialize signature manager: {e}. Signatures will not be available.")
                self._signature_manager = None
        else:
            logger.warning("Time service not available - deletion verification signatures unavailable")
            self._signature_manager = None

        if self._config:
            # Initialize dialect
            self._dialect = get_dialect(self._config.dialect.value)

            # Load privacy schema if path provided
            if self._privacy_schema_path:
                self._config.privacy_schema = self._schema_loader.load_from_file(self._privacy_schema_path)

            # Connect to database
            await self._connect()

            # TODO: Move to debug level after tool registration is confirmed working
            self._logger.info(f"SQLToolService initialized successfully - tools: {await self.list_tools()}")

    async def _connect(self) -> None:
        """Establish database connection."""
        if not self._config:
            return

        try:
            self._engine = create_engine(
                self._config.connection_string,
                connect_args={"timeout": self._config.connection_timeout},
                pool_pre_ping=True,
                echo=False,
            )
            # Test connection
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            dialect_name = self._dialect.name if self._dialect else "unknown"
            self._logger.info(f"Connected to {dialect_name} database: {self._connector_id}")
        except SQLAlchemyError as e:
            self._logger.error(f"Failed to connect to database: {e}")
            raise

    # BaseService Protocol Methods ----------------------------------------------
    def get_service_type(self) -> ServiceType:
        """Return service type."""
        return ServiceType.TOOL

    def _get_actions(self) -> List[str]:
        """Return list of available actions/tools.

        Uses generic SQL tool names. Connector ID is passed as parameter.
        """
        return [
            "initialize_sql_connector",
            "get_sql_service_metadata",
            "sql_find_user_data",
            "sql_export_user",
            "sql_delete_user",
            "sql_anonymize_user",
            "sql_verify_deletion",
            "sql_get_stats",
            "sql_query",
        ]

    def _check_dependencies(self) -> bool:
        """Check if service dependencies are met.

        At start time, we just need config to be available.
        Engine and dialect will be initialized in initialize().
        """
        return self._config is not None

    # ToolServiceProtocol Methods -----------------------------------------------
    async def list_tools(self) -> List[str]:
        """List available SQL tools.

        Returns generic SQL tool names. Connector ID is passed as parameter to each tool.

        Returns:
            List of generic SQL tool names
        """
        # TODO: Move to debug level after tool registration is confirmed working
        self._logger.info(f"list_tools() called on SQLToolService")
        tools = [
            "initialize_sql_connector",
            "get_sql_service_metadata",
            "sql_find_user_data",
            "sql_export_user",
            "sql_delete_user",
            "sql_anonymize_user",
            "sql_verify_deletion",
            "sql_get_stats",
            "sql_query",
        ]
        # TODO: Move to debug level after tool registration is confirmed working
        self._logger.info(f"list_tools() returning {len(tools)} tools: {tools}")
        return tools

    async def execute_tool(self, tool_name: str, parameters: JSONDict) -> ToolExecutionResult:
        """Execute SQL tool.

        Args:
            tool_name: Generic SQL tool name (e.g. "sql_find_user_data")
            parameters: Tool parameters including connector_id

        Returns:
            Tool execution result
        """
        # TODO: Move to debug level after tool registration is confirmed working
        self._logger.info(f"execute_tool() called with tool_name={tool_name}, parameters={list(parameters.keys())}")

        # Extract or generate correlation ID for result tracking
        import uuid

        correlation_id_raw = parameters.get("correlation_id")
        correlation_id = str(correlation_id_raw) if correlation_id_raw else str(uuid.uuid4())

        # Handle initialization and metadata tools (no connector_id validation needed)
        if tool_name == "initialize_sql_connector":
            result = await self._initialize_connector(parameters)
            self._results[correlation_id] = result
            return result
        elif tool_name == "get_sql_service_metadata":
            result = await self._get_sql_metadata(parameters)
            self._results[correlation_id] = result
            return result

        # Validate tool name format for SQL tools
        if not tool_name.startswith("sql_"):
            result = ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={},
                error=f"Tool {tool_name} is not a SQL tool",
                correlation_id=correlation_id,
            )
            self._results[correlation_id] = result
            return result

        # Extract connector_id from parameters
        connector_id = parameters.get("connector_id")
        if not connector_id:
            result = ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={},
                error="connector_id parameter is required",
                correlation_id=correlation_id,
            )
            self._results[correlation_id] = result
            return result

        # Verify this service handles the requested connector
        if connector_id != self._connector_id:
            result = ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={},
                error=f"This service handles connector '{self._connector_id}', not '{connector_id}'",
                correlation_id=correlation_id,
            )
            self._results[correlation_id] = result
            return result

        # Extract method name from tool name
        method_name = tool_name[4:]  # Strip "sql_" prefix

        # Route to appropriate method
        exec_result: ToolExecutionResult
        if method_name == "find_user_data":
            exec_result = await self._find_user_data(parameters, correlation_id)
        elif method_name == "export_user":
            exec_result = await self._export_user(parameters, correlation_id)
        elif method_name == "delete_user":
            exec_result = await self._delete_user(parameters, correlation_id)
        elif method_name == "anonymize_user":
            exec_result = await self._anonymize_user(parameters, correlation_id)
        elif method_name == "verify_deletion":
            exec_result = await self._verify_deletion(parameters, correlation_id)
        elif method_name == "get_stats":
            exec_result = await self._get_stats(parameters, correlation_id)
        elif method_name == "query":
            exec_result = await self._query(parameters, correlation_id)
        else:
            exec_result = ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={},
                error=f"Unknown tool: {method_name}",
                correlation_id=correlation_id,
            )

        # Store result for later retrieval
        self._results[correlation_id] = exec_result
        return exec_result

    # Tool Implementation Methods -----------------------------------------------
    async def _initialize_connector(self, parameters: JSONDict) -> ToolExecutionResult:
        """Initialize or reconfigure SQL connector dynamically.

        Args:
            parameters: Dict containing:
                - connector_id: Unique identifier for the connector
                - connection_string: Database connection string
                - dialect: SQL dialect (sqlite, postgres, mysql, etc.)
                - privacy_schema_path: Path to privacy schema YAML file

        Returns:
            ToolExecutionResult with connector configuration details
        """
        # TODO: Move to debug level after tool registration is confirmed working
        self._logger.info(f"_initialize_connector called with parameters: {list(parameters.keys())}")

        # Extract or generate correlation ID
        import uuid

        correlation_id_raw = parameters.get("correlation_id")
        correlation_id = str(correlation_id_raw) if correlation_id_raw else str(uuid.uuid4())

        try:
            # Extract required parameters
            connector_id = parameters.get("connector_id")
            connection_string = parameters.get("connection_string")
            dialect = parameters.get("dialect")
            privacy_schema_path = parameters.get("privacy_schema_path")

            if not all([connector_id, connection_string, dialect]):
                return ToolExecutionResult(
                    tool_name="initialize_sql_connector",
                    status=ToolExecutionStatus.FAILED,
                    success=False,
                    data={},
                    error="Missing required parameters: connector_id, connection_string, and dialect are required",
                    correlation_id=correlation_id,
                )

            # Parse dialect
            try:
                sql_dialect = SQLDialect(str(dialect))
            except ValueError:
                return ToolExecutionResult(
                    tool_name="initialize_sql_connector",
                    status=ToolExecutionStatus.FAILED,
                    success=False,
                    data={},
                    error=f"Invalid dialect: {dialect}. Must be one of: {[d.value for d in SQLDialect]}",
                    correlation_id=correlation_id,
                )

            # Load privacy schema if path provided
            privacy_schema = None
            if privacy_schema_path and isinstance(privacy_schema_path, str):
                try:
                    with open(privacy_schema_path, "r") as f:
                        import yaml

                        schema_data = yaml.safe_load(f)
                        privacy_schema = PrivacySchemaConfig(**schema_data)
                except Exception as e:
                    self._logger.error(f"Failed to load privacy schema from {privacy_schema_path}: {e}")
                    return ToolExecutionResult(
                        tool_name="initialize_sql_connector",
                        status=ToolExecutionStatus.FAILED,
                        success=False,
                        data={},
                        error=f"Failed to load privacy schema: {str(e)}",
                        correlation_id=correlation_id,
                    )

            # Validate types for config creation
            if not isinstance(connector_id, str):
                connector_id = str(connector_id) if connector_id else ""
            if not isinstance(connection_string, str):
                connection_string = str(connection_string) if connection_string else ""

            # Create new config with safe type conversions
            conn_timeout = parameters.get("connection_timeout", 30)
            q_timeout = parameters.get("query_timeout", 60)
            retries = parameters.get("max_retries", 3)

            new_config = SQLConnectorConfig(
                connector_id=connector_id,
                connection_string=connection_string,
                dialect=sql_dialect,
                privacy_schema=privacy_schema,
                connection_timeout=int(conn_timeout) if isinstance(conn_timeout, (int, float, str)) else 30,
                query_timeout=int(q_timeout) if isinstance(q_timeout, (int, float, str)) else 60,
                max_retries=int(retries) if isinstance(retries, (int, float, str)) else 3,
            )

            # Update instance configuration
            self._config = new_config
            self._connector_id = connector_id
            self._dialect = get_dialect(sql_dialect.value)

            # Reinitialize engine
            try:
                from sqlalchemy import create_engine

                self._engine = create_engine(connection_string, connect_args={"timeout": new_config.connection_timeout})

                # Test connection
                with self._engine.connect() as conn:
                    conn.execute(text("SELECT 1"))

            except Exception as e:
                self._logger.error(f"Failed to initialize database engine: {e}")
                return ToolExecutionResult(
                    tool_name="initialize_sql_connector",
                    status=ToolExecutionStatus.FAILED,
                    success=False,
                    data={},
                    error=f"Failed to connect to database: {str(e)}",
                    correlation_id=correlation_id,
                )

            # Return success with configuration details
            self._logger.info(f"Successfully initialized connector: {connector_id}")
            return ToolExecutionResult(
                tool_name="initialize_sql_connector",
                status=ToolExecutionStatus.COMPLETED,
                success=True,
                data={
                    "connector_id": connector_id,
                    "dialect": str(dialect),
                    "privacy_schema_configured": privacy_schema is not None,
                    "connection_successful": True,
                },
                error=None,
                correlation_id=correlation_id,
            )

        except Exception as e:
            self._logger.error(f"Unexpected error in _initialize_connector: {e}")
            return ToolExecutionResult(
                tool_name="initialize_sql_connector",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={},
                error=f"Unexpected error: {str(e)}",
                correlation_id=correlation_id,
            )

    async def _get_sql_metadata(self, parameters: JSONDict) -> ToolExecutionResult:
        """Get metadata about the SQL connector and its capabilities.

        Args:
            parameters: Dict containing:
                - connector_id: Connector to get metadata for

        Returns:
            ToolExecutionResult with connector metadata
        """
        # TODO: Move to debug level after tool registration is confirmed working
        self._logger.info(f"_get_sql_metadata called with parameters: {list(parameters.keys())}")

        # Extract or generate correlation ID
        import uuid

        correlation_id_raw = parameters.get("correlation_id")
        correlation_id = str(correlation_id_raw) if correlation_id_raw else str(uuid.uuid4())

        try:
            connector_id = parameters.get("connector_id")

            # Verify connector matches this service
            if connector_id and connector_id != self._connector_id:
                return ToolExecutionResult(
                    tool_name="get_sql_service_metadata",
                    status=ToolExecutionStatus.FAILED,
                    success=False,
                    data={},
                    error=f"This service handles connector '{self._connector_id}', not '{connector_id}'",
                    correlation_id=correlation_id,
                )

            if not self._config or not self._engine:
                return ToolExecutionResult(
                    tool_name="get_sql_service_metadata",
                    status=ToolExecutionStatus.FAILED,
                    success=False,
                    data={},
                    error="Connector not initialized. Call initialize_sql_connector first.",
                    correlation_id=correlation_id,
                )

            # Get table count from database
            table_count = 0
            try:
                from sqlalchemy import inspect

                inspector = inspect(self._engine)
                tables = inspector.get_table_names()
                table_count = len(tables)
            except Exception as e:
                self._logger.warning(f"Could not get table count: {e}")

            # Build metadata response
            dialect_name = self._dialect.name if self._dialect else "unknown"
            metadata = {
                "data_source": True,
                "data_source_type": "sql",
                "contains_pii": True,  # Assumed true if privacy schema configured
                "gdpr_applicable": True,  # Assumed true for SQL data sources
                "connector_id": self._connector_id,
                "dialect": dialect_name,
                "dsar_capabilities": [
                    "find",
                    "export",
                    "delete",
                    "anonymize",
                ],
                "privacy_schema_configured": self._config.privacy_schema is not None,
                "table_count": table_count,
            }

            self._logger.info(f"Successfully retrieved metadata for connector: {self._connector_id}")
            return ToolExecutionResult(
                tool_name="get_sql_service_metadata",
                status=ToolExecutionStatus.COMPLETED,
                success=True,
                data=metadata,
                error=None,
                correlation_id=correlation_id,
            )

        except Exception as e:
            self._logger.error(f"Unexpected error in _get_sql_metadata: {e}")
            return ToolExecutionResult(
                tool_name="get_sql_service_metadata",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={},
                error=f"Unexpected error: {str(e)}",
                correlation_id=correlation_id,
            )

    async def _find_user_data(self, parameters: JSONDict, correlation_id: str) -> ToolExecutionResult:
        """Find all locations where user data exists."""
        if not self._engine or not self._config or not self._dialect:
            return ToolExecutionResult(
                tool_name="sql_find_user_data",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={},
                error="Database not configured",
                correlation_id=correlation_id,
            )

        user_identifier = parameters.get("user_identifier")
        if not user_identifier:
            return ToolExecutionResult(
                tool_name="sql_find_user_data",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={},
                error="user_identifier required",
                correlation_id=correlation_id,
            )

        locations: List[DataLocation] = []

        try:
            # Check privacy_schema is not None before accessing tables
            if self._config.privacy_schema is None:
                return ToolExecutionResult(
                    tool_name="sql_find_user_data",
                    status=ToolExecutionStatus.FAILED,
                    success=False,
                    data={},
                    error="Privacy schema not configured",
                    correlation_id=correlation_id,
                )

            with self._engine.connect() as conn:
                for table_mapping in self._config.privacy_schema.tables:
                    table_name = table_mapping.table_name
                    identifier_col = table_mapping.identifier_column

                    # Use dialect to build query
                    query_str = self._dialect.build_count_query(table_name, identifier_col)
                    result = conn.execute(text(query_str), {"user_id": user_identifier})
                    row_count = result.scalar()

                    if row_count and row_count > 0:
                        # Found data - record each privacy-sensitive column
                        for col_mapping in table_mapping.columns:
                            locations.append(
                                DataLocation(
                                    table_name=table_name,
                                    column_name=col_mapping.column_name,
                                    data_type=col_mapping.data_type,
                                    row_count=row_count,
                                )
                            )

            return ToolExecutionResult(
                tool_name="sql_find_user_data",
                status=ToolExecutionStatus.COMPLETED,
                success=True,
                data={"locations": [loc.model_dump() for loc in locations]},
                error=None,
                correlation_id=correlation_id,
            )
        except SQLAlchemyError as e:
            return ToolExecutionResult(
                tool_name="sql_find_user_data",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={},
                error=f"Database error: {e}",
                correlation_id=correlation_id,
            )

    async def _export_user(self, parameters: JSONDict, correlation_id: str) -> ToolExecutionResult:
        """Export all user data."""
        if not self._engine or not self._config or not self._dialect:
            return ToolExecutionResult(
                tool_name="sql_export_user",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={},
                error="Database not configured",
                correlation_id=correlation_id,
            )

        user_identifier = parameters.get("user_identifier")
        export_format = parameters.get("export_format", "json")

        if not user_identifier:
            return ToolExecutionResult(
                tool_name="sql_export_user",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={},
                error="user_identifier required",
                correlation_id=correlation_id,
            )

        data: Dict[str, List[Dict[str, Any]]] = {}
        total_rows = 0

        try:
            # Check privacy_schema is not None before accessing tables
            if self._config.privacy_schema is None:
                return ToolExecutionResult(
                    tool_name="sql_export_user",
                    status=ToolExecutionStatus.FAILED,
                    success=False,
                    data={},
                    error="Privacy schema not configured",
                    correlation_id=correlation_id,
                )

            with self._engine.connect() as conn:
                for table_mapping in self._config.privacy_schema.tables:
                    table_name = table_mapping.table_name
                    identifier_col = table_mapping.identifier_column

                    # Use dialect to build query
                    query_str = self._dialect.build_select_query(table_name, identifier_col)
                    result = conn.execute(text(query_str), {"user_id": user_identifier})

                    rows = []
                    for row in result:
                        rows.append(dict(row._mapping))

                    if rows:
                        data[table_name] = rows
                        total_rows += len(rows)

            # Generate checksum
            data_json = json.dumps(data, sort_keys=True)
            checksum = hashlib.sha256(data_json.encode()).hexdigest()

            export_result = SQLExportResult(
                success=True,
                user_identifier=str(user_identifier),
                tables_exported=list(data.keys()),
                total_rows=total_rows,
                data=data,
                export_format=str(export_format),
                checksum=checksum,
            )

            return ToolExecutionResult(
                tool_name="sql_export_user",
                status=ToolExecutionStatus.COMPLETED,
                success=True,
                data=export_result.model_dump(),
                error=None,
                correlation_id=correlation_id,
            )
        except SQLAlchemyError as e:
            return ToolExecutionResult(
                tool_name="sql_export_user",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={},
                error=f"Database error: {e}",
                correlation_id=correlation_id,
            )

    async def _delete_user(self, parameters: JSONDict, correlation_id: str) -> ToolExecutionResult:
        """Delete all user data."""
        if not self._engine or not self._config or not self._dialect:
            return ToolExecutionResult(
                tool_name="sql_delete_user",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={},
                error="Database not configured",
                correlation_id=correlation_id,
            )

        user_identifier = parameters.get("user_identifier")
        verify = parameters.get("verify", True)

        if not user_identifier:
            return ToolExecutionResult(
                tool_name="sql_delete_user",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={},
                error="user_identifier required",
                correlation_id=correlation_id,
            )

        tables_affected: List[str] = []
        total_rows_deleted = 0
        cascade_deletions: Dict[str, int] = {}

        try:
            # Check privacy_schema is not None before accessing tables
            if self._config.privacy_schema is None:
                return ToolExecutionResult(
                    tool_name="sql_delete_user",
                    status=ToolExecutionStatus.FAILED,
                    success=False,
                    data={},
                    error="Privacy schema not configured",
                    correlation_id=correlation_id,
                )

            with self._engine.begin() as conn:  # Transaction
                for table_mapping in self._config.privacy_schema.tables:
                    table_name = table_mapping.table_name
                    identifier_col = table_mapping.identifier_column

                    # Use dialect to build query
                    query_str = self._dialect.build_delete_query(table_name, identifier_col)
                    result = conn.execute(text(query_str), {"user_id": user_identifier})
                    rows_deleted = result.rowcount

                    if rows_deleted > 0:
                        tables_affected.append(table_name)
                        total_rows_deleted += rows_deleted

                    # Cascade deletions
                    for cascade_table in table_mapping.cascade_deletes:
                        cascade_query_str = self._dialect.build_delete_query(cascade_table, identifier_col)
                        cascade_result = conn.execute(text(cascade_query_str), {"user_id": user_identifier})
                        cascade_count = cascade_result.rowcount
                        if cascade_count > 0:
                            cascade_deletions[cascade_table] = cascade_count
                            total_rows_deleted += cascade_count

            # Verify deletion if requested
            verification_passed = False
            if verify:
                verify_result = await self._verify_deletion(
                    {"user_identifier": user_identifier, "sign": False}, correlation_id
                )
                if verify_result.data is not None and isinstance(verify_result.data, dict):
                    verification_passed = bool(verify_result.data.get("zero_data_confirmed", False))
                else:
                    verification_passed = False

            deletion_result = SQLDeletionResult(
                success=True,
                user_identifier=str(user_identifier),
                tables_affected=tables_affected,
                total_rows_deleted=total_rows_deleted,
                cascade_deletions=cascade_deletions,
                verification_passed=verification_passed,
            )

            return ToolExecutionResult(
                tool_name="sql_delete_user",
                status=ToolExecutionStatus.COMPLETED,
                success=True,
                data=deletion_result.model_dump(),
                error=None,
                correlation_id=correlation_id,
            )
        except SQLAlchemyError as e:
            return ToolExecutionResult(
                tool_name="sql_delete_user",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={},
                error=f"Database error: {e}",
                correlation_id=correlation_id,
            )

    async def _anonymize_user(self, parameters: JSONDict, correlation_id: str) -> ToolExecutionResult:
        """Anonymize user data instead of deleting."""
        if not self._engine or not self._config or not self._dialect:
            return ToolExecutionResult(
                tool_name="sql_anonymize_user",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={},
                error="Database not configured",
                correlation_id=correlation_id,
            )

        user_identifier = parameters.get("user_identifier")
        strategy = parameters.get("strategy", "pseudonymize")

        if not user_identifier:
            return ToolExecutionResult(
                tool_name="sql_anonymize_user",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={},
                error="user_identifier required",
                correlation_id=correlation_id,
            )

        tables_affected: List[str] = []
        columns_anonymized: Dict[str, List[str]] = {}
        total_rows_affected = 0

        try:
            # Check privacy_schema is not None before accessing tables
            if self._config.privacy_schema is None:
                return ToolExecutionResult(
                    tool_name="sql_anonymize_user",
                    status=ToolExecutionStatus.FAILED,
                    success=False,
                    data={},
                    error="Privacy schema not configured",
                    correlation_id=correlation_id,
                )

            with self._engine.begin() as conn:  # Transaction
                for table_mapping in self._config.privacy_schema.tables:
                    table_name = table_mapping.table_name
                    identifier_col = table_mapping.identifier_column
                    cols_to_anonymize = []

                    # Use dialect to build anonymization query
                    column_mappings = [cm for cm in table_mapping.columns if cm.anonymization_strategy != "delete"]

                    if column_mappings:
                        query_str = self._dialect.build_update_query(
                            table_name,
                            identifier_col,
                            column_mappings,
                            str(user_identifier),
                        )

                        if query_str:
                            result = conn.execute(text(query_str), {"user_id": user_identifier})
                            rows_affected = result.rowcount

                            if rows_affected > 0:
                                tables_affected.append(table_name)
                                cols_to_anonymize = [cm.column_name for cm in column_mappings]
                                columns_anonymized[table_name] = cols_to_anonymize
                                total_rows_affected += rows_affected

            anonymization_result = SQLAnonymizationResult(
                success=True,
                user_identifier=str(user_identifier),
                tables_affected=tables_affected,
                columns_anonymized=columns_anonymized,
                total_rows_affected=total_rows_affected,
                anonymization_strategy=str(strategy),
            )

            return ToolExecutionResult(
                tool_name="sql_anonymize_user",
                status=ToolExecutionStatus.COMPLETED,
                success=True,
                data=anonymization_result.model_dump(),
                error=None,
                correlation_id=correlation_id,
            )
        except SQLAlchemyError as e:
            return ToolExecutionResult(
                tool_name="sql_anonymize_user",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={},
                error=f"Database error: {e}",
                correlation_id=correlation_id,
            )

    async def _verify_deletion(self, parameters: JSONDict, correlation_id: str) -> ToolExecutionResult:
        """Verify that user data has been completely deleted."""
        if not self._engine or not self._config or not self._dialect:
            return ToolExecutionResult(
                tool_name="sql_verify_deletion",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={},
                error="Database not configured",
                correlation_id=correlation_id,
            )

        user_identifier = parameters.get("user_identifier")
        sign = parameters.get("sign", True)

        if not user_identifier:
            return ToolExecutionResult(
                tool_name="sql_verify_deletion",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={},
                error="user_identifier required",
                correlation_id=correlation_id,
            )

        tables_scanned: List[str] = []
        remaining_data: Dict[str, int] = {}

        try:
            # Check privacy_schema is not None before accessing tables
            if self._config.privacy_schema is None:
                return ToolExecutionResult(
                    tool_name="sql_verify_deletion",
                    status=ToolExecutionStatus.FAILED,
                    success=False,
                    data={},
                    error="Privacy schema not configured",
                    correlation_id=correlation_id,
                )

            with self._engine.connect() as conn:
                for table_mapping in self._config.privacy_schema.tables:
                    table_name = table_mapping.table_name
                    identifier_col = table_mapping.identifier_column

                    # Use dialect to build query
                    query_str = self._dialect.build_count_query(table_name, identifier_col)
                    result = conn.execute(text(query_str), {"user_id": user_identifier})
                    row_count = result.scalar()

                    tables_scanned.append(table_name)
                    if row_count and row_count > 0:
                        remaining_data[table_name] = row_count

            zero_data_confirmed = len(remaining_data) == 0

            # Check if time_service is available
            if self._time_service is None:
                # Fallback timestamp using datetime
                from datetime import datetime

                timestamp = datetime.utcnow().isoformat() + "Z"
            else:
                # Try to get timestamp from time service
                # TimeServiceProtocol doesn't have get_utc_timestamp_str, use alternative
                from datetime import datetime

                timestamp = datetime.utcnow().isoformat() + "Z"

            # Generate RSA-PSS signature for GDPR Article 17 deletion verification
            cryptographic_proof = None
            if sign and zero_data_confirmed:
                if self._signature_manager:
                    try:
                        # Create deterministic hash of verification data
                        verification_data = (
                            f"{user_identifier}|{timestamp}|{zero_data_confirmed}|{','.join(sorted(tables_scanned))}"
                        )
                        data_hash = hashlib.sha256(verification_data.encode("utf-8")).hexdigest()

                        # Sign the hash using RSA-PSS
                        signature = self._signature_manager.sign_entry(data_hash)
                        key_id = self._signature_manager.key_id or "unknown"
                        cryptographic_proof = f"rsa-pss:{key_id}:{signature}"

                        logger.info(
                            f"Generated deletion verification signature for {user_identifier} "
                            f"(key: {key_id[:8]}...)"
                        )
                    except Exception as e:
                        logger.error(f"Failed to generate deletion verification signature: {e}")
                        cryptographic_proof = None
                else:
                    logger.warning("Signature manager not available - deletion verification signature unavailable")

            verification_result = SQLVerificationResult(
                success=True,
                user_identifier=str(user_identifier),
                zero_data_confirmed=zero_data_confirmed,
                tables_scanned=tables_scanned,
                remaining_data=remaining_data,
                verification_timestamp=timestamp,
                cryptographic_proof=cryptographic_proof,
            )

            return ToolExecutionResult(
                tool_name="sql_verify_deletion",
                status=ToolExecutionStatus.COMPLETED,
                success=True,
                data=verification_result.model_dump(),
                error=None,
                correlation_id=correlation_id,
            )
        except SQLAlchemyError as e:
            return ToolExecutionResult(
                tool_name="sql_verify_deletion",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={},
                error=f"Database error: {e}",
                correlation_id=correlation_id,
            )

    async def _get_stats(self, parameters: JSONDict, correlation_id: str) -> ToolExecutionResult:
        """Get database statistics."""
        if not self._engine or not self._config or not self._dialect:
            return ToolExecutionResult(
                tool_name="sql_get_stats",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={},
                error="Database not configured",
                correlation_id=correlation_id,
            )

        tables: Dict[str, int] = {}
        total_rows = 0

        try:
            # Check privacy_schema is not None before accessing tables
            if self._config.privacy_schema is None:
                return ToolExecutionResult(
                    tool_name="sql_get_stats",
                    status=ToolExecutionStatus.FAILED,
                    success=False,
                    data={},
                    error="Privacy schema not configured",
                    correlation_id=correlation_id,
                )

            with self._engine.connect() as conn:
                # Get row counts for all privacy tables
                for table_mapping in self._config.privacy_schema.tables:
                    table_name = table_mapping.table_name
                    query_str = f"SELECT COUNT(*) as cnt FROM {table_name}"
                    result = conn.execute(text(query_str))
                    row_count = result.scalar()

                    tables[table_name] = row_count or 0
                    total_rows += row_count or 0

                # Get database size if supported
                database_size_mb = None
                size_query = self._dialect.get_database_size_query()
                if size_query:
                    result = conn.execute(text(size_query))
                    database_size_mb = result.scalar()

            stats_result = SQLStatsResult(
                success=True,
                total_tables=len(tables),
                total_rows=total_rows,
                tables=tables,
                database_size_mb=database_size_mb,
            )

            return ToolExecutionResult(
                tool_name="sql_get_stats",
                status=ToolExecutionStatus.COMPLETED,
                success=True,
                data=stats_result.model_dump(),
                error=None,
                correlation_id=correlation_id,
            )
        except SQLAlchemyError as e:
            return ToolExecutionResult(
                tool_name="sql_get_stats",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={},
                error=f"Database error: {e}",
                correlation_id=correlation_id,
            )

    def _validate_sql_query(self, sql: str) -> Optional[str]:
        """Validate SQL query against privacy schema.

        Security constraints:
        1. Only SELECT statements allowed
        2. Must query configured tables only
        3. No DDL (CREATE, DROP, ALTER)
        4. No DML (INSERT, UPDATE, DELETE) except via dedicated tools

        Args:
            sql: SQL query string to validate

        Returns:
            Error message if invalid, None if valid
        """
        # Normalize query for validation
        sql_upper = sql.strip().upper()

        # Only allow SELECT queries
        if not sql_upper.startswith("SELECT"):
            return "Only SELECT queries are allowed. Use dedicated tools for modifications."

        # Block dangerous keywords
        dangerous_keywords = [
            "DROP",
            "CREATE",
            "ALTER",
            "TRUNCATE",
            "INSERT",
            "UPDATE",
            "DELETE",
            "GRANT",
            "REVOKE",
            "EXEC",
            "EXECUTE",
        ]
        for keyword in dangerous_keywords:
            if keyword in sql_upper:
                return f"Keyword '{keyword}' is not allowed in queries"

        # Validate against privacy schema if configured
        if self._config and self._config.privacy_schema:
            # Extract table names from privacy schema
            allowed_tables = [table.table_name.upper() for table in self._config.privacy_schema.tables]

            # Basic table name extraction (this is not perfect, but provides basic protection)
            # Look for FROM and JOIN clauses
            import re

            # Find FROM clause
            from_match = re.search(r"\bFROM\s+(\w+)", sql_upper)
            if from_match:
                table_name = from_match.group(1)
                if table_name not in allowed_tables:
                    return f"Table '{table_name}' is not in privacy schema. Allowed: {', '.join(allowed_tables)}"

            # Find JOIN clauses
            join_matches = re.findall(r"\bJOIN\s+(\w+)", sql_upper)
            for table_name in join_matches:
                if table_name not in allowed_tables:
                    return f"Table '{table_name}' is not in privacy schema. Allowed: {', '.join(allowed_tables)}"

        return None  # Valid query

    async def _query(self, parameters: JSONDict, correlation_id: str) -> ToolExecutionResult:
        """Execute raw SQL query (with privacy constraints)."""
        if not self._engine:
            return ToolExecutionResult(
                tool_name="sql_query",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={},
                error="Database not configured",
                correlation_id=correlation_id,
            )

        sql = parameters.get("sql")
        query_params = parameters.get("parameters", {})

        if not sql:
            return ToolExecutionResult(
                tool_name="sql_query",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={},
                error="sql required",
                correlation_id=correlation_id,
            )

        # Validate types
        if not isinstance(sql, str):
            return ToolExecutionResult(
                tool_name="sql_query",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={},
                error="sql parameter must be a string",
                correlation_id=correlation_id,
            )

        if query_params is not None and not isinstance(query_params, dict):
            query_params = {}

        # SECURITY: Validate SQL query against privacy schema
        # Only allow SELECT queries on configured tables
        validation_error = self._validate_sql_query(sql)
        if validation_error:
            return ToolExecutionResult(
                tool_name="sql_query",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={},
                error=f"SQL validation failed: {validation_error}",
                correlation_id=correlation_id,
            )

        start_time = time.time()

        try:
            with self._engine.connect() as conn:
                result = conn.execute(text(sql), query_params)

                rows = []
                columns = []
                if result.returns_rows:
                    columns = list(result.keys())
                    for row in result:
                        rows.append(dict(row._mapping))

                execution_time_ms = (time.time() - start_time) * 1000

                query_result = SQLQueryResult(
                    success=True,
                    row_count=len(rows),
                    columns=columns,
                    rows=rows,
                    execution_time_ms=execution_time_ms,
                )

                return ToolExecutionResult(
                    tool_name="sql_query",
                    status=ToolExecutionStatus.COMPLETED,
                    success=True,
                    data=query_result.model_dump(),
                    error=None,
                    correlation_id=correlation_id,
                )
        except SQLAlchemyError as e:
            return ToolExecutionResult(
                tool_name="sql_query",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={},
                error=f"Database error: {e}",
                correlation_id=correlation_id,
            )

    # Tool Schema and Info Builders ---------------------------------------------
    def _build_tool_schemas(self) -> Dict[str, ToolParameterSchema]:
        """Build parameter schemas for all SQL tools.

        Uses generic SQL tool names with connector_id as a parameter.
        """
        # Base properties that all SQL tools need
        base_props = {
            "connector_id": {"type": "string", "description": "SQL connector ID to use"},
        }

        return {
            "initialize_sql_connector": ToolParameterSchema(
                type="object",
                properties={
                    "connector_id": {"type": "string", "description": "Unique identifier for the connector"},
                    "connection_string": {
                        "type": "string",
                        "description": "Database connection string (e.g., sqlite:///path/to/db.db)",
                    },
                    "dialect": {"type": "string", "description": "SQL dialect: sqlite, postgres, mysql, mssql"},
                    "privacy_schema_path": {"type": "string", "description": "Path to privacy schema YAML file"},
                    "connection_timeout": {
                        "type": "integer",
                        "description": "Connection timeout in seconds (default: 30)",
                    },
                    "query_timeout": {"type": "integer", "description": "Query timeout in seconds (default: 60)"},
                    "max_retries": {"type": "integer", "description": "Maximum retry attempts (default: 3)"},
                },
                required=["connector_id", "connection_string", "dialect"],
            ),
            "get_sql_service_metadata": ToolParameterSchema(
                type="object",
                properties={
                    "connector_id": {"type": "string", "description": "Connector to get metadata for"},
                },
                required=["connector_id"],
            ),
            "sql_find_user_data": ToolParameterSchema(
                type="object",
                properties={
                    **base_props,
                    "user_identifier": {"type": "string", "description": "User identifier (email, user_id, etc.)"},
                    "identifier_type": {
                        "type": "string",
                        "description": "Type of identifier: email, user_id, phone, etc.",
                    },
                },
                required=["connector_id", "user_identifier", "identifier_type"],
            ),
            "sql_export_user": ToolParameterSchema(
                type="object",
                properties={
                    **base_props,
                    "user_identifier": {"type": "string", "description": "User identifier"},
                    "identifier_type": {"type": "string", "description": "Type of identifier"},
                    "export_format": {"type": "string", "description": "Export format: json or csv (default: json)"},
                },
                required=["connector_id", "user_identifier", "identifier_type"],
            ),
            "sql_delete_user": ToolParameterSchema(
                type="object",
                properties={
                    **base_props,
                    "user_identifier": {"type": "string", "description": "User identifier"},
                    "identifier_type": {"type": "string", "description": "Type of identifier"},
                    "soft_delete": {"type": "boolean", "description": "Use soft delete if available (default: false)"},
                },
                required=["connector_id", "user_identifier", "identifier_type"],
            ),
            "sql_anonymize_user": ToolParameterSchema(
                type="object",
                properties={
                    **base_props,
                    "user_identifier": {"type": "string", "description": "User identifier"},
                    "identifier_type": {"type": "string", "description": "Type of identifier"},
                },
                required=["connector_id", "user_identifier", "identifier_type"],
            ),
            "sql_verify_deletion": ToolParameterSchema(
                type="object",
                properties={
                    **base_props,
                    "user_identifier": {"type": "string", "description": "User identifier"},
                    "identifier_type": {"type": "string", "description": "Type of identifier"},
                },
                required=["connector_id", "user_identifier", "identifier_type"],
            ),
            "sql_get_stats": ToolParameterSchema(
                type="object",
                properties={**base_props},
                required=["connector_id"],
            ),
            "sql_query": ToolParameterSchema(
                type="object",
                properties={
                    **base_props,
                    "query": {"type": "string", "description": "SQL query to execute (SELECT only)"},
                    "parameters": {"type": "object", "description": "Query parameters for parameterized queries"},
                },
                required=["connector_id", "query"],
            ),
        }

    def _build_tool_info(self) -> Dict[str, ToolInfo]:
        """Build ToolInfo objects for all SQL tools.

        Uses generic SQL tool names. Connector ID is specified via parameter.
        """
        return {
            "initialize_sql_connector": ToolInfo(
                name="initialize_sql_connector",
                description="Initialize or reconfigure SQL connector with connection details and privacy schema",
                parameters=self._tool_schemas["initialize_sql_connector"],
                category="configuration",
            ),
            "get_sql_service_metadata": ToolInfo(
                name="get_sql_service_metadata",
                description="Get metadata about SQL connector including DSAR capabilities and table information",
                parameters=self._tool_schemas["get_sql_service_metadata"],
                category="metadata",
            ),
            "sql_find_user_data": ToolInfo(
                name="sql_find_user_data",
                description="Find all user data across configured SQL tables using privacy schema",
                parameters=self._tool_schemas["sql_find_user_data"],
                category="data_privacy",
            ),
            "sql_export_user": ToolInfo(
                name="sql_export_user",
                description="Export all user data in specified format (JSON or CSV)",
                parameters=self._tool_schemas["sql_export_user"],
                category="data_privacy",
            ),
            "sql_delete_user": ToolInfo(
                name="sql_delete_user",
                description="Delete all user data from configured SQL tables",
                parameters=self._tool_schemas["sql_delete_user"],
                category="data_privacy",
            ),
            "sql_anonymize_user": ToolInfo(
                name="sql_anonymize_user",
                description="Anonymize user PII using configured anonymization strategies",
                parameters=self._tool_schemas["sql_anonymize_user"],
                category="data_privacy",
            ),
            "sql_verify_deletion": ToolInfo(
                name="sql_verify_deletion",
                description="Verify that user data has been completely deleted",
                parameters=self._tool_schemas["sql_verify_deletion"],
                category="data_privacy",
            ),
            "sql_get_stats": ToolInfo(
                name="sql_get_stats",
                description="Get database statistics and table information",
                parameters=self._tool_schemas["sql_get_stats"],
                category="database",
            ),
            "sql_query": ToolInfo(
                name="sql_query",
                description="Execute a read-only SQL query (SELECT statements only)",
                parameters=self._tool_schemas["sql_query"],
                category="database",
            ),
        }

    # Additional ToolServiceProtocol Methods ------------------------------------
    async def get_tool_schema(self, tool_name: str) -> Optional[ToolParameterSchema]:
        """Get parameter schema for a specific tool."""
        return self._tool_schemas.get(tool_name)

    async def get_available_tools(self) -> List[str]:
        """Get list of all available tools (alias for list_tools)."""
        return await self.list_tools()

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed information about a specific tool."""
        return self._tool_info.get(tool_name)

    async def get_all_tool_info(self) -> List[ToolInfo]:
        """Get detailed information about all available tools."""
        return list(self._tool_info.values())

    async def validate_parameters(self, tool_name: str, parameters: JSONDict) -> bool:
        """Validate parameters for a specific tool without executing it."""
        schema = await self.get_tool_schema(tool_name)
        if not schema:
            return False

        # Check required parameters
        for required_param in schema.required:
            if required_param not in parameters:
                return False

        # Basic type validation could be added here
        return True

    async def get_tool_result(self, correlation_id: str, timeout: float = 30.0) -> Optional[ToolExecutionResult]:
        """Get the result of a previously executed tool by correlation ID."""
        return self._results.get(correlation_id)

    def get_service_metadata(self) -> Dict[str, Any]:
        """Return SQL data source metadata for DSAR coordination.

        Returns:
            Dict with data source metadata including:
            - data_source: True (this is a data source)
            - data_source_type: "sql"
            - contains_pii: True (configured via privacy schema)
            - gdpr_applicable: True
            - connector_id: Unique connector identifier
            - dialect: SQL dialect (sqlite, postgresql, mysql)
            - dsar_capabilities: List of DSAR operations supported
            - privacy_schema_configured: Whether privacy schema is loaded
            - table_count: Number of tables configured for privacy
        """
        # Determine DSAR capabilities
        dsar_capabilities = []
        if self._config and self._config.privacy_schema:
            dsar_capabilities.extend(
                [
                    "find_user_data",
                    "export_user",
                    "delete_user",
                    "anonymize_user",
                    "verify_deletion",
                ]
            )

        # Count configured privacy tables
        table_count = 0
        if self._config and self._config.privacy_schema:
            table_count = len(self._config.privacy_schema.tables)

        return {
            "data_source": True,
            "data_source_type": "sql",
            "contains_pii": True,  # SQL databases configured with privacy schema contain PII
            "gdpr_applicable": True,
            "connector_id": self._connector_id,
            "dialect": self._dialect.name if self._dialect else None,
            "dsar_capabilities": dsar_capabilities,
            "privacy_schema_configured": self._config is not None and self._config.privacy_schema is not None,
            "table_count": table_count,
        }

    async def shutdown(self) -> None:
        """Shutdown service and close database connection."""
        if self._engine:
            self._engine.dispose()
            self._logger.info("Database connection closed")
        # Note: BaseService doesn't have shutdown(), but this is required by framework
        # await super().shutdown()  # Skip if not implemented
