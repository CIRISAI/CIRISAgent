"""
Shared fixtures for API adapter tests.

High-quality centralized fixtures for comprehensive API testing including:
- Complete APICommunicationService setup with all dependencies
- Mock services and correlations for testing message flow
- WebSocket client simulation
- Time service mocking for consistent timestamps
- Service correlation fixtures for testing message fetching
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.api_communication import APICommunicationService
from ciris_engine.logic.adapters.api.app import create_app
from ciris_engine.logic.adapters.api.services.auth_service import APIAuthService
from ciris_engine.schemas.runtime.messages import FetchedMessage
from ciris_engine.schemas.telemetry.core import (
    ServiceCorrelation,
    ServiceCorrelationStatus,
    ServiceRequestData,
    ServiceResponseData,
)


@pytest.fixture
def mock_time_service():
    """Create consistent mock time service."""
    service = Mock()
    # Fixed time for consistent testing
    fixed_time = datetime(2025, 9, 8, 12, 0, 0, tzinfo=timezone.utc)
    service.now.return_value = fixed_time
    service.now_iso.return_value = fixed_time.isoformat()
    service.strftime.return_value = fixed_time.strftime("%Y%m%d_%H%M%S")
    return service


@pytest.fixture
def mock_app_state():
    """Create mock app state with message tracking."""
    state = Mock()
    state.message_channel_map = {}
    state.sent_messages = {}
    return state


@pytest.fixture
def mock_websocket_client():
    """Create mock WebSocket client for testing."""
    client = Mock()
    client.send_json = AsyncMock()
    return client


@pytest.fixture
async def api_communication_service(mock_time_service, mock_app_state):
    """Create fully configured APICommunicationService for testing."""
    service = APICommunicationService()
    service._time_service = mock_time_service
    service._app_state = mock_app_state
    
    # Start the service
    await service.start()
    
    yield service
    
    # Clean up
    await service.stop()


@pytest.fixture
def sample_speak_correlation(mock_time_service):
    """Create sample 'speak' correlation for testing message fetching."""
    fixed_time = mock_time_service.now()
    
    return ServiceCorrelation(
        correlation_id="speak-corr-123",
        service_type="api",
        handler_name="APIAdapter",
        action_type="speak",
        status=ServiceCorrelationStatus.COMPLETED,
        created_at=fixed_time,
        updated_at=fixed_time,
        timestamp=fixed_time,
        request_data=ServiceRequestData(
            service_type="api",
            method_name="speak",
            request_timestamp=fixed_time,
            channel_id="api_127.0.0.1_8080",
            parameters={
                "content": "Hello from CIRIS!",
                "channel_id": "api_127.0.0.1_8080"
            },
        ),
        response_data=ServiceResponseData(
            success=True,
            result_summary="Message sent",
            execution_time_ms=15,
            response_timestamp=fixed_time
        ),
    )


@pytest.fixture
def sample_observe_correlation(mock_time_service):
    """Create sample 'observe' correlation for testing message fetching."""
    fixed_time = mock_time_service.now()
    
    return ServiceCorrelation(
        correlation_id="observe-corr-456",
        service_type="api",
        handler_name="APIAdapter",
        action_type="observe",
        status=ServiceCorrelationStatus.COMPLETED,
        created_at=fixed_time,
        updated_at=fixed_time,
        timestamp=fixed_time,
        request_data=ServiceRequestData(
            service_type="api",
            method_name="observe",
            request_timestamp=fixed_time,
            channel_id="api_127.0.0.1_8080",
            parameters={
                "content": "Hello CIRIS!",
                "author_id": "user123",
                "author_name": "Test User",
                "message_id": "msg-456"
            },
        ),
        response_data=ServiceResponseData(
            success=True,
            result_summary="Message observed",
            execution_time_ms=5,
            response_timestamp=fixed_time
        ),
    )


@pytest.fixture
def sample_correlations(sample_speak_correlation, sample_observe_correlation):
    """Create list of sample correlations for comprehensive testing."""
    return [sample_observe_correlation, sample_speak_correlation]


@pytest.fixture
def expected_fetched_messages(mock_time_service):
    """Create expected FetchedMessage objects for testing."""
    timestamp = mock_time_service.now().isoformat()
    
    return [
        # User message (observe)
        FetchedMessage(
            message_id="observe-corr-456",
            author_id="user123",
            author_name="Test User",
            content="Hello CIRIS!",
            timestamp=timestamp,
            is_bot=False,
        ),
        # Agent message (speak)
        FetchedMessage(
            message_id="speak-corr-123",
            author_id="ciris",
            author_name="CIRIS",
            content="Hello from CIRIS!",
            timestamp=timestamp,
            is_bot=True,
        )
    ]


@pytest.fixture
def mock_persistence():
    """Mock persistence module for testing correlation storage/retrieval."""
    with pytest.MonkeyPatch().context() as m:
        mock_add_correlation = Mock()
        mock_get_correlations = Mock()
        
        m.setattr("ciris_engine.logic.persistence.add_correlation", mock_add_correlation)
        m.setattr("ciris_engine.logic.persistence.get_correlations_by_channel", mock_get_correlations)
        
        yield {
            "add_correlation": mock_add_correlation,
            "get_correlations_by_channel": mock_get_correlations,
        }


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
    mock_runtime = MagicMock()
    mock_runtime.is_running = True
    app.state.runtime = mock_runtime

    return mock_runtime
