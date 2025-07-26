"""
API routes for CIRISManager v2 with pre-approved template support.

Provides endpoints for agent creation, discovery, and management.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import logging
from .auth import get_current_user_dependency as get_current_user

logger = logging.getLogger(__name__)


class CreateAgentRequest(BaseModel):
    """Request model for agent creation."""
    template: str = Field(..., description="Template name (e.g., 'scout', 'sage')")
    name: str = Field(..., description="Agent name")
    environment: Optional[Dict[str, str]] = Field(default=None, description="Additional environment variables")
    wa_signature: Optional[str] = Field(default=None, description="WA signature for non-approved templates")


class AgentResponse(BaseModel):
    """Response model for agent information."""
    agent_id: str
    name: str
    container: str
    port: int
    api_endpoint: str
    template: str
    status: str


class AgentListResponse(BaseModel):
    """Response model for agent list."""
    agents: List[Dict[str, Any]]


class StatusResponse(BaseModel):
    """Response model for manager status."""
    status: str
    version: str = "1.0.0"
    components: Dict[str, str]


class TemplateListResponse(BaseModel):
    """Response model for template list."""
    templates: Dict[str, str]
    pre_approved: List[str]


def create_routes(manager) -> APIRouter:
    """
    Create API routes with manager instance.
    
    Args:
        manager: CIRISManager instance
        
    Returns:
        Configured APIRouter
    """
    router = APIRouter()
    
    @router.get("/health")
    async def health_check() -> Dict[str, str]:
        """Health check endpoint."""
        return {"status": "healthy", "service": "ciris-manager"}
    
    @router.get("/status", response_model=StatusResponse)
    async def get_status() -> StatusResponse:
        """Get manager status."""
        status = manager.get_status()
        return StatusResponse(
            status="running" if status['running'] else "stopped",
            components=status['components']
        )
    
    @router.get("/agents", response_model=AgentListResponse)
    async def list_agents() -> AgentListResponse:
        """List all managed agents by discovering Docker containers."""
        from ciris_manager.docker_discovery import DockerAgentDiscovery
        
        discovery = DockerAgentDiscovery()
        agents = discovery.discover_agents()
        
        # Don't update nginx on GET requests - only update when agents change state
        
        return AgentListResponse(agents=agents)
    
    @router.get("/agents/{agent_name}")
    async def get_agent(agent_name: str) -> Dict[str, Any]:
        """Get specific agent by name."""
        agent = manager.agent_registry.get_agent_by_name(agent_name)
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
        
        return {
            "agent_id": agent.agent_id,
            "name": agent.name,
            "port": agent.port,
            "template": agent.template,
            "api_endpoint": f"http://localhost:{agent.port}",
            "compose_file": agent.compose_file,
            "created_at": agent.created_at
        }
    
    @router.post("/agents", response_model=AgentResponse)
    async def create_agent(
        request: CreateAgentRequest,
        user: dict = Depends(get_current_user)
    ) -> AgentResponse:
        """Create a new agent."""
        try:
            result = await manager.create_agent(
                template=request.template,
                name=request.name,
                environment=request.environment,
                wa_signature=request.wa_signature
            )
            
            return AgentResponse(
                agent_id=result['agent_id'],
                name=request.name,
                container=result['container'],
                port=result['port'],
                api_endpoint=result['api_endpoint'],
                template=request.template,
                status=result['status']
            )
            
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e))
        except Exception as e:
            logger.error(f"Failed to create agent: {e}")
            raise HTTPException(status_code=500, detail="Failed to create agent")
        
        logger.info(f"Agent {result['agent_id']} created by {user['email']}")
    
    @router.delete("/agents/{agent_id}")
    async def delete_agent(
        agent_id: str,
        user: dict = Depends(get_current_user)
    ) -> Dict[str, str]:
        """
        Delete an agent and clean up all resources.
        
        This will:
        - Stop and remove the agent container
        - Remove nginx routes
        - Free the allocated port
        - Remove agent from registry
        - Clean up agent directory
        """
        # Check if agent exists in registry
        agent = manager.agent_registry.get_agent(agent_id)
        if not agent:
            # Check if it's a discovered agent (not managed by CIRISManager)
            from ciris_manager.docker_discovery import DockerAgentDiscovery
            discovery = DockerAgentDiscovery()
            discovered_agents = discovery.discover_agents()
            
            discovered_agent = next((a for a in discovered_agents if a['agent_id'] == agent_id), None)
            if discovered_agent:
                # This is a discovered agent not managed by CIRISManager
                raise HTTPException(
                    status_code=400, 
                    detail=f"Agent '{agent_id}' was not created by CIRISManager. Please stop it manually using docker-compose."
                )
            else:
                raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
        
        # Perform deletion for Manager-created agents
        success = await manager.delete_agent(agent_id)
        
        if success:
            logger.info(f"Agent {agent_id} deleted by {user['email']}")
            return {
                "status": "deleted", 
                "agent_id": agent_id,
                "message": f"Agent {agent_id} and all its resources have been removed"
            }
        else:
            raise HTTPException(
                status_code=500, 
                detail=f"Failed to delete agent {agent_id}. Check logs for details."
            )
    
    @router.get("/templates", response_model=TemplateListResponse)
    async def list_templates() -> TemplateListResponse:
        """List available templates."""
        from pathlib import Path
        
        # Get pre-approved templates from manifest (if it exists)
        pre_approved = manager.template_verifier.list_pre_approved_templates()
        
        # Scan template directory for all available templates
        all_templates = {}
        templates_dir = Path(manager.config.manager.templates_directory)
        
        if templates_dir.exists():
            for template_file in templates_dir.glob("*.yaml"):
                template_name = template_file.stem
                # Simple description from filename
                all_templates[template_name] = f"{template_name.title()} agent template"
        
        # For development: if no manifest exists, treat some templates as pre-approved
        if not pre_approved and all_templates:
            # Common templates that don't need special approval
            default_pre_approved = ["echo", "scout", "sage", "test"]
            pre_approved_list = [t for t in default_pre_approved if t in all_templates]
        else:
            pre_approved_list = list(pre_approved.keys())
        
        return TemplateListResponse(
            templates=all_templates,
            pre_approved=pre_approved_list
        )
    
    @router.get("/ports/allocated")
    async def get_allocated_ports() -> Dict[str, Any]:
        """Get allocated ports."""
        return {
            "allocated": manager.port_manager.allocated_ports,
            "reserved": list(manager.port_manager.reserved_ports),
            "range": {
                "start": manager.port_manager.start_port,
                "end": manager.port_manager.end_port
            }
        }
    
    @router.get("/env/default")
    async def get_default_env() -> Dict[str, str]:
        """Get default .env file content for agent creation."""
        import os
        from pathlib import Path
        
        # Look for .env file in the project root
        # Try to find the project root by looking for ciris_templates directory
        current_path = Path(__file__).parent.parent.parent  # Go up to project root
        env_path = current_path / ".env"
        
        if env_path.exists():
            try:
                content = env_path.read_text()
                return {"content": content}
            except Exception as e:
                logger.error(f"Failed to read .env file: {e}")
                return {"content": ""}
        
        return {"content": ""}
    
    return router