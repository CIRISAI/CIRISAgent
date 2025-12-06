"""
Metrics consolidation for TSDB data.

Consolidates both service correlations AND graph nodes of type TSDB_DATA.
"""

import logging
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ciris_engine.logic.buses.memory_bus import MemoryBus
from ciris_engine.logic.utils.jsondict_helpers import get_dict, get_float, get_int, get_str
from ciris_engine.schemas.services.graph.consolidation import MetricCorrelationData
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope
from ciris_engine.schemas.services.nodes import TSDBSummary
from ciris_engine.schemas.services.operations import MemoryOpStatus
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


class MetricsConsolidator:
    """Consolidates metrics from multiple sources."""

    def __init__(self, memory_bus: Optional[MemoryBus] = None):
        """
        Initialize metrics consolidator.

        Args:
            memory_bus: Memory bus for storing results
        """
        self._memory_bus = memory_bus

    async def consolidate(
        self,
        period_start: datetime,
        period_end: datetime,
        period_label: str,
        tsdb_nodes: List[GraphNode],
        metric_correlations: List[MetricCorrelationData],
    ) -> Optional[TSDBSummary]:
        """
        Consolidate metrics from both graph nodes and correlations.

        Args:
            period_start: Start of consolidation period
            period_end: End of consolidation period
            period_label: Human-readable period label
            tsdb_nodes: TSDB_DATA nodes from graph
            metric_correlations: List of MetricCorrelationData objects

        Returns:
            TSDBSummary node if successful, None otherwise
        """
        # Combine data from both sources
        all_metrics = []

        # Process TSDB nodes
        for node in tsdb_nodes:
            attrs = node.attributes
            if isinstance(attrs, dict):
                metric_data = {
                    "metric_name": get_str(attrs, "metric_name", "unknown"),
                    "value": get_float(attrs, "value", 0.0),
                    "timestamp": attrs.get("timestamp"),
                    "tags": get_dict(attrs, "tags", {}),
                    "source": "graph_node",
                }
            else:
                # Handle GraphNodeAttributes
                attrs_dict = attrs.model_dump() if hasattr(attrs, "model_dump") else {}
                metric_data = {
                    "metric_name": get_str(attrs_dict, "metric_name", "unknown"),
                    "value": get_float(attrs_dict, "value", 0.0),
                    "timestamp": attrs_dict.get("timestamp"),
                    "tags": get_dict(attrs_dict, "tags", {}),
                    "source": "graph_node",
                }
            all_metrics.append(metric_data)

        # Process correlations using typed schema
        for corr in metric_correlations:
            metric_data = {
                "metric_name": corr.metric_name,
                "value": corr.value,
                "timestamp": corr.timestamp.isoformat() if isinstance(corr.timestamp, datetime) else corr.timestamp,
                "tags": corr.tags,
                "source": corr.source,
            }
            all_metrics.append(metric_data)

        if not all_metrics:
            logger.info(f"No metrics found for period {period_start} to {period_end} - creating empty summary")

        logger.info(
            f"Consolidating {len(all_metrics)} metrics ({len(tsdb_nodes)} nodes, {len(metric_correlations)} correlations)"
        )

        # Aggregate metrics
        metrics_by_name = defaultdict(list)
        resource_totals = {"tokens": 0, "cost": 0.0, "carbon": 0.0, "energy": 0.0}
        action_counts: Dict[str, int] = defaultdict(int)
        error_count = 0
        success_count = 0
        total_operations = 0

        for metric in all_metrics:
            # Type narrowing with isinstance checks
            metric_name_val = metric.get("metric_name")
            metric_name = str(metric_name_val) if isinstance(metric_name_val, str) else "unknown"

            value_val = metric.get("value")
            if isinstance(value_val, (int, float)):
                value = float(value_val)
            else:
                value = 0.0

            # Collect values by metric name
            metrics_by_name[metric_name].append(value)

            # Extract resource usage
            if "tokens_used" in metric_name or "tokens.total" in metric_name:
                resource_totals["tokens"] += int(value)
            elif "cost_cents" in metric_name or "cost.cents" in metric_name:
                resource_totals["cost"] += value
            elif "carbon_grams" in metric_name or "carbon.grams" in metric_name:
                resource_totals["carbon"] += value
            elif "energy_kwh" in metric_name or "energy.kwh" in metric_name:
                resource_totals["energy"] += value

            # Count actions
            if metric_name.startswith("action.") and metric_name.endswith(".count"):
                action_type = metric_name.split(".")[1].upper()
                action_counts[action_type] += int(value)
                total_operations += int(value)
            elif metric_name.startswith("action_selected_"):
                action_type = metric_name.replace("action_selected_", "").upper()
                action_counts[action_type] += 1
                total_operations += 1

            # Count errors and successes
            if "error" in metric_name and value > 0:
                error_count += int(value)
            elif "success" in metric_name:
                success_count += int(value)
                if "action" not in metric_name:  # Avoid double counting
                    total_operations += int(value)

        # Calculate aggregates for each metric
        metric_summaries = {}
        for name, values in metrics_by_name.items():
            if values:
                metric_summaries[name] = {
                    "count": float(len(values)),
                    "sum": float(sum(values)),
                    "min": float(min(values)),
                    "max": float(max(values)),
                    "avg": float(sum(values) / len(values)),
                }

        # Calculate success rate
        if total_operations > 0:
            success_rate = (total_operations - error_count) / total_operations
        else:
            success_rate = 1.0

        # Create summary node with period timestamps
        summary = TSDBSummary(
            id=f"tsdb_summary_{period_start.strftime('%Y%m%d_%H')}",
            period_start=period_start,
            period_end=period_end,
            period_label=period_label,
            created_at=period_end,  # Use period end as creation time
            updated_at=period_end,  # Use period end as update time
            metrics=metric_summaries,
            # metrics_count=len(all_metrics),  # Not in schema - store in attributes
            total_tokens=int(resource_totals["tokens"]),
            total_cost_cents=resource_totals["cost"],
            total_carbon_grams=resource_totals["carbon"],
            total_energy_kwh=resource_totals["energy"],
            action_counts=dict(action_counts),
            error_count=error_count,
            success_rate=success_rate,
            source_node_count=len(tsdb_nodes),  # Actual graph nodes
            raw_data_expired=False,
            scope=GraphScope.LOCAL,
            attributes={
                "correlation_count": len(metric_correlations),
                "unique_metrics": len(metrics_by_name),
                "metrics_count": len(all_metrics),
                "service_correlations_count": len(metric_correlations),
                "total_data_points": len(all_metrics),
                "consolidation_level": "basic",
            },
        )

        # Convert to GraphNode
        summary_node = summary.to_graph_node()

        # Store summary
        if self._memory_bus:
            result = await self._memory_bus.memorize(node=summary_node)
            if result.status != MemoryOpStatus.OK:
                logger.error(f"Failed to store TSDB summary: {result.error}")
                return None
        else:
            logger.warning("Memory bus not available - summary not stored")

        return summary

    def get_edges(
        self, summary_node: GraphNode, tsdb_nodes: List[GraphNode], metric_correlations: List[MetricCorrelationData]
    ) -> List[Tuple[GraphNode, GraphNode, str, JSONDict]]:
        """
        Get edges to create for metrics summary.

        Returns edges from summary to:
        - High-value TSDB nodes (cost > threshold)
        - Error-generating nodes
        - Anomalous metric patterns
        """
        edges: List[Tuple[GraphNode, GraphNode, str, JSONDict]] = []

        # Link to high-cost metrics
        for node in tsdb_nodes:
            attrs = node.attributes
            if isinstance(attrs, dict):
                cost = get_float(attrs, "cost_cents", 0.0)
                if cost > 1.0:  # Metrics costing more than 1 cent
                    edge_attrs: JSONDict = {
                        "cost_cents": str(cost),
                        "metric_name": get_str(attrs, "metric_name", "unknown"),
                    }
                    edges.append((summary_node, node, "HIGH_COST_METRIC", edge_attrs))

        # Link to error metrics from correlations
        error_count = 0
        for corr in metric_correlations:
            if corr.tags.get("has_error", False):
                error_count += 1
                if error_count <= 10:  # Limit to first 10 errors
                    # Create a reference edge using correlation ID
                    edge_attrs_error: JSONDict = {
                        "correlation_id": corr.correlation_id,
                        "error_type": corr.tags.get("error_type", "unknown"),
                        "component": corr.tags.get("component_id", "unknown"),
                    }
                    edges.append((summary_node, summary_node, "ERROR_METRIC", edge_attrs_error))

        return edges
