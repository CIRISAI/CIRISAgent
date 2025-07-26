"""
NGINX configuration management for CIRIS agents.

This module handles dynamic nginx configuration generation using a template-based
approach. It generates complete nginx.conf files rather than fragments.
"""
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class NginxManager:
    """Manages nginx configuration using template generation."""
    
    def __init__(self, config_dir: str = "/home/ciris/nginx",
                 container_name: str = "ciris-nginx"):
        """
        Initialize nginx manager.
        
        Args:
            config_dir: Directory for nginx configuration files
            container_name: Name of the nginx Docker container
        """
        self.config_dir = Path(config_dir)
        self.container_name = container_name
        self.config_path = self.config_dir / "nginx.conf"
        self.new_config_path = self.config_dir / "nginx.conf.new"
        self.backup_path = self.config_dir / "nginx.conf.backup"
        
        # Ensure directory exists
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
    def update_config(self, agents: List[Dict]) -> bool:
        """
        Update nginx configuration with current agent list.
        
        Args:
            agents: List of agent dictionaries with id, name, port info
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # 1. Generate new config
            new_config = self.generate_config(agents)
            
            # 2. Write to temporary file
            self.new_config_path.write_text(new_config)
            logger.info(f"Generated new nginx config with {len(agents)} agents")
            
            # 3. Validate configuration
            if not self._validate_config():
                logger.error("Nginx config validation failed")
                return False
                
            # 4. Backup current config if it exists
            if self.config_path.exists():
                shutil.copy2(self.config_path, self.backup_path)
                logger.info("Backed up current nginx config")
                
            # 5. Atomic replace
            os.rename(self.new_config_path, self.config_path)
            logger.info("Installed new nginx config")
            
            # 6. Reload nginx
            if self._reload_nginx():
                logger.info("Nginx reloaded successfully")
                return True
            else:
                logger.error("Nginx reload failed, rolling back")
                self._rollback()
                return False
                
        except Exception as e:
            logger.error(f"Failed to update nginx config: {e}")
            self._rollback()
            return False
    
    def generate_config(self, agents: List[Dict]) -> str:
        """
        Generate complete nginx configuration from agent list.
        
        Args:
            agents: List of agent dictionaries
            
        Returns:
            Complete nginx.conf content
        """
        config = self._generate_base_config()
        config += self._generate_upstreams(agents)
        config += self._generate_server_block(agents)
        return config
    
    def _generate_base_config(self) -> str:
        """Generate base nginx configuration."""
        return """events {
    worker_connections 1024;
}

