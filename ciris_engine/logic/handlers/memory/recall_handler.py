import json
import logging
from typing import List, Optional

from ciris_engine.logic import persistence
from ciris_engine.logic.infrastructure.handlers.base_handler import BaseActionHandler
from ciris_engine.logic.infrastructure.handlers.shared_helpers import build_recalled_node_info, fetch_connected_nodes
from ciris_engine.schemas.actions import RecallParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.handlers.memory_schemas import RecallResult
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtStatus
from ciris_engine.schemas.runtime.models import Thought
from ciris_engine.schemas.services.graph.memory import MemorySearchFilter
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryQuery

logger = logging.getLogger(__name__)


class RecallHandler(BaseActionHandler):
    async def handle(
        self, result: ActionSelectionDMAResult, thought: Thought, dispatch_context: DispatchContext
    ) -> Optional[str]:
        raw_params = result.action_parameters
        thought_id = thought.thought_id

        try:
            params: RecallParams = self._validate_and_convert_params(raw_params, RecallParams)
        except Exception as e:
            await self._handle_error(HandlerActionType.RECALL, dispatch_context, thought_id, e)
            persistence.update_thought_status(thought_id=thought_id, status=ThoughtStatus.FAILED)
            return self.complete_thought_and_create_followup(
                thought=thought, follow_up_content=f"RECALL action failed: {e}", action_result=result
            )

        assert isinstance(params, RecallParams)

        # Perform recall query
        nodes = await self._perform_recall_query(params)

        # Build result
        recall_result = await self._build_recall_result(nodes, params)

        return self.complete_thought_and_create_followup(
            thought=thought, follow_up_content=recall_result.to_follow_up_content(), action_result=result
        )

    async def _perform_recall_query(self, params: RecallParams) -> List[GraphNode]:
        """Execute recall query with fallback to search."""
        nodes: List[GraphNode] = []
        scope = params.scope or GraphScope.LOCAL

        # Try exact match first if node_id provided
        if params.node_id:
            memory_query = MemoryQuery(
                node_id=params.node_id,
                scope=scope,
                type=NodeType(params.node_type) if params.node_type else None,
                include_edges=False,
                depth=1,
            )
            nodes = await self.bus_manager.memory.recall(
                recall_query=memory_query, handler_name=self.__class__.__name__
            )

        # Fallback to search if no exact match
        if not nodes:
            nodes = await self._try_search_fallback(params, scope)

        return nodes

    async def _try_search_fallback(self, params: RecallParams, scope: GraphScope) -> List[GraphNode]:
        """Try search-based recall as fallback."""
        search_query = params.query or params.node_id or params.node_type or ""

        search_filter = MemorySearchFilter(node_type=params.node_type, scope=scope.value, limit=params.limit)

        logger.info(f"No exact match for recall, trying search with query: '{search_query}', type: {params.node_type}")
        nodes = await self.bus_manager.memory.search(query=search_query, filters=search_filter)

        # If still no results and we have a node_type, try getting all nodes of that type
        if not nodes and params.node_type and not params.query and not params.node_id:
            nodes = await self._get_all_nodes_of_type(params, scope)

        return nodes

    async def _get_all_nodes_of_type(self, params: RecallParams, scope: GraphScope) -> List[GraphNode]:
        """Get all nodes of a specific type."""
        wildcard_query = MemoryQuery(
            node_id="*",
            scope=scope,
            type=NodeType(params.node_type),
            include_edges=False,
            depth=1,
        )
        nodes = await self.bus_manager.memory.recall(recall_query=wildcard_query, handler_name=self.__class__.__name__)

        # Apply limit
        if nodes and len(nodes) > params.limit:
            nodes = nodes[: params.limit]

        return nodes

    async def _build_recall_result(self, nodes: List[GraphNode], params: RecallParams) -> RecallResult:
        """Build RecallResult with connected nodes."""
        query_desc = self._build_query_description(params)
        success = bool(nodes)

        recall_result = RecallResult(
            success=success,
            query_description=query_desc,
            total_results=len(nodes) if success else 0,
        )

        if not success:
            return recall_result

        # Process each node
        for node in nodes:
            node_info = build_recalled_node_info(node)

            # Fetch connected nodes
            connected = await fetch_connected_nodes(node, self.bus_manager, self.__class__.__name__)
            if connected:
                node_info.connected_nodes = connected

            recall_result.nodes[node.id] = node_info

        # Check if results need truncation
        self._check_truncation(recall_result)

        return recall_result

    def _build_query_description(self, params: RecallParams) -> str:
        """Build a descriptive query string."""
        query_desc = params.node_id or params.query or "recall request"
        if params.node_type and params.query:
            query_desc = f"{params.node_type} {query_desc}"
        elif params.node_type and not params.query and not params.node_id:
            query_desc = f"{params.node_type} {query_desc}"
        return query_desc

    def _check_truncation(self, recall_result: RecallResult) -> None:
        """Check if results should be marked as truncated."""
        data_str = json.dumps(
            {k: v.model_dump() for k, v in recall_result.nodes.items()},
            indent=2,
            default=str,
        )
        if len(data_str) > 10000:
            recall_result.truncated = True
