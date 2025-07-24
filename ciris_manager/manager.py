"""
Main CIRISManager service.

Coordinates container management, crash loop detection, and provides
API for agent discovery and lifecycle management.
"""
import asyncio
import logging
import signal
import subprocess
from pathlib import Path
from typing import Optional, Dict, List, Any

from ciris_manager.core.container_manager import ContainerManager
from ciris_manager.core.watchdog import CrashLoopWatchdog
from ciris_manager.config.settings import CIRISManagerConfig
from ciris_manager.port_manager import PortManager
from ciris_manager.template_verifier import TemplateVerifier
from ciris_manager.agent_registry import AgentRegistry
from ciris_manager.compose_generator import ComposeGenerator
from ciris_manager.nginx_manager import NginxManager

logger = logging.getLogger(__name__)


class CIRISManager:
    """Main manager service coordinating all components."""
    
    def __init__(self, config: Optional[CIRISManagerConfig] = None):
        """
        Initialize CIRISManager.
        
        Args:
            config: Configuration object, uses defaults if not provided
        """
        self.config = config or CIRISManagerConfig()
        
        # Create necessary directories
        self.agents_dir = Path(self.config.manager.agents_directory)
        self.agents_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize new components
        metadata_path = self.agents_dir / "metadata.json"
        self.agent_registry = AgentRegistry(metadata_path)
        
        self.port_manager = PortManager(
            start_port=self.config.ports.start,
            end_port=self.config.ports.end,
            metadata_path=metadata_path
        )
        
        # Add reserved ports
        for port in self.config.ports.reserved:
            self.port_manager.add_reserved_port(port)
        
        # Initialize template verifier
        manifest_path = Path(self.config.manager.manifest_path)
        self.template_verifier = TemplateVerifier(manifest_path)
        
        # Initialize compose generator
        self.compose_generator = ComposeGenerator(
            docker_registry=self.config.docker.registry,
            default_image=self.config.docker.image
        )
        
        # Initialize nginx manager
        self.nginx_manager = NginxManager(
            config_dir=self.config.nginx.config_dir,
            container_name=self.config.nginx.container_name
        )
        
        # Initialize existing components (updated for per-agent management)
        self.container_manager = None  # Will be replaced with per-agent management
        
        self.watchdog = CrashLoopWatchdog(
            check_interval=self.config.watchdog.check_interval,
            crash_threshold=self.config.watchdog.crash_threshold,
            crash_window=self.config.watchdog.crash_window
        )
        
        # Scan existing agents on startup
        self._scan_existing_agents()
        
        self._running = False
        self._shutdown_event = asyncio.Event()
    
    def _scan_existing_agents(self) -> None:
        """Scan agent directories to rebuild registry on startup."""
        if not self.agents_dir.exists():
            return
        
        # Look for agent directories
        for agent_dir in self.agents_dir.iterdir():
            if not agent_dir.is_dir() or agent_dir.name == "metadata.json":
                continue
            
            compose_path = agent_dir / "docker-compose.yml"
            if compose_path.exists():
                # Extract agent info from directory name
                agent_name = agent_dir.name
                agent_id = agent_name
                
                # Try to get port from existing registry
                agent_info = self.agent_registry.get_agent(agent_id)
                if agent_info:
                    # Ensure port manager knows about this allocation
                    self.port_manager.allocate_port(agent_id)
                    logger.info(f"Found existing agent: {agent_id} on port {agent_info.port}")
    
    async def create_agent(
        self,
        template: str,
        name: str,
        environment: Optional[Dict[str, str]] = None,
        wa_signature: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new agent.
        
        Args:
            template: Template name (e.g., 'scout')
            name: Agent name
            environment: Additional environment variables
            wa_signature: WA signature for non-approved templates
            
        Returns:
            Agent creation result
            
        Raises:
            ValueError: Invalid template or name
            PermissionError: WA signature required but not provided
        """
        # Validate inputs
        template_path = Path(self.config.manager.templates_directory) / f"{template}.yaml"
        if not template_path.exists():
            raise ValueError(f"Template not found: {template}")
        
        # Check if template is pre-approved
        is_pre_approved = self.template_verifier.is_pre_approved(template, template_path)
        
        if not is_pre_approved and not wa_signature:
            raise PermissionError(
                f"Template '{template}' is not pre-approved. WA signature required."
            )
        
        # TODO: Verify WA signature if provided
        if wa_signature and not is_pre_approved:
            logger.info(f"Verifying WA signature for custom template: {template}")
            # Implementation would go here
        
        # Generate agent ID and allocate port
        agent_id = name.lower()
        allocated_port = self.port_manager.allocate_port(agent_id)
        
        # Create agent directory
        agent_dir = self.agents_dir / name.lower()
        agent_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate docker-compose.yml
        compose_config = self.compose_generator.generate_compose(
            agent_id=agent_id,
            agent_name=name,
            port=allocated_port,
            template=template,
            agent_dir=agent_dir,
            environment=environment,
            use_mock_llm=True  # For testing
        )
        
        # Write compose file
        compose_path = agent_dir / "docker-compose.yml"
        self.compose_generator.write_compose_file(compose_config, compose_path)
        
        # Register agent
        agent_info = self.agent_registry.register_agent(
            agent_id=agent_id,
            name=name,
            port=allocated_port,
            template=template,
            compose_file=str(compose_path)
        )
        
        # Update nginx routing
        await self._add_nginx_route(name.lower(), allocated_port)
        
        # Start the agent
        await self._start_agent(agent_id, compose_path)
        
        return {
            "agent_id": agent_id,
            "container": f"ciris-{agent_id}",
            "port": allocated_port,
            "api_endpoint": f"http://localhost:{allocated_port}",
            "compose_file": str(compose_path),
            "status": "starting"
        }
    
    async def update_nginx_config(self) -> bool:
        """Update nginx configuration with all current agents."""
        try:
            # Discover all running agents
            from ciris_manager.docker_discovery import DockerAgentDiscovery
            discovery = DockerAgentDiscovery()
            agents = discovery.discover_agents()
            
            # Update nginx config with current agent list
            success = self.nginx_manager.update_config(agents)
            
            if success:
                logger.info(f"Updated nginx config with {len(agents)} agents")
            else:
                logger.error("Failed to update nginx configuration")
            
            return success
            
        except Exception as e:
            logger.error(f"Error updating nginx config: {e}")
            return False
    
    async def _add_nginx_route(self, agent_name: str, port: int) -> None:
        """Update nginx configuration after adding a new agent."""
        # With the new template-based approach, we regenerate the entire config
        success = await self.update_nginx_config()
        if not success:
            raise RuntimeError("Failed to update nginx configuration")
    
    async def _start_agent(self, agent_id: str, compose_path: Path) -> None:
        """Start an agent container."""
        cmd = ["docker-compose", "-f", str(compose_path), "up", "-d"]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            logger.error(f"Failed to start agent {agent_id}: {stderr.decode()}")
            raise RuntimeError(f"Failed to start agent: {stderr.decode()}")
        
        logger.info(f"Started agent {agent_id}")
    
    async def container_management_loop(self) -> None:
        """Updated container management for per-agent compose files."""
        while self._running:
            try:
                # Iterate through all registered agents
                for agent_info in self.agent_registry.list_agents():
                    compose_path = Path(agent_info.compose_file)
                    if compose_path.exists():
                        # Pull latest images if configured
                        if self.config.container_management.pull_images:
                            await self._pull_agent_images(compose_path)
                        
                        # Run docker-compose up -d for this agent
                        await self._start_agent(agent_info.agent_id, compose_path)
                
                # Wait for next iteration
                await asyncio.sleep(self.config.container_management.interval)
                
            except Exception as e:
                logger.error(f"Error in container management loop: {e}")
                await asyncio.sleep(30)  # Back off on error
    
    async def _pull_agent_images(self, compose_path: Path) -> None:
        """Pull latest images for an agent."""
        cmd = ["docker-compose", "-f", str(compose_path), "pull"]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        
    async def start(self):
        """Start all manager services."""
        logger.info("Starting CIRISManager...")
        
        self._running = True
        
        # Generate initial nginx config if it doesn't exist
        await self.update_nginx_config()
        
        # Start the new container management loop
        asyncio.create_task(self.container_management_loop())
        
        # Start watchdog
        await self.watchdog.start()
        
        # Start API server if configured
        if hasattr(self.config.manager, 'port') and self.config.manager.port:
            asyncio.create_task(self._start_api_server())
        
        logger.info("CIRISManager started successfully")
    
    async def _start_api_server(self):
        """Start the FastAPI server for CIRISManager API."""
        try:
            from fastapi import FastAPI
            import uvicorn
            from .api.routes import create_routes
            
            app = FastAPI(title="CIRISManager API", version="1.0.0")
            
            # Create routes with manager instance
            router = create_routes(self)
            app.include_router(router, prefix="/manager/v1")
            
            config = uvicorn.Config(
                app,
                host=self.config.manager.host,
                port=self.config.manager.port,
                log_level="info"
            )
            server = uvicorn.Server(config)
            
            logger.info(f"Starting API server on {self.config.manager.host}:{self.config.manager.port}")
            await server.serve()
            
        except Exception as e:
            logger.error(f"Failed to start API server: {e}")
        
    async def delete_agent(self, agent_id: str) -> bool:
        """
        Delete an agent and clean up its resources.
        
        Args:
            agent_id: ID of agent to delete
            
        Returns:
            True if successful
        """
        try:
            # Get agent info
            agent_info = self.agent_registry.get_agent(agent_id)
            if not agent_info:
                logger.error(f"Agent {agent_id} not found")
                return False
                
            # Stop the agent container
            compose_path = Path(agent_info.compose_file)
            if compose_path.exists():
                logger.info(f"Stopping agent {agent_id}")
                cmd = ["docker-compose", "-f", str(compose_path), "down", "-v"]
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await process.communicate()
                
            # Remove nginx routes
            logger.info(f"Removing nginx routes for {agent_id}")
            self.nginx_manager.remove_agent_route(agent_id)
            
            # Free the port
            self.port_manager.free_port(agent_info.port)
            
            # Remove from registry
            self.agent_registry.remove_agent(agent_id)
            
            # Remove agent directory
            agent_dir = compose_path.parent
            if agent_dir.exists() and agent_dir != self.agents_dir:
                import shutil
                shutil.rmtree(agent_dir)
                logger.info(f"Removed agent directory: {agent_dir}")
                
            logger.info(f"Successfully deleted agent {agent_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete agent {agent_id}: {e}")
            return False
    
    async def stop(self):
        """Stop all manager services."""
        logger.info("Stopping CIRISManager...")
        
        self._running = False
        
        # Stop watchdog
        await self.watchdog.stop()
        
        self._shutdown_event.set()
        
        logger.info("CIRISManager stopped")
        
    async def run(self):
        """Run the manager until shutdown signal."""
        # Setup signal handlers
        loop = asyncio.get_event_loop()
        
        def handle_signal():
            logger.info("Shutdown signal received")
            self._shutdown_event.set()
            
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, handle_signal)
            
        try:
            # Start services
            await self.start()
            
            # Wait for shutdown
            await self._shutdown_event.wait()
            
        finally:
            # Stop services
            await self.stop()
            
    def get_status(self) -> dict:
        """Get current manager status."""
        return {
            'running': self._running,
            'config': self.config.model_dump(),
            'watchdog_status': self.watchdog.get_status(),
            'components': {
                'container_manager': 'running' if self._running else 'stopped',
                'watchdog': 'running' if self._running else 'stopped',
                'api_server': 'not_implemented'
            }
        }


async def main():
    """Main entry point for CIRISManager."""
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Load configuration
    config_path = "/etc/ciris-manager/config.yml"
    config = CIRISManagerConfig.from_file(config_path)
    
    # Create and run manager
    manager = CIRISManager(config)
    await manager.run()


if __name__ == "__main__":
    asyncio.run(main())