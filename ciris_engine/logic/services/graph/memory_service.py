from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Dict, List, Optional, Union
from uuid import uuid4

from ciris_engine.constants import UTC_TIMEZONE_SUFFIX
from ciris_engine.logic.config import get_sqlite_db_full_path
from ciris_engine.logic.persistence import get_db_connection, initialize_database
from ciris_engine.logic.secrets.service import SecretsService
from ciris_engine.logic.services.base_graph_service import BaseGraphService, GraphNodeConvertible
from ciris_engine.protocols.services import GraphMemoryServiceProtocol, MemoryService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.memory import TimeSeriesDataPoint
from ciris_engine.schemas.secrets.service import DecapsulationContext
from ciris_engine.schemas.services.graph.attributes import AnyNodeAttributes, NodeAttributes, TelemetryNodeAttributes
from ciris_engine.schemas.services.graph.memory import MemorySearchFilter
from ciris_engine.schemas.services.graph_core import GraphEdge, GraphNode, GraphNodeAttributes, GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryOpResult, MemoryOpStatus, MemoryQuery

# No longer using psutil - resource_monitor handles process metrics


logger = logging.getLogger(__name__)


class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles datetime objects and Pydantic models."""

    def default(self, obj: object) -> Union[str, dict, list, int, float, bool, None]:
        if isinstance(obj, datetime):
            return obj.isoformat()
        # Handle Pydantic models
        if hasattr(obj, "model_dump"):
            return obj.model_dump()  # type: ignore[no-any-return]
        # Handle any object with to_dict method
        if hasattr(obj, "to_dict"):
            return obj.to_dict()  # type: ignore[no-any-return]
        return super().default(obj)  # type: ignore[no-any-return]


class LocalGraphMemoryService(BaseGraphService, MemoryService, GraphMemoryServiceProtocol):
    """Graph memory backed by the persistence database."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        secrets_service: Optional[SecretsService] = None,
        time_service: Optional[TimeServiceProtocol] = None,
    ) -> None:
        # Initialize BaseGraphService - LocalGraphMemoryService doesn't use memory_bus
        super().__init__(memory_bus=None, time_service=time_service)

        self.db_path = db_path or get_sqlite_db_full_path()
        initialize_database(db_path=self.db_path)
        self.secrets_service = secrets_service  # Must be provided, not created here
        self._start_time: Optional[datetime] = None

    async def memorize(self, node: GraphNode) -> MemoryOpResult:
        """Store a node with automatic secrets detection and processing."""
        self._track_request()
        try:
            # Process secrets in node attributes before storing
            processed_node = await self._process_secrets_for_memorize(node)

            from ciris_engine.logic.persistence.models import graph as persistence

            if self._time_service:
                persistence.add_graph_node(processed_node, db_path=self.db_path, time_service=self._time_service)
            else:
                raise RuntimeError("TimeService is required for adding graph nodes")
            return MemoryOpResult(status=MemoryOpStatus.OK)
        except Exception as e:
            logger.exception("Error storing node %s: %s", node.id, e)
            return MemoryOpResult(status=MemoryOpStatus.DENIED, error=str(e))

    async def recall(self, recall_query: MemoryQuery) -> List[GraphNode]:
        """Recall nodes from memory based on query."""
        self._track_request()
        try:
            from ciris_engine.logic.persistence import get_all_graph_nodes
            from ciris_engine.logic.persistence.models import graph as persistence

            logger.debug(
                f"Memory recall called with node_id='{recall_query.node_id}', scope={recall_query.scope}, type={recall_query.type}"
            )

            # Check if this is a wildcard query
            if recall_query.node_id in ["*", "%", "all"]:
                logger.debug(f"Memory recall: wildcard query with scope {recall_query.scope}, type {recall_query.type}")

                # Use the new get_all_graph_nodes function
                nodes = get_all_graph_nodes(
                    scope=recall_query.scope,
                    node_type=recall_query.type.value if recall_query.type else None,
                    limit=100,  # Reasonable default limit for wildcard queries
                    db_path=self.db_path,
                )
                logger.debug(f"Wildcard query returned {len(nodes)} nodes")

                # Process secrets for all nodes
                processed_nodes = []
                for node in nodes:
                    # Process attributes - convert to proper schema
                    processed_attrs: Union[AnyNodeAttributes, GraphNodeAttributes, dict] = {}
                    if node.attributes:
                        processed_attrs = await self._process_secrets_for_recall(node.attributes, "recall")

                    # Include edges if requested
                    if recall_query.include_edges:
                        from ciris_engine.logic.persistence.models.graph import get_edges_for_node

                        edges = get_edges_for_node(node.id, node.scope, db_path=self.db_path)

                        if edges:
                            edges_data = []
                            for edge in edges:
                                edge_dict = {
                                    "source": edge.source,
                                    "target": edge.target,
                                    "relationship": edge.relationship,
                                    "weight": edge.weight,
                                    "attributes": (
                                        edge.attributes.model_dump()
                                        if hasattr(edge.attributes, "model_dump")
                                        else edge.attributes
                                    ),
                                }
                                edges_data.append(edge_dict)

                            # Add edges to attributes
                            # processed_attrs is always a dict after _process_secrets_for_recall
                            if isinstance(processed_attrs, dict):
                                processed_attrs["_edges"] = edges_data

                    processed_node = GraphNode(
                        id=node.id,
                        type=node.type,
                        scope=node.scope,
                        attributes=processed_attrs,
                        version=node.version,
                        updated_by=node.updated_by,
                        updated_at=node.updated_at,
                    )
                    processed_nodes.append(processed_node)

                return processed_nodes

            else:
                # Regular single node query
                logger.debug(f"Memory recall: getting node {recall_query.node_id} scope {recall_query.scope}")
                stored = persistence.get_graph_node(recall_query.node_id, recall_query.scope, db_path=self.db_path)
                if not stored:
                    return []

                # Process secrets in the node's attributes
                if stored.attributes:
                    processed_attrs = await self._process_secrets_for_recall(stored.attributes, "recall")
                    stored = GraphNode(
                        id=stored.id,
                        type=stored.type,
                        scope=stored.scope,
                        attributes=processed_attrs,
                        version=stored.version,
                        updated_by=stored.updated_by,
                        updated_at=stored.updated_at,
                    )

                nodes = [stored]

                # If include_edges is True, fetch connected nodes up to specified depth
                if recall_query.include_edges and recall_query.depth > 0:
                    # Import edge functions
                    from ciris_engine.logic.persistence.models.graph import get_edges_for_node

                    # Get edges for the node
                    edges = get_edges_for_node(stored.id, stored.scope, db_path=self.db_path)

                    # Add edges to the node's attributes if they exist
                    if edges:
                        # Convert edges to dict format for inclusion in response
                        edges_data = []
                        for edge in edges:
                            edge_dict = {
                                "source": edge.source,
                                "target": edge.target,
                                "relationship": edge.relationship,
                                "weight": edge.weight,
                                "attributes": (
                                    edge.attributes.model_dump()
                                    if hasattr(edge.attributes, "model_dump")
                                    else edge.attributes
                                ),
                            }
                            edges_data.append(edge_dict)

                        # Add edges to node attributes
                        # Need to ensure we have a mutable dict for attributes
                        if isinstance(stored.attributes, dict):
                            stored.attributes["_edges"] = edges_data
                        else:
                            # For typed attributes, we need to convert to dict first
                            attrs_dict = (
                                stored.attributes.model_dump()
                                if hasattr(stored.attributes, "model_dump")
                                else dict(stored.attributes) if stored.attributes else {}
                            )
                            attrs_dict["_edges"] = edges_data
                            stored = GraphNode(
                                id=stored.id,
                                type=stored.type,
                                scope=stored.scope,
                                attributes=attrs_dict,
                                version=stored.version,
                                updated_by=stored.updated_by,
                                updated_at=stored.updated_at,
                            )

                        nodes = [stored]

                    # If depth > 1, fetch connected nodes recursively
                    if recall_query.depth > 1:
                        visited_nodes = {stored.id}
                        nodes_to_process = [(stored, 0)]
                        all_nodes = [stored]

                        while nodes_to_process:
                            current_node, current_depth = nodes_to_process.pop(0)

                            if current_depth < recall_query.depth - 1:
                                # Get edges for current node
                                current_edges = get_edges_for_node(
                                    current_node.id, current_node.scope, db_path=self.db_path
                                )

                                for edge in current_edges:
                                    # Determine the connected node ID
                                    connected_id = edge.target if edge.source == current_node.id else edge.source

                                    if connected_id not in visited_nodes:
                                        # Fetch the connected node
                                        connected_node = persistence.get_graph_node(
                                            connected_id, edge.scope, db_path=self.db_path
                                        )
                                        if connected_node:
                                            visited_nodes.add(connected_id)

                                            # Process secrets if needed
                                            connected_processed_attrs: Union[
                                                AnyNodeAttributes, GraphNodeAttributes, dict
                                            ] = {}
                                            if connected_node.attributes:
                                                connected_processed_attrs = await self._process_secrets_for_recall(
                                                    connected_node.attributes, "recall"
                                                )

                                            # Add edges to connected node
                                            connected_edges = get_edges_for_node(
                                                connected_node.id, connected_node.scope, db_path=self.db_path
                                            )
                                            if connected_edges:
                                                edges_data = []
                                                for e in connected_edges:
                                                    edge_dict = {
                                                        "source": e.source,
                                                        "target": e.target,
                                                        "relationship": e.relationship,
                                                        "weight": e.weight,
                                                        "attributes": (
                                                            e.attributes.model_dump()
                                                            if hasattr(e.attributes, "model_dump")
                                                            else e.attributes
                                                        ),
                                                    }
                                                    edges_data.append(edge_dict)

                                                # Add edges to processed attributes dict
                                                if isinstance(connected_processed_attrs, dict):
                                                    connected_processed_attrs["_edges"] = edges_data

                                            # Create new node with processed attributes
                                            connected_node = GraphNode(
                                                id=connected_node.id,
                                                type=connected_node.type,
                                                scope=connected_node.scope,
                                                attributes=connected_processed_attrs,
                                                version=connected_node.version,
                                                updated_by=connected_node.updated_by,
                                                updated_at=connected_node.updated_at,
                                            )

                                            all_nodes.append(connected_node)
                                            nodes_to_process.append((connected_node, current_depth + 1))

                        nodes = all_nodes

                return nodes

        except Exception as e:
            logger.exception("Error recalling nodes for query %s: %s", recall_query.node_id, e)
            return []

    def forget(self, node: GraphNode) -> MemoryOpResult:
        """Forget a node and clean up any associated secrets."""
        self._track_request()
        try:
            # First retrieve the node to check for secrets
            from ciris_engine.logic.persistence.models import graph as persistence

            stored = persistence.get_graph_node(node.id, node.scope, db_path=self.db_path)
            if stored:
                self._process_secrets_for_forget(stored.attributes)

            from ciris_engine.logic.persistence.models import graph as persistence

            persistence.delete_graph_node(node.id, node.scope, db_path=self.db_path)
            return MemoryOpResult(status=MemoryOpStatus.OK)
        except Exception as e:
            logger.exception("Error forgetting node %s: %s", node.id, e)
            return MemoryOpResult(status=MemoryOpStatus.DENIED, error=str(e))

    def export_identity_context(self) -> str:
        lines: List[str] = []
        with get_db_connection(db_path=self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT node_id, attributes_json FROM graph_nodes WHERE scope = ?", (GraphScope.IDENTITY.value,)
            )
            for row in cursor.fetchall():
                attrs = json.loads(row["attributes_json"]) if row["attributes_json"] else {}
                lines.append(f"{row['node_id']}: {attrs}")
        return "\n".join(lines)

    async def _process_secrets_for_memorize(self, node: GraphNode) -> GraphNode:
        """Process secrets in node attributes during memorization."""
        if not node.attributes:
            return node

        # Convert attributes to JSON string for processing
        # Handle both dict and Pydantic model attributes
        if hasattr(node.attributes, "model_dump"):
            attributes_dict = node.attributes.model_dump()
        else:
            attributes_dict = node.attributes
        attributes_str = json.dumps(attributes_dict, cls=DateTimeEncoder)

        # Process for secrets detection and replacement
        # SecretsService requires source_message_id
        if not self.secrets_service:
            return node
        processed_text, secret_refs = await self.secrets_service.process_incoming_text(
            attributes_str, source_message_id=f"memorize_{node.id}"
        )

        # Create new node with processed attributes
        processed_attributes = json.loads(processed_text) if processed_text != attributes_str else node.attributes

        # Add secret references to node metadata if any were found
        if secret_refs:
            if isinstance(processed_attributes, dict):
                processed_attributes.setdefault("secret_refs", []).extend([ref.uuid for ref in secret_refs])
            logger.info(f"Stored {len(secret_refs)} secret references in memory node {node.id}")

        return GraphNode(
            id=node.id,
            type=node.type,
            scope=node.scope,
            attributes=processed_attributes,
            version=node.version,
            updated_by=node.updated_by,
            updated_at=node.updated_at,
        )

    async def _process_secrets_for_recall(
        self, attributes: Union[AnyNodeAttributes, GraphNodeAttributes, dict], action_type: str
    ) -> dict:
        """Process secrets in recalled attributes for potential decryption."""
        if not attributes:
            return {}

        # Convert GraphNodeAttributes to dict if needed
        attributes_dict: dict
        if hasattr(attributes, "model_dump"):
            attributes_dict = attributes.model_dump()
        elif hasattr(attributes, "dict"):
            attributes_dict = attributes.dict()
        else:  # isinstance(attributes, dict)
            attributes_dict = attributes

        secret_refs = attributes_dict.get("secret_refs", [])
        if not secret_refs:
            return attributes_dict

        should_decrypt = False
        if self.secrets_service and hasattr(self.secrets_service, "filter"):
            should_decrypt = action_type in getattr(
                self.secrets_service.filter.detection_config, "auto_decrypt_for_actions", ["speak", "tool"]
            )

        if should_decrypt:
            _attributes_str = json.dumps(attributes_dict, cls=DateTimeEncoder)

            if not self.secrets_service:
                return attributes_dict
            decapsulated_attributes = await self.secrets_service.decapsulate_secrets_in_parameters(
                action_type=action_type,
                action_params=attributes_dict,
                context=DecapsulationContext(action_type=action_type, thought_id="memory_recall", user_id="system"),
            )

            if decapsulated_attributes != attributes_dict:
                logger.info(f"Auto-decrypted secrets in recalled data for {action_type}")
                # Type assertion: decapsulate_secrets_in_parameters should return dict
                assert isinstance(decapsulated_attributes, dict)
                return decapsulated_attributes

        return attributes_dict

    def _process_secrets_for_forget(self, attributes: Union[AnyNodeAttributes, GraphNodeAttributes, dict]) -> None:
        """Clean up secrets when forgetting a node."""
        if not attributes:
            return

        # Convert GraphNodeAttributes to dict if needed
        attributes_dict: dict
        if hasattr(attributes, "model_dump"):
            attributes_dict = attributes.model_dump()
        elif hasattr(attributes, "dict"):
            attributes_dict = attributes.dict()
        else:  # isinstance(attributes, dict)
            attributes_dict = attributes

        # Check for secret references
        secret_refs = attributes_dict.get("secret_refs", [])
        if secret_refs:
            # Note: We don't automatically delete secrets on FORGET since they might be
            # referenced elsewhere. This would need to be a conscious decision by the agent.
            if isinstance(secret_refs, list):
                logger.info(f"Node being forgotten contained {len(secret_refs)} secret references")
            else:
                logger.info("Node being forgotten contained secret references")

            # Could implement reference counting here in the future if needed

    async def recall_timeseries(
        self,
        scope: str = "default",
        hours: int = 24,
        correlation_types: Optional[List[str]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[TimeSeriesDataPoint]:
        """
        Recall time-series data from TSDB graph nodes.

        Args:
            scope: The memory scope to search (mapped to TSDB tags)
            hours: Number of hours to look back (ignored if start_time/end_time provided)
            correlation_types: Optional filter by correlation types (for compatibility)
            start_time: Specific start time for the query (overrides hours)
            end_time: Specific end time for the query (defaults to now if not provided)

        Returns:
            List of time-series data points from graph nodes
        """
        self._track_request()
        try:
            # Calculate time window
            if not self._time_service:
                raise RuntimeError("TimeService is required for recall_timeseries")

            # Handle time range parameters
            if start_time and end_time:
                # Use explicit time range
                pass
            elif start_time and not end_time:
                # Start time provided, use now as end
                end_time = self._time_service.now()
            else:
                # Fall back to hours-based calculation (backward compatible)
                end_time = end_time or self._time_service.now()
                start_time = end_time - timedelta(hours=hours)

            # Query TSDB_DATA nodes directly from graph_nodes table
            data_points: List[TimeSeriesDataPoint] = []

            # Run database query in thread pool to avoid blocking event loop
            import asyncio

            loop = asyncio.get_event_loop()

            def _query_tsdb_nodes():
                with get_db_connection(db_path=self.db_path) as conn:
                    cursor = conn.cursor()

                    # Query for TSDB_DATA nodes in the time range
                    # ORDER BY DESC to get most recent metrics first
                    cursor.execute(
                        """
                        SELECT node_id, attributes_json, created_at
                        FROM graph_nodes
                        WHERE node_type = 'tsdb_data'
                          AND scope = ?
                          AND datetime(created_at) >= datetime(?)
                          AND datetime(created_at) <= datetime(?)
                        ORDER BY created_at DESC
                        LIMIT 1000
                    """,
                        (scope, start_time.isoformat(), end_time.isoformat()),
                    )

                    return cursor.fetchall()

            rows = await loop.run_in_executor(None, _query_tsdb_nodes)

            for row in rows:
                try:
                    # Parse attributes
                    attrs = json.loads(row["attributes_json"]) if row["attributes_json"] else {}

                    # Extract metric data
                    metric_name = attrs.get("metric_name")
                    metric_value = attrs.get("value")

                    if not metric_name or metric_value is None:
                        continue

                    # Get timestamp from created_at or attributes
                    timestamp_str = attrs.get("created_at", row["created_at"])
                    if isinstance(timestamp_str, str):
                        # Handle both timezone-aware and naive timestamps
                        if "Z" in timestamp_str:
                            timestamp = datetime.fromisoformat(timestamp_str.replace("Z", UTC_TIMEZONE_SUFFIX))
                        elif "+" in timestamp_str or "-" in timestamp_str[-6:]:
                            timestamp = datetime.fromisoformat(timestamp_str)
                        else:
                            # Naive timestamp - assume UTC
                            timestamp = datetime.fromisoformat(timestamp_str)
                            if timestamp.tzinfo is None:
                                timestamp = timestamp.replace(tzinfo=timezone.utc)
                    else:
                        timestamp = timestamp_str
                        # Ensure timezone awareness
                        if hasattr(timestamp, "tzinfo") and timestamp.tzinfo is None:
                            timestamp = timestamp.replace(tzinfo=timezone.utc)

                    # Get tags
                    metric_tags = attrs.get("metric_tags", {})
                    if not isinstance(metric_tags, dict):
                        metric_tags = {}

                    # Create data point
                    data_point = TimeSeriesDataPoint(
                        timestamp=timestamp,
                        metric_name=metric_name,
                        value=float(metric_value),
                        correlation_type="METRIC_DATAPOINT",  # Default for metrics
                        tags=metric_tags,
                        source=attrs.get("created_by", "memory_service"),
                    )
                    data_points.append(data_point)

                except Exception as e:
                    logger.warning(f"Error parsing TSDB node {row['node_id']}: {e}")
                    continue

            # Sort by timestamp
            data_points.sort(key=lambda x: x.timestamp)

            logger.debug(f"Recalled {len(data_points)} time series data points from graph nodes")
            return data_points

        except Exception as e:
            logger.exception(f"Error recalling timeseries data: {e}")
            return []

    async def memorize_metric(
        self, metric_name: str, value: float, tags: Optional[Dict[str, str]] = None, scope: str = "local"
    ) -> MemoryOpResult:
        """
        Convenience method to memorize a metric as a graph node.

        Metrics are stored only as TSDB_DATA nodes in the graph, not as correlations,
        to prevent double storage and aggregation issues.
        """
        self._track_request()
        try:
            # Create a graph node for the metric
            if not self._time_service:
                raise RuntimeError("TimeService is required for memorize_metric")
            now = self._time_service.now()
            # Use microsecond precision to ensure unique IDs
            node_id = f"metric_{metric_name}_{int(now.timestamp() * 1000000)}"

            # Create typed attributes with metric-specific data
            telemetry_attrs = TelemetryNodeAttributes(
                created_at=now,
                updated_at=now,
                created_by="memory_service",
                tags=["metric", metric_name],
                metric_name=metric_name,
                metric_type="gauge",  # Default metric type
                value=value,
                start_time=now,
                end_time=now,
                duration_seconds=0.0,
                sample_count=1,
                labels=tags or {},
                service_name="memory_service",
            )

            node = GraphNode(
                id=node_id,
                type=NodeType.TSDB_DATA,
                scope=GraphScope(scope),
                attributes=telemetry_attrs.model_dump(),  # Convert to dict for storage
                updated_by="memory_service",
                updated_at=now,
            )

            # Store in graph memory
            memory_result = await self.memorize(node)

            # No longer storing metrics as correlations - only as graph nodes
            # This prevents double storage and inflated aggregation issues

            return memory_result

        except Exception as e:
            logger.exception(f"Error memorizing metric {metric_name}: {e}")
            return MemoryOpResult(status=MemoryOpStatus.DENIED, error=str(e))

    def create_edge(self, edge: GraphEdge) -> MemoryOpResult:
        """Create an edge between two nodes in the memory graph."""
        self._track_request()
        try:
            from ciris_engine.logic.persistence.models.graph import add_graph_edge

            edge_id = add_graph_edge(edge, db_path=self.db_path)
            logger.info(f"Created edge {edge_id}: {edge.source} -{edge.relationship}-> {edge.target}")

            return MemoryOpResult(status=MemoryOpStatus.OK)
        except Exception as e:
            logger.exception(f"Error creating edge: {e}")
            return MemoryOpResult(status=MemoryOpStatus.DENIED, error=str(e))

    def get_node_edges(self, node_id: str, scope: GraphScope) -> List[GraphEdge]:
        """Get all edges connected to a node."""
        try:
            from ciris_engine.logic.persistence.models.graph import get_edges_for_node

            edges = get_edges_for_node(node_id, scope, db_path=self.db_path)
            return edges
        except Exception as e:
            logger.exception(f"Error getting edges for node {node_id}: {e}")
            return []

    async def memorize_log(
        self, log_message: str, log_level: str = "INFO", tags: Optional[Dict[str, str]] = None, scope: str = "local"
    ) -> MemoryOpResult:
        """
        Convenience method to memorize a log entry as both a graph node and TSDB correlation.
        """
        self._track_request()
        try:
            # Import correlation models here to avoid circular imports
            from ciris_engine.logic.persistence.models.correlations import add_correlation
            from ciris_engine.schemas.telemetry.core import (
                CorrelationType,
                ServiceCorrelation,
                ServiceCorrelationStatus,
            )

            # Create a graph node for the log entry
            if not self._time_service:
                raise RuntimeError("TimeService is required for memorize_log")
            now = self._time_service.now()
            node_id = f"log_{log_level}_{int(now.timestamp())}"

            # Create typed attributes with log-specific data
            # Using base NodeAttributes with additional log fields in the dict
            node_attrs = NodeAttributes(
                created_at=now, updated_at=now, created_by="memory_service", tags=["log", log_level.lower()]
            )

            # Convert to dict and add log-specific fields
            attrs_dict = node_attrs.model_dump()
            attrs_dict.update(
                {"log_message": log_message, "log_level": log_level, "log_tags": tags or {}, "retention_policy": "raw"}
            )

            node = GraphNode(
                id=node_id,
                type=NodeType.TSDB_DATA,
                scope=GraphScope(scope),
                attributes=attrs_dict,
                updated_by="memory_service",
                updated_at=now,
            )

            # Store in graph memory
            memory_result = await self.memorize(node)

            # Also store as TSDB correlation
            correlation = ServiceCorrelation(
                correlation_id=str(uuid4()),
                service_type="memory",
                handler_name="memory_service",
                action_type="memorize_log",
                correlation_type=CorrelationType.LOG_ENTRY,
                timestamp=now,
                created_at=now,
                updated_at=now,
                tags=(
                    {**tags, "scope": scope, "message": log_message}
                    if tags
                    else {"scope": scope, "message": log_message}
                ),
                status=ServiceCorrelationStatus.COMPLETED,
                retention_policy="raw",
                request_data=None,
                response_data=None,
                metric_data=None,
                log_data=None,
                trace_context=None,
                ttl_seconds=None,
                parent_correlation_id=None,
            )

            if self._time_service:
                add_correlation(correlation, db_path=self.db_path, time_service=self._time_service)
            else:
                raise RuntimeError("TimeService is required for add_correlation")

            return memory_result

        except Exception as e:
            logger.exception(f"Error memorizing log entry: {e}")
            return MemoryOpResult(status=MemoryOpStatus.DENIED, error=str(e))

    # ============================================================================
    # GRAPH PROTOCOL METHODS
    # ============================================================================

    async def search(self, query: str, filters: Optional[MemorySearchFilter] = None) -> List[GraphNode]:
        """Search memories in the graph."""
        self._track_request()
        logger.debug(f"Memory search START: query='{query}', filters={filters}")
        try:
            from ciris_engine.logic.persistence import get_all_graph_nodes, get_nodes_by_type

            # Extract filters
            scope = filters.scope if filters and hasattr(filters, "scope") else GraphScope.LOCAL
            node_type = filters.node_type if filters and hasattr(filters, "node_type") else None
            limit = filters.limit if filters and hasattr(filters, "limit") else 100

            # Parse query string for additional filters
            query_parts = query.split() if query else []
            for part in query_parts:
                if part.startswith("type:"):
                    # Override node_type from query string if provided
                    node_type = part.split(":")[1]
                elif part.startswith("scope:"):
                    # Override scope from query string if provided
                    scope = GraphScope(part.split(":")[1].lower())

            # Use the new persistence functions
            if node_type:
                nodes = get_nodes_by_type(
                    node_type=node_type,
                    scope=scope if isinstance(scope, GraphScope) else GraphScope.LOCAL,
                    limit=limit,
                    db_path=self.db_path,
                )
            else:
                nodes = get_all_graph_nodes(
                    scope=scope if isinstance(scope, GraphScope) else GraphScope.LOCAL,
                    limit=limit,
                    db_path=self.db_path,
                )

            # If query contains text search terms (not just filters), filter by content
            if query and not all(part.startswith(("type:", "scope:")) for part in query_parts):
                search_terms = [part.lower() for part in query_parts if not part.startswith(("type:", "scope:"))]
                filtered_nodes = []

                for node in nodes:
                    # Search in node ID
                    if any(term in node.id.lower() for term in search_terms):
                        filtered_nodes.append(node)
                        continue

                    # Search in attributes
                    if node.attributes:
                        attrs_str = json.dumps(node.attributes, cls=DateTimeEncoder).lower()
                        if any(term in attrs_str for term in search_terms):
                            filtered_nodes.append(node)

                nodes = filtered_nodes

            # Process secrets for recall
            processed_nodes = []
            for node in nodes:
                if node.attributes:
                    processed_attrs = await self._process_secrets_for_recall(node.attributes, "search")
                    processed_node = GraphNode(
                        id=node.id,
                        type=node.type,
                        scope=node.scope,
                        attributes=processed_attrs,
                        version=node.version,
                        updated_by=node.updated_by,
                        updated_at=node.updated_at,
                    )
                    processed_nodes.append(processed_node)
                else:
                    processed_nodes.append(node)

            return processed_nodes

        except Exception as e:
            logger.exception(f"Error searching graph: {e}")
            return []

    # ============================================================================
    # SERVICE PROTOCOL METHODS
    # ============================================================================

    def start(self) -> None:
        """Start the memory service."""
        # Don't call super() as BaseService has async start
        self._started = True
        self._initialized = True
        if self._time_service:
            self._start_time = self._time_service.now()
        logger.info("LocalGraphMemoryService started")

    def stop(self) -> None:
        """Stop the memory service."""
        logger.info("LocalGraphMemoryService stopped")
        # Don't call super() as BaseService has async stop
        self._started = False

    def _collect_custom_metrics(self) -> Dict[str, float]:
        """Collect memory-specific metrics from v1.4.3 set."""
        metrics = super()._collect_custom_metrics()

        # Count graph nodes and edges
        node_count = 0
        edge_count = 0
        storage_size_mb = 0.0

        try:
            with get_db_connection(db_path=self.db_path) as conn:
                cursor = conn.cursor()

                # Get node count
                cursor.execute("SELECT COUNT(*) FROM graph_nodes")
                result = cursor.fetchone()
                node_count = result[0] if result else 0

                # Get edge count
                cursor.execute("SELECT COUNT(*) FROM graph_edges")
                result = cursor.fetchone()
                edge_count = result[0] if result else 0

        except Exception:
            pass

        # Get database file size
        try:
            import os

            if os.path.exists(self.db_path):
                storage_size_mb = os.path.getsize(self.db_path) / (1024 * 1024)
        except (OSError, IOError, ImportError):
            # Ignore file system and import errors when checking storage size
            pass

        # Calculate uptime in seconds
        uptime_seconds = 0.0
        if self._start_time and self._time_service:
            uptime_delta = self._time_service.now() - self._start_time
            uptime_seconds = uptime_delta.total_seconds()

        # Return EXACTLY the 5 metrics from v1.4.3 set - no other metrics
        memory_metrics = {
            "memory_nodes_total": float(node_count),
            "memory_edges_total": float(edge_count),
            "memory_operations_total": float(self._request_count),
            "memory_db_size_mb": storage_size_mb,
            "memory_uptime_seconds": uptime_seconds,
            # Add secrets_enabled metric for test compatibility
            "secrets_enabled": 1.0 if self.secrets_service else 0.0,
        }

        # Update with the exact v1.4.3 memory metrics
        metrics.update(memory_metrics)

        return metrics

    async def is_healthy(self) -> bool:
        """Check if service is healthy."""
        # Check if service is started
        if not hasattr(self, "_started") or not self._started:
            return False

        try:
            # Try a simple database operation
            with get_db_connection(db_path=self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM graph_nodes")
                cursor.fetchone()
            return True
        except Exception:
            return False

    async def store_in_graph(self, node: Union[GraphNode, GraphNodeConvertible]) -> str:
        """Store a node in the graph."""
        # Convert to GraphNode if needed
        if hasattr(node, "to_graph_node"):
            graph_node = node.to_graph_node()
        else:
            graph_node = node

        result = await self.memorize(graph_node)
        return graph_node.id if result.status == MemoryOpStatus.OK else ""

    async def query_graph(self, query: MemoryQuery) -> List[GraphNode]:
        """Query the graph."""
        return await self.recall(query)

    def get_node_type(self) -> str:
        """Get the type of nodes this service manages."""
        return "ALL"  # Memory service manages all node types

    # Required methods for BaseGraphService

    def get_service_type(self) -> ServiceType:
        """Get the service type."""
        return ServiceType.MEMORY

    def _get_actions(self) -> List[str]:
        """Get the list of actions this service supports."""
        return [
            "memorize",
            "recall",
            "forget",
            "memorize_metric",
            "memorize_log",
            "recall_timeseries",
            "export_identity_context",
            "search",
            "create_edge",
            "get_node_edges",
        ]

    def _check_dependencies(self) -> bool:
        """Check if all dependencies are satisfied."""
        # Memory service doesn't use memory bus (it IS what memory bus uses)
        # Check for optional dependencies
        return True  # Base memory service has no hard dependencies
