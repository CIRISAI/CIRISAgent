"""
Unit tests for CIRISManager API routes.
"""

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI
from unittest.mock import Mock, MagicMock, AsyncMock
from pathlib import Path
from ciris_manager.api.routes_v2 import create_routes
from ciris_manager.agent_registry import AgentInfo


class TestAPIRoutes:
    """Test cases for API routes."""
    
    @pytest.fixture
    def mock_manager(self):
        """Create mock CIRISManager instance."""
        manager = Mock()
        
        # Mock config
        manager.config = Mock()
        manager.config.running = True
        
        # Mock agent registry
        manager.agent_registry = Mock()
        manager.agent_registry.list_agents = Mock(return_value=[])
        manager.agent_registry.get_agent_by_name = Mock(return_value=None)
        manager.agent_registry.unregister_agent = Mock()
        
        # Mock port manager
        manager.port_manager = Mock()
        manager.port_manager.allocated_ports = {"agent-test": 8080}
        manager.port_manager.reserved_ports = {8888, 3000}
        manager.port_manager.start_port = 8080
        manager.port_manager.end_port = 8200
        
        # Mock template verifier
        manager.template_verifier = Mock()
        manager.template_verifier.list_pre_approved_templates = Mock(return_value={
            "scout": "Scout template",
            "sage": "Sage template"
        })
        
        # Mock status
        manager.get_status = Mock(return_value={
            'running': True,
            'components': {
                'watchdog': 'running',
                'container_manager': 'running'
            }
        })
        
        # Mock create_agent as async
        manager.create_agent = AsyncMock()
        
        return manager
    
    @pytest.fixture
    def client(self, mock_manager):
        """Create test client."""
        app = FastAPI()
        router = create_routes(mock_manager)
        app.include_router(router, prefix="/manager/v1")
        return TestClient(app)
    
    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/manager/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "ciris-manager"
    
    def test_get_status(self, client, mock_manager):
        """Test status endpoint."""
        response = client.get("/manager/v1/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert data["version"] == "1.0.0"
        assert "components" in data
        assert data["components"]["watchdog"] == "running"
    
    def test_list_agents_empty(self, client):
        """Test listing agents when none exist."""
        response = client.get("/manager/v1/agents")
        assert response.status_code == 200
        data = response.json()
        assert data["agents"] == []
    
    def test_list_agents_with_data(self, client, mock_manager):
        """Test listing agents with data."""
        # Create mock agents
        agent1 = AgentInfo(
            agent_id="agent-scout",
            name="Scout",
            port=8081,
            template="scout",
            compose_file="/path/to/scout/docker-compose.yml"
        )
        agent2 = AgentInfo(
            agent_id="agent-sage",
            name="Sage",
            port=8082,
            template="sage",
            compose_file="/path/to/sage/docker-compose.yml"
        )
        
        mock_manager.agent_registry.list_agents.return_value = [agent1, agent2]
        
        response = client.get("/manager/v1/agents")
        assert response.status_code == 200
        data = response.json()
        assert len(data["agents"]) == 2
        
        # Check first agent
        assert data["agents"][0]["agent_id"] == "agent-scout"
        assert data["agents"][0]["name"] == "Scout"
        assert data["agents"][0]["port"] == 8081
        assert data["agents"][0]["api_endpoint"] == "http://localhost:8081"
    
    def test_get_agent_exists(self, client, mock_manager):
        """Test getting specific agent that exists."""
        agent = AgentInfo(
            agent_id="agent-scout",
            name="Scout",
            port=8081,
            template="scout",
            compose_file="/path/to/scout/docker-compose.yml"
        )
        
        mock_manager.agent_registry.get_agent_by_name.return_value = agent
        
        response = client.get("/manager/v1/agents/scout")
        assert response.status_code == 200
        data = response.json()
        assert data["agent_id"] == "agent-scout"
        assert data["name"] == "Scout"
        assert data["port"] == 8081
    
    def test_get_agent_not_found(self, client, mock_manager):
        """Test getting agent that doesn't exist."""
        mock_manager.agent_registry.get_agent_by_name.return_value = None
        
        response = client.get("/manager/v1/agents/nonexistent")
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"]
    
    def test_create_agent_success(self, client, mock_manager):
        """Test successful agent creation."""
        mock_manager.create_agent.return_value = {
            "agent_id": "agent-scout",
            "container": "ciris-agent-scout",
            "port": 8081,
            "api_endpoint": "http://localhost:8081",
            "compose_file": "/path/to/compose.yml",
            "status": "starting"
        }
        
        response = client.post("/manager/v1/agents", json={
            "template": "scout",
            "name": "Scout",
            "environment": {"CUSTOM": "value"}
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["agent_id"] == "agent-scout"
        assert data["name"] == "Scout"
        assert data["container"] == "ciris-agent-scout"
        assert data["port"] == 8081
        assert data["status"] == "starting"
        
        # Verify create_agent was called correctly
        mock_manager.create_agent.assert_called_once_with(
            template="scout",
            name="Scout",
            environment={"CUSTOM": "value"},
            wa_signature=None
        )
    
    def test_create_agent_with_wa_signature(self, client, mock_manager):
        """Test agent creation with WA signature."""
        mock_manager.create_agent.return_value = {
            "agent_id": "agent-custom",
            "container": "ciris-agent-custom",
            "port": 8083,
            "api_endpoint": "http://localhost:8083",
            "compose_file": "/path/to/compose.yml",
            "status": "starting"
        }
        
        response = client.post("/manager/v1/agents", json={
            "template": "custom",
            "name": "Custom",
            "wa_signature": "test_signature"
        })
        
        assert response.status_code == 200
        mock_manager.create_agent.assert_called_once_with(
            template="custom",
            name="Custom",
            environment=None,
            wa_signature="test_signature"
        )
    
    def test_create_agent_invalid_template(self, client, mock_manager):
        """Test agent creation with invalid template."""
        mock_manager.create_agent.side_effect = ValueError("Template not found")
        
        response = client.post("/manager/v1/agents", json={
            "template": "nonexistent",
            "name": "Test"
        })
        
        assert response.status_code == 400
        data = response.json()
        assert "Template not found" in data["detail"]
    
    def test_create_agent_permission_denied(self, client, mock_manager):
        """Test agent creation without permission."""
        mock_manager.create_agent.side_effect = PermissionError("WA signature required")
        
        response = client.post("/manager/v1/agents", json={
            "template": "custom",
            "name": "Custom"
        })
        
        assert response.status_code == 403
        data = response.json()
        assert "WA signature required" in data["detail"]
    
    def test_create_agent_internal_error(self, client, mock_manager):
        """Test agent creation with internal error."""
        mock_manager.create_agent.side_effect = Exception("Internal error")
        
        response = client.post("/manager/v1/agents", json={
            "template": "scout",
            "name": "Scout"
        })
        
        assert response.status_code == 500
        data = response.json()
        assert "Failed to create agent" in data["detail"]
    
    def test_delete_agent_exists(self, client, mock_manager):
        """Test deleting existing agent."""
        agent = AgentInfo(
            agent_id="agent-scout",
            name="Scout",
            port=8081,
            template="scout",
            compose_file="/path/to/scout/docker-compose.yml"
        )
        
        mock_manager.agent_registry.get_agent_by_name.return_value = agent
        mock_manager.delete_agent = AsyncMock(return_value=True)
        
        response = client.delete("/manager/v1/agents/scout")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deleted"
        assert data["agent_id"] == "agent-scout"
        
        mock_manager.delete_agent.assert_called_once_with("agent-scout")
    
    def test_delete_agent_not_found(self, client, mock_manager):
        """Test deleting non-existent agent."""
        mock_manager.agent_registry.get_agent_by_name.return_value = None
        
        response = client.delete("/manager/v1/agents/nonexistent")
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"]
    
    def test_list_templates(self, client, mock_manager):
        """Test listing templates."""
        response = client.get("/manager/v1/templates")
        assert response.status_code == 200
        data = response.json()
        assert "scout" in data["templates"]
        assert "sage" in data["templates"]
        assert data["templates"]["scout"] == "Scout template"
        assert "scout" in data["pre_approved"]
        assert "sage" in data["pre_approved"]
    
    def test_get_allocated_ports(self, client, mock_manager):
        """Test getting allocated ports."""
        response = client.get("/manager/v1/ports/allocated")
        assert response.status_code == 200
        data = response.json()
        assert data["allocated"] == {"agent-test": 8080}
        assert 8888 in data["reserved"]
        assert 3000 in data["reserved"]
        assert data["range"]["start"] == 8080
        assert data["range"]["end"] == 8200