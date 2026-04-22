"""
Aggregation helper functions for TSDB consolidation.

Functions to aggregate metrics, resources, and action counts from summaries.
"""

import json
import logging
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Dict, List, Tuple, cast

from ciris_engine.logic.utils.jsondict_helpers import get_dict, get_float, get_int
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


class MetricStats:
    """Statistics for a single metric."""

    def __init__(self) -> None:
        self.count: int = 0
        self.sum: float = 0.0
        self.min: float = float("inf")
        self.max: float = float("-inf")
        self.avg: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary format."""
        return {
            "count": self.count,
            "sum": self.sum,
            "min": self.min if self.min != float("inf") else 0.0,
            "max": self.max if self.max != float("-inf") else 0.0,
            "avg": self.avg,
        }


class ResourceTotals:
    """Total resource usage across summaries."""

    def __init__(self) -> None:
        self.total_tokens: int = 0
        self.total_cost_cents: float = 0.0
        self.total_carbon_grams: float = 0.0
        self.total_energy_kwh: float = 0.0
        self.error_count: int = 0

    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary format."""
        return {
            "total_tokens": self.total_tokens,
            "total_cost_cents": self.total_cost_cents,
            "total_carbon_grams": self.total_carbon_grams,
            "total_energy_kwh": self.total_energy_kwh,
            "error_count": self.error_count,
        }


def aggregate_metric_stats(summaries: List[JSONDict]) -> Dict[str, Dict[str, float]]:
    """
    Aggregate metric statistics from multiple summaries.

    Handles both old format (single value) and new format (stats dict).

    Args:
        summaries: List of summary attribute dictionaries

    Returns:
        Dictionary mapping metric name to aggregated stats

    Examples:
        >>> summaries = [
        ...     {"metrics": {"cpu": {"count": 2, "sum": 1.5, "min": 0.5, "max": 1.0}}},
        ...     {"metrics": {"cpu": {"count": 1, "sum": 0.8, "min": 0.8, "max": 0.8}}},
        ... ]
        >>> result = aggregate_metric_stats(summaries)
        >>> result["cpu"]["count"]
        3
        >>> result["cpu"]["sum"]
        2.3
    """
    metrics: Dict[str, MetricStats] = defaultdict(MetricStats)

    for summary in summaries:
        for metric_name, stats in get_dict(summary, "metrics", {}).items():
            metric_obj = metrics[metric_name]

            # Handle both old format (single value) and new format (stats dict)
            if isinstance(stats, dict):
                metric_obj.count += get_int(stats, "count", 1)
                metric_obj.sum += get_float(stats, "sum", 0.0)
                metric_obj.min = min(metric_obj.min, get_float(stats, "min", float("inf")))
                metric_obj.max = max(metric_obj.max, get_float(stats, "max", float("-inf")))
            elif isinstance(stats, (int, float)):
                # Old format - single numeric value
                metric_obj.count += 1
                metric_obj.sum += float(stats)
                metric_obj.min = min(metric_obj.min, float(stats))
                metric_obj.max = max(metric_obj.max, float(stats))

    # Calculate averages and convert to dict
    result: Dict[str, Dict[str, float]] = {}
    for metric_name, metric_obj in metrics.items():
        if metric_obj.count > 0:
            metric_obj.avg = metric_obj.sum / metric_obj.count
        else:
            metric_obj.avg = 0.0
        result[metric_name] = metric_obj.to_dict()

    return result


def aggregate_resource_usage(summaries: List[JSONDict]) -> Dict[str, float]:
    """
    Aggregate resource usage (tokens, cost, carbon, energy) from summaries.

    Args:
        summaries: List of summary attribute dictionaries

    Returns:
        Dictionary with total resource usage

    Examples:
        >>> summaries = [
        ...     {"total_tokens": 100, "total_cost_cents": 0.5},
        ...     {"total_tokens": 200, "total_cost_cents": 1.0},
        ... ]
        >>> result = aggregate_resource_usage(summaries)
        >>> result["total_tokens"]
        300
        >>> result["total_cost_cents"]
        1.5
    """
    totals = ResourceTotals()

    for summary in summaries:
        totals.total_tokens += get_int(summary, "total_tokens", 0)
        totals.total_cost_cents += get_float(summary, "total_cost_cents", 0.0)
        totals.total_carbon_grams += get_float(summary, "total_carbon_grams", 0.0)
        totals.total_energy_kwh += get_float(summary, "total_energy_kwh", 0.0)
        totals.error_count += get_int(summary, "error_count", 0)

    return totals.to_dict()


def aggregate_action_counts(summaries: List[JSONDict]) -> Dict[str, int]:
    """
    Aggregate action counts from summaries.

    Args:
        summaries: List of summary attribute dictionaries

    Returns:
        Dictionary mapping action name to total count

    Examples:
        >>> summaries = [
        ...     {"action_counts": {"speak": 5, "observe": 3}},
        ...     {"action_counts": {"speak": 2, "tool": 1}},
        ... ]
        >>> result = aggregate_action_counts(summaries)
        >>> result["speak"]
        7
        >>> result["observe"]
        3
        >>> result["tool"]
        1
    """
    action_totals: Dict[str, int] = defaultdict(int)

    for summary in summaries:
        for action_name, count in get_dict(summary, "action_counts", {}).items():
            if isinstance(count, int):
                action_totals[action_name] += count

    return dict(action_totals)


