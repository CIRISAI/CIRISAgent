"""
Setup wizard redirect middleware.

Redirects unauthenticated requests to the setup wizard if initial configuration
is incomplete.
"""

import logging
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ciris_engine.logic.setup.first_run import is_first_run

logger = logging.getLogger(__name__)


class SetupRedirectMiddleware(BaseHTTPMiddleware):
    """Middleware to redirect to setup wizard on first run."""

    EXCLUDED_PATHS = {
        "/v1/system/setup-status",
        "/v1/system/setup/llm",
        "/v1/system/setup/admin",
        "/v1/system/setup/skip",
        "/v1/system/setup/complete",
        "/setup-wizard.html",
        "/setup-wizard",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/_next/",  # Next.js assets
        "/favicon.ico",
    }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Redirect to setup wizard if first run and accessing protected endpoints.

        Args:
            request: Incoming request
            call_next: Next middleware or route handler

        Returns:
            Response (either redirect or normal response)
        """
        # Check if this is a first run
        if not is_first_run():
            # Not a first run, proceed normally
            return await call_next(request)

        # Check if request path is excluded from redirect
        path = request.url.path

        # Allow setup wizard endpoints
        if any(path.startswith(excluded) for excluded in self.EXCLUDED_PATHS):
            return await call_next(request)

        # Allow static assets
        if "/_next/" in path or "/static/" in path or path.endswith((".js", ".css", ".png", ".jpg", ".svg", ".ico")):
            return await call_next(request)

        # For HTML requests (browser), redirect to setup wizard
        accept_header = request.headers.get("accept", "")
        if "text/html" in accept_header:
            logger.info(f"First run detected - redirecting {path} to setup wizard")
            return RedirectResponse(url="/setup-wizard.html", status_code=302)

        # For API requests, return 503 with setup required message
        return Response(
            content='{"detail":"System not configured. Please complete setup wizard at /setup-wizard.html"}',
            status_code=503,
            media_type="application/json",
        )
