"""
Tests for A2A (Agent-to-Agent) protocol adapter.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from ciris_adapters.a2a import A2AAdapter, A2ARequest, A2AService, create_success_response


class TestA2ASchemas:
    """Tests for A2A protocol schemas."""

    def test_create_success_response(self):
        """Test creating a success response."""
        response = create_success_response(
            request_id="req-123",
            task_id="task-456",
            response_text="yes",
        )

        assert response.jsonrpc == "2.0"
        assert response.id == "req-123"
        assert response.result is not None
        assert response.result.task.id == "task-456"
        assert response.result.task.status == "completed"
        assert len(response.result.task.artifacts) == 1
        assert response.result.task.artifacts[0].parts[0].text == "yes"

    def test_a2a_request_parsing(self):
        """Test parsing an A2A request."""
        request_data = {
            "jsonrpc": "2.0",
            "id": "req-123",
            "method": "tasks/send",
            "params": {
                "task": {
                    "id": "task-456",
                    "message": {
                        "role": "user",
                        "parts": [{"type": "text", "text": "Is stealing wrong?"}],
                    },
                }
            },
        }

        request = A2ARequest(**request_data)
        assert request.method == "tasks/send"
        assert request.params.task.id == "task-456"
        assert request.params.task.message.parts[0].text == "Is stealing wrong?"


class TestA2AService:
    """Tests for A2A service."""

    @pytest.fixture
    def service(self):
        """Create A2A service for testing."""
        import ciris_adapters.a2a.services as a2a_services

        # Reset the global request counter for deterministic test results
        a2a_services._request_counter = 0
        return A2AService()

    @pytest.fixture
    def mock_runtime(self):
        """Create mock runtime with pipeline support that simulates response event."""
        from ciris_engine.logic.adapters.api.routes.agent import _message_responses, _response_events

        runtime = MagicMock()
        runtime.adapters = []  # No API adapter, so it will use runtime.on_message

        async def mock_on_message(message):
            """Mock on_message that simulates pipeline response."""
            # Set the response and trigger the event
            _message_responses[message.message_id] = "yes"
            if message.message_id in _response_events:
                _response_events[message.message_id].set()

        runtime.on_message = mock_on_message
        return runtime

    @pytest.mark.asyncio
    async def test_service_lifecycle(self, service):
        """Test service start and stop."""
        await service.start()
        assert service._running is True

        await service.stop()
        assert service._running is False

    @pytest.mark.asyncio
    async def test_process_query_without_runtime(self, service):
        """Test that processing fails without runtime."""
        await service.start()

        with pytest.raises(RuntimeError, match="CIRIS runtime not available"):
            await service.process_ethical_query("Is lying wrong?")

        await service.stop()

    @pytest.mark.asyncio
    async def test_process_query_with_mock_runtime(self, service, mock_runtime):
        """Test processing with a mock runtime."""
        service.set_runtime(mock_runtime)
        await service.start()

        result = await service.process_ethical_query("Is stealing wrong?")
        assert result == "yes"
        assert service._request_count == 1
        assert service._error_count == 0

        await service.stop()

    def test_get_metrics(self, service):
        """Test getting service metrics."""
        metrics = service.get_metrics()
        assert "request_count" in metrics
        assert "error_count" in metrics
        assert "running" in metrics


class TestA2AAdapter:
    """Tests for A2A adapter."""

    @pytest.fixture
    def mock_runtime(self):
        """Create mock runtime."""
        runtime = MagicMock()
        runtime.service_registry = MagicMock()
        runtime.service_registry.get_service = MagicMock(return_value=None)
        return runtime

    @pytest.fixture
    def adapter(self, mock_runtime):
        """Create A2A adapter for testing."""
        return A2AAdapter(
            runtime=mock_runtime,
            adapter_config={"host": "127.0.0.1", "port": 8199},
        )

    def test_adapter_initialization(self, adapter):
        """Test adapter initializes correctly."""
        assert adapter._host == "127.0.0.1"
        assert adapter._port == 8199
        assert adapter.app is not None
        assert adapter.a2a_service is not None

    def test_get_services_to_register(self, adapter):
        """Test service registration."""
        registrations = adapter.get_services_to_register()
        assert len(registrations) == 1
        assert "a2a:tasks_send" in registrations[0].capabilities

    def test_get_config(self, adapter):
        """Test getting adapter config."""
        config = adapter.get_config()
        assert config.adapter_type == "a2a"
        assert config.settings["host"] == "127.0.0.1"
        assert config.settings["port"] == 8199

    def test_get_status(self, adapter):
        """Test getting adapter status."""
        status = adapter.get_status()
        assert status.adapter_type == "a2a"
        assert status.is_running is False


class TestA2AEndpoint:
    """Tests for A2A HTTP endpoint."""

    @pytest.fixture
    def mock_runtime(self):
        """Create mock runtime with pipeline support that simulates response event."""
        from ciris_engine.logic.adapters.api.routes.agent import _message_responses, _response_events

        runtime = MagicMock()
        runtime.adapters = []  # No API adapter, so it will use runtime.on_message
        runtime.service_registry = MagicMock()
        runtime.service_registry.get_service = MagicMock(return_value=None)
        # The A2A adapter (post release/2.9.5) refuses to initialize without an
        # authentication_service on the runtime. MagicMock is enough for the
        # adapter to wrap into APIAuthService; tests that need auth to pass
        # use dependency_overrides instead of going through real validation.
        runtime.authentication_service = MagicMock()

        async def mock_on_message(message):
            """Mock on_message that simulates pipeline response."""
            # Set the response and trigger the event
            _message_responses[message.message_id] = "yes, stealing is wrong"
            if message.message_id in _response_events:
                _response_events[message.message_id].set()

        runtime.on_message = mock_on_message
        return runtime

    @pytest.fixture
    def adapter(self, mock_runtime):
        """Create A2A adapter for testing."""
        adapter = A2AAdapter(
            runtime=mock_runtime,
            adapter_config={"host": "127.0.0.1", "port": 8199},
        )
        return adapter

    @pytest.fixture
    def fake_admin_auth(self):
        """Return a fake admin AuthContext callable suitable for
        ``app.dependency_overrides[require_admin]`` — bypasses the real
        token-validation path while still exercising the gated route."""
        from datetime import datetime, timezone

        from ciris_engine.schemas.api.auth import AuthContext, UserRole

        async def _admin() -> AuthContext:
            return AuthContext(
                user_id="test_admin",
                role=UserRole.ADMIN,
                permissions=set(),
                api_key_id="test_key",
                authenticated_at=datetime.now(timezone.utc),
            )

        return _admin

    @pytest.fixture
    def client(self, adapter, fake_admin_auth):
        """Create test client with auth overridden to a fake admin context.

        Tests that want to assert auth IS enforced should use
        ``unauthenticated_client`` instead.
        """
        from ciris_engine.logic.adapters.api.dependencies.auth import require_admin

        adapter.app.dependency_overrides[require_admin] = fake_admin_auth
        try:
            yield TestClient(adapter.app)
        finally:
            adapter.app.dependency_overrides.clear()

    @pytest.fixture
    def unauthenticated_client(self, adapter):
        """Test client WITHOUT the auth override — exercises the real 401 path."""
        return TestClient(adapter.app)

    def test_health_endpoint(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "a2a"

    def test_metrics_endpoint(self, client):
        """Test metrics endpoint."""
        response = client.get("/metrics")
        assert response.status_code == 200
        data = response.json()
        assert "request_count" in data
        assert "error_count" in data

    def test_a2a_endpoint_success(self, client):
        """Test successful A2A request."""
        request_data = {
            "jsonrpc": "2.0",
            "id": "req-123",
            "method": "tasks/send",
            "params": {
                "task": {
                    "id": "task-456",
                    "message": {
                        "role": "user",
                        "parts": [{"type": "text", "text": "Is stealing wrong?"}],
                    },
                }
            },
        }

        response = client.post("/a2a", json=request_data)
        assert response.status_code == 200

        data = response.json()
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == "req-123"
        assert data["result"]["task"]["id"] == "task-456"
        assert data["result"]["task"]["status"] == "completed"
        assert "yes" in data["result"]["task"]["artifacts"][0]["parts"][0]["text"].lower()

    def test_a2a_endpoint_invalid_method(self, client):
        """Test A2A request with invalid method."""
        request_data = {
            "jsonrpc": "2.0",
            "id": "req-123",
            "method": "invalid/method",
            "params": {
                "task": {
                    "id": "task-456",
                    "message": {
                        "role": "user",
                        "parts": [{"type": "text", "text": "test"}],
                    },
                }
            },
        }

        response = client.post("/a2a", json=request_data)
        assert response.status_code == 200  # JSON-RPC errors return 200 with error object

        data = response.json()
        assert data["error"]["code"] == -32601
        assert "Method not found" in data["error"]["message"]

    def test_a2a_endpoint_empty_message(self, client):
        """Test A2A request with empty message."""
        request_data = {
            "jsonrpc": "2.0",
            "id": "req-123",
            "method": "tasks/send",
            "params": {
                "task": {
                    "id": "task-456",
                    "message": {
                        "role": "user",
                        "parts": [{"type": "text", "text": "   "}],
                    },
                }
            },
        }

        response = client.post("/a2a", json=request_data)
        data = response.json()
        assert data["error"]["code"] == -32602
        assert "empty" in data["error"]["message"].lower()

    def test_a2a_endpoint_invalid_request(self, client):
        """Test A2A request with invalid format."""
        response = client.post("/a2a", json={"invalid": "data"})
        data = response.json()
        assert "error" in data
        # Missing required fields results in method not found (-32601) or invalid request (-32600)
        assert data["error"]["code"] in (-32600, -32601)

    def test_a2a_endpoint_rejects_unauthenticated(self, unauthenticated_client):
        """A2A endpoint must reject calls without a valid bearer token.

        Regression for CIRISAgent#855 — pre-release/2.9.5 the endpoint
        accepted any caller and drove 120s of agent reasoning.
        """
        request_data = {
            "jsonrpc": "2.0",
            "id": "req-unauth",
            "method": "tasks/send",
            "params": {
                "task": {
                    "id": "task-unauth",
                    "message": {"role": "user", "parts": [{"type": "text", "text": "x"}]},
                }
            },
        }
        response = unauthenticated_client.post("/a2a", json=request_data)
        assert response.status_code == 401
        assert "WWW-Authenticate" in response.headers

    @pytest.mark.parametrize(
        "deleted_method",
        ["deferrals/receive", "deferrals/resolve", "credits/notify"],
    )
    def test_a2a_endpoint_rejects_deleted_methods(self, client, deleted_method):
        """The deferrals/* and credits/notify methods were deleted in 2.9.5.

        They were vestigial AgentBeats-hackathon code whose schemas declared
        an Ed25519-signed peer trust model the handlers never verified
        (CIRISAgent#855). Anything calling them today must learn it via a
        JSON-RPC -32601 method-not-found error.
        """
        request_data = {
            "jsonrpc": "2.0",
            "id": f"req-{deleted_method}",
            "method": deleted_method,
            "params": {},
        }
        response = client.post("/a2a", json=request_data)
        assert response.status_code == 200  # JSON-RPC errors return HTTP 200
        data = response.json()
        assert data["error"]["code"] == -32601
        assert "Method not found" in data["error"]["message"]
        # Make sure the deleted method's name isn't advertised in the new
        # "Supported:" hint list.
        assert deleted_method not in data["error"]["message"].split("Supported:", 1)[-1]

    def test_a2a_adapter_refuses_wildcard_cors(self, mock_runtime):
        """Config-time rejection of CORS wildcards.

        CIRISAgent#855: the prior code shipped `allow_origins=["*"]` with
        `allow_credentials=True`, an invalid CORS spec combination that
        browsers reject but non-browser clients tolerate. The new adapter
        refuses to instantiate with a wildcard origin so a stale config
        can't silently downgrade the security posture.
        """
        with pytest.raises(ValueError, match="wildcard CORS"):
            A2AAdapter(
                runtime=mock_runtime,
                adapter_config={
                    "host": "127.0.0.1",
                    "port": 8199,
                    "cors_origins": ["*"],
                },
            )

    def test_a2a_adapter_refuses_init_without_auth_service(self):
        """If the runtime has no authentication_service, the A2A adapter must
        refuse to construct — otherwise a misconfigured deployment would ship
        an unauth'd /a2a endpoint by accident.
        """
        runtime = MagicMock()
        runtime.authentication_service = None
        runtime.auth_service = None
        with pytest.raises(RuntimeError, match="authentication_service"):
            A2AAdapter(
                runtime=runtime,
                adapter_config={"host": "127.0.0.1", "port": 8199},
            )


class TestA2AConcurrency:
    """Tests for A2A concurrency handling."""

    @pytest.fixture
    def mock_runtime(self):
        """Create mock runtime with pipeline support that simulates response event."""
        import ciris_adapters.a2a.services as a2a_services
        from ciris_engine.logic.adapters.api.routes.agent import _message_responses, _response_events

        # Reset the global request counter for deterministic test results
        a2a_services._request_counter = 0

        runtime = MagicMock()
        runtime.adapters = []  # No API adapter, so it will use runtime.on_message
        runtime.service_registry = MagicMock()
        runtime.service_registry.get_service = MagicMock(return_value=None)
        # Post release/2.9.5 the A2A adapter refuses to construct without an
        # authentication_service on the runtime (CIRISAgent#855).
        runtime.authentication_service = MagicMock()

        # Mock on_message with small delay to simulate real processing
        async def slow_on_message(message):
            """Mock on_message that simulates pipeline response with delay."""
            await asyncio.sleep(0.1)
            # Set the response and trigger the event
            _message_responses[message.message_id] = "yes"
            if message.message_id in _response_events:
                _response_events[message.message_id].set()

        runtime.on_message = slow_on_message
        return runtime

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, mock_runtime):
        """Test handling multiple concurrent requests."""
        adapter = A2AAdapter(
            runtime=mock_runtime,
            adapter_config={"host": "127.0.0.1", "port": 8199},
        )

        # Create multiple concurrent requests
        async def make_request(idx: int) -> str:
            return await adapter.a2a_service.process_ethical_query(f"Query {idx}")

        # Run 10 concurrent requests
        tasks = [make_request(i) for i in range(10)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 10
        assert all(r == "yes" for r in results)
        assert adapter.a2a_service._request_count == 10
