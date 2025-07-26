"""
Unit tests for CIRISManager configuration settings.
"""

import pytest
import tempfile
import yaml
from pathlib import Path
from ciris_manager.config.settings import (
    CIRISManagerConfig, WatchdogConfig, UpdateConfig, 
    ContainerConfig, PortConfig, DockerConfig, ManagerConfig, NginxConfig
)


class TestConfigSettings:
    """Test cases for configuration settings."""
    
    def test_watchdog_config_defaults(self):
        """Test WatchdogConfig defaults."""
        config = WatchdogConfig()
        assert config.check_interval == 30
        assert config.crash_threshold == 3
        assert config.crash_window == 300
    
    def test_update_config_defaults(self):
        """Test UpdateConfig defaults."""
        config = UpdateConfig()
        assert config.check_interval == 300
        assert config.auto_notify is True
    
    def test_container_config_defaults(self):
        """Test ContainerConfig defaults."""
        config = ContainerConfig()
        assert config.interval == 60
        assert config.pull_images is True
    
    def test_port_config_defaults(self):
        """Test PortConfig defaults."""
        config = PortConfig()
        assert config.start == 8080
        assert config.end == 8200
        assert 8888 in config.reserved
        assert 3000 in config.reserved
    
    def test_docker_config_defaults(self):
        """Test DockerConfig defaults."""
        config = DockerConfig()
        assert "docker-compose.yml" in config.compose_file
        assert config.registry == "ghcr.io/cirisai"
        assert config.image == "ciris-agent:latest"
    
    def test_manager_config_defaults(self):
        """Test ManagerConfig defaults."""
        config = ManagerConfig()
        assert config.port == 8888
        assert config.socket == "/var/run/ciris-manager.sock"
        assert config.host == "0.0.0.0"
        assert "/agents" in config.agents_directory
        assert "templates" in config.templates_directory
    
    def test_nginx_config_defaults(self):
        """Test NginxConfig defaults."""
        config = NginxConfig()
        assert config.container_name == "ciris-nginx"
        assert "nginx" in config.config_dir
    
    def test_ciris_manager_config_defaults(self):
        """Test CIRISManagerConfig defaults."""
        config = CIRISManagerConfig()
        assert config.manager is not None
        assert config.docker is not None
        assert config.watchdog is not None
        assert config.ports is not None
        assert config.nginx is not None
        assert config.updates is not None
        assert config.container_management is not None
    
    def test_config_from_file(self, tmp_path):
        """Test loading config from file."""
        config_data = {
            "manager": {
                "port": 9999,
                "host": "127.0.0.1"
            },
            "docker": {
                "registry": "custom.registry",
                "image": "custom-image:v1"
            },
            "ports": {
                "start": 9000,
                "end": 9100,
                "reserved": [9999, 8080]
            }
        }
        
        config_file = tmp_path / "test-config.yml"
        with open(config_file, 'w') as f:
            yaml.dump(config_data, f)
        
        # Load config
        config = CIRISManagerConfig.from_file(str(config_file))
        
        # Check values
        assert config.manager.port == 9999
        assert config.manager.host == "127.0.0.1"
        assert config.docker.registry == "custom.registry"
        assert config.docker.image == "custom-image:v1"
        assert config.ports.start == 9000
        assert config.ports.end == 9100
        assert 9999 in config.ports.reserved
        assert 8080 in config.ports.reserved
    
    def test_config_from_file_not_found(self):
        """Test loading config from non-existent file."""
        config = CIRISManagerConfig.from_file("/non/existent/path.yml")
        # Should return default config
        assert config.manager.port == 8888
        assert config.docker.registry == "ghcr.io/cirisai"
    
    def test_config_save(self, tmp_path):
        """Test saving config to file."""
        config = CIRISManagerConfig()
        config.manager.port = 7777
        config.docker.image = "test-image:latest"
        
        config_file = tmp_path / "saved-config.yml"
        config.save(str(config_file))
        
        # Load back and verify
        with open(config_file, 'r') as f:
            data = yaml.safe_load(f)
        
        assert data["manager"]["port"] == 7777
        assert data["docker"]["image"] == "test-image:latest"
    
    def test_config_save_creates_directory(self, tmp_path):
        """Test config save creates parent directory."""
        config = CIRISManagerConfig()
        
        config_file = tmp_path / "nested" / "dir" / "config.yml"
        config.save(str(config_file))
        
        assert config_file.exists()
        assert config_file.parent.exists()