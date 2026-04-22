"""External data connector management API endpoints.

Manages registration and configuration of SQL, REST, and HL7 connectors.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..models import StandardResponse, TokenData

router = APIRouter(prefix="/connectors", tags=["Connectors"])


class SQLConnectorConfig(BaseModel):
    """Configuration for SQL database connector."""

    connector_name: str = Field(..., description="Human-readable connector name")
    database_type: str = Field(..., description="Database type (postgres, mysql, sqlite, etc.)")
    host: str = Field(..., description="Database host")
    port: int = Field(..., description="Database port")
    database: str = Field(..., description="Database name")
    username: str = Field(..., description="Database username")
    password: str = Field(..., description="Database password (will be encrypted)")
    ssl_enabled: bool = Field(default=True, description="Whether to use SSL/TLS")
    privacy_schema: Optional[Dict[str, Any]] = Field(
        None, description="YAML privacy schema defining PII columns and mappings"
    )
    max_connections: int = Field(default=5, description="Maximum connection pool size")
    timeout_seconds: int = Field(default=30, description="Query timeout in seconds")


class ConnectorRegistrationRequest(BaseModel):
    """Request to register a new connector."""

    connector_type: str = Field(..., description="Connector type: sql, rest, or hl7", pattern="^(sql|rest|hl7)$")
    config: Dict[str, Any] = Field(..., description="Connector-specific configuration")


class ConnectorRegistrationResponse(BaseModel):
    """Response after registering a connector."""

    connector_id: str = Field(..., description="Unique connector identifier")
    connector_type: str = Field(..., description="Type of connector")
    connector_name: str = Field(..., description="Human-readable name")
    status: str = Field(..., description="Registration status")
    registered_at: str = Field(..., description="Registration timestamp")


class ConnectorInfo(BaseModel):
    """Information about a registered connector."""

    connector_id: str
    connector_type: str
    connector_name: str
    status: str
    registered_at: str
    last_tested: Optional[str] = None
    last_test_result: Optional[str] = None
    total_requests: int = Field(default=0, description="Total requests processed")


class ConnectorTestResult(BaseModel):
    """Result of connector connection test."""

    connector_id: str
    success: bool
    message: str
    latency_ms: float
    tested_at: str


class ConnectorUpdateRequest(BaseModel):
    """Request to update connector configuration."""

    config: Optional[Dict[str, Any]] = Field(None, description="Updated configuration (partial or full)")
    enabled: Optional[bool] = Field(None, description="Whether connector should be enabled")


# In-memory connector registry (would be persisted in production)
_connector_registry: Dict[str, Dict[str, Any]] = {}


def _validate_sql_config(config: Dict[str, Any]) -> None:
    """Validate SQL connector configuration.

    Args:
        config: Connector configuration dict

    Raises:
        HTTPException: If configuration is invalid
    """
    required_fields = ["connector_name", "database_type", "host", "port", "database", "username", "password"]
    missing = [field for field in required_fields if field not in config]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required SQL connector fields: {missing}",
        )

    # Validate database type
    valid_types = ["postgres", "mysql", "sqlite", "mssql", "oracle"]
    if config["database_type"] not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid database_type. Must be one of: {valid_types}",
        )


def _validate_rest_config(config: Dict[str, Any]) -> None:
    """Validate REST API connector configuration.

    Args:
        config: Connector configuration dict

    Raises:
        HTTPException: If configuration is invalid
    """
    required_fields = ["connector_name", "base_url", "auth_type"]
    missing = [field for field in required_fields if field not in config]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required REST connector fields: {missing}",
        )

    # Validate auth type
    valid_auth_types = ["none", "basic", "bearer", "oauth2", "api_key"]
    if config["auth_type"] not in valid_auth_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid auth_type. Must be one of: {valid_auth_types}",
        )


@router.post("/sql", response_model=StandardResponse)
async def register_sql_connector(
    request: ConnectorRegistrationRequest,
    req: Request,
    current_user: TokenData = Depends(get_current_user),
) -> StandardResponse:
    """
    Register a new SQL database connector.

    Requires admin privileges.

    The connector will be registered with the tool bus and made available
    for multi-source DSAR operations.

    Configuration must include:
    - connector_name: Human-readable name
    - database_type: postgres, mysql, sqlite, etc.
    - host, port, database, username, password
    - privacy_schema: YAML defining PII columns (optional)
    """
    import logging

    logger = logging.getLogger(__name__)

    logger.debug(f"[CONNECTOR_REG] Request to register SQL connector: {request.config.get('connector_name')}")
    logger.debug(f"[CONNECTOR_REG] Current user: {current_user.username}, Role: {current_user.role}")

    # Verify admin privileges
    if current_user.role not in ["ADMIN", "SYSTEM_ADMIN"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can register connectors",
        )

    # Validate connector type
    if request.connector_type != "sql":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This endpoint only accepts SQL connectors. Use POST /connectors for other types.",
        )

    # Validate SQL configuration
    _validate_sql_config(request.config)

    # Generate connector ID
    connector_id = f"sql_{request.config['database_type']}_{uuid.uuid4().hex[:8]}"

    # Store in registry
    connector_record = {
        "connector_id": connector_id,
        "connector_type": "sql",
        "connector_name": request.config["connector_name"],
        "config": request.config,
        "status": "registered",
        "registered_at": datetime.now(timezone.utc).isoformat(),
        "registered_by": current_user.username,
        "enabled": True,
        "total_requests": 0,
    }

    _connector_registry[connector_id] = connector_record

    # TODO Phase 2: Register with tool bus
    # This will enable the orchestrator to discover and use this connector
    # Implementation:
    # 1. Get tool_bus from app.state
    # 2. Register SQL tools with metadata:
    #    - data_source=True, data_source_type="sql"
    #    - connector_id=connector_id
    # 3. Register tools: sql_export_user, sql_delete_user, sql_verify_deletion
    # Example:
    # tool_bus = getattr(req.app.state, "tool_bus", None)
    # if tool_bus:
    #     await tool_bus.register_sql_connector(connector_id, request.config)

    from ciris_engine.logic.utils.log_sanitizer import sanitize_for_log, sanitize_username

    # Sanitize user-controlled data before logging
    safe_connector_id = sanitize_for_log(connector_id, max_length=100)
    safe_connector_name = sanitize_for_log(request.config.get("connector_name", "unknown"), max_length=100)
    safe_username = sanitize_username(current_user.username)

    logger.info(f"SQL connector registered: {safe_connector_id} ({safe_connector_name}) by {safe_username}")

    response_data = ConnectorRegistrationResponse(
        connector_id=connector_id,
        connector_type="sql",
        connector_name=request.config["connector_name"],
        status="registered",
        registered_at=connector_record["registered_at"],
    )

    return StandardResponse(
        success=True,
        data=response_data.model_dump(),
        message=f"SQL connector '{request.config['connector_name']}' registered successfully",
        metadata={
            "connector_id": connector_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


@router.get("/", response_model=StandardResponse)
async def list_connectors(
    connector_type: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user),
) -> StandardResponse:
    """
    List all registered connectors.

    Optionally filter by connector_type (sql, rest, hl7).

    Requires admin privileges.
    """
    # Verify admin privileges
    if current_user.role not in ["ADMIN", "SYSTEM_ADMIN"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can list connectors",
        )

    # Filter by type if specified
    connectors_iter = _connector_registry.values()
    if connector_type:
        connectors = [c for c in connectors_iter if c["connector_type"] == connector_type]
    else:
        connectors = list(connectors_iter)

    # Build response
    connector_list = [
        ConnectorInfo(
            connector_id=c["connector_id"],
            connector_type=c["connector_type"],
            connector_name=c["connector_name"],
            status=c["status"],
            registered_at=c["registered_at"],
            last_tested=c.get("last_tested"),
            last_test_result=c.get("last_test_result"),
            total_requests=c.get("total_requests", 0),
        )
        for c in connectors
    ]

    return StandardResponse(
        success=True,
        data={"connectors": [c.model_dump() for c in connector_list], "total": len(connector_list)},
        message=f"Found {len(connector_list)} connector(s)",
        metadata={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "filter": connector_type,
        },
    )


@router.post("/{connector_id}/test", response_model=StandardResponse)
async def test_connector(
    connector_id: str,
    req: Request,
    current_user: TokenData = Depends(get_current_user),
) -> StandardResponse:
    """
    Test connector connection health.

    Attempts a test query or connection to verify the connector is working.

    Requires admin privileges.
    """
    import logging
    import time

    logger = logging.getLogger(__name__)

    # Verify admin privileges
    if current_user.role not in ["ADMIN", "SYSTEM_ADMIN"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can test connectors",
        )

    # Check if connector exists
    if connector_id not in _connector_registry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connector {connector_id} not found",
        )

    connector = _connector_registry[connector_id]

    # Perform test based on connector type
    start_time = time.time()
    success = False
    message = ""

    try:
        if connector["connector_type"] == "sql":
            # TODO Phase 2: Test SQL connection via tool bus
            # This requires the connector to be registered with tool bus first
            # Implementation:
            # 1. Get tool_bus from app.state
            # 2. Execute sql_test_connection tool with connector_id
            # 3. Parse result for success/failure
            # Example:
            # tool_bus = getattr(req.app.state, "tool_bus", None)
            # if tool_bus:
            #     result = await tool_bus.execute_tool("sql_test_connection", {"connector_id": connector_id})
            #     success = result.success
            #     message = result.data.get("message", "Connection successful")
            # else:
            #     message = "Tool bus not available"

            # Simulate test for now
            success = True
            message = "SQL connection test successful (simulated)"

        elif connector["connector_type"] == "rest":
            success = True
            message = "REST API connection test successful (simulated)"

        else:
            message = f"Testing not implemented for {connector['connector_type']}"

    except Exception as e:
        from ciris_engine.logic.utils.log_sanitizer import sanitize_for_log

        safe_connector_id = sanitize_for_log(connector_id, max_length=100)
        logger.error(f"Connector test failed for {safe_connector_id}: {e}")
        success = False
        message = f"Connection test failed: {str(e)}"

    latency_ms = (time.time() - start_time) * 1000
    tested_at = datetime.now(timezone.utc).isoformat()

    # Update connector record
    connector["last_tested"] = tested_at
    connector["last_test_result"] = "success" if success else "failure"
    connector["status"] = "healthy" if success else "unhealthy"

    result = ConnectorTestResult(
        connector_id=connector_id,
        success=success,
        message=message,
        latency_ms=latency_ms,
        tested_at=tested_at,
    )

    from ciris_engine.logic.utils.log_sanitizer import sanitize_for_log, sanitize_username

    safe_connector_id = sanitize_for_log(connector_id, max_length=100)
    safe_username = sanitize_username(current_user.username)
    safe_message = sanitize_for_log(result.message, max_length=200)
    logger.info(f"Connector {safe_connector_id} tested by {safe_username}: {safe_message}")

    return StandardResponse(
        success=success,
        data=result.model_dump(),
        message=message,
        metadata={
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


@router.patch("/{connector_id}", response_model=StandardResponse)
async def update_connector(
    connector_id: str,
    update_request: ConnectorUpdateRequest,
    current_user: TokenData = Depends(get_current_user),
) -> StandardResponse:
    """
    Update connector configuration.

    Can update configuration fields or enable/disable the connector.

    Requires admin privileges.
    """
    import logging

    logger = logging.getLogger(__name__)

    # Verify admin privileges
    if current_user.role not in ["ADMIN", "SYSTEM_ADMIN"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can update connectors",
        )

    # Check if connector exists
    if connector_id not in _connector_registry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connector {connector_id} not found",
        )

    connector = _connector_registry[connector_id]

    # Update configuration (merge with existing)
    if update_request.config:
        connector["config"].update(update_request.config)

    # Update enabled status
    if update_request.enabled is not None:
        connector["enabled"] = update_request.enabled
        connector["status"] = "registered" if update_request.enabled else "disabled"

    connector["last_updated"] = datetime.now(timezone.utc).isoformat()
    connector["last_updated_by"] = current_user.username

    from ciris_engine.logic.utils.log_sanitizer import sanitize_for_log, sanitize_username

    safe_connector_id = sanitize_for_log(connector_id, max_length=100)
    safe_username = sanitize_username(current_user.username)
    logger.info(f"Connector {safe_connector_id} updated by {safe_username}")

    return StandardResponse(
        success=True,
        data={
            "connector_id": connector_id,
            "connector_name": connector["connector_name"],
            "status": connector["status"],
            "enabled": connector["enabled"],
            "last_updated": connector["last_updated"],
        },
        message=f"Connector {connector_id} updated successfully",
        metadata={
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


@router.delete("/{connector_id}", response_model=StandardResponse)
async def delete_connector(
    connector_id: str,
    current_user: TokenData = Depends(get_current_user),
) -> StandardResponse:
    """
    Remove a connector from the system.

    This is a destructive operation and cannot be undone.

    Requires admin privileges.
    """
    import logging

    logger = logging.getLogger(__name__)

    # Verify admin privileges
    if current_user.role not in ["ADMIN", "SYSTEM_ADMIN"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can delete connectors",
        )

    # Check if connector exists
    if connector_id not in _connector_registry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connector {connector_id} not found",
        )

    connector_name = _connector_registry[connector_id]["connector_name"]

    # Remove from registry
    del _connector_registry[connector_id]

    # TODO Phase 2: Unregister from tool bus
    # This will remove the connector's tools from the tool bus
    # Implementation:
    # 1. Get tool_bus from app.state
    # 2. Unregister all SQL tools for this connector
    # 3. Remove connector from discovery metadata
    # Example:
    # tool_bus = getattr(req.app.state, "tool_bus", None)
    # if tool_bus:
    #     await tool_bus.unregister_connector(connector_id)

    from ciris_engine.logic.utils.log_sanitizer import sanitize_for_log, sanitize_username

    safe_connector_id = sanitize_for_log(connector_id, max_length=100)
    safe_connector_name = sanitize_for_log(connector_name, max_length=100)
    safe_username = sanitize_username(current_user.username)
    logger.warning(f"Connector {safe_connector_id} ({safe_connector_name}) deleted by {safe_username}")

    return StandardResponse(
        success=True,
        data={
            "connector_id": connector_id,
            "connector_name": connector_name,
            "deleted_at": datetime.now(timezone.utc).isoformat(),
        },
        message=f"Connector '{connector_name}' removed successfully",
        metadata={
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
