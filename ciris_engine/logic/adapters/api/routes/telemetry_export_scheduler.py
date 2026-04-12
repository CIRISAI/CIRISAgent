"""
Telemetry Export Push Scheduler.

Background service that periodically pushes telemetry data to configured
export destinations. Reads destination config from GraphConfigService and
pushes metrics/traces/logs in OTLP, Prometheus, or Graphite formats.
"""

import asyncio
import base64
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast

import httpx

from ciris_engine.schemas.types import JSONDict

from .telemetry_converters import convert_to_graphite, convert_to_prometheus
from .telemetry_export import EXPORT_DESTINATIONS_KEY, _get_destinations
from .telemetry_logs_reader import LogFileReader
from .telemetry_otlp import convert_logs_to_otlp_json, convert_to_otlp_json, convert_traces_to_otlp_json

logger = logging.getLogger(__name__)


class TelemetryExportScheduler:
    """
    Background scheduler that pushes telemetry to configured export destinations.

    This service:
    1. Reads export destinations from GraphConfigService
    2. Tracks last push time for each destination
    3. Periodically checks and pushes when interval is reached
    4. Supports OTLP, Prometheus, and Graphite formats
    5. Handles authentication (bearer, basic, header)
    """

    def __init__(
        self,
        telemetry_service: Any,
        config_service: Any,
        visibility_service: Optional[Any] = None,
        check_interval: float = 10.0,
    ) -> None:
        """
        Initialize the export scheduler.

        Args:
            telemetry_service: GraphTelemetryService for collecting metrics
            config_service: GraphConfigService for reading destinations
            visibility_service: Optional VisibilityService for traces
            check_interval: How often to check for destinations needing push (seconds)
        """
        self._telemetry_service = telemetry_service
        self._config_service = config_service
        self._visibility_service = visibility_service
        self._check_interval = check_interval

        # Track last push time per destination
        self._last_push_times: Dict[str, datetime] = {}

        # Background task
        self._scheduler_task: Optional[asyncio.Task[None]] = None
        self._running = False

        # HTTP client
        self._client: Optional[httpx.AsyncClient] = None

        # Stats
        self._pushes_total = 0
        self._pushes_success = 0
        self._pushes_failed = 0

    async def start(self) -> None:
        """Start the export scheduler background task."""
        if self._running:
            logger.warning("TelemetryExportScheduler already running")
            return

        logger.info("=" * 60)
        logger.info("🚀 TELEMETRY EXPORT SCHEDULER STARTING")
        logger.info(f"   Check interval: {self._check_interval}s")
        logger.info("=" * 60)

        self._running = True
        self._client = httpx.AsyncClient(timeout=30.0)
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())

    async def stop(self) -> None:
        """Stop the export scheduler."""
        logger.info("🛑 TELEMETRY EXPORT SCHEDULER STOPPING")

        self._running = False

        if self._scheduler_task and not self._scheduler_task.done():
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:  # noqa: ASYNC910  # NOSONAR
                # Expected: we just cancelled this child task above.
                # Do NOT re-raise - this is OUR cancellation, not external.
                pass

        if self._client:
            await self._client.aclose()
            self._client = None

        logger.info(f"📊 Export stats: {self._pushes_success}/{self._pushes_total} successful")

    async def _scheduler_loop(self) -> None:
        """Main scheduler loop - checks destinations and pushes when due."""
        while self._running:
            try:
                await self._check_and_push()
                await asyncio.sleep(self._check_interval)
            except asyncio.CancelledError:
                logger.debug("Export scheduler loop cancelled")
                raise  # Re-raise per asyncio contract
            except Exception as e:
                logger.error(f"Error in export scheduler loop: {e}")
                await asyncio.sleep(self._check_interval)

    async def _check_and_push(self) -> None:
        """Check all destinations and push to those that are due."""
        if not self._config_service:
            return

        try:
            destinations = await _get_destinations(self._config_service)
            now = datetime.now(timezone.utc)

            for dest in destinations:
                if not dest.get("enabled", True):
                    continue

                dest_id = dest.get("id", "")
                if not dest_id:
                    continue

                interval_seconds = dest.get("interval_seconds", 60)
                last_push = self._last_push_times.get(dest_id)

                # Check if push is due
                should_push = False
                if last_push is None:
                    should_push = True  # First push
                else:
                    elapsed = (now - last_push).total_seconds()
                    if elapsed >= interval_seconds:
                        should_push = True

                if should_push:
                    await self._push_to_destination(dest, now)
                    self._last_push_times[dest_id] = now

        except Exception as e:
            logger.error(f"Error checking destinations: {e}")

    async def _push_to_destination(self, dest: Dict[str, Any], timestamp: datetime) -> None:
        """Push telemetry data to a specific destination."""
        dest_id = dest.get("id", "unknown")
        dest_name = dest.get("name", "Unknown")
        endpoint = dest.get("endpoint", "")
        format_type = dest.get("format", "otlp")
        signals = dest.get("signals", ["metrics"])

        if not endpoint:
            logger.warning(f"Destination {dest_name} has no endpoint configured")
            return

        logger.info(f"📤 Pushing to {dest_name} ({format_type}): {signals}")
        self._pushes_total += 1

        try:
            # Build headers with authentication
            headers = self._build_headers(dest)

            # Push each signal type
            for signal in signals:
                await self._push_signal(dest, signal, format_type, headers, endpoint)

            self._pushes_success += 1
            logger.info(f"✅ Push to {dest_name} successful")

        except Exception as e:
            self._pushes_failed += 1
            logger.error(f"❌ Push to {dest_name} failed: {e}")

    def _build_headers(self, dest: Dict[str, Any]) -> Dict[str, str]:
        """Build HTTP headers including authentication."""
        headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "User-Agent": "CIRIS-Telemetry-Exporter/1.0",
        }

        auth_type = dest.get("auth_type", "none")
        auth_value = dest.get("auth_value")

        if auth_type == "bearer" and auth_value:
            headers["Authorization"] = f"Bearer {auth_value}"
        elif auth_type == "basic" and auth_value:
            encoded = base64.b64encode(auth_value.encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"
        elif auth_type == "header" and auth_value:
            # Use 'or' to handle both missing key AND explicit null value
            header_name = dest.get("auth_header") or "X-API-Key"
            headers[header_name] = auth_value

        return headers

    async def _push_signal(
        self,
        dest: Dict[str, Any],
        signal: str,
        format_type: str,
        headers: Dict[str, str],
        base_endpoint: str,
    ) -> None:
        """Push a specific signal type to the destination."""
        if not self._client:
            return

        # Get data based on signal type
        data = await self._collect_signal_data(signal)
        if not data:
            logger.debug(f"No data for signal {signal}")
            return

        # Convert to appropriate format
        body: Any
        endpoint = base_endpoint

        if format_type == "otlp":
            # OTLP uses different endpoints per signal
            if signal == "metrics":
                # Metrics are always a single dict
                metrics_data = data if isinstance(data, dict) else data[0] if data else {}
                body = convert_to_otlp_json(metrics_data)
                endpoint = self._append_path(base_endpoint, "/v1/metrics")
            elif signal == "traces":
                body = convert_traces_to_otlp_json(data if isinstance(data, list) else [data])
                endpoint = self._append_path(base_endpoint, "/v1/traces")
            elif signal == "logs":
                body = convert_logs_to_otlp_json(data if isinstance(data, list) else [data])
                endpoint = self._append_path(base_endpoint, "/v1/logs")
            else:
                # Default: ensure we have a dict for OTLP
                otlp_data = data if isinstance(data, dict) else data[0] if data else {}
                body = convert_to_otlp_json(otlp_data)

            body_bytes = json.dumps(body).encode("utf-8")

        elif format_type == "prometheus":
            # Prometheus text format - needs a dict
            prom_data = data if isinstance(data, dict) else data[0] if data else {}
            body = convert_to_prometheus(prom_data)
            body_bytes = body.encode("utf-8")
            headers["Content-Type"] = "text/plain; charset=utf-8"

        elif format_type == "graphite":
            # Graphite line protocol - needs a dict
            graphite_data = data if isinstance(data, dict) else data[0] if data else {}
            body = convert_to_graphite(graphite_data)
            body_bytes = body.encode("utf-8")
            headers["Content-Type"] = "text/plain; charset=utf-8"

        else:
            # Default to JSON
            body_bytes = json.dumps(data).encode("utf-8")

        # Send the request
        response = await self._client.post(endpoint, content=body_bytes, headers=headers)

        if response.status_code >= 400:
            raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")

        logger.debug(f"Pushed {signal} to {endpoint}: {response.status_code}")

    def _append_path(self, base: str, path: str) -> str:
        """Append path to base URL, avoiding double slashes."""
        base = base.rstrip("/")
        path = path.lstrip("/")
        return f"{base}/{path}"

    async def _collect_signal_data(self, signal: str) -> Optional[JSONDict | List[JSONDict]]:
        """Collect data for a specific signal type."""
        try:
            if signal == "metrics":
                if hasattr(self._telemetry_service, "get_aggregated_telemetry"):
                    response = await self._telemetry_service.get_aggregated_telemetry()
                    if hasattr(response, "model_dump"):
                        return cast(JSONDict, response.model_dump())
                    return dict(response) if response else None
                return None

            elif signal == "traces":
                return await self._collect_traces()

            elif signal == "logs":
                return await self._collect_logs()

            return None

        except Exception as e:
            logger.error(f"Error collecting {signal} data: {e}")
            return None

    async def _collect_traces(self) -> Optional[List[JSONDict]]:
        """Collect trace data from reasoning event stream buffer."""
        try:
            # Import the global reasoning event stream
            from ciris_engine.logic.infrastructure.step_streaming import reasoning_event_stream

            # Get OLDEST events first (FIFO) - this matches clear_exported_events which
            # removes from the front of the buffer. Using newest-first would cause the
            # wrong events to be cleared when buffer > limit.
            events_to_export = reasoning_event_stream.get_oldest_events(limit=100)

            if not events_to_export:
                logger.debug("No reasoning events in buffer for export")
                return None

            # Convert to trace format
            traces: List[JSONDict] = []
            for event_update in events_to_export:
                trace_data = self._build_trace_from_reasoning_event(event_update)
                if trace_data:
                    traces.append(trace_data)

            # Clear the exported events from the front of the buffer
            # This works correctly because we exported from the front (oldest first)
            if events_to_export:
                reasoning_event_stream.clear_exported_events(len(events_to_export))
                logger.info(f"Collected {len(traces)} reasoning traces for export")

            return traces if traces else None

        except Exception as e:
            logger.debug(f"Failed to collect reasoning traces: {e}")
            return None

    def _build_trace_from_reasoning_event(self, event_update: JSONDict) -> Optional[JSONDict]:
        """Build a trace dict from a ReasoningStreamUpdate."""
        if not event_update:
            return None

        try:
            events = event_update.get("events", [])
            if not events:
                return None

            # Get first event from the update
            event = events[0] if isinstance(events, list) else events

            # Ensure event is a dict before accessing
            if not isinstance(event, dict):
                return None

            event_type = event.get("event_type", "unknown")
            thought_id = event.get("thought_id", "")
            task_id = event.get("task_id", "")
            timestamp = event_update.get("timestamp", "")
            seq = event_update.get("sequence_number", 0)

            return {
                "trace_id": thought_id or f"trace-{seq}",
                "span_id": f"{seq:016x}"[:16],
                "parent_span_id": task_id[:16] if task_id else None,
                "operation_name": event_type,
                "start_time": timestamp,
                "duration_ms": 0,  # Real-time events don't have duration
                "status": "ok",
                "attributes": {
                    "event_type": event_type,
                    "thought_id": thought_id,
                    "task_id": task_id,
                    "sequence_number": seq,
                    # Include relevant data from event (action, results, etc)
                    **{k: v for k, v in event.items() if k not in ("event_type", "thought_id", "task_id", "timestamp")},
                },
            }
        except Exception as e:
            logger.debug(f"Failed to build trace from reasoning event: {e}")

        return None

    async def _collect_logs(self) -> Optional[List[JSONDict]]:
        """Collect log data from log files."""
        try:
            log_reader = LogFileReader()
            log_entries = log_reader.read_logs(limit=100, include_incidents=True)

            if not log_entries:
                return None

            logs: List[JSONDict] = []
            for entry in log_entries:
                log_data = self._build_log_from_entry(entry)
                if log_data:
                    logs.append(log_data)

            return logs if logs else None

        except Exception as e:
            logger.debug(f"Failed to collect logs: {e}")
            return None

    def _build_log_from_entry(self, entry: Any) -> Optional[JSONDict]:
        """Build a log dict from a LogEntry object."""
        if not entry:
            return None

        try:
            timestamp = getattr(entry, "timestamp", None)
            if timestamp is not None and hasattr(timestamp, "isoformat"):
                timestamp_str: str = timestamp.isoformat()
            else:
                timestamp_str = str(timestamp) if timestamp else ""

            return {
                "timestamp": timestamp_str,
                "severity": getattr(entry, "level", "INFO"),
                "service": getattr(entry, "service", "unknown"),
                "message": getattr(entry, "message", ""),
                "trace_id": getattr(entry, "trace_id", None),
                "attributes": {},
            }
        except Exception as e:
            logger.debug(f"Failed to build log from entry: {e}")

        return None

    def get_metrics(self) -> Dict[str, Any]:
        """Get scheduler metrics for telemetry."""
        return {
            "pushes_total": self._pushes_total,
            "pushes_success": self._pushes_success,
            "pushes_failed": self._pushes_failed,
            "destinations_tracked": len(self._last_push_times),
            "running": self._running,
        }


# Global scheduler instance (set by service initializer)
_scheduler_instance: Optional[TelemetryExportScheduler] = None


def get_scheduler() -> Optional[TelemetryExportScheduler]:
    """Get the global scheduler instance."""
    return _scheduler_instance


def set_scheduler(scheduler: TelemetryExportScheduler) -> None:
    """Set the global scheduler instance."""
    global _scheduler_instance
    _scheduler_instance = scheduler


async def start_export_scheduler(
    telemetry_service: Any,
    config_service: Any,
    visibility_service: Optional[Any] = None,
) -> TelemetryExportScheduler:
    """
    Create and start the telemetry export scheduler.

    Args:
        telemetry_service: GraphTelemetryService instance
        config_service: GraphConfigService instance
        visibility_service: Optional VisibilityService for traces

    Returns:
        Started TelemetryExportScheduler instance
    """
    scheduler = TelemetryExportScheduler(
        telemetry_service=telemetry_service,
        config_service=config_service,
        visibility_service=visibility_service,
    )
    await scheduler.start()
    set_scheduler(scheduler)
    return scheduler


async def stop_export_scheduler() -> None:
    """Stop the global scheduler if running."""
    scheduler = get_scheduler()
    if scheduler:
        await scheduler.stop()
        set_scheduler(None)  # type: ignore
