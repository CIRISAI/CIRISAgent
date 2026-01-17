"""
Storage helpers for telemetry service memory operations.

Handles storage of different memory types: behavioral, social, identity, and telemetry data.
"""

import logging
from datetime import datetime
from typing import Any, List, Optional

from ciris_engine.schemas.runtime.system_context import ChannelContext as SystemChannelContext
from ciris_engine.schemas.runtime.system_context import SystemSnapshot, UserProfile
from ciris_engine.schemas.services.graph.telemetry import BehavioralData, ResourceData, TelemetryData
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType

from .aggregator import MemoryType

logger = logging.getLogger(__name__)


async def store_telemetry_metrics(
    telemetry_service: Any,
    telemetry: TelemetryData,
    thought_id: str,
    task_id: Optional[str],
) -> None:
    """Store telemetry data as operational memories.

    Args:
        telemetry_service: The telemetry service instance (for record_metric)
        telemetry: TelemetryData to store
        thought_id: Associated thought ID
        task_id: Associated task ID (optional)
    """
    # Process metrics
    for key, value in telemetry.metrics.items():
        await telemetry_service.record_metric(
            f"telemetry.{key}",
            float(value),
            {"thought_id": thought_id, "task_id": task_id or "", "memory_type": MemoryType.OPERATIONAL.value},
        )

    # Process events
    for event_key, event_value in telemetry.events.items():
        await telemetry_service.record_metric(
            f"telemetry.event.{event_key}",
            1.0,  # Event occurrence
            {
                "thought_id": thought_id,
                "task_id": task_id or "",
                "memory_type": MemoryType.OPERATIONAL.value,
                "event_value": str(event_value),
            },
        )


def _get_numeric_field(data: dict, key: str) -> Optional[float]:
    """Extract numeric field from dict, returning None if not valid."""
    value = data.get(key)
    return value if isinstance(value, (int, float)) else None


def _get_string_field(data: dict, key: str) -> Optional[str]:
    """Extract string field from dict, returning None if not valid."""
    value = data.get(key)
    return value if isinstance(value, str) else None


def _create_llm_usage_data(llm_dict: dict) -> Any:
    """Create LLMUsageData from raw dict with type validation."""
    from ciris_engine.schemas.services.graph.telemetry import LLMUsageData

    return LLMUsageData(
        tokens_used=_get_numeric_field(llm_dict, "tokens_used"),
        tokens_input=_get_numeric_field(llm_dict, "tokens_input"),
        tokens_output=_get_numeric_field(llm_dict, "tokens_output"),
        cost_cents=_get_numeric_field(llm_dict, "cost_cents"),
        carbon_grams=_get_numeric_field(llm_dict, "carbon_grams"),
        energy_kwh=_get_numeric_field(llm_dict, "energy_kwh"),
        model_used=_get_string_field(llm_dict, "model_used"),
    )


def _create_resource_usage(llm_data: Any) -> Any:
    """Create ResourceUsage from LLMUsageData with defaults."""
    from ciris_engine.schemas.runtime.resources import ResourceUsage

    return ResourceUsage(
        tokens_used=int(llm_data.tokens_used) if llm_data.tokens_used is not None else 0,
        tokens_input=int(llm_data.tokens_input) if llm_data.tokens_input is not None else 0,
        tokens_output=int(llm_data.tokens_output) if llm_data.tokens_output is not None else 0,
        cost_cents=float(llm_data.cost_cents) if llm_data.cost_cents is not None else 0.0,
        carbon_grams=float(llm_data.carbon_grams) if llm_data.carbon_grams is not None else 0.0,
        energy_kwh=float(llm_data.energy_kwh) if llm_data.energy_kwh is not None else 0.0,
        model_used=llm_data.model_used,
    )