http {
    # Default MIME types and settings
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    
    # Performance settings
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    
    # Logging
    access_log /var/log/nginx/access.log;
    error_log /var/log/nginx/error.log;
    
    # Size limits
    client_max_body_size 10M;
    
"""

    def _generate_upstreams(self, agents: List[Dict]) -> str:
        """Generate upstream blocks for all services."""
        upstreams = """    # === UPSTREAMS ===
    # GUI upstream (running on host)
    upstream gui {
        server host.docker.internal:3000;
    }
    
    # Manager upstream
    upstream manager {
        server host.docker.internal:8888;
    }
"""
        
        # Add agent upstreams
        if agents:
            upstreams += "\n    # Agent upstreams\n"
            for agent in agents:
                agent_id = agent.get('agent_id', agent.get('id'))
                port = agent.get('api_port', agent.get('port'))
                
                # Skip agents without valid ports
                if not port or str(port).lower() == 'none':
                    logger.warning(f"Skipping agent {agent_id} - no valid port")
                    continue
                    
                # Use host-based routing for global scale
                # This allows agents to run anywhere - same machine, different machines, cloud
                upstreams += f"""    upstream agent_{agent_id} {{
        server host.docker.internal:{port};
    }}
"""
        
        return upstreams + "\n"
    
    def _generate_server_block(self, agents: List[Dict]) -> str:
        """Generate main server block with all routes."""
        # Find default agent (first one or 'datum' if exists)
        default_agent = None
        if agents:
            default_agent = next((a for a in agents if a.get('agent_id') == 'datum'), agents[0])
        
        server = """    # === MAIN SERVER ===
    server {
        listen 80;
        server_name _;
        
        # Health check endpoint
        location /health {
            access_log off;
            return 200 "healthy\\n";
            add_header Content-Type text/plain;
        }
        
        # GUI routes
        location / {
            proxy_pass http://gui;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection 'upgrade';
            proxy_set_header Host $host;
            proxy_cache_bypass $http_upgrade;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
        
        # Manager routes
        location /manager/v1/ {
            proxy_pass http://manager/manager/v1/;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
"""
        
        # Add default API route if we have a default agent
        if default_agent:
            agent_id = default_agent.get('agent_id', default_agent.get('id'))
            server += f"""
        # Default API route ({agent_id})
        location /v1/ {{
            proxy_pass http://agent_{agent_id}/v1/;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_read_timeout 300s;
            proxy_connect_timeout 75s;
        }}
"""
        
        # Add agent-specific routes
        if agents:
            server += "\n        # === AGENT ROUTES ===\n"
            for agent in agents:
                agent_id = agent.get('agent_id', agent.get('id'))
                agent_name = agent.get('agent_name', agent.get('name', agent_id))
                port = agent.get('api_port', agent.get('port'))
                
                # Skip agents without valid ports
                if not port or str(port).lower() == 'none':
                    continue
                
                # OAuth callback route
                server += f"""
        # {agent_name} OAuth callbacks
        location ~ ^/v1/auth/oauth/{agent_id}/(.+)/callback$ {{
            proxy_pass http://agent_{agent_id}/v1/auth/oauth/$1/callback$is_args$args;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }}
        
        # {agent_name} API routes
        location ~ ^/api/{agent_id}/(.*)$ {{
            proxy_pass http://agent_{agent_id}/$1$is_args$args;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_read_timeout 300s;
            proxy_connect_timeout 75s;
            
            # WebSocket support
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }}
"""
        
        server += """    }
}
"""
        return server
    
    def _validate_config(self) -> bool:
        """Validate nginx configuration using docker exec."""
        # First copy the new config to container for validation
        copy_result = subprocess.run([
            'docker', 'cp',
            str(self.new_config_path),
            f'{self.container_name}:/etc/nginx/nginx.conf.new'
        ], capture_output=True)
        
        if copy_result.returncode != 0:
            logger.error(f"Failed to copy config to container: {copy_result.stderr.decode()}")
            return False
        
        # Validate the config
        result = subprocess.run([
            'docker', 'exec', self.container_name,
            'nginx', '-t', '-c', '/etc/nginx/nginx.conf.new'
        ], capture_output=True)
        
        if result.returncode != 0:
            logger.error(f"Nginx validation failed: {result.stderr.decode()}")
            return False
            
        return True
    
    def _reload_nginx(self) -> bool:
        """Reload nginx configuration."""
        # First copy the validated config to the proper location
        copy_result = subprocess.run([
            'docker', 'cp',
            str(self.config_path),
            f'{self.container_name}:/etc/nginx/nginx.conf'
        ], capture_output=True)
        
        if copy_result.returncode != 0:
            logger.error(f"Failed to copy config to container: {copy_result.stderr.decode()}")
            return False
        
        # Reload nginx
        result = subprocess.run([
            'docker', 'exec', self.container_name,
            'nginx', '-s', 'reload'
        ], capture_output=True)
        
        if result.returncode != 0:
            logger.error(f"Nginx reload failed: {result.stderr.decode()}")
            return False
            
        return True
    
    def _rollback(self):
        """Rollback to previous configuration."""
        if self.backup_path.exists():
            try:
                shutil.copy2(self.backup_path, self.config_path)
                self._reload_nginx()
                logger.info("Rolled back to previous nginx config")
            except Exception as e:
                logger.error(f"Rollback failed: {e}")
        
        # Clean up temporary file
        if self.new_config_path.exists():
            self.new_config_path.unlink()
    
    def remove_agent_routes(self, agent_id: str, agents: List[Dict]) -> bool:
        """
        Remove routes for a specific agent by regenerating config without it.
        
        Args:
            agent_id: ID of agent to remove
            agents: Current list of ALL agents (will filter out the one to remove)
            
        Returns:
            True if successful
        """
        # Filter out the agent to remove
        remaining_agents = [a for a in agents if a.get('agent_id', a.get('id')) != agent_id]
        
        # Regenerate config with remaining agents
        return self.update_config(remaining_agents)
    
    def get_current_config(self) -> Optional[str]:
        """Get current nginx configuration."""
        if self.config_path.exists():
            return self.config_path.read_text()
        return None