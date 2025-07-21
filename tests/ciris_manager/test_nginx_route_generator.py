"""
Unit tests for NginxRouteGenerator.
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, AsyncMock
from ciris_manager.nginx_route_generator import NginxRouteGenerator


class TestNginxRouteGenerator:
    """Test cases for NginxRouteGenerator."""
    
    @pytest.fixture
    def temp_config_dir(self):
        """Create a temporary directory for nginx configs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)
    
    @pytest.fixture
    def generator(self, temp_config_dir):
        """Create NginxRouteGenerator instance with temp directory."""
        return NginxRouteGenerator(str(temp_config_dir))
    
    def test_initialization(self, generator, temp_config_dir):
        """Test NginxRouteGenerator initialization."""
        assert generator.nginx_config_dir == temp_config_dir
    
    def test_generate_agent_config(self, generator):
        """Test generating nginx config for an agent."""
        config = generator.generate_agent_config(
            agent_id="datum",
            container_name="ciris-agent-datum",
            port=8080
        )
        
        # Check required elements
        assert "location ~ ^/api/datum/" in config
        assert "proxy_pass http://ciris-agent-datum:8080/" in config
        assert "proxy_http_version 1.1" in config
        assert "proxy_set_header Upgrade" in config
        assert "proxy_set_header Host" in config
        assert "proxy_read_timeout 86400" in config
        
        # Check OAuth callback route
        assert "location = /oauth/datum/callback" in config
    
    def test_generate_agent_config_different_ports(self, generator):
        """Test generating configs for agents on different ports."""
        config1 = generator.generate_agent_config("agent1", "container1", 8080)
        config2 = generator.generate_agent_config("agent2", "container2", 8081)
        
        assert "proxy_pass http://container1:8080/" in config1
        assert "proxy_pass http://container2:8081/" in config2
        assert "/api/agent1/" in config1
        assert "/api/agent2/" in config2
    
    def test_write_agent_config(self, generator, temp_config_dir):
        """Test writing agent config to file."""
        config_file = generator.write_agent_config(
            agent_id="scout",
            container_name="ciris-agent-scout",
            port=8081
        )
        
        # Check file was created
        assert config_file.exists()
        assert config_file.name == "scout.conf"
        assert config_file.parent == temp_config_dir
        
        # Check content
        content = config_file.read_text()
        assert "location ~ ^/api/scout/" in content
        assert "proxy_pass http://ciris-agent-scout:8081/" in content
    
    def test_write_agent_config_creates_directory(self, temp_config_dir):
        """Test that write_agent_config creates directory if needed."""
        # Use a subdirectory that doesn't exist
        sub_dir = temp_config_dir / "subdir"
        generator = NginxRouteGenerator(str(sub_dir))
        
        config_file = generator.write_agent_config("test", "test-container", 8080)
        
        assert sub_dir.exists()
        assert config_file.exists()
    
    def test_remove_agent_config_exists(self, generator, temp_config_dir):
        """Test removing existing agent config."""
        # First write a config
        generator.write_agent_config("datum", "ciris-agent-datum", 8080)
        config_file = temp_config_dir / "datum.conf"
        assert config_file.exists()
        
        # Remove it
        result = generator.remove_agent_config("datum")
        assert result is True
        assert not config_file.exists()
    
    def test_remove_agent_config_not_exists(self, generator):
        """Test removing non-existent agent config."""
        result = generator.remove_agent_config("nonexistent")
        assert result is False
    
    def test_generate_include_directive(self, generator):
        """Test generating nginx include directive."""
        directive = generator.generate_include_directive()
        assert directive == f"include {generator.nginx_config_dir}/*.conf;"
    
    def test_generate_include_directive_custom_path(self):
        """Test include directive with custom path."""
        generator = NginxRouteGenerator("/custom/path")
        directive = generator.generate_include_directive()
        assert directive == "include /custom/path/*.conf;"
    
    @pytest.mark.asyncio
    async def test_reload_nginx_success(self, generator):
        """Test successful nginx reload."""
        with patch('asyncio.create_subprocess_exec') as mock_subprocess:
            # Mock successful test and reload
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(b"", b""))
            mock_subprocess.return_value = mock_process
            
            result = await generator.reload_nginx()
            assert result is True
            
            # Check both test and reload were called
            assert mock_subprocess.call_count == 2
            
            # First call should be config test
            first_call = mock_subprocess.call_args_list[0]
            assert first_call[0][0:4] == ("docker", "exec", "ciris-nginx", "nginx")
            assert first_call[0][4] == "-t"
            
            # Second call should be reload
            second_call = mock_subprocess.call_args_list[1]
            assert second_call[0][0:5] == ("docker", "exec", "ciris-nginx", "nginx", "-s")
            assert second_call[0][5] == "reload"
    
    @pytest.mark.asyncio
    async def test_reload_nginx_test_failure(self, generator):
        """Test nginx reload when config test fails."""
        with patch('asyncio.create_subprocess_exec') as mock_subprocess:
            # Mock failed test
            mock_process = AsyncMock()
            mock_process.returncode = 1
            mock_process.communicate = AsyncMock(return_value=(b"", b"nginx: configuration file test failed"))
            mock_subprocess.return_value = mock_process
            
            result = await generator.reload_nginx()
            assert result is False
            
            # Should only call test, not reload
            assert mock_subprocess.call_count == 1
    
    @pytest.mark.asyncio
    async def test_reload_nginx_reload_failure(self, generator):
        """Test nginx reload when reload command fails."""
        with patch('asyncio.create_subprocess_exec') as mock_subprocess:
            # Mock successful test but failed reload
            mock_test_process = AsyncMock()
            mock_test_process.returncode = 0
            mock_test_process.communicate = AsyncMock(return_value=(b"", b""))
            
            mock_reload_process = AsyncMock()
            mock_reload_process.returncode = 1
            mock_reload_process.communicate = AsyncMock(return_value=(b"", b"reload failed"))
            
            mock_subprocess.side_effect = [mock_test_process, mock_reload_process]
            
            result = await generator.reload_nginx()
            assert result is False
            assert mock_subprocess.call_count == 2
    
    @pytest.mark.asyncio
    async def test_reload_nginx_custom_container(self, generator):
        """Test nginx reload with custom container name."""
        with patch('asyncio.create_subprocess_exec') as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(b"", b""))
            mock_subprocess.return_value = mock_process
            
            result = await generator.reload_nginx(container_name="custom-nginx")
            assert result is True
            
            # Check custom container name was used
            first_call = mock_subprocess.call_args_list[0]
            assert first_call[0][2] == "custom-nginx"
    
    @pytest.mark.asyncio
    async def test_reload_nginx_exception(self, generator):
        """Test nginx reload with exception."""
        with patch('asyncio.create_subprocess_exec') as mock_subprocess:
            mock_subprocess.side_effect = Exception("Docker not available")
            
            result = await generator.reload_nginx()
            assert result is False
    
    def test_multiple_agent_configs(self, generator, temp_config_dir):
        """Test managing multiple agent configs."""
        # Write configs for multiple agents
        agents = [
            ("datum", "ciris-agent-datum", 8080),
            ("scout", "ciris-agent-scout", 8081),
            ("sage", "ciris-agent-sage", 8082),
        ]
        
        for agent_id, container, port in agents:
            generator.write_agent_config(agent_id, container, port)
        
        # Check all files exist
        config_files = list(temp_config_dir.glob("*.conf"))
        assert len(config_files) == 3
        
        # Check each file has correct content
        for agent_id, container, port in agents:
            config_file = temp_config_dir / f"{agent_id}.conf"
            content = config_file.read_text()
            assert f"/api/{agent_id}/" in content
            assert f"http://{container}:{port}/" in content
        
        # Remove one config
        generator.remove_agent_config("scout")
        
        # Check only 2 remain
        config_files = list(temp_config_dir.glob("*.conf"))
        assert len(config_files) == 2
        assert not (temp_config_dir / "scout.conf").exists()
    
    def test_agent_id_sanitization(self, generator):
        """Test that agent IDs are used as-is in routes."""
        config = generator.generate_agent_config(
            agent_id="test-agent_123",
            container_name="test-container",
            port=8080
        )
        
        # Agent ID should be preserved exactly
        assert "location ~ ^/api/test-agent_123/" in config
        assert "location = /oauth/test-agent_123/callback" in config