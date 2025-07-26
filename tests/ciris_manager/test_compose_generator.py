"""
Unit tests for ComposeGenerator.
"""

import pytest
import tempfile
import yaml
from pathlib import Path
from ciris_manager.compose_generator import ComposeGenerator


class TestComposeGenerator:
    """Test cases for ComposeGenerator."""
    
    @pytest.fixture
    def generator(self):
        """Create ComposeGenerator instance."""
        return ComposeGenerator(
            docker_registry="ghcr.io/cirisai",
            default_image="ciris-agent:latest"
        )
    
    @pytest.fixture
    def temp_agent_dir(self):
        """Create temporary agent directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)
    
    def test_initialization(self, generator):
        """Test ComposeGenerator initialization."""
        assert generator.docker_registry == "ghcr.io/cirisai"
        assert generator.default_image == "ciris-agent:latest"
    
    def test_generate_compose_basic(self, generator, temp_agent_dir):
        """Test basic compose generation."""
        compose = generator.generate_compose(
            agent_id="agent-scout",
            agent_name="Scout",
            port=8081,
            template="scout",
            agent_dir=temp_agent_dir
        )
        
        # Check structure
        assert "version" in compose
        assert compose["version"] == "3.8"
        assert "services" in compose
        assert "agent-scout" in compose["services"]
        assert "networks" in compose
        
        # Check service config
        service = compose["services"]["agent-scout"]
        assert service["container_name"] == "ciris-agent-scout"
        # Now uses build context instead of image
        assert "build" in service
        assert service["build"]["context"] == "/home/ciris/ciris/forks/CIRISAgent"
        assert service["build"]["dockerfile"] == "Dockerfile"
        assert service["ports"] == ["8081:8080"]
        assert service["restart"] == "unless-stopped"
        
        # Check environment
        env = service["environment"]
        # CIRIS_AGENT_NAME removed - display name derived from agent_id
        assert env["CIRIS_AGENT_ID"] == "agent-scout"
        assert env["CIRIS_TEMPLATE"] == "scout"
        assert env["CIRIS_API_HOST"] == "0.0.0.0"
        assert env["CIRIS_API_PORT"] == "8080"
        assert env["CIRIS_USE_MOCK_LLM"] == "true"
        
        # Check volumes
        volumes = service["volumes"]
        assert f"{temp_agent_dir}/data:/app/data" in volumes
        assert f"{temp_agent_dir}/logs:/app/logs" in volumes
        assert "/home/ciris/shared/oauth:/home/ciris/shared/oauth:ro" in volumes
        
        # Check healthcheck
        health = service["healthcheck"]
        assert health["test"] == ["CMD", "curl", "-f", "http://localhost:8080/v1/system/health"]
        assert health["interval"] == "30s"
        assert health["timeout"] == "10s"
        assert health["retries"] == 3
        assert health["start_period"] == "40s"
        
        # Check logging
        logging = service["logging"]
        assert logging["driver"] == "json-file"
        assert logging["options"]["max-size"] == "10m"
        assert logging["options"]["max-file"] == "3"
        
        # Check network  
        network = compose["networks"]["default"]
        assert network["name"] == "ciris-agent-scout-network"
    
    def test_generate_compose_with_environment(self, generator, temp_agent_dir):
        """Test compose generation with additional environment."""
        compose = generator.generate_compose(
            agent_id="agent-scout",
            agent_name="Scout",
            port=8081,
            template="scout",
            agent_dir=temp_agent_dir,
            environment={
                "CUSTOM_VAR": "custom_value",
                "CIRIS_USE_MOCK_LLM": "false",  # Override default
                "DEBUG": "true"
            }
        )
        
        env = compose["services"]["agent-scout"]["environment"]
        assert env["CUSTOM_VAR"] == "custom_value"
        assert env["CIRIS_USE_MOCK_LLM"] == "false"  # Overridden
        assert env["DEBUG"] == "true"
        # CIRIS_AGENT_NAME removed - display name derived from agent_id  # Base env still present
    
    def test_generate_compose_no_mock_llm(self, generator, temp_agent_dir):
        """Test compose generation without mock LLM."""
        compose = generator.generate_compose(
            agent_id="agent-scout",
            agent_name="Scout",
            port=8081,
            template="scout",
            agent_dir=temp_agent_dir,
            use_mock_llm=False
        )
        
        env = compose["services"]["agent-scout"]["environment"]
        assert "CIRIS_USE_MOCK_LLM" not in env
    
    def test_generate_compose_custom_oauth_volume(self, generator, temp_agent_dir):
        """Test compose generation with custom OAuth volume."""
        compose = generator.generate_compose(
            agent_id="agent-scout",
            agent_name="Scout",
            port=8081,
            template="scout",
            agent_dir=temp_agent_dir,
            oauth_volume="/custom/oauth/path"
        )
        
        volumes = compose["services"]["agent-scout"]["volumes"]
        assert "/custom/oauth/path:/home/ciris/shared/oauth:ro" in volumes
    
    def test_write_compose_file(self, generator, temp_agent_dir):
        """Test writing compose file to disk."""
        compose = generator.generate_compose(
            agent_id="agent-scout",
            agent_name="Scout",
            port=8081,
            template="scout",
            agent_dir=temp_agent_dir
        )
        
        compose_path = temp_agent_dir / "docker-compose.yml"
        generator.write_compose_file(compose, compose_path)
        
        # Verify file exists
        assert compose_path.exists()
        
        # Verify content
        with open(compose_path, 'r') as f:
            loaded = yaml.safe_load(f)
        
        assert loaded == compose
        
        # Verify formatting
        with open(compose_path, 'r') as f:
            content = f.read()
        
        # Should be properly formatted
        assert "version: '3.8'" in content
        assert "  agent-scout:" in content  # Proper indentation
    
    def test_write_compose_file_creates_directory(self, generator, temp_agent_dir):
        """Test compose file writing creates parent directories."""
        compose = generator.generate_compose(
            agent_id="agent-scout",
            agent_name="Scout",
            port=8081,
            template="scout",
            agent_dir=temp_agent_dir
        )
        
        # Use nested path
        compose_path = temp_agent_dir / "nested" / "dir" / "docker-compose.yml"
        generator.write_compose_file(compose, compose_path)
        
        # Verify file and directories exist
        assert compose_path.exists()
        assert compose_path.parent.exists()
    
    def test_generate_env_file(self, generator, temp_agent_dir):
        """Test .env file generation."""
        env_vars = {
            "OPENAI_API_KEY": "sk-test123",
            "DISCORD_TOKEN": "discord.token.here",
            "CUSTOM_SECRET": "secret value with spaces"
        }
        
        env_path = temp_agent_dir / ".env"
        generator.generate_env_file(env_vars, env_path)
        
        # Verify file exists
        assert env_path.exists()
        
        # Verify content
        with open(env_path, 'r') as f:
            content = f.read()
        
        assert "OPENAI_API_KEY=sk-test123" in content
        assert "DISCORD_TOKEN=discord.token.here" in content
        assert 'CUSTOM_SECRET="secret value with spaces"' in content  # Quoted
    
    def test_network_naming(self, generator, temp_agent_dir):
        """Test network naming for different agent names."""
        # Test with various agent IDs - network name is based on agent_id not agent_name
        test_cases = [
            ("agent-scout", "Scout", "ciris-agent-scout-network"),
            ("agent-sage", "SAGE", "ciris-agent-sage-network"),
            ("echo-core", "Echo-Core", "ciris-echo-core-network"),
            ("agent-123", "Agent 123", "ciris-agent-123-network")
        ]
        
        for agent_id, agent_name, expected_network in test_cases:
            compose = generator.generate_compose(
                agent_id=agent_id,
                agent_name=agent_name,
                port=8080,
                template="default",
                agent_dir=temp_agent_dir
            )
            
            assert compose["networks"]["default"]["name"] == expected_network
    
    def test_port_mapping(self, generator, temp_agent_dir):
        """Test various port mappings."""
        # Test different ports
        for port in [8080, 8081, 8200, 9000]:
            compose = generator.generate_compose(
                agent_id="agent-test",
                agent_name="Test",
                port=port,
                template="default",
                agent_dir=temp_agent_dir
            )
            
            service = compose["services"]["agent-test"]
            assert service["ports"] == [f"{port}:8080"]