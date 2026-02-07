"""
Common utilities and response patterns for API routes.

This module provides reusable components to reduce duplication across route files:
- Standard HTTP response dictionaries for OpenAPI documentation
- Common type aliases for FastAPI dependency injection (Annotated patterns)
- Shared helper functions for error handling

Usage:
    from ._common import (
        RESPONSES_404_500,
        RESPONSES_503,
        AuthDep,
        AuthObserverDep,
        AuthServiceDep,
    )

    @router.get("/items/{id}", responses=RESPONSES_404_500)
    async def get_item(id: str, auth: AuthObserverDep) -> ItemResponse:
        ...
"""

from typing import Annotated, Any, Dict, Optional, Union

from fastapi import Depends

from ciris_engine.schemas.api.auth import AuthContext

from ..dependencies.auth import get_auth_context, get_auth_service, optional_auth, require_admin, require_observer
from ..services.auth_service import APIAuthService

# ============================================================================
# Annotated Type Aliases for FastAPI Dependency Injection
# ============================================================================
# These follow the modern FastAPI pattern using Annotated types instead of
# default parameter values with Depends(). This is the recommended approach
# as of FastAPI 0.95+ and fixes SonarCloud S8410 issues.

# Basic authentication - requires any authenticated user
AuthDep = Annotated[AuthContext, Depends(get_auth_context)]

# Role-based authentication dependencies
AuthObserverDep = Annotated[AuthContext, Depends(require_observer)]
AuthAdminDep = Annotated[AuthContext, Depends(require_admin)]

# Optional authentication - returns None if not authenticated
OptionalAuthDep = Annotated[Optional[AuthContext], Depends(optional_auth)]

# Auth service dependency for direct service access
AuthServiceDep = Annotated[APIAuthService, Depends(get_auth_service)]

# ============================================================================
# Common error message constants (avoid duplication - SonarCloud S1192)
# ============================================================================

MSG_BILLING_SERVICE_UNAVAILABLE = "Billing service unavailable"
MSG_BILLING_OR_RESOURCE_UNAVAILABLE = "Billing service unavailable or resource monitor not available"
MSG_GOOGLE_AUTH_REQUIRED = "Google Sign-In required or authentication failed"

# ============================================================================
# Standard HTTP Response Dictionaries for OpenAPI Documentation
# ============================================================================
# These are used in the `responses` parameter of route decorators to document
# possible error responses. FastAPI uses these to generate OpenAPI schemas.

# Use Union[int, str] for FastAPI compatibility (OpenAPI allows string status codes)
ResponseDict = Dict[Union[int, str], Dict[str, Any]]

RESPONSES_400: ResponseDict = {400: {"description": "Bad request - invalid input parameters"}}

RESPONSES_401: ResponseDict = {401: {"description": "Unauthorized - authentication required"}}

RESPONSES_403: ResponseDict = {403: {"description": "Forbidden - insufficient permissions"}}

RESPONSES_404: ResponseDict = {404: {"description": "Resource not found"}}

RESPONSES_409: ResponseDict = {409: {"description": "Conflict - resource already exists or state conflict"}}

RESPONSES_500: ResponseDict = {500: {"description": "Internal server error"}}

RESPONSES_503: ResponseDict = {503: {"description": "Service unavailable"}}

# ============================================================================
# Combined Response Dictionaries (common patterns)
# ============================================================================

RESPONSES_404_500: ResponseDict = {**RESPONSES_404, **RESPONSES_500}

RESPONSES_404_503: ResponseDict = {**RESPONSES_404, **RESPONSES_503}

RESPONSES_500_503: ResponseDict = {**RESPONSES_500, **RESPONSES_503}

RESPONSES_404_500_503: ResponseDict = {
    **RESPONSES_404,
    **RESPONSES_500,
    **RESPONSES_503,
}

RESPONSES_400_404_500: ResponseDict = {
    **RESPONSES_400,
    **RESPONSES_404,
    **RESPONSES_500,
}

RESPONSES_401_403: ResponseDict = {**RESPONSES_401, **RESPONSES_403}

RESPONSES_401_403_404: ResponseDict = {
    **RESPONSES_401,
    **RESPONSES_403,
    **RESPONSES_404,
}

RESPONSES_401_403_404_500: ResponseDict = {
    **RESPONSES_401,
    **RESPONSES_403,
    **RESPONSES_404,
    **RESPONSES_500,
}

RESPONSES_400_403_500: ResponseDict = {
    **RESPONSES_400,
    **RESPONSES_403,
    **RESPONSES_500,
}

RESPONSES_401_500: ResponseDict = {
    **RESPONSES_401,
    **RESPONSES_500,
}

RESPONSES_402: ResponseDict = {402: {"description": "Payment required - insufficient credits"}}

RESPONSES_402_403_503: ResponseDict = {
    402: {"description": "Payment required - insufficient credits"},
    **RESPONSES_403,
    **RESPONSES_503,
}

# ============================================================================
# Adapter-specific response patterns
# ============================================================================

RESPONSES_ADAPTER_CRUD: ResponseDict = {
    400: {"description": "Invalid adapter configuration"},
    404: {"description": "Adapter not found"},
    409: {"description": "Adapter already exists"},
    500: {"description": "Adapter operation failed"},
    503: {"description": "Adapter service unavailable"},
}

RESPONSES_ADAPTER_STATUS: ResponseDict = {
    404: {"description": "Adapter not found"},
    500: {"description": "Failed to retrieve adapter status"},
    503: {"description": "Adapter service unavailable"},
}

RESPONSES_ADAPTER_CONFIG: ResponseDict = {
    404: {"description": "Adapter or session not found"},
    500: {"description": "Configuration operation failed"},
    503: {"description": "Adapter configuration service unavailable"},
}

RESPONSES_ADAPTER_CONFIG_SESSION: ResponseDict = {
    400: {"description": "Invalid session state or OAuth callback"},
    404: {"description": "Session not found"},
    500: {"description": "Configuration step failed"},
}

# ============================================================================
# Billing-specific response patterns
# ============================================================================

RESPONSES_BILLING_503: ResponseDict = {503: {"description": MSG_BILLING_OR_RESOURCE_UNAVAILABLE}}

RESPONSES_BILLING_PURCHASE_INITIATE: ResponseDict = {
    400: {"description": "Invalid purchase request or email required"},
    403: {"description": "Billing not enabled"},
    503: {"description": MSG_BILLING_OR_RESOURCE_UNAVAILABLE},
}

RESPONSES_BILLING_PURCHASE_STATUS: ResponseDict = {
    400: {"description": "Invalid payment ID format"},
    404: {"description": "Payment not found"},
    503: {"description": MSG_BILLING_OR_RESOURCE_UNAVAILABLE},
}

# ============================================================================
# Tool-specific response patterns
# ============================================================================

RESPONSES_TOOL_BALANCE: ResponseDict = {
    401: {"description": MSG_GOOGLE_AUTH_REQUIRED},
    404: {"description": "Tool not found"},
    503: {"description": MSG_BILLING_SERVICE_UNAVAILABLE},
}

RESPONSES_TOOL_BALANCE_ALL: ResponseDict = {
    401: {"description": MSG_GOOGLE_AUTH_REQUIRED},
    503: {"description": MSG_BILLING_SERVICE_UNAVAILABLE},
}

RESPONSES_TOOL_PURCHASE: ResponseDict = {
    400: {"description": "Invalid tool name or purchase data"},
    401: {"description": MSG_GOOGLE_AUTH_REQUIRED},
    409: {"description": "Purchase already processed"},
    503: {"description": MSG_BILLING_SERVICE_UNAVAILABLE},
}
