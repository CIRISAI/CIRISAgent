"""
Unit tests for Docker discovery module.
"""

import pytest
from unittest.mock import Mock, MagicMock
from ciris_manager.docker_discovery import DockerAgentDiscovery


class TestDockerDiscovery:
    """Test cases for DockerAgentDiscovery."""
    
    def test_display_name_derivation(self):
        """Test deriving display names from agent IDs."""
        discovery = DockerAgentDiscovery()
        discovery.client = Mock()  # Mock the docker client
        
        # Test cases for name derivation
        test_cases = [
            # Development agents (no suffix)
            {
                "agent_id": "datum",
                "expected_name": "Datum",
                "env_dict": {"CIRIS_AGENT_ID": "datum"},
                "container_name": "ciris-agent-datum"
            },
            {
                "agent_id": "wise-authority",
                "expected_name": "Wise Authority", 
                "env_dict": {"CIRIS_AGENT_ID": "wise-authority"},
                "container_name": "ciris-agent-wise-authority"
            },
            # Production agents (with 6-char suffix)
            {
                "agent_id": "datum-a3b7c9",
                "expected_name": "Datum (a3b7c9)",
                "env_dict": {"CIRIS_AGENT_ID": "datum-a3b7c9"},
                "container_name": "ciris-agent-datum-a3b7c9"
            },
            {
                "agent_id": "wise-authority-x9k2m4",
                "expected_name": "Wise Authority (x9k2m4)",
                "env_dict": {"CIRIS_AGENT_ID": "wise-authority-x9k2m4"},
                "container_name": "ciris-agent-wise-authority-x9k2m4"
            },
            # Non-standard formats (should still work but not follow convention)
            {
                "agent_id": "datum-123",  # 3 chars, not 6
                "expected_name": "Datum 123",
                "env_dict": {"CIRIS_AGENT_ID": "datum-123"},
                "container_name": "ciris-agent-datum-123"
            },
            {
                "agent_id": "datum-a3b7",  # 4 chars (old format) - title() capitalizes each word
                "expected_name": "Datum A3B7",  # title() makes it A3B7 not A3b7
                "env_dict": {"CIRIS_AGENT_ID": "datum-a3b7"},
                "container_name": "ciris-agent-datum-a3b7"
            },
            {
                "agent_id": "datum-toolong",  # More than 6 chars
                "expected_name": "Datum Toolong",
                "env_dict": {"CIRIS_AGENT_ID": "datum-toolong"},
                "container_name": "ciris-agent-datum-toolong"
            }
        ]
        
        for test_case in test_cases:
            # Create mock container
            container = Mock()
            container.name = test_case["container_name"]
            container.id = "abcd1234567890"
            container.status = "running"
            
            # Mock container attributes
            container.attrs = {
                "Config": {
                    "Env": [f"{k}={v}" for k, v in test_case["env_dict"].items()],
                    "Labels": {},
                    "Image": "ciris:latest"
                },
                "State": {
                    "Status": "running",
                    "Running": True,
                    "ExitCode": 0,
                    "StartedAt": "2024-01-01T00:00:00Z"
                },
                "NetworkSettings": {
                    "Ports": {"8080/tcp": [{"HostPort": "8080"}]}
                },
                "Created": "2024-01-01T00:00:00Z",
                "HostConfig": {
                    "RestartPolicy": {"Name": "unless-stopped"}
                }
            }
            
            # Extract agent info
            agent_info = discovery._extract_agent_info(container, test_case["env_dict"])
            
            # Verify
            assert agent_info is not None
            assert agent_info["agent_id"] == test_case["agent_id"]
            assert agent_info["agent_name"] == test_case["expected_name"]
            
    def test_requires_ciris_agent_id(self):
        """Test that containers without CIRIS_AGENT_ID are rejected."""
        discovery = DockerAgentDiscovery()
        discovery.client = Mock()
        
        container = Mock()
        container.name = "some-container"
        container.id = "abcd1234567890"
        container.status = "running"
        
        container.attrs = {
            "Config": {"Env": ["OTHER_VAR=value"], "Labels": {}, "Image": "ciris:latest"},
            "State": {"Status": "running", "Running": True},
            "NetworkSettings": {"Ports": {}},
            "Created": "2024-01-01T00:00:00Z",
            "HostConfig": {"RestartPolicy": {"Name": "unless-stopped"}}
        }
        
        # Container without CIRIS_AGENT_ID should return None
        env_dict = {"OTHER_VAR": "value"}
        agent_info = discovery._extract_agent_info(container, env_dict)
        
        assert agent_info is None
        
    def test_discover_agents_filters_correctly(self):
        """Test that discover_agents only returns containers with CIRIS_AGENT_ID."""
        discovery = DockerAgentDiscovery()
        discovery.client = Mock()
        
        # Create mock containers - mix of CIRIS and non-CIRIS
        container1 = Mock()  # Valid CIRIS agent
        container1.name = "ciris-agent-datum"
        container1.attrs = {
            "Config": {"Env": ["CIRIS_AGENT_ID=datum", "CIRIS_MOCK_LLM=true"]}
        }
        
        container2 = Mock()  # Non-CIRIS container
        container2.name = "postgres"
        container2.attrs = {
            "Config": {"Env": ["POSTGRES_DB=ciris"]}
        }
        
        container3 = Mock()  # Another valid CIRIS agent with 6-char suffix
        container3.name = "ciris-agent-scout-a3b7c9"
        container3.attrs = {
            "Config": {"Env": ["CIRIS_AGENT_ID=scout-a3b7c9"]}
        }
        
        discovery.client.containers.list = Mock(return_value=[container1, container2, container3])
        
        # Mock _extract_agent_info to return simple dict for valid agents
        def mock_extract(container, env_dict):
            if "CIRIS_AGENT_ID" in env_dict:
                return {"agent_id": env_dict["CIRIS_AGENT_ID"], "container_name": container.name}
            return None
            
        discovery._extract_agent_info = mock_extract
        
        # Discover agents
        agents = discovery.discover_agents()
        
        # Should only find the two CIRIS agents
        assert len(agents) == 2
        assert agents[0]["agent_id"] == "datum"
        assert agents[1]["agent_id"] == "scout-a3b7c9"