"""
Shared pytest fixtures for CIRISManager tests.
"""
import pytest
from pathlib import Path
from ciris_manager.config.settings import CIRISManagerConfig


@pytest.fixture
def test_config(tmp_path):
    """Create a test configuration with temp directories."""
    # Create all necessary directories
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    
    nginx_dir = tmp_path / "nginx"
    nginx_dir.mkdir()
    
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    
    return CIRISManagerConfig(
        manager={
            "agents_directory": str(agents_dir),
            "templates_directory": str(templates_dir),
            "manifest_path": str(tmp_path / "pre-approved-templates.json"),
            "port": 0,  # Use 0 for random port in tests
            "host": "127.0.0.1"
        },
        nginx={
            "agents_config_dir": str(nginx_dir),
            "container_name": "test-nginx"
        }
    )


def create_test_config(base_path: Path, **overrides) -> CIRISManagerConfig:
    """
    Create a test configuration with custom overrides.
    
    Args:
        base_path: Base path for all directories
        **overrides: Additional config overrides
    
    Returns:
        CIRISManagerConfig instance
    """
    # Create directories
    agents_dir = base_path / "agents"
    agents_dir.mkdir(exist_ok=True)
    
    nginx_dir = base_path / "nginx"
    nginx_dir.mkdir(exist_ok=True)
    
    config_dict = {
        "manager": {
            "agents_directory": str(agents_dir),
            "port": 0
        },
        "nginx": {
            "agents_config_dir": str(nginx_dir),
            "container_name": "test-nginx"
        }
    }
    
    # Apply overrides
    for key, value in overrides.items():
        if key in config_dict:
            config_dict[key].update(value)
        else:
            config_dict[key] = value
    
    return CIRISManagerConfig(**config_dict)