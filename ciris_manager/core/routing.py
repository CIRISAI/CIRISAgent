"""
Stateless container routing - Docker as source of truth.
"""

import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ManagedContainer:
    """A container we can route traffic to."""
    
    container_id: str
    agent_id: str
    host_port: int
    container_name: str
    
    def __post_init__(self):
        if not self.agent_id:
            raise ValueError("Agent ID required")
        if not 1 <= self.host_port <= 65535:
            raise ValueError(f"Invalid port: {self.host_port}")
        if not self.container_name.startswith('ciris-'):
            raise ValueError(f"Container name must start with 'ciris-': {self.container_name}")
    
    @property
    def nginx_upstream_name(self) -> str:
        return f"agent_{self.agent_id.replace('-', '_')}"
    
    @property 
    def nginx_server(self) -> str:
        return f"{self.container_name}:{self.host_port}"
    
    def to_legacy_dict(self) -> Dict[str, Any]:
        return {
            'agent_id': self.agent_id,
            'container_name': self.container_name,
            'api_port': self.host_port,
            'container_id': self.container_id,
            'status': 'running',
        }


def _is_infrastructure_container(name: str) -> bool:
    """Check if container is infrastructure (not an agent)."""
    infra_names = ['ciris-nginx', 'ciris-gui', 'ciris-gui-dev', 'ciris-manager']
    return name in infra_names


def _extract_env_dict(container) -> Dict[str, str]:
    """Extract environment variables as dictionary."""
    env_vars = container.attrs.get('Config', {}).get('Env', [])
    env_dict = {}
    for env in env_vars:
        if '=' in env:
            key, value = env.split('=', 1)
            env_dict[key] = value
    return env_dict


def _get_agent_id(container, env_dict: Dict[str, str]) -> Optional[str]:
    """Get agent ID from environment or labels."""
    agent_id = env_dict.get('CIRIS_AGENT_ID')
    if not agent_id:
        agent_id = container.labels.get('ai.ciris.agent.id')
    return agent_id


def _get_host_port(container) -> Optional[int]:
    """Find the host port for a container."""
    for container_port in ['8080/tcp', '8081/tcp', '8082/tcp']:
        port_bindings = container.ports.get(container_port, [])
        if port_bindings and port_bindings[0].get('HostPort'):
            return int(port_bindings[0]['HostPort'])
    return None


def _process_container(container) -> Optional[ManagedContainer]:
    """Process a single container and return ManagedContainer if routable."""
    if not container.name.startswith('ciris-'):
        return None
    
    if _is_infrastructure_container(container.name):
        return None
    
    env_dict = _extract_env_dict(container)
    agent_id = _get_agent_id(container, env_dict)
    
    if not agent_id:
        logger.debug(f"Container {container.name} missing agent ID")
        return None
    
    host_port = _get_host_port(container)
    if not host_port:
        logger.warning(
            f"Container {container.name} (agent: {agent_id}) "
            "has no accessible port - skipping"
        )
        return None
    
    return ManagedContainer(
        container_id=container.id,
        agent_id=agent_id,
        host_port=host_port,
        container_name=container.name
    )


def get_routable_containers() -> List[ManagedContainer]:
    """Get all containers we can route to from Docker."""
    try:
        import docker
        client = docker.from_env()
    except Exception as e:
        logger.error(f"Failed to connect to Docker: {e}")
        return []
    
    routable = []
    
    try:
        containers = client.containers.list()
        
        for container in containers:
            try:
                managed_container = _process_container(container)
                if managed_container:
                    routable.append(managed_container)
                    logger.debug(
                        f"Found routable container: {managed_container.agent_id} "
                        f"on port {managed_container.host_port}"
                    )
            except Exception as e:
                logger.warning(f"Error processing container {container.name}: {e}")
                continue
                
    except Exception as e:
        logger.error(f"Error listing containers: {e}")
    
    logger.info(f"Found {len(routable)} routable containers")
    return routable


def _validate_container(container, result: Dict[str, Any]) -> None:
    """Validate a single container and update result."""
    if not container.name.startswith('ciris-'):
        return
    
    agent_id = container.labels.get('ai.ciris.agent.id', 'NO_LABEL')
    status = container.status
    
    if status != 'running':
        result['skipped'].append({
            'name': container.name,
            'reason': f'Not running (status: {status})',
            'agent_id': agent_id
        })
        return
    
    if agent_id == 'NO_LABEL':
        result['skipped'].append({
            'name': container.name,
            'reason': 'Missing ai.ciris.agent.id label',
            'agent_id': agent_id
        })
        return
    
    # Check for accessible ports
    has_port = False
    for port in ['8080/tcp', '8081/tcp', '8082/tcp']:
        if container.ports.get(port):
            has_port = True
            break
    
    if not has_port:
        result['skipped'].append({
            'name': container.name,
            'reason': 'No accessible port',
            'agent_id': agent_id
        })
    else:
        result['routable_count'] += 1


def validate_routing_setup() -> Dict[str, Any]:
    """Validate the routing setup and return diagnostic info."""
    import docker
    
    result = {
        'routable_count': 0,
        'skipped': [],
        'errors': []
    }
    
    try:
        client = docker.from_env()
        containers = client.containers.list(all=True)
        
        for container in containers:
            try:
                _validate_container(container, result)
            except Exception as e:
                result['errors'].append({
                    'name': container.name,
                    'error': str(e)
                })
                
    except Exception as e:
        logger.error(f"Error connecting to Docker: {e}")
        result['errors'].append({
            'name': 'docker',
            'error': str(e)
        })
    
    return result