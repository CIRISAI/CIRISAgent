"""
FastAPI application for CIRIS API v1.

This module creates and configures the FastAPI application with all routes.
"""

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

# Import rate limiting middleware
from .middleware.rate_limiter import RateLimitMiddleware

# Import all route modules from adapter
from .routes import (
    agent,
    audit,
    auth,
    billing,
    config,
    connectors,
    consent,
    dsar,
    dsar_multi_source,
    emergency,
    memory,
    partnership,
    setup,
    system,
    system_extensions,
    telemetry,
    tickets,
    tools,
    transparency,
    users,
    verification,
    wa,
)

# Import auth service
from .services.auth_service import APIAuthService


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application lifecycle."""
    # Startup
    print("Starting CIRIS API...")
    yield
    # Shutdown
    print("Shutting down CIRIS API...")


# ============================================================================
# Helper functions to reduce cognitive complexity (SonarCloud S3776)
# ============================================================================


def _configure_cors(app: FastAPI, adapter_config: Any) -> None:
    """Configure CORS middleware based on adapter config."""
    cors_enabled = True
    cors_origins: list[str] = ["*"]
    cors_allow_credentials = False

    if adapter_config:
        cors_enabled = bool(getattr(adapter_config, "cors_enabled", True))
        configured_origins = getattr(adapter_config, "cors_origins", ["*"])
        if isinstance(configured_origins, list) and configured_origins:
            cors_origins = configured_origins
        cors_allow_credentials = bool(getattr(adapter_config, "cors_allow_credentials", False))

    if not cors_enabled:
        return

    # Browsers reject wildcard origins with credentials; fail safe by disabling credentials
    if "*" in cors_origins and cors_allow_credentials:
        print("CORS warning: wildcard origins cannot use credentials. Disabling credentials.")
        cors_allow_credentials = False

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def _configure_rate_limiting(app: FastAPI, adapter_config: Any) -> None:
    """Configure rate limiting middleware if enabled."""
    if not adapter_config or not getattr(adapter_config, "rate_limit_enabled", False):
        return

    rate_limit = getattr(adapter_config, "rate_limit_per_minute", 60)
    rate_limit_middleware = RateLimitMiddleware(requests_per_minute=rate_limit)

    @app.middleware("http")
    async def rate_limit_wrapper(request: Request, call_next: Callable[..., Any]) -> Response:
        return await rate_limit_middleware(request, call_next)

    print(f"Rate limiting enabled: {rate_limit} requests per minute")


def _initialize_app_state(app: FastAPI, runtime: Any) -> None:
    """Initialize app.state with runtime and service placeholders."""
    app.state.runtime = runtime
    app.state.auth_service = APIAuthService()

    # Graph Services (7)
    app.state.memory_service = None
    app.state.consent_manager = None
    app.state.config_service = None
    app.state.telemetry_service = None
    app.state.audit_service = None
    app.state.incident_management_service = None
    app.state.tsdb_consolidation_service = None

    # Infrastructure Services (7)
    app.state.time_service = None
    app.state.shutdown_service = None
    app.state.initialization_service = None
    app.state.authentication_service = None
    app.state.resource_monitor = None
    app.state.database_maintenance_service = None
    app.state.secrets_service = None

    # Governance Services (4)
    app.state.wise_authority_service = None
    app.state.wa_service = None
    app.state.adaptive_filter_service = None
    app.state.visibility_service = None
    app.state.self_observation_service = None

    # Runtime Services (3)
    app.state.llm_service = None
    app.state.runtime_control_service = None
    app.state.task_scheduler = None

    # Tool Services (1)
    app.state.secrets_tool_service = None

    # Infrastructure components
    app.state.service_registry = None
    app.state.agent_processor = None
    app.state.message_handler = None
    app.state.communication_service = None
    app.state.tool_service = None
    app.state.adapter_configuration_service = None
    app.state.tool_bus = None
    app.state.memory_bus = None


def _mount_gui_assets(app: FastAPI) -> None:
    """Mount GUI static assets or configure API-only mode."""
    from pathlib import Path

    from fastapi.staticfiles import StaticFiles

    from ciris_engine.logic.utils.path_resolution import is_android, is_managed

    package_root = Path(__file__).resolve().parent.parent.parent.parent
    android_gui_dir = package_root.parent / "android_gui_static"
    gui_static_dir = package_root / "gui_static"

    # Choose appropriate GUI directory
    if is_android() and android_gui_dir.exists() and any(android_gui_dir.iterdir()):
        gui_static_dir = android_gui_dir
        print(f"📱 Using Android GUI static assets: {gui_static_dir}")

    # Skip GUI in managed/Docker mode
    if is_managed():
        print("ℹ️  GUI disabled in managed mode (manager provides frontend)")
        _add_api_root_endpoint(app, "managed_mode", "Running in managed mode - GUI provided by CIRIS Manager")
    elif gui_static_dir.exists() and any(gui_static_dir.iterdir()):
        app.mount("/", StaticFiles(directory=str(gui_static_dir), html=True), name="gui")
        print(f"✅ GUI enabled at / (static assets: {gui_static_dir})")
    else:
        _add_api_root_endpoint(
            app, "not_available", "Install from PyPI for the full package with GUI: pip install ciris-agent"
        )
        print("ℹ️  API-only mode (no GUI assets found)")


def _add_api_root_endpoint(app: FastAPI, gui_status: str, message: str) -> None:
    """Add a root endpoint for API-only mode."""

    @app.get("/")
    def root() -> dict[str, str]:
        return {
            "name": "CIRIS API",
            "version": "1.0.0",
            "docs": "/docs",
            "redoc": "/redoc",
            "openapi": "/openapi.json",
            "gui": gui_status,
            "message": message,
        }


def create_app(runtime: Any = None, adapter_config: Any = None) -> FastAPI:
    """
    Create and configure the FastAPI application.

    Args:
        runtime: Optional runtime instance for service access
        adapter_config: Optional APIAdapterConfig instance

    Returns:
        Configured FastAPI application
    """
    # Determine root_path for reverse proxy support
    root_path = ""
    if adapter_config and hasattr(adapter_config, "proxy_path") and adapter_config.proxy_path:
        root_path = adapter_config.proxy_path
        print(f"Configuring FastAPI with root_path='{root_path}' for reverse proxy support")

    app = FastAPI(
        title="CIRIS API v1",
        description="Autonomous AI Agent Interaction and Observability API (Pre-Beta)",
        version="1.0.0",
        lifespan=lifespan,
        root_path=root_path or "",
    )

    # Configure middleware
    _configure_cors(app, adapter_config)
    _configure_rate_limiting(app, adapter_config)

    # Initialize app state with runtime and service placeholders
    if runtime:
        _initialize_app_state(app, runtime)

    # Mount v1 API routes
    v1_routers = [
        setup.router,
        agent.router,
        billing.router,
        tools.router,
        memory.router,
        system_extensions.router,
        system.router,
        config.router,
        telemetry.router,
        audit.router,
        wa.router,
        auth.router,
        users.router,
        consent.router,
        dsar.router,
        dsar_multi_source.router,
        connectors.router,
        tickets.router,
        verification.router,
        partnership.router,
        transparency.router,
    ]

    for router in v1_routers:
        app.include_router(router, prefix="/v1")

    # Mount emergency routes at root level (no /v1 prefix)
    app.include_router(emergency.router)

    # Mount GUI static assets (MUST be LAST for proper route priority)
    _mount_gui_assets(app)

    return app


# For running standalone (development)
if __name__ == "__main__":
    import os

    import uvicorn

    app = create_app()
    # Use environment variable or secure default (localhost only)
    host = os.environ.get("CIRIS_API_HOST", "127.0.0.1")
    port = int(os.environ.get("CIRIS_API_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
