"""
Tests for stateless container routing.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from ciris_manager.core.routing import ManagedContainer, get_routable_containers


class TestManagedContainer:
    """Test the ManagedContainer dataclass."""
    
    def test_valid_container(self):
        """Test creating a valid container."""
        container = ManagedContainer(
            container_id="abc123def456",
            agent_id="datum-a3b7c9",
            host_port=8080,
            container_name="ciris-datum-a3b7c9"
        )
        
        assert container.container_id == "abc123def456"
        assert container.agent_id == "datum-a3b7c9"
        assert container.host_port == 8080
        assert container.container_name == "ciris-datum-a3b7c9"
    
    def test_nginx_upstream_name(self):
        """Test nginx upstream name generation."""
        container = ManagedContainer(
            container_id="abc123",
            agent_id="scout-b4d8f2",
            host_port=8081,
            container_name="ciris-scout-b4d8f2"
        )
        
        assert container.nginx_upstream_name == "agent_scout_b4d8f2"
    
    def test_nginx_server(self):
        """Test nginx server string generation."""
        container = ManagedContainer(
            container_id="abc123",
            agent_id="sage-c5e9g3",
            host_port=8082,
            container_name="ciris-sage-c5e9g3"
        )
        
        assert container.nginx_server == "ciris-sage-c5e9g3:8082"
    
    def test_to_legacy_dict(self):
        """Test conversion to legacy dictionary format."""
        container = ManagedContainer(
            container_id="abc123def456",
            agent_id="datum-a3b7c9",
            host_port=8080,
            container_name="ciris-datum-a3b7c9"
        )
        
        legacy = container.to_legacy_dict()
        assert legacy == {
            'agent_id': 'datum-a3b7c9',
            'container_name': 'ciris-datum-a3b7c9',
            'api_port': 8080,
            'container_id': 'abc123def456',
            'status': 'running',
        }
    
    def test_invalid_agent_id(self):
        """Test that empty agent_id raises error."""
        with pytest.raises(ValueError, match="Agent ID required"):
            ManagedContainer(
                container_id="abc123",
                agent_id="",
                host_port=8080,
                container_name="ciris-test"
            )
    
    def test_invalid_port_zero(self):
        """Test that port 0 raises error."""
        with pytest.raises(ValueError, match="Invalid port: 0"):
            ManagedContainer(
                container_id="abc123",
                agent_id="test",
                host_port=0,
                container_name="ciris-test"
            )
    
    def test_invalid_port_too_high(self):
        """Test that port > 65535 raises error."""
        with pytest.raises(ValueError, match="Invalid port: 70000"):
            ManagedContainer(
                container_id="abc123",
                agent_id="test",
                host_port=70000,
                container_name="ciris-test"
            )
    
    def test_invalid_container_name(self):
        """Test that non-ciris container name raises error."""
        with pytest.raises(ValueError, match="Container name must start with 'ciris-'"):
            ManagedContainer(
                container_id="abc123",
                agent_id="test",
                host_port=8080,
                container_name="other-container"
            )


class TestGetRoutableContainers:
    """Test the get_routable_containers function."""
    
    @patch('docker.from_env')
    def test_docker_connection_failure(self, mock_from_env):
        """Test handling of Docker connection failure."""
        mock_from_env.side_effect = Exception("Cannot connect to Docker")
        
        containers = get_routable_containers()
        assert containers == []
    
    @patch('docker.from_env')
    def test_no_containers(self, mock_from_env):
        """Test when no containers are running."""
        mock_client = Mock()
        mock_client.containers.list.return_value = []
        mock_from_env.return_value = mock_client
        
        containers = get_routable_containers()
        assert containers == []
    
    @patch('docker.from_env')
    def test_skip_non_ciris_containers(self, mock_from_env):
        """Test that non-ciris containers are skipped."""
        mock_container = MagicMock()
        mock_container.name = "other-app"
        
        mock_client = Mock()
        mock_client.containers.list.return_value = [mock_container]
        mock_from_env.return_value = mock_client
        
        containers = get_routable_containers()
        assert containers == []
    
    @patch('docker.from_env')
    def test_skip_infrastructure_containers(self, mock_from_env):
        """Test that infrastructure containers are skipped."""
        infra_names = ['ciris-nginx', 'ciris-gui', 'ciris-gui-dev', 'ciris-manager']
        mock_containers = []
        
        for name in infra_names:
            mock_container = MagicMock()
            mock_container.name = name
            mock_containers.append(mock_container)
        
        mock_client = Mock()
        mock_client.containers.list.return_value = mock_containers
        mock_from_env.return_value = mock_client
        
        containers = get_routable_containers()
        assert containers == []
    
    @patch('docker.from_env')
    def test_valid_agent_container(self, mock_from_env):
        """Test discovering a valid agent container."""
        mock_container = MagicMock()
        mock_container.name = "ciris-datum-a3b7c9"
        mock_container.id = "abc123def456"
        # Mock container attributes based on actual implementation
        mock_container.labels = MagicMock()
        mock_container.labels.get.return_value = 'datum-a3b7c9'
        mock_container.ports = MagicMock()
        mock_container.ports.get.return_value = [{'HostPort': '8081'}]
        
        mock_client = Mock()
        mock_client.containers.list.return_value = [mock_container]
        mock_from_env.return_value = mock_client
        
        containers = get_routable_containers()
        assert len(containers) == 1
        assert containers[0].agent_id == "datum-a3b7c9"
        assert containers[0].host_port == 8081
        assert containers[0].container_name == "ciris-datum-a3b7c9"
    
    @patch('docker.from_env')
    def test_skip_container_without_agent_id(self, mock_from_env):
        """Test that containers without CIRIS_AGENT_ID are skipped."""
        mock_container = MagicMock()
        mock_container.name = "ciris-test"
        # Container without agent ID label
        mock_container.labels = MagicMock()
        mock_container.labels.get.return_value = None
        
        mock_client = Mock()
        mock_client.containers.list.return_value = [mock_container]
        mock_from_env.return_value = mock_client
        
        containers = get_routable_containers()
        assert containers == []
    
    @patch('docker.from_env')
    def test_skip_container_without_port_mapping(self, mock_from_env):
        """Test that containers without port mappings are skipped."""
        mock_container = MagicMock()
        mock_container.name = "ciris-datum"
        mock_container.id = "abc123"
        # Container with agent ID but no ports
        mock_container.labels = MagicMock()
        mock_container.labels.get.return_value = 'datum'
        mock_container.ports = MagicMock()
        mock_container.ports.get.return_value = []  # No port mappings
        
        mock_client = Mock()
        mock_client.containers.list.return_value = [mock_container]
        mock_from_env.return_value = mock_client
        
        containers = get_routable_containers()
        assert containers == []
    
    @patch('docker.from_env')
    def test_multiple_valid_containers(self, mock_from_env):
        """Test discovering multiple valid agent containers."""
        mock_containers = []
        
        # First container
        container1 = MagicMock()
        container1.name = "ciris-datum-a3b7c9"
        container1.id = "abc123"
        container1.labels = MagicMock()
        container1.labels.get.return_value = 'datum-a3b7c9'
        container1.ports = MagicMock()
        container1.ports.get.return_value = [{'HostPort': '8080'}]
        mock_containers.append(container1)
        
        # Second container
        container2 = MagicMock()
        container2.name = "ciris-scout-b4d8f2"
        container2.id = "def456"
        container2.labels = MagicMock()
        container2.labels.get.return_value = 'scout-b4d8f2'
        container2.ports = MagicMock()
        container2.ports.get.return_value = [{'HostPort': '8081'}]
        mock_containers.append(container2)
        
        # Invalid container (should be skipped)
        container3 = MagicMock()
        container3.name = "ciris-invalid"
        container3.labels = MagicMock()
        container3.labels.get.return_value = None  # No agent ID label
        mock_containers.append(container3)
        
        mock_client = Mock()
        mock_client.containers.list.return_value = mock_containers
        mock_from_env.return_value = mock_client
        
        containers = get_routable_containers()
        assert len(containers) == 2
        assert containers[0].agent_id == "datum-a3b7c9"
        assert containers[0].host_port == 8080
        assert containers[1].agent_id == "scout-b4d8f2"
        assert containers[1].host_port == 8081
    
    @patch('docker.from_env')
    def test_container_with_malformed_env(self, mock_from_env):
        """Test handling of containers with malformed environment variables."""
        mock_container = MagicMock()
        mock_container.name = "ciris-test"
        # Container with valid label and ports
        mock_container.labels = MagicMock()
        mock_container.labels.get.return_value = 'test'
        mock_container.ports = MagicMock()
        mock_container.ports.get.return_value = [{'HostPort': '8080'}]
        
        mock_client = Mock()
        mock_client.containers.list.return_value = [mock_container]
        mock_from_env.return_value = mock_client
        
        # Should handle gracefully and still find the container
        containers = get_routable_containers()
        assert len(containers) == 1
        assert containers[0].agent_id == "test"
    
    @patch('docker.from_env')
    def test_exception_during_container_processing(self, mock_from_env):
        """Test handling of exceptions during container processing."""
        # One good container
        good_container = MagicMock()
        good_container.name = "ciris-datum"
        good_container.id = "abc123"
        good_container.labels = MagicMock()
        good_container.labels.get.return_value = 'datum'
        good_container.ports = MagicMock()
        good_container.ports.get.return_value = [{'HostPort': '8080'}]
        
        # One container that will cause an exception
        bad_container = MagicMock()
        bad_container.name = "ciris-bad"
        bad_container.labels = MagicMock()
        bad_container.labels.get.side_effect = AttributeError("Bad container")  # This will cause AttributeError
        
        mock_client = Mock()
        mock_client.containers.list.return_value = [bad_container, good_container]
        mock_from_env.return_value = mock_client
        
        # Should handle exception and still return the good container
        containers = get_routable_containers()
        assert len(containers) == 1
        assert containers[0].agent_id == "datum"
    
    @patch('docker.from_env')
    def test_container_list_exception(self, mock_from_env):
        """Test handling when docker.containers.list raises exception."""
        mock_client = Mock()
        mock_client.containers.list.side_effect = Exception("Docker API error")
        mock_from_env.return_value = mock_client
        
        # Should return empty list on error
        containers = get_routable_containers()
        assert len(containers) == 0
    
    @patch('docker.from_env')
    def test_env_var_without_equals(self, mock_from_env):
        """Test handling environment variable without equals sign."""
        mock_container = MagicMock()
        mock_container.name = "ciris-test"
        mock_container.id = "abc123"
        mock_container.status = "running"
        mock_container.labels = MagicMock()
        mock_container.labels.get.return_value = None  # No label
        
        # Attrs with env vars, one without equals
        mock_container.attrs = {
            'Config': {
                'Env': ['INVALID_VAR', 'CIRIS_AGENT_ID=test-agent']
            }
        }
        mock_container.ports = MagicMock()
        mock_container.ports.get.return_value = [{'HostPort': '8080'}]
        
        mock_client = Mock()
        mock_client.containers.list.return_value = [mock_container]
        mock_from_env.return_value = mock_client
        
        # Should handle malformed env var and still find agent ID
        containers = get_routable_containers()
        assert len(containers) == 1
        assert containers[0].agent_id == "test-agent"


class TestValidateRoutingSetup:
    """Test cases for validate_routing_setup function."""
    
    @patch('docker.from_env')
    def test_validate_routing_setup_success(self, mock_from_env):
        """Test successful routing validation."""
        from ciris_manager.core.routing import validate_routing_setup
        
        # Create mock containers
        running_container = Mock()
        running_container.name = "ciris-datum"
        running_container.status = "running"
        running_container.labels = {"ai.ciris.agent.id": "datum"}
        running_container.ports = {"8080/tcp": [{"HostPort": "8080"}]}
        
        stopped_container = Mock()
        stopped_container.name = "ciris-scout"
        stopped_container.status = "exited"
        stopped_container.labels = {"ai.ciris.agent.id": "scout"}
        
        no_label_container = Mock()
        no_label_container.name = "ciris-test"
        no_label_container.status = "running"
        no_label_container.labels = {}
        
        no_port_container = Mock()
        no_port_container.name = "ciris-noportz"
        no_port_container.status = "running"
        no_port_container.labels = {"ai.ciris.agent.id": "noport"}
        no_port_container.ports = {}
        
        mock_client = Mock()
        mock_client.containers.list.return_value = [
            running_container,
            stopped_container,
            no_label_container,
            no_port_container
        ]
        mock_from_env.return_value = mock_client
        
        result = validate_routing_setup()
        
        assert result['routable_count'] == 1
        assert len(result['skipped']) == 3
        assert len(result['errors']) == 0
        
        # Check skipped reasons
        skipped_reasons = [s['reason'] for s in result['skipped']]
        assert any('Not running' in r for r in skipped_reasons)
        assert any('Missing ai.ciris.agent.id label' in r for r in skipped_reasons)
        assert any('No accessible port' in r for r in skipped_reasons)
    
    @patch('docker.from_env')
    def test_validate_routing_setup_docker_error(self, mock_from_env):
        """Test routing validation with Docker error."""
        from ciris_manager.core.routing import validate_routing_setup
        
        mock_from_env.side_effect = Exception("Docker connection failed")
        
        result = validate_routing_setup()
        
        assert result['routable_count'] == 0
        assert len(result['errors']) == 1
        assert "Docker connection failed" in result['errors'][0]
    
    @patch('docker.from_env')
    def test_validate_routing_setup_multiple_ports(self, mock_from_env):
        """Test validation with container having multiple ports."""
        from ciris_manager.core.routing import validate_routing_setup
        
        container = Mock()
        container.name = "ciris-multi"
        container.status = "running"
        container.labels = {"ai.ciris.agent.id": "multi"}
        container.ports = {
            "8080/tcp": None,  # No binding
            "8081/tcp": [{"HostPort": "8081"}],  # Has binding
            "8082/tcp": None
        }
        
        mock_client = Mock()
        mock_client.containers.list.return_value = [container]
        mock_from_env.return_value = mock_client
        
        result = validate_routing_setup()
        
        assert result['routable_count'] == 1
        assert len(result['skipped']) == 0