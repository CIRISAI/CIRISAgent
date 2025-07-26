"""
Additional tests for Docker discovery module to improve coverage.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from ciris_manager.docker_discovery import DockerAgentDiscovery
import docker.errors


class TestDockerDiscoveryCoverage:
    """Additional test cases for DockerAgentDiscovery to improve coverage."""
    
    def test_init_no_docker_client(self):
        """Test initialization when Docker client cannot be created."""
        with patch('docker.from_env', side_effect=Exception("Docker not available")):
            discovery = DockerAgentDiscovery()
            assert discovery.client is None
    
    def test_discover_agents_no_client(self):
        """Test discover_agents when no Docker client is available."""
        discovery = DockerAgentDiscovery()
        discovery.client = None
        
        agents = discovery.discover_agents()
        assert agents == []
    
    def test_extract_agent_info_exception(self):
        """Test _extract_agent_info handles exceptions gracefully."""
        discovery = DockerAgentDiscovery()
        discovery.client = Mock()
        
        # Create a container that will raise an exception when accessing attrs
        container = Mock()
        container.name = "ciris-agent-bad"
        container.attrs = Mock(side_effect=Exception("Attribute error"))
        
        result = discovery._extract_agent_info(container, {})
        assert result is None
    
    def test_get_agent_logs_success(self):
        """Test successful log retrieval."""
        discovery = DockerAgentDiscovery()
        mock_client = Mock()
        discovery.client = mock_client
        
        # Mock container with logs
        mock_container = Mock()
        mock_container.logs.return_value = b"Log line 1\nLog line 2\n"
        mock_client.containers.get.return_value = mock_container
        
        logs = discovery.get_agent_logs("ciris-agent-test", lines=50)
        assert logs == "Log line 1\nLog line 2\n"
        mock_container.logs.assert_called_once_with(tail=50)
    
    def test_get_agent_logs_no_client(self):
        """Test get_agent_logs when no Docker client is available."""
        discovery = DockerAgentDiscovery()
        discovery.client = None
        
        logs = discovery.get_agent_logs("ciris-agent-test")
        assert logs == ""
    
    def test_get_agent_logs_container_not_found(self):
        """Test get_agent_logs when container doesn't exist."""
        discovery = DockerAgentDiscovery()
        mock_client = Mock()
        discovery.client = mock_client
        
        mock_client.containers.get.side_effect = docker.errors.NotFound("Container not found")
        
        logs = discovery.get_agent_logs("ciris-agent-missing")
        assert logs == ""
    
    def test_get_agent_logs_exception(self):
        """Test get_agent_logs handles general exceptions."""
        discovery = DockerAgentDiscovery()
        mock_client = Mock()
        discovery.client = mock_client
        
        mock_client.containers.get.side_effect = Exception("Docker API error")
        
        logs = discovery.get_agent_logs("ciris-agent-error")
        assert logs == ""
    
    def test_restart_agent_success(self):
        """Test successful agent restart."""
        discovery = DockerAgentDiscovery()
        mock_client = Mock()
        discovery.client = mock_client
        
        mock_container = Mock()
        mock_container.restart.return_value = None
        mock_client.containers.get.return_value = mock_container
        
        result = discovery.restart_agent("ciris-agent-test")
        assert result is True
        mock_container.restart.assert_called_once()
    
    def test_restart_agent_no_client(self):
        """Test restart_agent when no Docker client is available."""
        discovery = DockerAgentDiscovery()
        discovery.client = None
        
        result = discovery.restart_agent("ciris-agent-test")
        assert result is False
    
    def test_restart_agent_container_not_found(self):
        """Test restart_agent when container doesn't exist."""
        discovery = DockerAgentDiscovery()
        mock_client = Mock()
        discovery.client = mock_client
        
        mock_client.containers.get.side_effect = docker.errors.NotFound("Container not found")
        
        result = discovery.restart_agent("ciris-agent-missing")
        assert result is False
    
    def test_restart_agent_exception(self):
        """Test restart_agent handles exceptions."""
        discovery = DockerAgentDiscovery()
        mock_client = Mock()
        discovery.client = mock_client
        
        mock_container = Mock()
        mock_container.restart.side_effect = Exception("Restart failed")
        mock_client.containers.get.return_value = mock_container
        
        result = discovery.restart_agent("ciris-agent-error")
        assert result is False
    
    def test_stop_agent_success(self):
        """Test successful agent stop."""
        discovery = DockerAgentDiscovery()
        mock_client = Mock()
        discovery.client = mock_client
        
        mock_container = Mock()
        mock_container.stop.return_value = None
        mock_client.containers.get.return_value = mock_container
        
        result = discovery.stop_agent("ciris-agent-test")
        assert result is True
        mock_container.stop.assert_called_once()
    
    def test_stop_agent_no_client(self):
        """Test stop_agent when no Docker client is available."""
        discovery = DockerAgentDiscovery()
        discovery.client = None
        
        result = discovery.stop_agent("ciris-agent-test")
        assert result is False
    
    def test_stop_agent_container_not_found(self):
        """Test stop_agent when container doesn't exist."""
        discovery = DockerAgentDiscovery()
        mock_client = Mock()
        discovery.client = mock_client
        
        mock_client.containers.get.side_effect = docker.errors.NotFound("Container not found")
        
        result = discovery.stop_agent("ciris-agent-missing")
        assert result is False
    
    def test_stop_agent_exception(self):
        """Test stop_agent handles exceptions."""
        discovery = DockerAgentDiscovery()
        mock_client = Mock()
        discovery.client = mock_client
        
        mock_container = Mock()
        mock_container.stop.side_effect = Exception("Stop failed")
        mock_client.containers.get.return_value = mock_container
        
        result = discovery.stop_agent("ciris-agent-error")
        assert result is False
    
    def test_discover_agents_container_list_exception(self):
        """Test discover_agents when container list raises exception."""
        discovery = DockerAgentDiscovery()
        mock_client = Mock()
        discovery.client = mock_client
        
        mock_client.containers.list.side_effect = Exception("Docker API error")
        
        agents = discovery.discover_agents()
        assert agents == []
    
    def test_extract_agent_info_missing_fields(self):
        """Test _extract_agent_info with missing container fields."""
        discovery = DockerAgentDiscovery()
        discovery.client = Mock()
        
        container = Mock()
        container.name = "ciris-agent-test"
        container.id = "abc123"
        container.status = "running"
        
        # Minimal attrs - missing many expected fields
        container.attrs = {
            "Config": {
                "Env": ["CIRIS_AGENT_ID=test"],
                "Labels": {}
            },
            "State": {},  # Missing Status, Running, etc.
            "NetworkSettings": {},  # Missing Ports
            "HostConfig": {}  # Missing RestartPolicy
        }
        
        env_dict = {"CIRIS_AGENT_ID": "test"}
        agent_info = discovery._extract_agent_info(container, env_dict)
        
        # Should still extract basic info
        assert agent_info is not None
        assert agent_info["agent_id"] == "test"
        assert agent_info["container_name"] == "ciris-agent-test"
        assert agent_info["status"] == "running"
        assert agent_info["api_port"] is None  # No port info
    
    def test_extract_agent_info_with_ports(self):
        """Test _extract_agent_info correctly extracts port information."""
        discovery = DockerAgentDiscovery()
        discovery.client = Mock()
        
        container = Mock()
        container.name = "ciris-agent-test"
        container.id = "abc123"
        container.status = "running"
        
        container.attrs = {
            "Config": {
                "Env": ["CIRIS_AGENT_ID=test", "CIRIS_API_PORT=8080"],
                "Labels": {"ai.ciris.template": "scout"}
            },
            "State": {
                "Status": "running",
                "Running": True,
                "ExitCode": 0
            },
            "NetworkSettings": {
                "Ports": {
                    "8080/tcp": [{"HostPort": "8081"}]  # Host port different from container port
                }
            },
            "HostConfig": {
                "RestartPolicy": {"Name": "unless-stopped"}
            }
        }
        
        env_dict = {"CIRIS_AGENT_ID": "test", "CIRIS_API_PORT": "8080"}
        agent_info = discovery._extract_agent_info(container, env_dict)
        
        assert agent_info is not None
        assert agent_info["api_port"] == "8081"  # Port is returned as string