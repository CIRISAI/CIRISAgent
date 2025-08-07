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
    config,
    dsar,
    emergency,
    memory,
    system,
    system_extensions,
    telemetry,
    transparency,
    users,
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
    app = FastAPI(
        title="CIRIS API v1",
        description="Autonomous AI Agent Interaction and Observability API (Pre-Beta)",
        version="1.0.0",
        lifespan=lifespan,
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
        async def rate_limit_wrapper(request: Request, call_next: Callable) -> Response:
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

        # === INFRASTRUCTURE COMPONENTS (not part of the 21 services) ===
        app.state.service_registry = None
        app.state.agent_processor = None
        app.state.message_handler = None
        # Adapter-created services
        app.state.communication_service = None
        app.state.tool_service = None

    # Mount v1 API routes (all routes except emergency under /v1)
    v1_routers = [
        agent.router,  # Agent interaction
        memory.router,  # Memory operations
        system.router,  # System operations (includes health, time, resources, runtime)
        system_extensions.router,  # Extended system operations (queue, services, processors)
        config.router,  # Configuration management
        telemetry.router,  # Telemetry & observability
        audit.router,  # Audit trail
        wa.router,  # Wise Authority
        auth.router,  # Authentication
        users.router,  # User management
        dsar.router,  # Data Subject Access Requests (GDPR compliance)
        transparency.router,  # Public transparency feed (no auth)
    ]

    # Include all v1 routes with /v1 prefix
    for router in v1_routers:
        app.include_router(router, prefix="/v1")

    # Mount emergency routes at root level (no /v1 prefix)
    # This is special - requires signed commands, no auth
    app.include_router(emergency.router)

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
