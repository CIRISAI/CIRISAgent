"""
Compression utilities for profound consolidation.

This module handles in-place compression of daily summaries for long-term storage efficiency.
Future versions will include multimedia compression for images, video, and telemetry data.
"""

import json
import logging
from typing import Dict, List, cast

from ciris_engine.logic.utils.jsondict_helpers import get_int, get_str
from ciris_engine.schemas.services.graph.tsdb_models import CompressionResult, SummaryAttributes
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


class SummaryCompressor:
    """Handles compression of summary nodes for profound consolidation."""

    def __init__(self, target_mb_per_day: float):
        """
        Initialize the compressor.

        Args:
            target_mb_per_day: Target size in MB per day after compression
        """
        self.target_mb_per_day = target_mb_per_day

    def compress_summary(self, attributes: SummaryAttributes) -> CompressionResult:
        """
        Compress a summary's attributes in-place.

        Args:
            attributes: The summary attributes to compress

        Returns:
            CompressionResult with compressed attributes and metrics
        """
        # Calculate original size
        original_data = attributes.model_dump(exclude_none=True)
        original_size = len(json.dumps(original_data, default=str))

        # Create a copy for compression
        compressed = attributes.model_copy(deep=True)

        # Current compression strategies (text-based)
        compressed = self._compress_metrics(compressed)
        compressed = self._compress_descriptions(compressed)
        compressed = self._remove_redundancy(compressed)

        # Future compression strategies
        # compressed = self._compress_images(compressed)
        # compressed = self._compress_video_thumbnails(compressed)
        # compressed = self._compress_telemetry_data(compressed)

        # Calculate compressed size
        compressed_data = compressed.model_dump(exclude_none=True)
        compressed_size = len(json.dumps(compressed_data, default=str))
        reduction_ratio = 1.0 - (compressed_size / original_size) if original_size > 0 else 0.0

        return CompressionResult(
            compressed_attributes=compressed,
            original_size=original_size,
            compressed_size=compressed_size,
            reduction_ratio=reduction_ratio,
            compression_method="text",
        )

    def _compress_metrics(self, attrs: SummaryAttributes) -> SummaryAttributes:
        """
        Compress metrics by keeping only significant patterns.

        Args:
            attrs: Attributes containing metrics

        Returns:
            Attributes with compressed metrics
        """
        # Compress basic metrics into a simplified format
        compressed_metrics: Dict[str, float] = {}

        # Only keep non-zero metrics (convert to float for schema compatibility)
        if attrs.total_interactions > 0:
            compressed_metrics["ti"] = float(attrs.total_interactions)  # Shortened key
        if attrs.unique_services > 0:
            compressed_metrics["us"] = float(attrs.unique_services)
        if attrs.total_tasks > 0:
            compressed_metrics["tt"] = float(attrs.total_tasks)
        if attrs.total_thoughts > 0:
            compressed_metrics["tth"] = float(attrs.total_thoughts)

        # Store compressed version
        attrs.compressed_metrics = compressed_metrics if compressed_metrics else None

        # Clear original fields if we compressed them
        if attrs.compressed_metrics:
            attrs.total_interactions = 0
            attrs.unique_services = 0
            attrs.total_tasks = 0
            attrs.total_thoughts = 0

        return attrs

    def _compress_descriptions(self, attrs: SummaryAttributes) -> SummaryAttributes:
        """
        Compress text descriptions by removing redundancy.

        Args:
            attrs: Attributes containing descriptions

        Returns:
            Attributes with compressed descriptions
        """
        # Compress conversation summaries
        if attrs.messages_by_channel:
            # Build new dict with proper typing - compress to Dict[str, int]
            compressed_channels: Dict[str, int] = {}
            for channel, data in attrs.messages_by_channel.items():
                # Keep only channel ID and count
                if isinstance(data, dict):
                    # Extract count from dict with type narrowing
                    count_val = data.get("count", 0)
                    if isinstance(count_val, int):
                        compressed_channels[channel] = count_val
                    else:
                        compressed_channels[channel] = 0
                elif isinstance(data, int):
                    # Already an int, keep it
                    compressed_channels[channel] = data
                else:
                    # Unknown type, default to 0
                    compressed_channels[channel] = 0

            # Now cast the Dict[str, int] to the Union type the field expects
            from typing import Union

            attrs.messages_by_channel = cast(Dict[str, Union[int, JSONDict]], compressed_channels)

        # Compress participant data
        if attrs.participants:
            compressed_participants: JSONDict = {}
            for user_id, data in attrs.participants.items():
                # Keep only essential data
                if isinstance(data, dict):
                    # Use get_str and get_int for type-safe access
                    author_name = get_str(data, "author_name", "")
                    msg_count = get_int(data, "message_count", 0)
                    compressed_participants[user_id] = {
                        "msg_count": msg_count,
                        "name": author_name[:20],  # Truncate names
                    }
            attrs.participants = cast(Dict[str, JSONDict], compressed_participants)

        # Compress patterns and events
        if attrs.dominant_patterns and len(attrs.dominant_patterns) > 5:
            attrs.dominant_patterns = attrs.dominant_patterns[:5]

        if attrs.significant_events and len(attrs.significant_events) > 10:
            attrs.significant_events = attrs.significant_events[:10]

        return attrs

    def _remove_redundancy(self, attrs: SummaryAttributes) -> SummaryAttributes:
        """
        Remove redundant information from attributes.

        Args:
            attrs: Attributes to clean

        Returns:
            Attributes with redundancy removed
        """
        # Since we're using typed models, redundancy removal is less relevant
        # The model already has defined fields

        # We can clear any extra fields if using extra="allow"
        # But for now, just ensure compressed fields are used efficiently

        # If we have compressed versions, clear originals
        if attrs.compressed_metrics:
            attrs.total_interactions = 0
            attrs.unique_services = 0
            attrs.total_tasks = 0
            attrs.total_thoughts = 0

        if attrs.compressed_descriptions:
            # Clear long descriptions if compressed version exists
            attrs.dominant_patterns = []
            attrs.significant_events = []

        return attrs

    def estimate_daily_size(self, summaries: List[SummaryAttributes], days_in_period: int) -> float:
        """
        Estimate the daily storage size for a set of summaries.

        Args:
            summaries: List of summary attributes
            days_in_period: Number of days covered by these summaries

        Returns:
            Estimated MB per day
        """
        total_size = sum(len(json.dumps(s.model_dump(exclude_none=True), default=str)) for s in summaries)
        size_mb = total_size / (1024 * 1024)
        return size_mb / days_in_period if days_in_period > 0 else 0

    def needs_compression(self, summaries: List[SummaryAttributes], days_in_period: int) -> bool:
        """
        Check if summaries need compression based on target size.

        Args:
            summaries: List of summary attributes
            days_in_period: Number of days covered

        Returns:
            True if compression is needed
        """
        current_daily_mb = self.estimate_daily_size(summaries, days_in_period)
        return current_daily_mb > self.target_mb_per_day

    # Future multimedia compression methods

    def _compress_images(self, attrs: SummaryAttributes) -> SummaryAttributes:
        """
        Future: Compress embedded images using lossy compression.

        Will handle:
        - Converting to JPEG with quality reduction
        - Resizing to thumbnails
        - Extracting key frames only
        """
        # TODO: Implement when image support is added
        return attrs

    def _compress_video_thumbnails(self, attrs: SummaryAttributes) -> SummaryAttributes:
        """
        Future: Compress video data to thumbnails and metadata.

        Will handle:
        - Extracting keyframes
        - Creating timeline thumbnails
        - Keeping only metadata (duration, resolution, codec)
        """
        # TODO: Implement when video support is added
        return attrs

    def _compress_telemetry_data(self, attrs: SummaryAttributes) -> SummaryAttributes:
        """
        Future: Compress robotic/sensor telemetry data.

        Will handle:
        - Downsampling time series data
        - Statistical aggregation (min/max/avg/std)
        - Anomaly detection and preservation
        """
        # TODO: Implement when telemetry support is added
        return attrs
