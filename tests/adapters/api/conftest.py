"""
Shared fixtures for API adapter tests.
"""

import pytest
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.app import create_app
from ciris_engine.logic.adapters.api.services.auth_service import APIAuthService


@pytest.fixture
def app():
    """Create FastAPI app with minimal required state."""
    app = create_app()

    # Initialize auth service (required for auth endpoints)
    app.state.auth_service = APIAuthService()

    # Initialize auth service with dev mode if needed
    app.state.auth_service._dev_mode = True

    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Get auth headers for testing using dev credentials."""
    # In dev mode, username:password format is supported
    return {"Authorization": "Bearer admin:ciris_admin_password"}


@pytest.fixture
def mock_runtime(app):
    """Add mock runtime to app state."""
    from unittest.mock import MagicMock

    mock_runtime = MagicMock()
    mock_runtime.is_running = True
    app.state.runtime = mock_runtime

    return mock_runtime
