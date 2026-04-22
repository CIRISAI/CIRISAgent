"""
Conversation consolidation for service interactions.

Consolidates SERVICE_INTERACTION correlations into ConversationSummaryNode.
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from ciris_engine.logic.buses.memory_bus import MemoryBus
from ciris_engine.logic.services.governance.consent import ConsentNotFoundError, ConsentService
from ciris_engine.logic.utils.jsondict_helpers import get_str
from ciris_engine.schemas.consent.core import ConsentRequest, ConsentStream
from ciris_engine.schemas.services.graph.consolidation import ConversationEntry, ParticipantData, ServiceInteractionData
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryOpStatus
from ciris_engine.schemas.types import JSONDict

if TYPE_CHECKING:
    from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol

logger = logging.getLogger(__name__)


class ConversationConsolidator:
    """Consolidates conversation and interaction data."""

    def __init__(self, memory_bus: Optional[MemoryBus] = None, time_service: Optional["TimeServiceProtocol"] = None):
        """
        Initialize conversation consolidator.

        Args:
            memory_bus: Memory bus for storing results
            time_service: Time service for consistent timestamps
        """
        self._memory_bus = memory_bus
        self._time_service = time_service

    async def consolidate(
        self,
        period_start: datetime,
        period_end: datetime,
        period_label: str,
        service_interactions: List[ServiceInteractionData],
    ) -> Optional[GraphNode]:
        """
        Consolidate service interactions into a conversation summary.

        Args:
            period_start: Start of consolidation period
            period_end: End of consolidation period
            period_label: Human-readable period label
            service_interactions: List of ServiceInteractionData objects

        Returns:
            ConversationSummaryNode as GraphNode if successful
        """
        if not service_interactions:
            logger.info(f"No service interactions found for period {period_start} - creating empty summary")

        logger.info(f"Consolidating {len(service_interactions)} service interactions")

        # Group by channel and build conversation history
        conversations_by_channel = defaultdict(list)
        unique_users = set()
        action_counts: Dict[str, int] = defaultdict(int)
        service_calls: Dict[str, int] = defaultdict(int)
        total_response_time = 0.0
        response_count = 0
        error_count = 0

        for interaction in service_interactions:
            # Extract key data from typed schema
            correlation_id = interaction.correlation_id
            action_type = interaction.action_type
            service_type = interaction.service_type
            timestamp = interaction.timestamp
            channel_id = interaction.channel_id

            # Extract message content
            content = interaction.content or ""
            author_id = interaction.author_id
            author_name = interaction.author_name

            if author_id:
                unique_users.add(author_id)

            # Get response metrics
            execution_time = interaction.execution_time_ms
            success = interaction.success

            if execution_time > 0:
                total_response_time += execution_time
                response_count += 1

            if not success:
                error_count += 1

            # Build conversation entry using typed schema
            conv_entry = ConversationEntry(
                timestamp=timestamp.isoformat() if timestamp else None,
                correlation_id=correlation_id,
                action_type=action_type,
                content=content,
                author_id=author_id,
                author_name=author_name,
                execution_time_ms=execution_time,
                success=success,
            )

            conversations_by_channel[channel_id].append(conv_entry.model_dump())
            action_counts[action_type] += 1
            service_calls[service_type] += 1

        # Calculate metrics
        total_messages = sum(len(msgs) for msgs in conversations_by_channel.values())
        messages_by_channel = {ch: len(msgs) for ch, msgs in conversations_by_channel.items()}
        avg_response_time = total_response_time / response_count if response_count > 0 else 0.0
        success_rate = 1.0 - (error_count / len(service_interactions)) if len(service_interactions) > 0 else 1.0

        # Sort conversations by timestamp
        for channel_id in conversations_by_channel:
            conversations_by_channel[channel_id].sort(key=lambda x: x["timestamp"] if x["timestamp"] else "")

        # Create summary data
        summary_data = {
            "id": f"conversation_summary_{period_start.strftime('%Y%m%d_%H')}",
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "period_label": period_label,
            "conversations_by_channel": dict(conversations_by_channel),
            "total_messages": total_messages,
            "messages_by_channel": messages_by_channel,
            "unique_users": len(unique_users),
            "user_list": list(unique_users),
            "action_counts": dict(action_counts),
            "service_calls": dict(service_calls),
            "avg_response_time_ms": avg_response_time,
            "total_processing_time_ms": total_response_time,
            "error_count": error_count,
            "success_rate": success_rate,
            "source_correlation_count": len(service_interactions),
            "created_at": period_end.isoformat(),
            "updated_at": period_end.isoformat(),
        }

        # Create GraphNode
        summary_node = GraphNode(
            id=str(summary_data["id"]),
            type=NodeType.CONVERSATION_SUMMARY,
            scope=GraphScope.LOCAL,
            attributes=summary_data,
            updated_by="tsdb_consolidation",
            updated_at=period_end,  # Use period end as timestamp
        )

        # Store summary
        if self._memory_bus:
            result = await self._memory_bus.memorize(node=summary_node)
            if result.status != MemoryOpStatus.OK:
                logger.error(f"Failed to store conversation summary: {result.error}")
                return None
        else:
            logger.warning("No memory bus available - summary not stored")

        return summary_node

    def get_edges(
        self, summary_node: GraphNode, service_interactions: List[ServiceInteractionData]
    ) -> List[Tuple[GraphNode, GraphNode, str, JSONDict]]:
        """
        Get edges to create for conversation summary.

        Returns edges from summary to:
        - User participants (INVOLVED_USER)
        - Channels where conversations happened (OCCURRED_IN_CHANNEL)

        NOTE: Consent checking happens during consolidation phase, not edge creation.
        """
        edges = []

        # Get period_end from summary node attributes for fallback timestamp
        period_end = datetime.now(timezone.utc)
        if isinstance(summary_node.attributes, dict):
            period_end_str = get_str(summary_node.attributes, "period_end", "")
            if period_end_str:
                try:
                    period_end = datetime.fromisoformat(period_end_str.replace("Z", "+00:00"))
                except Exception:
                    pass

        # Get participant data
        participant_data = self.get_participant_data(service_interactions)

        # Create edges to participants
        for user_id, participant in participant_data.items():
            if user_id and participant.message_count > 0:
                # NOTE: Consent is checked and added during memorize operations
                # Here we just create the node with basic info
                # The memorize_handler will add consent metadata

                user_node = GraphNode(
                    id=f"user_{user_id}",
                    type=NodeType.USER,
                    scope=GraphScope.LOCAL,
                    attributes={
                        "user_id": user_id,
                        "username": participant.author_name or user_id,
                        # Consent metadata will be added by memorize_handler
                    },
                    updated_by="tsdb_consolidation",
                    updated_at=self._time_service.now() if self._time_service else period_end,
                )

                edge_attrs: JSONDict = {
                    "message_count": str(participant.message_count),
                    "channels": str(participant.channels),
                }
                edges.append(
                    (
                        summary_node,
                        user_node,
                        "INVOLVED_USER",
                        edge_attrs,
                    )
                )

        # Create edges to channels
        channels = set()
        for interaction in service_interactions:
            channel_id = interaction.channel_id
            if channel_id and channel_id != "unknown":
                channels.add(channel_id)

        for channel_id in channels:
            channel_node = GraphNode(
                id=f"channel_{channel_id}",
                type=NodeType.CHANNEL,
                scope=GraphScope.LOCAL,
                attributes={"channel_id": channel_id},
                updated_by="tsdb_consolidation",
                updated_at=self._time_service.now() if self._time_service else period_end,
            )

            channel_attrs: JSONDict = {
                "message_count": str(len([i for i in service_interactions if i.channel_id == channel_id]))
            }
            edges.append(
                (
                    summary_node,
                    channel_node,
                    "OCCURRED_IN_CHANNEL",
                    channel_attrs,
                )
            )

        return edges

    def get_participant_data(self, service_interactions: List[ServiceInteractionData]) -> Dict[str, ParticipantData]:
        """
        Extract participant data for edge creation.

        Returns a dict mapping user_id to participation metrics.
        """
        # Track participant data with proper typing
        participant_counts: Dict[str, int] = defaultdict(int)
        participant_channels: Dict[str, set[str]] = defaultdict(set)
        participant_names: Dict[str, str] = {}

        for interaction in service_interactions:
            if interaction.action_type in ["speak", "observe"]:
                author_id = interaction.author_id

                if author_id:
                    participant_counts[author_id] += 1
                    participant_channels[author_id].add(interaction.channel_id)
                    if interaction.author_name:
                        participant_names[author_id] = interaction.author_name

        # Build typed ParticipantData objects
        result: Dict[str, ParticipantData] = {}
        for user_id in participant_counts:
            result[user_id] = ParticipantData(
                message_count=participant_counts[user_id],
                channels=list(participant_channels[user_id]),
                author_name=participant_names.get(user_id),
            )

        return result
