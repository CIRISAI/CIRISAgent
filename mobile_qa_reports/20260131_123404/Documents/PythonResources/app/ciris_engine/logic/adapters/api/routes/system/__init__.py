"""
System routes module.

This module provides a unified router that combines all system-related endpoints
organized into logical sub-modules:

- health: System health and time endpoints
- runtime: Runtime control and cognitive state transitions
- services: Services status and resource monitoring
- shutdown: Graceful and local shutdown
- adapters: Adapter management (list, load, unload, reload)
- adapter_config: Interactive adapter configuration workflow
- tools: Available tools listing

The main router is exported for backward compatibility with existing code
that imports `from ...routes.system import router`.
"""

from fastapi import APIRouter

from . import adapter_config, adapters, health, runtime, services, shutdown, tools

# Create the main router with the system prefix and tags
router = APIRouter(prefix="/system", tags=["system"])

# Include all sub-routers
# Health endpoints: /system/health, /system/time
router.include_router(health.router)

# Runtime control: /system/runtime/{action}, /system/state/transition
router.include_router(runtime.router)

# Services and resources: /system/services, /system/resources
router.include_router(services.router)

# Shutdown: /system/shutdown, /system/local-shutdown
router.include_router(shutdown.router)

# Adapter management: /system/adapters/*
router.include_router(adapters.router)

# Adapter configuration workflow: /system/adapters/{type}/configure/*, /system/adapters/configure/*
router.include_router(adapter_config.router)

# Tools: /system/tools
router.include_router(tools.router)

# Re-export schemas for backward compatibility
from .schemas import (
    AdapterActionRequest,
    ConfigStepInfo,
    ConfigurableAdapterInfo,
    ConfigurableAdaptersResponse,
    ConfigurationCompleteRequest,
    ConfigurationCompleteResponse,
    ConfigurationSessionResponse,
    ConfigurationStatusResponse,
    PersistedConfigsResponse,
    RemovePersistedResponse,
    ResourceUsageResponse,
    RuntimeAction,
    RuntimeControlResponse,
    ServicesStatusResponse,
    ServiceStatus,
    ShutdownRequest,
    ShutdownResponse,
    StateTransitionRequest,
    StateTransitionResponse,
    StepExecutionRequest,
    StepExecutionResponse,
    SystemHealthResponse,
    SystemTimeResponse,
    ToolInfoResponse,
)

__all__ = [
    # Main router
    "router",
    # Schemas (for backward compatibility)
    "AdapterActionRequest",
    "ConfigStepInfo",
    "ConfigurableAdapterInfo",
    "ConfigurableAdaptersResponse",
    "ConfigurationCompleteRequest",
    "ConfigurationCompleteResponse",
    "ConfigurationSessionResponse",
    "ConfigurationStatusResponse",
    "PersistedConfigsResponse",
    "RemovePersistedResponse",
    "ResourceUsageResponse",
    "RuntimeAction",
    "RuntimeControlResponse",
    "ServiceStatus",
    "ServicesStatusResponse",
    "ShutdownRequest",
    "ShutdownResponse",
    "StateTransitionRequest",
    "StateTransitionResponse",
    "StepExecutionRequest",
    "StepExecutionResponse",
    "SystemHealthResponse",
    "SystemTimeResponse",
    "ToolInfoResponse",
]
