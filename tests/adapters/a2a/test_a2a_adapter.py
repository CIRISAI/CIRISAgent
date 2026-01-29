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
        return A2AService()

    @pytest.fixture
    def mock_runtime(self):
        """Create mock runtime with pipeline support."""
        runtime = MagicMock()
        runtime.process_message = AsyncMock(return_value=MagicMock(response="yes"))
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
        """Create mock runtime with pipeline support."""
        runtime = MagicMock()
        runtime.process_message = AsyncMock(return_value=MagicMock(response="yes, stealing is wrong"))
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
    def client(self, adapter):
        """Create test client."""
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
        assert data["error"]["code"] == -32600


class TestA2AConcurrency:
    """Tests for A2A concurrency handling."""

    @pytest.fixture
    def mock_runtime(self):
        """Create mock runtime with pipeline support."""
        runtime = MagicMock()

        # Mock process_message with small delay to simulate real processing
        async def slow_process(*args, **kwargs):
            await asyncio.sleep(0.1)
            return MagicMock(response="yes")

        runtime.process_message = slow_process
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
