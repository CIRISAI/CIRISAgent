"""
Docker Compose file generator for CIRIS agents.

Generates individual docker-compose.yml files for each agent.
"""

import yaml
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class ComposeGenerator:
    """Generates Docker Compose configurations for agents."""
    
    def __init__(self, docker_registry: str, default_image: str):
        """
        Initialize compose generator.
        
        Args:
            docker_registry: Docker registry URL
            default_image: Default agent image name
        """
        self.docker_registry = docker_registry
        self.default_image = default_image
    
    def generate_compose(
        self,
        agent_id: str,
        agent_name: str,
        port: int,
        template: str,
        agent_dir: Path,
        environment: Optional[Dict[str, str]] = None,
        use_mock_llm: bool = True,
        oauth_volume: str = "/home/ciris/shared/oauth"
    ) -> Dict[str, Any]:
        """
        Generate docker-compose configuration for an agent.
        
        Args:
            agent_id: Unique agent identifier
            agent_name: Human-friendly agent name
            port: Allocated port number
            template: Template name
            agent_dir: Agent's directory path
            environment: Additional environment variables
            use_mock_llm: Whether to use mock LLM
            oauth_volume: Path to shared OAuth configuration
            
        Returns:
            Docker compose configuration dict
        """
        # Base environment
        base_env = {
            "CIRIS_AGENT_ID": agent_id,
            "CIRIS_TEMPLATE": template,
            "CIRIS_API_HOST": "0.0.0.0",
            "CIRIS_API_PORT": "8080",
        }
        
        if use_mock_llm:
            base_env["CIRIS_USE_MOCK_LLM"] = "true"
        
        # Merge with additional environment
        if environment:
            base_env.update(environment)
        
        # Intelligently determine communication channels based on configuration
        channels = []
        
        # API is always enabled for management and monitoring
        channels.append("api")
        logger.info("Communication channel enabled: API (Web GUI access)")
        
        # Check for Discord configuration
        discord_indicators = [
            "DISCORD_BOT_TOKEN",
            "DISCORD_TOKEN", 
            "DISCORD_HOME_CHANNEL_ID",
            "DISCORD_CHANNEL_IDS"
        ]
        
        if any(key in base_env and base_env.get(key) for key in discord_indicators):
            channels.append("discord")
            logger.info("Communication channel enabled: Discord (bot token detected)")
        
        # Future: Add detection for other platforms
        # if "SLACK_BOT_TOKEN" in base_env:
        #     channels.append("slack")
        #     logger.info("Communication channel enabled: Slack")
        
        # Set the final adapter configuration
        base_env["CIRIS_ADAPTER"] = ",".join(channels)
        logger.info(f"Agent will be accessible via: {', '.join(channels)}")
        
        # Build compose configuration
        compose_config = {
            "version": "3.8",
            "services": {
                agent_id: {
                    "container_name": f"ciris-{agent_id}",
                    "build": {
                        "context": "/home/ciris/ciris/forks/CIRISAgent",
                        "dockerfile": "Dockerfile"
                    },
                    "ports": [f"{port}:8080"],
                    "environment": base_env,
                    "volumes": [
                        f"{agent_dir}/data:/app/data",
                        f"{agent_dir}/logs:/app/logs",
                        f"{oauth_volume}:/home/ciris/shared/oauth:ro"
                    ],
                    "restart": "unless-stopped",
                    "healthcheck": {
                        "test": ["CMD", "curl", "-f", "http://localhost:8080/v1/system/health"],
                        "interval": "30s",
                        "timeout": "10s",
                        "retries": 3,
                        "start_period": "40s"
                    },
                    "logging": {
                        "driver": "json-file",
                        "options": {
                            "max-size": "10m",
                            "max-file": "3"
                        }
                    },
                    "labels": {
                        "ai.ciris.agents.id": agent_id,
                        "ai.ciris.agents.created": datetime.utcnow().isoformat() + "Z",
                        "ai.ciris.agents.template": template
                    }
                }
            },
            "networks": {
                "default": {
                    "name": f"ciris-{agent_id}-network"
                }
            }
        }
        
        return compose_config
    
    def write_compose_file(
        self,
        compose_config: Dict[str, Any],
        compose_path: Path
    ) -> None:
        """
        Write compose configuration to file.
        
        Args:
            compose_config: Docker compose configuration
            compose_path: Path to write the file
        """
        # Ensure directory exists
        compose_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write with proper formatting
        with open(compose_path, 'w') as f:
            yaml.dump(
                compose_config,
                f,
                default_flow_style=False,
                sort_keys=False,
                width=120
            )
        
        logger.info(f"Wrote docker-compose.yml to {compose_path}")
    
    def generate_env_file(
        self,
        env_vars: Dict[str, str],
        env_path: Path
    ) -> None:
        """
        Generate .env file for sensitive environment variables.
        
        Args:
            env_vars: Environment variables
            env_path: Path to .env file
        """
        with open(env_path, 'w') as f:
            for key, value in env_vars.items():
                # Quote values that contain spaces
                if ' ' in value:
                    value = f'"{value}"'
                f.write(f"{key}={value}\n")
        
        logger.info(f"Wrote .env file to {env_path}")