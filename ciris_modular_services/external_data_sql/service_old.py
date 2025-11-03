"""SQL Tool Service for external data access."""

import hashlib
import json
import time
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from ciris_engine.logic.services.base_service import BaseService
from ciris_engine.protocols.services import TimeServiceProtocol, ToolService
from ciris_engine.schemas.adapters.tools import ToolExecutionResult
from ciris_engine.schemas.types import JSONDict

from .schemas import (
    DataLocation,
    SQLAnonymizationResult,
    SQLConnectorConfig,
    SQLDeletionResult,
    SQLDialect,
    SQLExportResult,
    SQLQueryResult,
    SQLStatsResult,
    SQLVerificationResult,
)


class SQLToolService(BaseService, ToolService):
    """Tool service for SQL database access and DSAR automation.

    Provides dialect-aware SQL operations for SQLite, MySQL, and PostgreSQL.
    Follows organic architecture: external data sources as tools.
    """

    def __init__(
        self,
        time_service: TimeServiceProtocol,
        config: Optional[SQLConnectorConfig] = None,
    ):
        """Initialize SQL tool service.

        Args:
            time_service: Time service for timestamps
            config: Optional connector configuration
        """
        super().__init__(time_service=time_service, service_name="SQLToolService")
        self._config = config
        self._engine: Optional[Engine] = None
        self._connector_id = config.connector_id if config else "sql"

    async def initialize(self) -> None:
        """Initialize the service and database connection."""
        await super().initialize()
        if self._config:
            await self._connect()

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
            self.log_info(f"Connected to {self._config.dialect} database: {self._connector_id}")
        except SQLAlchemyError as e:
            self.log_error(f"Failed to connect to database: {e}")
            raise

    async def list_tools(self) -> List[str]:
        """List available SQL tools.

        Returns:
            List of tool names prefixed with connector ID
        """
        prefix = self._connector_id
        return [
            f"{prefix}_find_user_data",
            f"{prefix}_export_user",
            f"{prefix}_delete_user",
            f"{prefix}_anonymize_user",
            f"{prefix}_verify_deletion",
            f"{prefix}_get_stats",
            f"{prefix}_query",
        ]

    async def execute_tool(self, tool_name: str, parameters: JSONDict) -> ToolExecutionResult:
        """Execute SQL tool.

        Args:
            tool_name: Tool name (with connector prefix)
            parameters: Tool parameters

        Returns:
            Tool execution result
        """
        # Strip connector prefix
        prefix = f"{self._connector_id}_"
        if not tool_name.startswith(prefix):
            return ToolExecutionResult(
                success=False,
                result={},
                error=f"Tool {tool_name} does not belong to connector {self._connector_id}",
            )

        method_name = tool_name[len(prefix) :]

        # Route to appropriate method
        if method_name == "find_user_data":
            return await self._find_user_data(parameters)
        elif method_name == "export_user":
            return await self._export_user(parameters)
        elif method_name == "delete_user":
            return await self._delete_user(parameters)
        elif method_name == "anonymize_user":
            return await self._anonymize_user(parameters)
        elif method_name == "verify_deletion":
            return await self._verify_deletion(parameters)
        elif method_name == "get_stats":
            return await self._get_stats(parameters)
        elif method_name == "query":
            return await self._query(parameters)
        else:
            return ToolExecutionResult(success=False, result={}, error=f"Unknown tool: {method_name}")

    async def _find_user_data(self, parameters: JSONDict) -> ToolExecutionResult:
        """Find all locations where user data exists."""
        if not self._engine or not self._config:
            return ToolExecutionResult(success=False, result={}, error="Database not configured")

        user_identifier = parameters.get("user_identifier")
        if not user_identifier:
            return ToolExecutionResult(success=False, result={}, error="user_identifier required")

        locations: List[DataLocation] = []

        try:
            with self._engine.connect() as conn:
                for table_mapping in self._config.privacy_schema.tables:
                    table_name = table_mapping.table_name
                    identifier_col = table_mapping.identifier_column

                    # Count rows for this user
                    query = text(f"SELECT COUNT(*) as cnt FROM {table_name} WHERE {identifier_col} = :user_id")
                    result = conn.execute(query, {"user_id": user_identifier})
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
                success=True,
                result={"locations": [loc.model_dump() for loc in locations]},
            )
        except SQLAlchemyError as e:
            return ToolExecutionResult(success=False, result={}, error=f"Database error: {e}")

    async def _export_user(self, parameters: JSONDict) -> ToolExecutionResult:
        """Export all user data."""
        if not self._engine or not self._config:
            return ToolExecutionResult(success=False, result={}, error="Database not configured")

        user_identifier = parameters.get("user_identifier")
        export_format = parameters.get("export_format", "json")

        if not user_identifier:
            return ToolExecutionResult(success=False, result={}, error="user_identifier required")

        data: Dict[str, List[Dict[str, Any]]] = {}
        total_rows = 0

        try:
            with self._engine.connect() as conn:
                for table_mapping in self._config.privacy_schema.tables:
                    table_name = table_mapping.table_name
                    identifier_col = table_mapping.identifier_column

                    # Export all columns for this user
                    query = text(f"SELECT * FROM {table_name} WHERE {identifier_col} = :user_id")
                    result = conn.execute(query, {"user_id": user_identifier})

                    rows = []
                    for row in result:
                        rows.append(dict(row._mapping))

                    if rows:
                        data[table_name] = rows
                        total_rows += len(rows)

            # Generate checksum
            data_json = json.dumps(data, sort_keys=True)
            checksum = hashlib.sha256(data_json.encode()).hexdigest()

            result = SQLExportResult(
                success=True,
                user_identifier=user_identifier,
                tables_exported=list(data.keys()),
                total_rows=total_rows,
                data=data,
                export_format=export_format,
                checksum=checksum,
            )

            return ToolExecutionResult(success=True, result=result.model_dump())
        except SQLAlchemyError as e:
            return ToolExecutionResult(success=False, result={}, error=f"Database error: {e}")

    async def _delete_user(self, parameters: JSONDict) -> ToolExecutionResult:
        """Delete all user data."""
        if not self._engine or not self._config:
            return ToolExecutionResult(success=False, result={}, error="Database not configured")

        user_identifier = parameters.get("user_identifier")
        verify = parameters.get("verify", True)

        if not user_identifier:
            return ToolExecutionResult(success=False, result={}, error="user_identifier required")

        tables_affected: List[str] = []
        total_rows_deleted = 0
        cascade_deletions: Dict[str, int] = {}

        try:
            with self._engine.begin() as conn:  # Transaction
                for table_mapping in self._config.privacy_schema.tables:
                    table_name = table_mapping.table_name
                    identifier_col = table_mapping.identifier_column

                    # Delete from main table
                    query = text(f"DELETE FROM {table_name} WHERE {identifier_col} = :user_id")
                    result = conn.execute(query, {"user_id": user_identifier})
                    rows_deleted = result.rowcount

                    if rows_deleted > 0:
                        tables_affected.append(table_name)
                        total_rows_deleted += rows_deleted

                    # Cascade deletions
                    for cascade_table in table_mapping.cascade_deletes:
                        cascade_query = text(f"DELETE FROM {cascade_table} WHERE {identifier_col} = :user_id")
                        cascade_result = conn.execute(cascade_query, {"user_id": user_identifier})
                        cascade_count = cascade_result.rowcount
                        if cascade_count > 0:
                            cascade_deletions[cascade_table] = cascade_count
                            total_rows_deleted += cascade_count

            # Verify deletion if requested
            verification_passed = False
            if verify:
                verify_result = await self._verify_deletion({"user_identifier": user_identifier, "sign": False})
                verification_passed = verify_result.result.get("zero_data_confirmed", False)

            result = SQLDeletionResult(
                success=True,
                user_identifier=user_identifier,
                tables_affected=tables_affected,
                total_rows_deleted=total_rows_deleted,
                cascade_deletions=cascade_deletions,
                verification_passed=verification_passed,
            )

            return ToolExecutionResult(success=True, result=result.model_dump())
        except SQLAlchemyError as e:
            return ToolExecutionResult(success=False, result={}, error=f"Database error: {e}")

    async def _anonymize_user(self, parameters: JSONDict) -> ToolExecutionResult:
        """Anonymize user data instead of deleting."""
        if not self._engine or not self._config:
            return ToolExecutionResult(success=False, result={}, error="Database not configured")

        user_identifier = parameters.get("user_identifier")
        strategy = parameters.get("strategy", "pseudonymize")

        if not user_identifier:
            return ToolExecutionResult(success=False, result={}, error="user_identifier required")

        tables_affected: List[str] = []
        columns_anonymized: Dict[str, List[str]] = {}
        total_rows_affected = 0

        try:
            with self._engine.begin() as conn:  # Transaction
                for table_mapping in self._config.privacy_schema.tables:
                    table_name = table_mapping.table_name
                    identifier_col = table_mapping.identifier_column
                    cols_to_anonymize = []

                    # Build anonymization query
                    updates = []
                    for col_mapping in table_mapping.columns:
                        col_name = col_mapping.column_name
                        anon_strategy = col_mapping.anonymization_strategy

                        if anon_strategy == "delete":
                            continue  # Skip deletion columns
                        elif anon_strategy == "null":
                            updates.append(f"{col_name} = NULL")
                        elif anon_strategy == "hash":
                            # Dialect-aware hash
                            if self._config.dialect == SQLDialect.POSTGRESQL:
                                updates.append(f"{col_name} = md5({col_name})")
                            else:
                                # SQLite doesn't have md5, use placeholder
                                updates.append(f"{col_name} = 'ANONYMIZED'")
                        elif anon_strategy == "pseudonymize":
                            # Generate pseudonym
                            pseudonym = hashlib.sha256(f"{user_identifier}_{col_name}".encode()).hexdigest()[:16]
                            updates.append(f"{col_name} = '{pseudonym}'")
                        elif anon_strategy == "truncate":
                            # Keep first 3 characters
                            updates.append(f"{col_name} = SUBSTR({col_name}, 1, 3) || '***'")

                        cols_to_anonymize.append(col_name)

                    if updates:
                        update_clause = ", ".join(updates)
                        query = text(f"UPDATE {table_name} SET {update_clause} WHERE {identifier_col} = :user_id")
                        result = conn.execute(query, {"user_id": user_identifier})
                        rows_affected = result.rowcount

                        if rows_affected > 0:
                            tables_affected.append(table_name)
                            columns_anonymized[table_name] = cols_to_anonymize
                            total_rows_affected += rows_affected

            result = SQLAnonymizationResult(
                success=True,
                user_identifier=user_identifier,
                tables_affected=tables_affected,
                columns_anonymized=columns_anonymized,
                total_rows_affected=total_rows_affected,
                anonymization_strategy=strategy,
            )

            return ToolExecutionResult(success=True, result=result.model_dump())
        except SQLAlchemyError as e:
            return ToolExecutionResult(success=False, result={}, error=f"Database error: {e}")

    async def _verify_deletion(self, parameters: JSONDict) -> ToolExecutionResult:
        """Verify that user data has been completely deleted."""
        if not self._engine or not self._config:
            return ToolExecutionResult(success=False, result={}, error="Database not configured")

        user_identifier = parameters.get("user_identifier")
        sign = parameters.get("sign", True)

        if not user_identifier:
            return ToolExecutionResult(success=False, result={}, error="user_identifier required")

        tables_scanned: List[str] = []
        remaining_data: Dict[str, int] = {}

        try:
            with self._engine.connect() as conn:
                for table_mapping in self._config.privacy_schema.tables:
                    table_name = table_mapping.table_name
                    identifier_col = table_mapping.identifier_column

                    # Count remaining rows
                    query = text(f"SELECT COUNT(*) as cnt FROM {table_name} WHERE {identifier_col} = :user_id")
                    result = conn.execute(query, {"user_id": user_identifier})
                    row_count = result.scalar()

                    tables_scanned.append(table_name)
                    if row_count and row_count > 0:
                        remaining_data[table_name] = row_count

            zero_data_confirmed = len(remaining_data) == 0
            timestamp = self._time_service.get_utc_timestamp_str()

            # TODO: Generate Ed25519 signature via AuditService
            cryptographic_proof = None
            if sign and zero_data_confirmed:
                # This would call AuditService to sign the verification
                proof_data = {
                    "user_identifier": user_identifier,
                    "timestamp": timestamp,
                    "zero_data_confirmed": True,
                }
                # cryptographic_proof = await audit_service.sign_proof(proof_data)
                cryptographic_proof = "TODO:Ed25519_signature"

            result = SQLVerificationResult(
                success=True,
                user_identifier=user_identifier,
                zero_data_confirmed=zero_data_confirmed,
                tables_scanned=tables_scanned,
                remaining_data=remaining_data,
                verification_timestamp=timestamp,
                cryptographic_proof=cryptographic_proof,
            )

            return ToolExecutionResult(success=True, result=result.model_dump())
        except SQLAlchemyError as e:
            return ToolExecutionResult(success=False, result={}, error=f"Database error: {e}")

    async def _get_stats(self, parameters: JSONDict) -> ToolExecutionResult:
        """Get database statistics."""
        if not self._engine or not self._config:
            return ToolExecutionResult(success=False, result={}, error="Database not configured")

        tables: Dict[str, int] = {}
        total_rows = 0

        try:
            with self._engine.connect() as conn:
                # Get row counts for all privacy tables
                for table_mapping in self._config.privacy_schema.tables:
                    table_name = table_mapping.table_name
                    query = text(f"SELECT COUNT(*) as cnt FROM {table_name}")
                    result = conn.execute(query)
                    row_count = result.scalar()

                    tables[table_name] = row_count or 0
                    total_rows += row_count or 0

            result = SQLStatsResult(
                success=True,
                total_tables=len(tables),
                total_rows=total_rows,
                tables=tables,
            )

            return ToolExecutionResult(success=True, result=result.model_dump())
        except SQLAlchemyError as e:
            return ToolExecutionResult(success=False, result={}, error=f"Database error: {e}")

    async def _query(self, parameters: JSONDict) -> ToolExecutionResult:
        """Execute raw SQL query (with privacy constraints)."""
        if not self._engine:
            return ToolExecutionResult(success=False, result={}, error="Database not configured")

        sql = parameters.get("sql")
        query_params = parameters.get("parameters", {})

        if not sql:
            return ToolExecutionResult(success=False, result={}, error="sql required")

        # TODO: Add privacy constraints - only allow queries on configured tables
        # For now, allow any query (dangerous - needs WA approval)

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

                return ToolExecutionResult(success=True, result=query_result.model_dump())
        except SQLAlchemyError as e:
            return ToolExecutionResult(success=False, result={}, error=f"Database error: {e}")

    async def shutdown(self) -> None:
        """Shutdown service and close database connection."""
        if self._engine:
            self._engine.dispose()
            self.log_info("Database connection closed")
        await super().shutdown()
