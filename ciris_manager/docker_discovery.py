"""
Docker container discovery for CIRISManager.
Discovers running CIRIS agents by querying Docker directly.
"""
import docker
import json
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class DockerAgentDiscovery:
    """Discovers CIRIS agents running in Docker containers."""
    
    def __init__(self):
        try:
            self.client = docker.from_env()
        except Exception as e:
            logger.error(f"Failed to connect to Docker: {e}")
            self.client = None
    
    def discover_agents(self) -> List[Dict[str, Any]]:
        """Discover all CIRIS agent containers."""
        if not self.client:
            return []
        
        agents = []
        try:
            # Find all containers with CIRIS agent characteristics
            containers = self.client.containers.list(all=True)
            
            for container in containers:
                # Check if this is a CIRIS agent by looking at environment variables
                env_vars = container.attrs.get('Config', {}).get('Env', [])
                env_dict = {}
                for env in env_vars:
                    if '=' in env:
                        key, value = env.split('=', 1)
                        env_dict[key] = value
                
                # Is this a CIRIS agent?
                if 'CIRIS_AGENT_ID' in env_dict or 'CIRIS_AGENT_NAME' in env_dict:
                    agent_info = self._extract_agent_info(container, env_dict)
                    if agent_info:
                        agents.append(agent_info)
                        
        except Exception as e:
            logger.error(f"Error discovering agents: {e}")
            
        return agents
    
    def _extract_agent_info(self, container: Any, env_dict: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """Extract agent information from a container."""
        try:
            # Get container details
            attrs = container.attrs
            config = attrs.get('Config', {})
            state = attrs.get('State', {})
            network_settings = attrs.get('NetworkSettings', {})
            
            # Determine agent ID and name
            agent_id = env_dict.get('CIRIS_AGENT_ID', container.name)
            agent_name = env_dict.get('CIRIS_AGENT_NAME', container.name)
            
            # Get port mapping
            api_port = None
            port_bindings = network_settings.get('Ports', {})
            for container_port, host_bindings in port_bindings.items():
                if '8080' in container_port and host_bindings:
                    api_port = host_bindings[0].get('HostPort')
                    break
            
            # Determine API endpoint
            api_endpoint = None
            if api_port:
                api_endpoint = f"http://localhost:{api_port}"
            
            # Get health status
            health_status = None
            health_check = state.get('Health')
            if health_check:
                health_status = health_check.get('Status')
            
            # Build agent info
            agent_info = {
                'agent_id': agent_id,
                'agent_name': agent_name,
                'container_name': container.name,
                'container_id': container.id[:12],
                'status': container.status,
                'health': health_status,
                'api_endpoint': api_endpoint,
                'api_port': api_port,
                'created_at': attrs.get('Created'),
                'started_at': state.get('StartedAt'),
                'exit_code': state.get('ExitCode', 0),
                'environment': {
                    'CIRIS_ADAPTER': env_dict.get('CIRIS_ADAPTER'),
                    'CIRIS_MOCK_LLM': env_dict.get('CIRIS_MOCK_LLM'),
                    'CIRIS_PORT': env_dict.get('CIRIS_PORT', '8080'),
                },
                'labels': config.get('Labels', {}),
                'image': config.get('Image'),
                'restart_policy': attrs.get('HostConfig', {}).get('RestartPolicy', {}).get('Name'),
            }
            
            return agent_info
            
        except Exception as e:
            logger.error(f"Error extracting info from container {container.name}: {e}")
            return None
    
    def get_agent_logs(self, container_name: str, lines: int = 100) -> str:
        """Get logs from an agent container."""
        if not self.client:
            return ""
        
        try:
            container = self.client.containers.get(container_name)
            return container.logs(tail=lines).decode('utf-8')
        except Exception as e:
            logger.error(f"Error getting logs for {container_name}: {e}")
            return ""
    
    def restart_agent(self, container_name: str) -> bool:
        """Restart an agent container."""
        if not self.client:
            return False
        
        try:
            container = self.client.containers.get(container_name)
            container.restart()
            return True
        except Exception as e:
            logger.error(f"Error restarting {container_name}: {e}")
            return False
    
    def stop_agent(self, container_name: str) -> bool:
        """Stop an agent container."""
        if not self.client:
            return False
        
        try:
            container = self.client.containers.get(container_name)
            container.stop()
            return True
        except Exception as e:
            logger.error(f"Error stopping {container_name}: {e}")
            return False