async def store_resource_usage(telemetry_service: Any, resources: ResourceData) -> None:
    """Store resource usage as operational memories.

    Args:
        telemetry_service: The telemetry service instance
        resources: ResourceData containing LLM and other resource usage
    """
    if resources.llm:
        llm_data = _create_llm_usage_data(resources.llm)
        usage = _create_resource_usage(llm_data)
        await telemetry_service._record_resource_usage("llm_service", usage)


async def store_behavioral_data(
    telemetry_service: Any,
    data: BehavioralData,
    data_type: str,
    thought_id: str,
) -> None:
    """Store behavioral data (tasks/thoughts) as memories.

    Args:
        telemetry_service: The telemetry service instance
        data: BehavioralData to store
        data_type: Type of behavioral data ("task" or "thought")
        thought_id: Associated thought ID
    """
    now = telemetry_service._now()
    node = GraphNode(
        id=f"behavioral_{thought_id}_{data_type}",
        type=NodeType.BEHAVIORAL,
        scope=GraphScope.LOCAL,
        updated_by="telemetry_service",
        updated_at=now,
        attributes={
            "data_type": data.data_type,
            "thought_id": thought_id,
            "content": data.content,
            "metadata": data.metadata,
            "memory_type": MemoryType.BEHAVIORAL.value,
            "tags": {"thought_id": thought_id, "data_type": data_type},
        },
    )

    if telemetry_service._memory_bus:
        await telemetry_service._memory_bus.memorize(
            node=node, handler_name="telemetry_service", metadata={"behavioral": True}
        )


async def store_social_context(
    telemetry_service: Any,
    user_profiles: List[UserProfile],
    channel_context: Optional[SystemChannelContext],
    thought_id: str,
) -> None:
    """Store social context as memories.

    Args:
        telemetry_service: The telemetry service instance
        user_profiles: List of user profiles to store
        channel_context: Channel context information (optional)
        thought_id: Associated thought ID
    """
    now = telemetry_service._now()
    node = GraphNode(
        id=f"social_{thought_id}",
        type=NodeType.SOCIAL,
        scope=GraphScope.LOCAL,
        updated_by="telemetry_service",
        updated_at=now,
        attributes={
            "user_profiles": [p.model_dump() for p in user_profiles],
            "channel_context": channel_context.model_dump() if channel_context else None,
            "memory_type": MemoryType.SOCIAL.value,
            "tags": {"thought_id": thought_id, "user_count": str(len(user_profiles))},
        },
    )

    if telemetry_service._memory_bus:
        await telemetry_service._memory_bus.memorize(
            node=node, handler_name="telemetry_service", metadata={"social": True}
        )


async def store_identity_context(
    telemetry_service: Any,
    snapshot: SystemSnapshot,
    thought_id: str,
) -> None:
    """Store identity-related context as memories.

    Args:
        telemetry_service: The telemetry service instance
        snapshot: SystemSnapshot containing identity information
        thought_id: Associated thought ID
    """
    now = telemetry_service._now()
    # Extract agent name from identity data if available
    agent_name = None
    if snapshot.agent_identity and isinstance(snapshot.agent_identity, dict):
        agent_name = snapshot.agent_identity.get("name") or snapshot.agent_identity.get("agent_name")

    node = GraphNode(
        id=f"identity_{thought_id}",
        type=NodeType.IDENTITY,
        scope=GraphScope.IDENTITY,
        updated_by="telemetry_service",
        updated_at=now,
        attributes={
            "agent_name": agent_name,
            "identity_purpose": snapshot.identity_purpose,
            "identity_capabilities": snapshot.identity_capabilities,
            "identity_restrictions": snapshot.identity_restrictions,
            "memory_type": MemoryType.IDENTITY.value,
            "tags": {"thought_id": thought_id, "has_purpose": str(bool(snapshot.identity_purpose))},
        },
    )

    if telemetry_service._memory_bus:
        await telemetry_service._memory_bus.memorize(
            node=node, handler_name="telemetry_service", metadata={"identity": True}
        )
