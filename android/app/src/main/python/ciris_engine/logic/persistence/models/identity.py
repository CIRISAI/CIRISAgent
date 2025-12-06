"""
Identity persistence model for storing and retrieving agent identity from the graph database.

This module provides robust functions for managing agent identity as the primary source
of truth, replacing the legacy profile system.
"""

import json
import logging
from typing import Optional

from ciris_engine.logic.persistence.db import get_db_connection
from ciris_engine.logic.persistence.models.graph import add_graph_node, get_graph_node
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.persistence.core import IdentityContext
from ciris_engine.schemas.runtime.core import AgentIdentityRoot
from ciris_engine.schemas.runtime.extended import CreationCeremonyRequest
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType

logger = logging.getLogger(__name__)


def store_agent_identity(
    identity: AgentIdentityRoot, time_service: TimeServiceProtocol, db_path: Optional[str] = None
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
        # Import IdentityNode
        from ciris_engine.schemas.services.nodes import IdentityNode

        # Convert AgentIdentityRoot to IdentityNode
        identity_node = IdentityNode.from_agent_identity_root(identity, time_service)

        # Convert to GraphNode for storage
        graph_node = identity_node.to_graph_node()

        # Store in graph
        add_graph_node(graph_node, time_service, db_path=db_path)
        logger.info(f"Stored identity for agent {identity.agent_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to store agent identity: {e}", exc_info=True)
        return False


def retrieve_agent_identity(db_path: Optional[str] = None) -> Optional[AgentIdentityRoot]:
    """
    Retrieve agent identity from the graph database.

    Args:
        db_path: Optional database path override

    Returns:
        AgentIdentityRoot if found, None otherwise
    """
    try:
        # Import IdentityNode
        from ciris_engine.schemas.services.nodes import IdentityNode

        # Get identity node
        graph_node = get_graph_node(node_id="agent/identity", scope=GraphScope.IDENTITY, db_path=db_path)

        if not graph_node:
            logger.debug("No identity node found in graph")
            return None

        # Convert GraphNode back to IdentityNode
        identity_node = IdentityNode.from_graph_node(graph_node)

        # Convert to AgentIdentityRoot
        agent_identity = identity_node.to_agent_identity_root()

        logger.info(f"Retrieved identity for agent {agent_identity.agent_id}")
        return agent_identity

    except Exception as e:
        logger.error(f"Failed to retrieve agent identity: {e}", exc_info=True)
        return None


def update_agent_identity(
    identity: AgentIdentityRoot, updated_by: str, time_service: TimeServiceProtocol, db_path: Optional[str] = None
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
        current_node = get_graph_node(node_id="agent/identity", scope=GraphScope.IDENTITY, db_path=db_path)

        version = 1
        if current_node:
            version = current_node.version + 1

        # Create updated node
        # Create proper GraphNodeAttributes
        from ciris_engine.schemas.services.graph_core import GraphNodeAttributes

        attributes = GraphNodeAttributes(
            created_at=time_service.now(),
            updated_at=time_service.now(),
            created_by=updated_by,
            tags=[f"identity:{identity.agent_id}", f"version:{version}"],
        )

        identity_node = GraphNode(
            id="agent/identity",
            type=NodeType.AGENT,
            scope=GraphScope.IDENTITY,
            attributes=attributes,
            version=version,
            updated_by=updated_by,
            updated_at=time_service.now(),
        )

        # Store updated identity
        add_graph_node(identity_node, time_service, db_path=db_path)
        logger.info(f"Updated identity for agent {identity.agent_id} by {updated_by}")
        return True

    except Exception as e:
        logger.error(f"Failed to update agent identity: {e}", exc_info=True)
        return False


def store_creation_ceremony(
    ceremony_request: CreationCeremonyRequest,
    new_agent_id: str,
    ceremony_id: str,
    time_service: TimeServiceProtocol,
    db_path: Optional[str] = None,
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
            "timestamp": time_service.now().isoformat(),
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
            "ceremony_status": "completed",
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
        # Import IdentityNode
        from ciris_engine.schemas.services.nodes import IdentityNode

        graph_node = get_graph_node(node_id="agent/identity", scope=GraphScope.IDENTITY, db_path=db_path)

        if not graph_node:
            raise RuntimeError(
                "CRITICAL: No agent identity found in graph database. System cannot start without identity."
            )

        # Convert GraphNode back to IdentityNode
        identity_node = IdentityNode.from_graph_node(graph_node)

        # Convert to AgentIdentityRoot
        identity = identity_node.to_agent_identity_root()

        # Convert permitted_actions strings to HandlerActionType enums
        from ciris_engine.schemas.runtime.enums import HandlerActionType

        permitted_action_enums = []
        for action_str in identity.permitted_actions:
            try:
                # Try to convert action string to HandlerActionType
                action = HandlerActionType(action_str.upper())
                permitted_action_enums.append(action)
            except ValueError:
                # Skip actions that don't map to HandlerActionType
                logger.debug(f"Action '{action_str}' does not map to a HandlerActionType")

        return IdentityContext(
            agent_name=identity.agent_id,
            agent_role=identity.core_profile.role_description,
            description=identity.core_profile.description,
            domain_specific_knowledge=identity.core_profile.domain_specific_knowledge,
            permitted_actions=permitted_action_enums,
            restricted_capabilities=identity.restricted_capabilities,
            # Include overrides for DMAs
            dsdma_prompt_template=identity.core_profile.dsdma_prompt_template,
            csdma_overrides=identity.core_profile.csdma_overrides,
            action_selection_pdma_overrides=identity.core_profile.action_selection_pdma_overrides,
        )

    except Exception as e:
        logger.critical(f"CRITICAL: Failed to retrieve agent identity: {e}", exc_info=True)
        raise RuntimeError(f"Cannot operate without valid agent identity: {e}") from e
