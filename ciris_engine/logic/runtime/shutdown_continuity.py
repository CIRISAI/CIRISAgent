"""
Shutdown continuity helpers for CIRISRuntime.

Handles preserving agent state and continuity awareness during shutdown,
creating shutdown memory nodes for future reactivation.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


def determine_shutdown_consent_status(runtime: Any) -> str:
    """Determine if shutdown was consensual based on agent processor result.

    Returns:
        Consent status: 'accepted', 'rejected', or 'manual'
    """
    if not runtime.agent_processor or not hasattr(runtime.agent_processor, "shutdown_processor"):
        return "manual"

    shutdown_proc = runtime.agent_processor.shutdown_processor
    if not shutdown_proc or not hasattr(shutdown_proc, "shutdown_result"):
        return "manual"

    result = shutdown_proc.shutdown_result
    if not result:
        return "manual"

    if result.action == "shutdown_accepted" or result.status == "completed":
        return "accepted"
    elif result.action == "shutdown_rejected" or result.status == "rejected":
        return "rejected"

    return "manual"


def build_shutdown_node_attributes(runtime: Any, reason: str, consent_status: str) -> JSONDict:
    """Build attributes dict for shutdown memory node.

    Args:
        runtime: The CIRISRuntime instance
        reason: Shutdown reason text
        consent_status: Consent status ('accepted', 'rejected', 'manual')

    Returns:
        Dictionary of node attributes
    """
    now = runtime.time_service.now() if runtime.time_service else datetime.now(timezone.utc)
    return {
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "created_by": "runtime_shutdown",
        "tags": ["shutdown", "continuity_awareness"],
        "reason": reason,
        "consent_status": consent_status,
    }


async def update_identity_with_shutdown_reference(runtime: Any, shutdown_node_id: str) -> None:
    """Update agent identity with shutdown memory reference.

    Args:
        runtime: The CIRISRuntime instance
        shutdown_node_id: ID of the shutdown node created
    """
    if not runtime.agent_identity or not hasattr(runtime.agent_identity, "core_profile"):
        return

    runtime.agent_identity.core_profile.last_shutdown_memory = shutdown_node_id

    # Increment modification count
    if hasattr(runtime.agent_identity, "identity_metadata"):
        runtime.agent_identity.identity_metadata.modification_count += 1

    # Save updated identity
    if runtime.identity_manager:
        await runtime.identity_manager._save_identity_to_graph(runtime.agent_identity)
        logger.debug("Agent identity updates saved to persistence layer")
    else:
        logger.debug("Agent identity updates stored in memory graph")


async def preserve_shutdown_continuity(runtime: Any) -> None:
    """Preserve agent state for future reactivation."""
    try:
        from ciris_engine.schemas.runtime.extended import ShutdownContext
        from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType

        # Create shutdown context
        shutdown_context = ShutdownContext(
            is_terminal=False,
            reason=runtime._shutdown_reason or "Graceful shutdown",
            initiated_by="runtime",
            allow_deferral=False,
            expected_reactivation=None,
            agreement_context=None,
        )

        # Determine consent status and build node
        consent_status = determine_shutdown_consent_status(runtime)
        now = runtime.time_service.now() if runtime.time_service else datetime.now(timezone.utc)

        shutdown_node = GraphNode(
            id=f"shutdown_{now.isoformat()}",
            type=NodeType.AGENT,
            scope=GraphScope.IDENTITY,
            attributes=build_shutdown_node_attributes(runtime, shutdown_context.reason, consent_status),
        )

        # Store in memory service
        if runtime.memory_service:
            await runtime.memory_service.memorize(shutdown_node)
            logger.info(f"Preserved shutdown continuity: {shutdown_node.id}")
            await update_identity_with_shutdown_reference(runtime, shutdown_node.id)

    except Exception as e:
        logger.error(f"Failed to preserve shutdown continuity: {e}")


async def create_startup_node(runtime: Any) -> None:
    """Create startup node for continuity tracking."""
    try:
        from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType

        # Create memory node for startup
        startup_node = GraphNode(
            id=f"startup_{runtime.time_service.now().isoformat() if runtime.time_service else datetime.now(timezone.utc).isoformat()}",
            type=NodeType.AGENT,
            scope=GraphScope.IDENTITY,
            attributes={"created_by": "runtime_startup", "tags": ["startup", "continuity_awareness"]},
        )

        # Store in memory service
        if runtime.memory_service:
            await runtime.memory_service.memorize(startup_node)
            logger.info(f"Created startup continuity node: {startup_node.id}")

    except Exception as e:
        logger.error(f"Failed to create startup node: {e}")
