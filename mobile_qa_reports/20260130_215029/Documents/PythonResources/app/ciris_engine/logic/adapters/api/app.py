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
        root_path=root_path or "",  # This tells FastAPI it's behind a proxy at this path
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure based on deployment
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add rate limiting middleware if enabled in config
    if adapter_config and getattr(adapter_config, "rate_limit_enabled", False):
        rate_limit = getattr(adapter_config, "rate_limit_per_minute", 60)

        # Create middleware instance
        rate_limit_middleware = RateLimitMiddleware(requests_per_minute=rate_limit)

        # Add middleware using a wrapper function
        @app.middleware("http")
        async def rate_limit_wrapper(request: Request, call_next: Callable[..., Any]) -> Response:
            return await rate_limit_middleware(request, call_next)

        print(f"Rate limiting enabled: {rate_limit} requests per minute")

    # Store runtime in app state for access in routes
    if runtime:
        app.state.runtime = runtime

        # Initialize auth service - will be properly initialized later with authentication service
        app.state.auth_service = APIAuthService()

        # Services will be injected later in ApiPlatform.start() after they're initialized
        # For now, just set placeholders to None

        # === THE 21 CORE CIRIS SERVICES ===
        # Graph Services (6)
        app.state.memory_service = None
        app.state.consent_manager = None  # Consent manager for Consensual Evolution Protocol (includes DSAR automation)
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
        app.state.wa_service = None  # Alias for wise_authority_service
        app.state.adaptive_filter_service = None
        app.state.visibility_service = None
        app.state.self_observation_service = None

        # Runtime Services (3)
        app.state.llm_service = None
        app.state.runtime_control_service = None
        app.state.task_scheduler = None

        # Tool Services (1)
        app.state.secrets_tool_service = None

        # === INFRASTRUCTURE COMPONENTS (not part of the 22 services) ===
        app.state.service_registry = None
        app.state.agent_processor = None
        app.state.message_handler = None
        # Adapter-created services
        app.state.communication_service = None
        app.state.tool_service = None
        # Adapter configuration service (for interactive adapter setup)
        app.state.adapter_configuration_service = None
        # Message buses (injected from bus_manager)
        app.state.tool_bus = None
        app.state.memory_bus = None

    # Mount v1 API routes (all routes except emergency under /v1)
    v1_routers = [
        setup.router,  # Setup wizard (first-run + reconfiguration) - MUST be first for first-run detection
        agent.router,  # Agent interaction
        billing.router,  # Billing & credits (frontend proxy) - LLM credits
        tools.router,  # Tool balance & credits (web_search, etc.) - separate from LLM credits
        memory.router,  # Memory operations
        system_extensions.router,  # Extended system operations (queue, services, processors) - MUST be before system.router
        system.router,  # System operations (includes health, time, resources, runtime)
        config.router,  # Configuration management
        telemetry.router,  # Telemetry & observability
        audit.router,  # Audit trail
        wa.router,  # Wise Authority
        auth.router,  # Authentication
        users.router,  # User management
        consent.router,  # Consent management (Consensual Evolution Protocol)
        dsar.router,  # Data Subject Access Requests (GDPR compliance - single source)
        dsar_multi_source.router,  # Multi-source DSAR (CIRIS + external databases)
        connectors.router,  # External data connector management (SQL, REST, HL7)
        tickets.router,  # Universal Ticket System (DSAR + custom workflows)
        verification.router,  # Deletion proof verification (public, no auth)
        partnership.router,  # Partnership management dashboard (admin only)
        transparency.router,  # Public transparency feed (no auth)
    ]

    # Include all v1 routes with /v1 prefix
    for router in v1_routers:
        app.include_router(router, prefix="/v1")

    # Mount emergency routes at root level (no /v1 prefix)
    # This is special - requires signed commands, no auth
    app.include_router(emergency.router)

    # Mount GUI static assets (if available) - MUST be LAST for proper route priority
    # This enables serving the CIRISGUI frontend when bundled in the wheel
    # ONLY in installed/standalone mode - NOT in managed/Docker mode
    from pathlib import Path

    from ciris_engine.logic.utils.path_resolution import is_android, is_managed

    # Path resolution for GUI static assets
    # Need 4 parent levels: api -> adapters -> logic -> ciris_engine
    package_root = Path(__file__).resolve().parent.parent.parent.parent

    # On Android, prefer android_gui_static (built from CIRISGUI-Android)
    # Otherwise fall back to gui_static (bundled in wheel for desktop/server)
    android_gui_dir = package_root.parent / "android_gui_static"
    gui_static_dir = package_root / "gui_static"

    # Choose the appropriate GUI directory
    if is_android() and android_gui_dir.exists() and any(android_gui_dir.iterdir()):
        gui_static_dir = android_gui_dir
        print(f"📱 Using Android GUI static assets: {gui_static_dir}")

    # Skip GUI in managed/Docker mode - manager provides its own frontend
    if is_managed():
        print("ℹ️  GUI disabled in managed mode (manager provides frontend)")

        # API-only mode for managed deployments
        @app.get("/")
        def root() -> dict[str, str]:
            return {
                "name": "CIRIS API",
                "version": "1.0.0",
                "docs": "/docs",
                "redoc": "/redoc",
                "openapi": "/openapi.json",
                "gui": "managed_mode",
                "message": "Running in managed mode - GUI provided by CIRIS Manager",
            }

    elif gui_static_dir.exists() and any(gui_static_dir.iterdir()):
        from fastapi.staticfiles import StaticFiles

        # Serve GUI at root (/) - catch-all, lowest priority
        # This works because FastAPI matches routes in order:
        # 1. /v1/* routes (highest priority)
        # 2. /emergency/* routes
        # 3. /docs, /redoc, /openapi.json (FastAPI built-ins)
        # 4. /* GUI static files (lowest priority, catch-all)
        app.mount("/", StaticFiles(directory=str(gui_static_dir), html=True), name="gui")
        print(f"✅ GUI enabled at / (static assets: {gui_static_dir})")
    else:
        # No GUI - API-only mode
        @app.get("/")
        def root() -> dict[str, str]:
            return {
                "name": "CIRIS API",
                "version": "1.0.0",
                "docs": "/docs",
                "redoc": "/redoc",
                "openapi": "/openapi.json",
                "gui": "not_available",
                "message": "Install from PyPI for the full package with GUI: pip install ciris-agent",
            }

        print("ℹ️  API-only mode (no GUI assets found)")

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
