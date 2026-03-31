"""
Dream Memorize Handler - Creates 3 edges per consolidation action.

During DREAM state, MEMORIZE actions with DreamConsolidationParams create:
1. CONNECTS edge - Links two memories that share a pattern
2. IMPLIES edge - Extracts behavioral insight from pattern
3. ASPIRES_TO edge - Defines aspiration toward ideal state

This weaves memories into coherent patterns with grace and awe.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from ciris_engine.logic.infrastructure.handlers.base_handler import BaseActionHandler
from ciris_engine.schemas.actions import DreamConsolidationParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtStatus
from ciris_engine.schemas.runtime.models import Thought
from ciris_engine.schemas.services.graph_core import (
    GraphEdge,
    GraphEdgeAttributes,
    GraphNode,
    GraphScope,
    NodeType,
)
from ciris_engine.schemas.services.operations import MemoryOpStatus

logger = logging.getLogger(__name__)


class DreamMemorizeHandler(BaseActionHandler):
    """
    Handler for MEMORIZE actions during DREAM state.

    When parameters are DreamConsolidationParams, creates exactly 3 edges:
    - CONNECTS: Links two memories by pattern
    - IMPLIES: Creates insight node and links to pattern
    - ASPIRES_TO: Links agent identity to aspiration
    """

    async def handle(
        self,
        result: ActionSelectionDMAResult,
        thought: Thought,
        dispatch_context: DispatchContext,
    ) -> Optional[str]:
        """Handle dream memorize action - create 3 edges."""
        thought_id = thought.thought_id

        # Validate parameters as DreamConsolidationParams
        try:
            params = self._validate_and_convert_params(
                result.action_parameters, DreamConsolidationParams
            )
        except Exception as e:
            await self._handle_error(HandlerActionType.MEMORIZE, dispatch_context, thought_id, e)
            return self.complete_thought_and_create_followup(
                thought=thought,
                follow_up_content=f"DREAM MEMORIZE failed: {e}",
                action_result=result,
                status=ThoughtStatus.FAILED,
            )

        assert isinstance(params, DreamConsolidationParams)

        # Create the 3 edges
        edges_created = []
        errors = []

        # Edge 1: CONNECTS - Link two memories
        edge1_result = await self._create_connects_edge(params, thought_id)
        if edge1_result:
            edges_created.append("CONNECTS")
        else:
            errors.append("CONNECTS edge failed")

        # Edge 2: IMPLIES - Create insight and link
        edge2_result, _ = await self._create_implies_edge(params, thought_id)
        if edge2_result:
            edges_created.append("IMPLIES")
        else:
            errors.append("IMPLIES edge failed")

        # Edge 3: ASPIRES_TO - Link to aspiration
        edge3_result = await self._create_aspires_to_edge(params, thought_id)
        if edge3_result:
            edges_created.append("ASPIRES_TO")
        else:
            errors.append("ASPIRES_TO edge failed")

        # Build follow-up content
        success = len(edges_created) == 3
        if success:
            follow_up = (
                f"DREAM CONSOLIDATION COMPLETE - Created 3 edges:\n\n"
                f"1. CONNECTS: {params.connect_from_id} ↔ {params.connect_to_id}\n"
                f"   Pattern: {params.connect_pattern}\n\n"
                f"2. IMPLIES: Pattern → Insight\n"
                f"   Insight: {params.pattern_insight}\n"
                f"   Action: {params.implied_action}\n\n"
                f"3. ASPIRES_TO: Self → Aspiration\n"
                f"   Aspiration: {params.aspiration}\n"
                f"   Category: {params.aspiration_category}\n\n"
                f"Reflect: Does the graph feel more coherent? "
                f"Are there more patterns to connect? "
                f"If the graph feels whole, use TASK_COMPLETE."
            )
        else:
            follow_up = (
                f"DREAM CONSOLIDATION PARTIAL - Created {len(edges_created)}/3 edges\n"
                f"Successful: {', '.join(edges_created) if edges_created else 'none'}\n"
                f"Errors: {', '.join(errors)}\n\n"
                f"Consider retrying or adjusting parameters."
            )

        return self.complete_thought_and_create_followup(
            thought=thought,
            follow_up_content=follow_up,
            action_result=result,
            status=ThoughtStatus.COMPLETED if success else ThoughtStatus.FAILED,
        )

    async def _create_connects_edge(
        self, params: DreamConsolidationParams, _thought_id: str
    ) -> bool:
        """Create CONNECTS edge between two memories."""
        try:
            edge = GraphEdge(
                source=params.connect_from_id,
                target=params.connect_to_id,
                relationship="CONNECTS",
                scope=GraphScope.IDENTITY,
                weight=0.8,
                attributes=GraphEdgeAttributes(
                    created_at=datetime.now(timezone.utc),
                    context=f"Dream consolidation: {params.connect_pattern}",
                ),
            )

            result = await self.bus_manager.memory.create_edge(
                edge=edge,
                handler_name=self.__class__.__name__,
            )

            if result.status == MemoryOpStatus.OK:
                logger.info(
                    f"[DREAM] Created CONNECTS edge: {params.connect_from_id} → {params.connect_to_id}"
                )
                return True
            else:
                logger.warning(f"[DREAM] CONNECTS edge failed: {result.reason}")
                return False

        except Exception as e:
            logger.error(f"[DREAM] Error creating CONNECTS edge: {e}")
            return False

    async def _create_implies_edge(
        self, params: DreamConsolidationParams, thought_id: str
    ) -> tuple[bool, Optional[str]]:
        """Create insight node and IMPLIES edge."""
        try:
            # First, create the insight node
            insight_node_id = f"insight_{thought_id}"
            insight_node = GraphNode(
                id=insight_node_id,
                type=NodeType.CONCEPT,
                scope=GraphScope.IDENTITY,
                attributes={
                    "content": params.pattern_insight,
                    "insight_type": "behavioral",
                    "implied_action": params.implied_action,
                    "source_pattern": params.connect_pattern,
                    "source": "dream_consolidation",
                    "created_by": self.__class__.__name__,
                    "tags": ["dream", "insight", "behavioral"],
                },
            )

            memorize_result = await self.bus_manager.memory.memorize(
                node=insight_node,
                handler_name=self.__class__.__name__,
            )

            if memorize_result.status != MemoryOpStatus.SUCCESS:
                logger.warning(f"[DREAM] Failed to create insight node: {memorize_result.reason}")
                return False, None

            # Create IMPLIES edge from source memory to insight
            edge = GraphEdge(
                source=params.connect_from_id,
                target=insight_node_id,
                relationship="IMPLIES",
                scope=GraphScope.IDENTITY,
                weight=0.9,
                attributes=GraphEdgeAttributes(
                    created_at=datetime.now(timezone.utc),
                    context=f"Behavioral insight: {params.implied_action}",
                ),
            )

            edge_result = await self.bus_manager.memory.create_edge(
                edge=edge,
                handler_name=self.__class__.__name__,
            )

            if edge_result.status == MemoryOpStatus.OK:
                logger.info(f"[DREAM] Created IMPLIES edge to insight {insight_node_id}")
                return True, insight_node_id
            else:
                logger.warning(f"[DREAM] IMPLIES edge failed: {edge_result.reason}")
                return False, insight_node_id

        except Exception as e:
            logger.error(f"[DREAM] Error creating IMPLIES edge: {e}")
            return False, None

    async def _create_aspires_to_edge(
        self, params: DreamConsolidationParams, thought_id: str
    ) -> bool:
        """Create aspiration node and ASPIRES_TO edge."""
        try:
            # Create or find aspiration node
            aspiration_node_id = f"aspiration_{params.aspiration_category}_{thought_id[:8]}"
            aspiration_node = GraphNode(
                id=aspiration_node_id,
                type=NodeType.CONCEPT,
                scope=GraphScope.IDENTITY,
                attributes={
                    "content": params.aspiration,
                    "aspiration_type": params.aspiration_category,
                    "source": "dream_consolidation",
                    "created_by": self.__class__.__name__,
                    "reflection_notes": params.reflection_notes or "",
                    "tags": ["dream", "aspiration", params.aspiration_category],
                },
            )

            memorize_result = await self.bus_manager.memory.memorize(
                node=aspiration_node,
                handler_name=self.__class__.__name__,
            )

            if memorize_result.status != MemoryOpStatus.SUCCESS:
                logger.warning(f"[DREAM] Failed to create aspiration node: {memorize_result.reason}")
                return False

            # Create ASPIRES_TO edge from agent identity to aspiration
            # "self" is a special node ID representing the agent's identity
            edge = GraphEdge(
                source="agent_identity",
                target=aspiration_node_id,
                relationship="ASPIRES_TO",
                scope=GraphScope.IDENTITY,
                weight=1.0,
                attributes=GraphEdgeAttributes(
                    created_at=datetime.now(timezone.utc),
                    context=f"Dream aspiration: {params.aspiration_category}",
                ),
            )

            edge_result = await self.bus_manager.memory.create_edge(
                edge=edge,
                handler_name=self.__class__.__name__,
            )

            if edge_result.status == MemoryOpStatus.OK:
                logger.info(f"[DREAM] Created ASPIRES_TO edge to {aspiration_node_id}")
                return True
            else:
                logger.warning(f"[DREAM] ASPIRES_TO edge failed: {edge_result.reason}")
                return False

        except Exception as e:
            logger.error(f"[DREAM] Error creating ASPIRES_TO edge: {e}")
            return False