def group_summaries_by_day(summaries: List[Tuple[str, str, str]]) -> Dict[date, List[Tuple[str, str]]]:
    """
    Group summaries by day based on period_start timestamp.

    Args:
        summaries: List of (node_id, attributes_json, period_start_str) tuples

    Returns:
        Dictionary mapping date to list of (node_id, attributes_json) tuples

    Examples:
        >>> from ciris_engine.constants import UTC_TIMEZONE_SUFFIX
        >>> summaries = [
        ...     ("node1", '{}', "2023-10-01T00:00:00Z"),
        ...     ("node2", '{}', "2023-10-01T06:00:00Z"),
        ...     ("node3", '{}', "2023-10-02T00:00:00Z"),
        ... ]
        >>> grouped = group_summaries_by_day(summaries)
        >>> len(grouped[date(2023, 10, 1)])
        2
        >>> len(grouped[date(2023, 10, 2)])
        1
    """
    from ciris_engine.constants import UTC_TIMEZONE_SUFFIX

    summaries_by_day: Dict[date, List[Tuple[str, str]]] = defaultdict(list)

    for node_id, attrs_json, period_start_str in summaries:
        if period_start_str:
            # Parse datetime and extract date
            normalized = period_start_str.replace("Z", UTC_TIMEZONE_SUFFIX)
            period_dt = datetime.fromisoformat(normalized)
            day_key = period_dt.date()
            summaries_by_day[day_key].append((node_id, attrs_json))

    return dict(summaries_by_day)


def group_summaries_by_month(summaries: List[Tuple[str, str, str]]) -> Dict[Tuple[int, int], List[Tuple[str, str]]]:
    """
    Group summaries by month based on period_start timestamp.

    Args:
        summaries: List of (node_id, attributes_json, period_start_str) tuples

    Returns:
        Dictionary mapping (year, month) to list of (node_id, attributes_json) tuples

    Examples:
        >>> summaries = [
        ...     ("node1", '{}', "2023-10-01T00:00:00Z"),
        ...     ("node2", '{}', "2023-10-15T00:00:00Z"),
        ...     ("node3", '{}', "2023-11-01T00:00:00Z"),
        ... ]
        >>> grouped = group_summaries_by_month(summaries)
        >>> len(grouped[(2023, 10)])
        2
        >>> len(grouped[(2023, 11)])
        1
    """
    from ciris_engine.constants import UTC_TIMEZONE_SUFFIX

    summaries_by_month: Dict[Tuple[int, int], List[Tuple[str, str]]] = defaultdict(list)

    for node_id, attrs_json, period_start_str in summaries:
        if period_start_str:
            # Parse datetime and extract year/month
            normalized = period_start_str.replace("Z", UTC_TIMEZONE_SUFFIX)
            period_dt = datetime.fromisoformat(normalized)
            month_key = (period_dt.year, period_dt.month)
            summaries_by_month[month_key].append((node_id, attrs_json))

    return dict(summaries_by_month)


def create_aggregated_summary_attributes(
    summary_type: str,
    period_start: datetime,
    period_end: datetime,
    consolidation_level: str,
    metrics: Dict[str, Dict[str, float]],
    resources: Dict[str, float],
    action_counts: Dict[str, int],
    source_summary_ids: List[str],
) -> JSONDict:
    """
    Create attributes dictionary for an aggregated summary node.

    Args:
        summary_type: Type of summary (e.g., "tsdb_summary")
        period_start: Start of aggregation period
        period_end: End of aggregation period
        consolidation_level: Level ('daily', 'weekly', 'monthly')
        metrics: Aggregated metric statistics
        resources: Aggregated resource usage
        action_counts: Aggregated action counts
        source_summary_ids: List of source summary node IDs

    Returns:
        Dictionary of attributes for the aggregated summary

    Examples:
        >>> from datetime import datetime, timezone
        >>> attrs = create_aggregated_summary_attributes(
        ...     "tsdb_summary",
        ...     datetime(2023, 10, 1, tzinfo=timezone.utc),
        ...     datetime(2023, 10, 1, 23, 59, 59, tzinfo=timezone.utc),
        ...     "daily",
        ...     {"cpu": {"count": 10, "sum": 5.0, "avg": 0.5, "min": 0.1, "max": 0.9}},
        ...     {"total_tokens": 1000, "total_cost_cents": 5.0},
        ...     {"speak": 10, "observe": 5},
        ...     ["summary1", "summary2"]
        ... )
        >>> attrs["consolidation_level"]
        'daily'
        >>> attrs["source_node_count"]
        2
    """
    attributes = {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "consolidation_level": consolidation_level,
        "source_node_count": len(source_summary_ids),
        "source_summary_ids": source_summary_ids,
    }

    # Add type-specific fields
    if summary_type == "tsdb_summary":
        attributes.update(metrics)
        attributes.update(resources)
        if action_counts:
            attributes["action_counts"] = action_counts
    elif summary_type == "audit_summary":
        # Audit summaries track event counts
        if action_counts:
            attributes["event_counts"] = action_counts
    elif summary_type == "task_summary":
        # Task summaries track completion counts
        if action_counts:
            attributes["task_outcomes"] = action_counts

    return cast(JSONDict, attributes)


def parse_summary_attributes(summaries: List[Tuple[str, str]]) -> List[JSONDict]:
    """
    Parse JSON attributes from summary tuples.

    Args:
        summaries: List of (node_id, attributes_json) tuples

    Returns:
        List of parsed attribute dictionaries

    Examples:
        >>> summaries = [
        ...     ("node1", '{"metrics": {"cpu": 0.5}}'),
        ...     ("node2", '{"metrics": {"cpu": 0.8}}'),
        ... ]
        >>> attrs = parse_summary_attributes(summaries)
        >>> len(attrs)
        2
        >>> attrs[0]["metrics"]["cpu"]
        0.5
    """
    parsed = []
    for node_id, attrs_json in summaries:
        try:
            attrs = json.loads(attrs_json) if attrs_json else {}
            parsed.append(attrs)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse attributes for {node_id}, skipping")
            continue

    return parsed
