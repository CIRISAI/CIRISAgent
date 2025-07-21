"""
Nginx route configuration generator for CIRISManager.

Generates individual nginx config files for each agent
to enable dynamic routing without manual configuration.
"""
import os
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class NginxRouteGenerator:
    """Generates nginx route configurations for agents."""
    
    def __init__(self, nginx_config_dir: str = "/etc/nginx/agents"):
        """
        Initialize the nginx route generator.
        
        Args:
            nginx_config_dir: Directory where agent config files will be written
        """
        self.nginx_config_dir = Path(nginx_config_dir)
        
    def generate_agent_config(self, agent_id: str, container_name: str, port: int) -> str:
        """
        Generate nginx configuration for a specific agent.
        
        Args:
            agent_id: Unique agent identifier (e.g., "datum", "scout")
            container_name: Docker container name (e.g., "ciris-agent-datum")
            port: Port the agent is listening on
            
        Returns:
            Nginx configuration content
        """
        # API routes
        api_config = f"""
# API routes for {agent_id}
location ~ ^/api/{agent_id}/(.*)$ {{
    proxy_pass http://{container_name}:{port}/$1;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 86400;
}}

# OAuth callback route for {agent_id}
location = /oauth/{agent_id}/callback {{
    return 301 $scheme://$host/oauth/{agent_id}/callback;
}}
"""
        
        return api_config
    
    def write_agent_config(self, agent_id: str, container_name: str, port: int) -> Path:
        """
        Write nginx configuration file for an agent.
        
        Args:
            agent_id: Unique agent identifier
            container_name: Docker container name
            port: Port the agent is listening on
            
        Returns:
            Path to the written config file
        """
        # Ensure config directory exists
        self.nginx_config_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate config content
        config_content = self.generate_agent_config(agent_id, container_name, port)
        
        # Write to file
        config_file = self.nginx_config_dir / f"{agent_id}.conf"
        config_file.write_text(config_content)
        
        logger.info(f"Wrote nginx config for {agent_id} to {config_file}")
        return config_file
    
    def remove_agent_config(self, agent_id: str) -> bool:
        """
        Remove nginx configuration file for an agent.
        
        Args:
            agent_id: Unique agent identifier
            
        Returns:
            True if file was removed, False if it didn't exist
        """
        config_file = self.nginx_config_dir / f"{agent_id}.conf"
        
        if config_file.exists():
            config_file.unlink()
            logger.info(f"Removed nginx config for {agent_id}")
            return True
        
        return False
    
    def generate_include_directive(self) -> str:
        """
        Generate the include directive to add to main nginx.conf.
        
        Returns:
            Include directive string
        """
        return f"include {self.nginx_config_dir}/*.conf;"
    
    async def reload_nginx(self, container_name: str = "ciris-nginx") -> bool:
        """
        Reload nginx configuration via docker exec.
        
        Args:
            container_name: Name of the nginx container
            
        Returns:
            True if reload was successful
        """
        import asyncio
        
        try:
            # Test nginx config first
            process = await asyncio.create_subprocess_exec(
                "docker", "exec", container_name, "nginx", "-t",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"Nginx config test failed: {stderr.decode()}")
                return False
            
            # Reload nginx
            process = await asyncio.create_subprocess_exec(
                "docker", "exec", container_name, "nginx", "-s", "reload",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"Nginx reload failed: {stderr.decode()}")
                return False
            
            logger.info("Successfully reloaded nginx configuration")
            return True
            
        except Exception as e:
            logger.error(f"Failed to reload nginx: {e}")
            return False