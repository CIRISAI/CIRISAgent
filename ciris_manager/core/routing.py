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
                if not container.name.startswith('ciris-'):
                    continue
                
                # Skip infrastructure containers
                if container.name in ['ciris-nginx', 'ciris-gui', 'ciris-gui-dev', 'ciris-manager']:
                    continue
                
                # For now, use environment variables until we add labels
                env_vars = container.attrs.get('Config', {}).get('Env', [])
                env_dict = {}
                for env in env_vars:
                    if '=' in env:
                        key, value = env.split('=', 1)
                        env_dict[key] = value
                
                # Check for CIRIS_AGENT_ID in environment
                agent_id = env_dict.get('CIRIS_AGENT_ID')
                if not agent_id:
                    # Fall back to label (for future containers)
                    agent_id = container.labels.get('ai.ciris.agent.id')
                if not agent_id:
                    logger.debug(f"Container {container.name} missing ai.ciris.agent.id label")
                    continue
                
                host_port = None
                for container_port in ['8080/tcp', '8081/tcp', '8082/tcp']:
                    port_bindings = container.ports.get(container_port, [])
                    if port_bindings and port_bindings[0].get('HostPort'):
                        host_port = int(port_bindings[0]['HostPort'])
                        break
                
                if not host_port:
                    logger.warning(
                        f"Container {container.name} (agent: {agent_id}) "
                        "has no accessible port - skipping"
                    )
                    continue
                
                routable.append(ManagedContainer(
                    container_id=container.id,
                    agent_id=agent_id,
                    host_port=host_port,
                    container_name=container.name
                ))
                
                logger.debug(f"Found routable container: {agent_id} on port {host_port}")
                
            except Exception as e:
                logger.warning(f"Error processing container {container.name}: {e}")
                continue
                
    except Exception as e:
        logger.error(f"Error listing containers: {e}")
    
    logger.info(f"Found {len(routable)} routable containers")
    return routable


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
            if not container.name.startswith('ciris-'):
                continue
                
            agent_id = container.labels.get('ai.ciris.agent.id', 'NO_LABEL')
            status = container.status
            
            if status != 'running':
                result['skipped'].append({
                    'name': container.name,
                    'reason': f'Not running (status: {status})',
                    'agent_id': agent_id
                })
            elif agent_id == 'NO_LABEL':
                result['skipped'].append({
                    'name': container.name,
                    'reason': 'Missing ai.ciris.agent.id label',
                    'agent_id': None
                })
            else:
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
                    
    except Exception as e:
        result['errors'].append(str(e))
    
    return result