"""
Configuration settings for CIRISManager.
"""
from pathlib import Path
from typing import Optional, List
from pydantic import BaseModel, Field


class WatchdogConfig(BaseModel):
    """Watchdog configuration."""
    check_interval: int = Field(default=30, description="Seconds between checks")
    crash_threshold: int = Field(default=3, description="Number of crashes to trigger intervention")
    crash_window: int = Field(default=300, description="Time window in seconds to count crashes")


class UpdateConfig(BaseModel):
    """Update checking configuration."""
    check_interval: int = Field(default=300, description="Seconds between update checks")
    auto_notify: bool = Field(default=True, description="Automatically notify agents of updates")


class ContainerConfig(BaseModel):
    """Container management configuration."""
    interval: int = Field(default=60, description="Seconds between docker-compose up -d runs")
    pull_images: bool = Field(default=True, description="Pull latest images before starting")


class PortConfig(BaseModel):
    """Port allocation configuration."""
    start: int = Field(default=8080, description="Start of port range")
    end: int = Field(default=8200, description="End of port range")
    reserved: List[int] = Field(
        default=[8888, 3000, 80, 443],
        description="Ports to never allocate"
    )


class DockerConfig(BaseModel):
    """Docker configuration."""
    compose_file: str = Field(
        default="/home/ciris/CIRISAgent/deployment/docker-compose.yml",
        description="Path to docker-compose.yml"
    )
    registry: str = Field(
        default="ghcr.io/cirisai",
        description="Docker registry for images"
    )
    image: str = Field(
        default="ciris-agent:latest",
        description="Default agent image"
    )


class ManagerConfig(BaseModel):
    """Manager API configuration."""
    port: int = Field(default=8888, description="API port")
    socket: Optional[str] = Field(
        default="/var/run/ciris-manager.sock",
        description="Unix socket path"
    )
    host: str = Field(default="0.0.0.0", description="API host")
    agents_directory: str = Field(
        default="/etc/ciris-manager/agents",
        description="Directory for agent configurations"
    )
    templates_directory: str = Field(
        default="/home/ciris/CIRISAgent/ciris_templates",
        description="Directory containing agent templates"
    )
    manifest_path: str = Field(
        default="/etc/ciris-manager/pre-approved-templates.json",
        description="Path to pre-approved templates manifest"
    )


class NginxConfig(BaseModel):
    """Nginx configuration."""
    config_path: str = Field(
        default="/etc/nginx/sites-available/agents.ciris.ai",
        description="Path to nginx config file"
    )
    reload_command: str = Field(
        default="systemctl reload nginx",
        description="Command to reload nginx"
    )
    agents_config_dir: str = Field(
        default="/etc/nginx/agents",
        description="Directory for per-agent nginx config files"
    )
    container_name: str = Field(
        default="ciris-nginx",
        description="Name of the nginx container"
    )


class CIRISManagerConfig(BaseModel):
    """Complete CIRISManager configuration."""
    manager: ManagerConfig = Field(default_factory=ManagerConfig)
    docker: DockerConfig = Field(default_factory=DockerConfig)
    watchdog: WatchdogConfig = Field(default_factory=WatchdogConfig)
    ports: PortConfig = Field(default_factory=PortConfig)
    nginx: NginxConfig = Field(default_factory=NginxConfig)
    updates: UpdateConfig = Field(default_factory=UpdateConfig)
    container_management: ContainerConfig = Field(default_factory=ContainerConfig)
    
    @classmethod
    def from_file(cls, path: str) -> "CIRISManagerConfig":
        """Load configuration from YAML file."""
        import yaml
        
        config_path = Path(path)
        if not config_path.exists():
            # Return default config
            return cls()
            
        with open(config_path) as f:
            data = yaml.safe_load(f)
            
        return cls(**data)
        
    def save(self, path: str):
        """Save configuration to YAML file."""
        import yaml
        
        config_path = Path(path)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(config_path, 'w') as f:
            yaml.dump(self.model_dump(), f, default_flow_style=False)