"""
API routes for CIRISManager v2 with pre-approved template support.

Provides endpoints for agent creation, discovery, and management.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import logging

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
        """List all managed agents."""
        agents = manager.agent_registry.list_agents()
        
        agent_list = []
        for agent in agents:
            agent_list.append({
                "agent_id": agent.agent_id,
                "name": agent.name,
                "port": agent.port,
                "template": agent.template,
                "api_endpoint": f"http://localhost:{agent.port}",
                "compose_file": agent.compose_file,
                "created_at": agent.created_at
            })
        
        return AgentListResponse(agents=agent_list)
    
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
    async def create_agent(request: CreateAgentRequest) -> AgentResponse:
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
    
    @router.delete("/agents/{agent_name}")
    async def delete_agent(agent_name: str) -> Dict[str, str]:
        """Delete an agent."""
        agent = manager.agent_registry.get_agent_by_name(agent_name)
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
        
        # Delete agent and clean up resources
        success = await manager.delete_agent(agent.agent_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete agent")
        
        return {"status": "deleted", "agent_id": agent.agent_id}
    
    @router.get("/templates", response_model=TemplateListResponse)
    async def list_templates() -> TemplateListResponse:
        """List available templates."""
        # Get pre-approved templates
        pre_approved = manager.template_verifier.list_pre_approved_templates()
        
        # TODO: Also scan template directory for all available templates
        all_templates = pre_approved.copy()
        
        return TemplateListResponse(
            templates=all_templates,
            pre_approved=list(pre_approved.keys())
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
    
    return router