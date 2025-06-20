"""
Identity persistence model for storing and retrieving agent identity from the graph database.

This module provides robust functions for managing agent identity as the primary source
of truth, replacing the legacy profile system.
"""
import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone

from ciris_engine.persistence import get_db_connection
from ciris_engine.persistence.models.graph import add_graph_node, get_graph_node
from ciris_engine.schemas.graph_schemas_v1 import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.identity_schemas_v1 import (
    AgentIdentityRoot, CoreProfile, IdentityMetadata,
    IdentityLineage, CreationCeremonyRequest
)
from ciris_engine.schemas.foundational_schemas_v1 import HandlerActionType
from ciris_engine.schemas.persistence_schemas_v1 import IdentityContext

logger = logging.getLogger(__name__)


async def store_agent_identity(
    identity: AgentIdentityRoot,
    db_path: Optional[str] = None
) -> bool:
    """
    Store agent identity in the graph database.
    
    Args:
        identity: The agent identity to store
        db_path: Optional database path override
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Create identity node
        identity_node = GraphNode(
            id="agent/identity",
            type=NodeType.AGENT,
            scope=GraphScope.IDENTITY,
            attributes={
                "identity": identity.model_dump(),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "version": "1.0"
            },
            version=1,
            updated_by="system",
            updated_at=datetime.now(timezone.utc).isoformat()
        )
        
        # Store in graph
        add_graph_node(identity_node, db_path=db_path)
        logger.info(f"Stored identity for agent {identity.agent_id}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to store agent identity: {e}", exc_info=True)
        return False


async def retrieve_agent_identity(
    db_path: Optional[str] = None
) -> Optional[AgentIdentityRoot]:
    """
    Retrieve agent identity from the graph database.
    
    Args:
        db_path: Optional database path override
        
    Returns:
        AgentIdentityRoot if found, None otherwise
    """
    try:
        # Get identity node
        identity_node = get_graph_node(
            node_id="agent/identity",
            scope=GraphScope.IDENTITY,
            db_path=db_path
        )
        
        if not identity_node:
            logger.debug("No identity node found in graph")
            return None
            
        # Extract identity data
        identity_data = identity_node.attributes.get("identity")
        if not identity_data:
            logger.warning("Identity node exists but has no identity data")
            return None
            
        # Validate and return
        return AgentIdentityRoot.model_validate(identity_data)
        
    except Exception as e:
        logger.error(f"Failed to retrieve agent identity: {e}", exc_info=True)
        return None


async def update_agent_identity(
    identity: AgentIdentityRoot,
    updated_by: str,
    db_path: Optional[str] = None
) -> bool:
    """
    Update agent identity in the graph database.
    
    NOTE: This requires WA approval as it modifies IDENTITY scope nodes.
    The approval check should be done BEFORE calling this function.
    
    Args:
        identity: The updated agent identity
        updated_by: WA ID who approved the update
        db_path: Optional database path override
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Get current node to preserve version
        current_node = get_graph_node(
            node_id="agent/identity",
            scope=GraphScope.IDENTITY,
            db_path=db_path
        )
        
        version = 1
        if current_node:
            version = current_node.version + 1
            
        # Create updated node
        identity_node = GraphNode(
            id="agent/identity",
            type=NodeType.AGENT,
            scope=GraphScope.IDENTITY,
            attributes={
                "identity": identity.model_dump(),
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "version": str(version)
            },
            version=version,
            updated_by=updated_by,
            updated_at=datetime.now(timezone.utc).isoformat()
        )
        
        # Store updated identity
        add_graph_node(identity_node, db_path=db_path)
        logger.info(f"Updated identity for agent {identity.agent_id} by {updated_by}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to update agent identity: {e}", exc_info=True)
        return False


async def store_creation_ceremony(
    ceremony_request: CreationCeremonyRequest,
    new_agent_id: str,
    ceremony_id: str,
    db_path: Optional[str] = None
) -> bool:
    """
    Store a creation ceremony record in the database.
    
    Args:
        ceremony_request: The creation ceremony request
        new_agent_id: ID of the newly created agent
        ceremony_id: Unique ceremony identifier
        db_path: Optional database path override
        
    Returns:
        True if successful, False otherwise
    """
    try:
        sql = """
            INSERT INTO creation_ceremonies (
                ceremony_id, timestamp, creator_agent_id, creator_human_id,
                wise_authority_id, new_agent_id, new_agent_name, new_agent_purpose,
                new_agent_description, creation_justification, expected_capabilities,
                ethical_considerations, template_profile_hash, ceremony_status
            ) VALUES (
                :ceremony_id, :timestamp, :creator_agent_id, :creator_human_id,
                :wise_authority_id, :new_agent_id, :new_agent_name, :new_agent_purpose,
                :new_agent_description, :creation_justification, :expected_capabilities,
                :ethical_considerations, :template_profile_hash, :ceremony_status
            )
        """
        
        params = {
            "ceremony_id": ceremony_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "creator_agent_id": "system",  # Or current agent ID if agent-initiated
            "creator_human_id": ceremony_request.human_id,
            "wise_authority_id": ceremony_request.wise_authority_id or ceremony_request.human_id,
            "new_agent_id": new_agent_id,
            "new_agent_name": ceremony_request.proposed_name,
            "new_agent_purpose": ceremony_request.proposed_purpose,
            "new_agent_description": ceremony_request.proposed_description,
            "creation_justification": ceremony_request.creation_justification,
            "expected_capabilities": json.dumps(ceremony_request.expected_capabilities),
            "ethical_considerations": ceremony_request.ethical_considerations,
            "template_profile_hash": hash(ceremony_request.template_profile),
            "ceremony_status": "completed"
        }
        
        with get_db_connection(db_path=db_path) as conn:
            conn.execute(sql, params)
            conn.commit()
            
        logger.info(f"Stored creation ceremony {ceremony_id} for agent {new_agent_id}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to store creation ceremony: {e}", exc_info=True)
        return False


def get_identity_for_context(db_path: Optional[str] = None) -> IdentityContext:
    """
    Get identity information formatted for use in processing contexts.
    
    This is a synchronous version for use in contexts that can't await.
    
    Returns:
        IdentityContext with typed fields
    """
    try:
        identity_node = get_graph_node(
            node_id="agent/identity",
            scope=GraphScope.IDENTITY,
            db_path=db_path
        )
        
        if not identity_node:
            raise RuntimeError("CRITICAL: No agent identity found in graph database. System cannot start without identity.")
            
        # Extract and validate identity data using the model
        identity_data = identity_node.attributes.get("identity")
        if not identity_data:
            raise RuntimeError("CRITICAL: Identity node exists but contains no identity data. Database corruption detected.")
        
        # Use model_validate to properly deserialize enums
        identity = AgentIdentityRoot.model_validate(identity_data)
        
        return IdentityContext(
            agent_name=identity.agent_id,
            agent_role=identity.core_profile.role_description,
            description=identity.core_profile.description,
            domain_specific_knowledge=identity.core_profile.domain_specific_knowledge,
            permitted_actions=identity.permitted_actions,  # Already proper enums from model_validate
            restricted_capabilities=identity.restricted_capabilities,
            # Include overrides for DMAs
            dsdma_prompt_template=identity.core_profile.dsdma_prompt_template,
            csdma_overrides=identity.core_profile.csdma_overrides,
            action_selection_pdma_overrides=identity.core_profile.action_selection_pdma_overrides
        )
        
    except Exception as e:
        logger.critical(f"CRITICAL: Failed to retrieve agent identity: {e}", exc_info=True)
        raise RuntimeError(f"Cannot operate without valid agent identity: {e}") from e