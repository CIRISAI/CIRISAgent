"""
Telemetry Export Destinations CRUD endpoints.

Manages export destinations for sending telemetry data (metrics, traces, logs)
to external systems using OTLP, Prometheus, or Graphite formats.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from ciris_engine.schemas.api.responses import ResponseMetadata, SuccessResponse

from ._common import RESPONSES_400, RESPONSES_404_500_503, RESPONSES_500_503, AuthAdminDep

logger = logging.getLogger(__name__)

# Storage key for export destinations in config service
EXPORT_DESTINATIONS_KEY = "telemetry_export:destinations"

router = APIRouter(prefix="/telemetry/export", tags=["telemetry-export"])


# Schemas


class ExportFormat(str, Enum):
    """Supported export formats."""

    OTLP = "otlp"
    PROMETHEUS = "prometheus"
    GRAPHITE = "graphite"


class SignalType(str, Enum):
    """Telemetry signal types."""

    METRICS = "metrics"
    TRACES = "traces"
    LOGS = "logs"


class AuthType(str, Enum):
    """Authentication types for export destinations."""

    NONE = "none"
    BEARER = "bearer"
    BASIC = "basic"
    HEADER = "header"


class ExportDestinationCreate(BaseModel):
    """Request model for creating an export destination."""

    name: str = Field(..., min_length=1, max_length=64, description="Human-friendly name")
    endpoint: str = Field(..., description="Endpoint URL")
    format: ExportFormat = Field(..., description="Export format")
    signals: List[SignalType] = Field(default=[SignalType.METRICS], description="Signals to export")
    auth_type: AuthType = Field(default=AuthType.NONE, description="Authentication type")
    auth_value: Optional[str] = Field(None, description="Auth credential (token, user:pass, or header value)")
    auth_header: Optional[str] = Field(None, description="Custom header name for HEADER auth type")
    interval_seconds: int = Field(default=60, ge=10, le=3600, description="Push interval in seconds")
    enabled: bool = Field(default=True, description="Whether export is enabled")

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, v: str) -> str:
        """Validate endpoint URL format."""
        if not v.startswith(("http://", "https://")):
            raise ValueError("Endpoint must be a valid HTTP/HTTPS URL")
        return v


class ExportDestination(ExportDestinationCreate):
    """Full export destination with ID and timestamps."""

    id: str = Field(..., description="Unique destination ID")
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")


class ExportDestinationUpdate(BaseModel):
    """Request model for updating an export destination."""

    name: Optional[str] = Field(None, min_length=1, max_length=64)
    endpoint: Optional[str] = None
    format: Optional[ExportFormat] = None
    signals: Optional[List[SignalType]] = None
    auth_type: Optional[AuthType] = None
    auth_value: Optional[str] = None
    auth_header: Optional[str] = None
    interval_seconds: Optional[int] = Field(None, ge=10, le=3600)
    enabled: Optional[bool] = None

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, v: Optional[str]) -> Optional[str]:
        """Validate endpoint URL format."""
        if v is not None and not v.startswith(("http://", "https://")):
            raise ValueError("Endpoint must be a valid HTTP/HTTPS URL")
        return v


class TestResult(BaseModel):
    """Result of testing connectivity to a destination."""

    success: bool = Field(..., description="Whether the test succeeded")
    status_code: Optional[int] = Field(None, description="HTTP status code")
    message: str = Field(..., description="Result message")
    latency_ms: Optional[float] = Field(None, description="Round-trip latency")


class DestinationsListResponse(BaseModel):
    """Response model for listing destinations."""

    destinations: List[ExportDestination] = Field(..., description="List of export destinations")
    total: int = Field(..., description="Total count")


# Helper functions


async def _get_destinations(config_service: Any) -> List[Dict[str, Any]]:
    """Get all export destinations from config service."""
    if not config_service:
        return []

    config = await config_service.get_config(EXPORT_DESTINATIONS_KEY)
    if not config or not config.value:
        return []

    value = config.value.value
    if isinstance(value, list):
        return value
    elif isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return []
    return []


async def _save_destinations(config_service: Any, destinations: List[Dict[str, Any]]) -> None:
    """Save export destinations to config service."""
    if not config_service:
        raise HTTPException(status_code=503, detail="Config service not available")

    await config_service.set_config(EXPORT_DESTINATIONS_KEY, destinations, updated_by="telemetry_export_api")


def _find_destination(destinations: List[Dict[str, Any]], destination_id: str) -> Optional[Dict[str, Any]]:
    """Find a destination by ID."""
    for dest in destinations:
        if dest.get("id") == destination_id:
            return dest
    return None


def _sanitize_destination(dest: Dict[str, Any]) -> ExportDestination:
    """Convert raw dict to ExportDestination, redacting sensitive fields."""
    sanitized = dict(dest)
    # Redact auth_value for display
    if sanitized.get("auth_value"):
        sanitized["auth_value"] = "***REDACTED***"
    return ExportDestination(**sanitized)


# Endpoints


@router.get("/destinations", response_model=None, responses=RESPONSES_500_503)
async def list_destinations(request: Request, auth: AuthAdminDep) -> SuccessResponse[DestinationsListResponse]:
    """
    List all telemetry export destinations.

    Returns all configured export destinations with sensitive auth values redacted.
    """
    config_service = getattr(request.app.state, "config_service", None)
    if not config_service:
        raise HTTPException(status_code=503, detail="Config service not available")

    try:
        raw_destinations = await _get_destinations(config_service)
        destinations = [_sanitize_destination(d) for d in raw_destinations]

        return SuccessResponse(
            data=DestinationsListResponse(destinations=destinations, total=len(destinations)),
            metadata=ResponseMetadata(
                timestamp=datetime.now(timezone.utc), request_id=str(uuid.uuid4()), duration_ms=0
            ),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list export destinations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/destinations/{destination_id}", response_model=None, responses=RESPONSES_404_500_503)
async def get_destination(
    request: Request, auth: AuthAdminDep, destination_id: str
) -> SuccessResponse[ExportDestination]:
    """
    Get a specific export destination by ID.

    Returns the destination with sensitive auth values redacted.
    """
    config_service = getattr(request.app.state, "config_service", None)
    if not config_service:
        raise HTTPException(status_code=503, detail="Config service not available")

    try:
        destinations = await _get_destinations(config_service)
        dest = _find_destination(destinations, destination_id)

        if not dest:
            raise HTTPException(status_code=404, detail=f"Destination '{destination_id}' not found")

        return SuccessResponse(
            data=_sanitize_destination(dest),
            metadata=ResponseMetadata(
                timestamp=datetime.now(timezone.utc), request_id=str(uuid.uuid4()), duration_ms=0
            ),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get export destination: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/destinations", response_model=None, responses={**RESPONSES_400, **RESPONSES_500_503})
async def create_destination(
    request: Request, auth: AuthAdminDep, destination: ExportDestinationCreate
) -> SuccessResponse[ExportDestination]:
    """
    Create a new export destination.

    Creates a new telemetry export destination for sending metrics, traces,
    or logs to an external system.
    """
    config_service = getattr(request.app.state, "config_service", None)
    if not config_service:
        raise HTTPException(status_code=503, detail="Config service not available")

    try:
        destinations = await _get_destinations(config_service)

        # Check for duplicate name
        for existing in destinations:
            if existing.get("name") == destination.name:
                raise HTTPException(
                    status_code=400, detail=f"Destination with name '{destination.name}' already exists"
                )

        # Create new destination
        now = datetime.now(timezone.utc).isoformat()
        new_dest = {
            "id": str(uuid.uuid4())[:8],
            **destination.model_dump(),
            "created_at": now,
            "updated_at": None,
        }
        # Convert enums to strings for JSON storage
        new_dest["format"] = new_dest["format"].value
        new_dest["auth_type"] = new_dest["auth_type"].value
        new_dest["signals"] = [s.value for s in new_dest["signals"]]

        destinations.append(new_dest)
        await _save_destinations(config_service, destinations)

        logger.info(f"Created export destination: {new_dest['id']} ({new_dest['name']})")

        return SuccessResponse(
            data=_sanitize_destination(new_dest),
            metadata=ResponseMetadata(
                timestamp=datetime.now(timezone.utc), request_id=str(uuid.uuid4()), duration_ms=0
            ),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create export destination: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/destinations/{destination_id}", response_model=None, responses=RESPONSES_404_500_503)
async def update_destination(
    request: Request, auth: AuthAdminDep, destination_id: str, update: ExportDestinationUpdate
) -> SuccessResponse[ExportDestination]:
    """
    Update an existing export destination.

    Partial updates are supported - only provided fields will be updated.
    """
    config_service = getattr(request.app.state, "config_service", None)
    if not config_service:
        raise HTTPException(status_code=503, detail="Config service not available")

    try:
        destinations = await _get_destinations(config_service)
        dest_index = None
        for i, d in enumerate(destinations):
            if d.get("id") == destination_id:
                dest_index = i
                break

        if dest_index is None:
            raise HTTPException(status_code=404, detail=f"Destination '{destination_id}' not found")

        # Update fields
        dest = destinations[dest_index]
        update_data = update.model_dump(exclude_unset=True)

        # Convert enums to strings
        if "format" in update_data and update_data["format"]:
            update_data["format"] = update_data["format"].value
        if "auth_type" in update_data and update_data["auth_type"]:
            update_data["auth_type"] = update_data["auth_type"].value
        if "signals" in update_data and update_data["signals"]:
            update_data["signals"] = [s.value for s in update_data["signals"]]

        dest.update(update_data)
        dest["updated_at"] = datetime.now(timezone.utc).isoformat()

        await _save_destinations(config_service, destinations)

        logger.info(f"Updated export destination: {destination_id}")

        return SuccessResponse(
            data=_sanitize_destination(dest),
            metadata=ResponseMetadata(
                timestamp=datetime.now(timezone.utc), request_id=str(uuid.uuid4()), duration_ms=0
            ),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update export destination: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/destinations/{destination_id}", response_model=None, responses=RESPONSES_404_500_503)
async def delete_destination(
    request: Request, auth: AuthAdminDep, destination_id: str
) -> SuccessResponse[Dict[str, str]]:
    """
    Delete an export destination.

    Permanently removes the export destination. Active exports will stop immediately.
    """
    config_service = getattr(request.app.state, "config_service", None)
    if not config_service:
        raise HTTPException(status_code=503, detail="Config service not available")

    try:
        destinations = await _get_destinations(config_service)
        original_len = len(destinations)

        destinations = [d for d in destinations if d.get("id") != destination_id]

        if len(destinations) == original_len:
            raise HTTPException(status_code=404, detail=f"Destination '{destination_id}' not found")

        await _save_destinations(config_service, destinations)

        logger.info(f"Deleted export destination: {destination_id}")

        return SuccessResponse(
            data={"message": f"Destination '{destination_id}' deleted successfully"},
            metadata=ResponseMetadata(
                timestamp=datetime.now(timezone.utc), request_id=str(uuid.uuid4()), duration_ms=0
            ),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete export destination: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/destinations/{destination_id}/test", response_model=None, responses=RESPONSES_404_500_503)
async def test_destination(request: Request, auth: AuthAdminDep, destination_id: str) -> SuccessResponse[TestResult]:
    """
    Test connectivity to an export destination.

    Sends a test request to the destination's endpoint to verify connectivity
    and authentication. Does not actually export any data.
    """
    config_service = getattr(request.app.state, "config_service", None)
    if not config_service:
        raise HTTPException(status_code=503, detail="Config service not available")

    try:
        destinations = await _get_destinations(config_service)
        dest = _find_destination(destinations, destination_id)

        if not dest:
            raise HTTPException(status_code=404, detail=f"Destination '{destination_id}' not found")

        # Build request headers based on auth type
        headers: Dict[str, str] = {"User-Agent": "CIRIS-Telemetry-Exporter/1.0"}
        auth_type = dest.get("auth_type", "none")
        auth_value = dest.get("auth_value")

        if auth_type == "bearer" and auth_value:
            headers["Authorization"] = f"Bearer {auth_value}"
        elif auth_type == "basic" and auth_value:
            import base64

            encoded = base64.b64encode(auth_value.encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"
        elif auth_type == "header" and auth_value:
            header_name = dest.get("auth_header", "X-API-Key")
            headers[header_name] = auth_value

        # Test connectivity
        endpoint = dest.get("endpoint", "")
        start_time = datetime.now(timezone.utc)

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                # Use HEAD request if possible, fall back to GET
                response = await client.head(endpoint, headers=headers, follow_redirects=True)
                if response.status_code == 405:  # Method not allowed, try GET
                    response = await client.get(endpoint, headers=headers, follow_redirects=True)

                latency = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

                success = 200 <= response.status_code < 400
                result = TestResult(
                    success=success,
                    status_code=response.status_code,
                    message=f"Connection {'successful' if success else 'failed'} with status {response.status_code}",
                    latency_ms=round(latency, 2),
                )
            except httpx.TimeoutException:
                result = TestResult(success=False, status_code=None, message="Connection timed out", latency_ms=None)
            except httpx.ConnectError as e:
                result = TestResult(
                    success=False, status_code=None, message=f"Connection failed: {str(e)}", latency_ms=None
                )
            except Exception as e:
                result = TestResult(success=False, status_code=None, message=f"Error: {str(e)}", latency_ms=None)

        return SuccessResponse(
            data=result,
            metadata=ResponseMetadata(
                timestamp=datetime.now(timezone.utc), request_id=str(uuid.uuid4()), duration_ms=0
            ),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to test export destination: {e}")
        raise HTTPException(status_code=500, detail=str(e))
