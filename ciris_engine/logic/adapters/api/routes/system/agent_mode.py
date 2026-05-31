"""
AgentMode endpoints — GET/PUT for the global agent mode.

GET /v1/system/agent-mode — OBSERVER+ can read.
PUT /v1/system/agent-mode — SYSTEM_ADMIN only. Switching to SERVER while the
data dir has < 256 GiB free returns 400 with structured error JSON.
"""

from __future__ import annotations

import logging
import shutil
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.responses import JSONResponse

from ciris_engine.constants import SERVER_MINIMUM_DISK_BYTES
from ciris_engine.logic.utils.agent_mode_broker import get_agent_mode_broker
from ciris_engine.schemas.api.responses import SuccessResponse
from ciris_engine.schemas.runtime.agent_mode import AgentMode, AgentModeStatus, AgentModeUpdateRequest

from ...dependencies.auth import AuthContext, require_observer, require_system_admin

logger = logging.getLogger(__name__)

AuthObserverDep = Annotated[AuthContext, Depends(require_observer)]
AuthSystemAdminDep = Annotated[AuthContext, Depends(require_system_admin)]

router = APIRouter()


def _resolve_data_dir() -> str:
    """Return a stringified data directory path for disk measurement."""
    try:
        from ciris_engine.logic.utils.path_resolution import get_data_dir

        return str(get_data_dir())
    except Exception:
        return "."


def _measure_disk(resource_monitor: Optional[Any], data_dir: str) -> tuple[int, bool]:
    """Return ``(available_bytes, server_eligible)`` for the data dir.

    Routes through the resource monitor when it exposes the new disk-gating
    methods (the production path) and falls back to ``shutil.disk_usage``
    for degraded boots and unit-test apps without a monitor wired in.
    """
    if resource_monitor is not None and hasattr(resource_monitor, "get_available_disk_bytes"):
        available = int(resource_monitor.get_available_disk_bytes())
        eligible = bool(resource_monitor.is_server_mode_eligible())
        return available, eligible

    try:
        available = int(shutil.disk_usage(data_dir).free)
    except (OSError, ValueError):
        available = 0
    return available, available >= SERVER_MINIMUM_DISK_BYTES


def _build_status(request: Request) -> AgentModeStatus:
    """Assemble an ``AgentModeStatus`` snapshot from current runtime state."""
    broker = get_agent_mode_broker()
    resource_monitor: Optional[Any] = getattr(request.app.state, "resource_monitor", None)
    data_dir = _resolve_data_dir()
    available, eligible = _measure_disk(resource_monitor, data_dir)

    return AgentModeStatus(
        mode=broker.current_mode(),
        available_disk_bytes=available,
        server_minimum_disk_bytes=SERVER_MINIMUM_DISK_BYTES,
        server_eligible=eligible,
        data_dir=data_dir,
    )


@router.get("/agent-mode")
async def get_agent_mode(
    request: Request,
    auth: AuthObserverDep,
) -> SuccessResponse[AgentModeStatus]:
    """Return the current ``AgentMode`` plus the disk facts that gate SERVER."""
    return SuccessResponse(data=_build_status(request))


@router.put(
    "/agent-mode",
    responses={
        400: {"description": "Cannot switch to SERVER without sufficient free disk"},
    },
)
async def put_agent_mode(
    request: Request,
    payload: AgentModeUpdateRequest,
    auth: AuthSystemAdminDep,
) -> JSONResponse:
    """Switch global ``AgentMode``.

    Returns a wrapped ``AgentModeStatus`` with a ``requires_restart`` flag.
    Currently ``requires_restart`` is always true because the Edge runtime
    needs a restart to pick up the new mode.

    On insufficient disk for SERVER mode, returns 400 with:
        {"error": "INSUFFICIENT_DISK", "available_bytes": N, "required_bytes": N}
    """
    target_mode = payload.mode
    broker = get_agent_mode_broker()
    resource_monitor: Optional[Any] = getattr(request.app.state, "resource_monitor", None)

    # Gate SERVER on free disk.
    if target_mode is AgentMode.SERVER:
        available, _ = _measure_disk(resource_monitor, _resolve_data_dir())
        if available < SERVER_MINIMUM_DISK_BYTES:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "INSUFFICIENT_DISK",
                    "available_bytes": available,
                    "required_bytes": SERVER_MINIMUM_DISK_BYTES,
                },
            )

    # Attach the runtime's GraphConfigService to the broker (idempotent)
    # so set_mode actually persists. Without this, the in-memory transition
    # works but the next boot re-seeds the broker from EssentialConfig and
    # Edge reads the OLD mode (CIRISAgent#841 review — Codex P1).
    # The broker's `attach_config_service` is a single-attribute set under
    # the broker's lock; safe to call on every PUT.
    config_service = getattr(request.app.state, "config_service", None)
    if config_service is not None:
        broker.attach_config_service(config_service)

    # Perform the transition (persists + broadcasts).
    try:
        await broker.set_mode(target_mode)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("AgentMode transition failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to set agent mode: {exc}")

    status = _build_status(request)
    return JSONResponse(
        status_code=200,
        content={
            "data": status.model_dump(mode="json"),
            "requires_restart": True,
        },
    )
