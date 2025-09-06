from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Callable, Deque, Dict, List, Optional, Tuple

import psutil

from ciris_engine.logic.persistence import get_db_connection
from ciris_engine.logic.services.base_scheduled_service import BaseScheduledService
from ciris_engine.protocols.services.infrastructure.resource_monitor import ResourceMonitorServiceProtocol
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.core import ServiceStatus
from ciris_engine.schemas.services.resources_core import ResourceAction, ResourceBudget, ResourceLimit, ResourceSnapshot

logger = logging.getLogger(__name__)


class ResourceSignalBus:
    """Simple signal bus for resource events."""

    def __init__(self) -> None:
        self._handlers: Dict[str, List[Callable[[str, str], asyncio.Future]]] = {
            "throttle": [],
            "defer": [],
            "reject": [],
            "shutdown": [],
        }

    def register(self, signal: str, handler: Callable[[str, str], asyncio.Future]) -> None:
        self._handlers.setdefault(signal, []).append(handler)

    async def emit(self, signal: str, resource: str) -> None:
        for handler in self._handlers.get(signal, []):
            try:
                await handler(signal, resource)
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("Signal handler error: %s", exc)


class ResourceMonitorService(BaseScheduledService, ResourceMonitorServiceProtocol):
    """Monitor system resources and enforce limits."""

    def __init__(
        self,
        budget: ResourceBudget,
        db_path: str,
        time_service: TimeServiceProtocol,
        signal_bus: Optional[ResourceSignalBus] = None,
    ) -> None:
        super().__init__(run_interval_seconds=1.0, time_service=time_service)
        self.budget = budget
        self.db_path = db_path
        self.snapshot = ResourceSnapshot()
        self.signal_bus = signal_bus or ResourceSignalBus()
        # Make time_service a direct attribute to match protocol
        self.time_service: Optional[TimeServiceProtocol] = time_service

        self._token_history: Deque[Tuple[datetime, int]] = deque(maxlen=86400)
        self._cpu_history: Deque[float] = deque(maxlen=60)
        self._last_action_time: Dict[str, datetime] = {}
        self._process = psutil.Process()
        self._monitoring = False  # For backward compatibility with tests

        # Network tracking for v1.4.3 metrics
        self._network_bytes_sent = 0
        self._network_bytes_recv = 0

    def get_service_type(self) -> ServiceType:
        """Get service type."""
        return ServiceType.VISIBILITY

    def _get_actions(self) -> List[str]:
        """Get list of actions this service provides."""
        return [
            "resource_monitoring",
            "cpu_tracking",
            "memory_tracking",
            "token_rate_limiting",
            "thought_counting",
            "resource_signals",
        ]

    def _check_dependencies(self) -> bool:
        """Check if all dependencies are available."""
        return True  # Only needs time service which is provided in init

    async def _on_start(self) -> None:
        """Called when service starts."""
        self._monitoring = True
        await super()._on_start()

    async def _on_stop(self) -> None:
        """Called when service stops."""
        self._monitoring = False
        await super()._on_stop()

    async def _run_scheduled_task(self) -> None:
        """Update resource snapshot and check limits."""
        await self._update_snapshot()
        await self._check_limits()

    async def _update_snapshot(self) -> None:
        if psutil and self._process:
            mem_info = self._process.memory_info()
            self.snapshot.memory_mb = mem_info.rss // 1024 // 1024
        else:
            self.snapshot.memory_mb = 0
        self.snapshot.memory_percent = self.snapshot.memory_mb * 100 // self.budget.memory_mb.limit

        if psutil and self._process:
            cpu_percent = self._process.cpu_percent(interval=0)
        else:
            cpu_percent = 0.0
        self._cpu_history.append(cpu_percent)
        self.snapshot.cpu_percent = int(cpu_percent)
        self.snapshot.cpu_average_1m = int(sum(self._cpu_history) / len(self._cpu_history))

        if psutil:
            disk_usage = psutil.disk_usage(self.db_path)
            self.snapshot.disk_free_mb = disk_usage.free // 1024 // 1024
            self.snapshot.disk_used_mb = disk_usage.used // 1024 // 1024
        else:  # pragma: no cover - fallback
            self.snapshot.disk_free_mb = 0
            self.snapshot.disk_used_mb = 0

        # Update network statistics for v1.4.3 metrics
        if psutil:
            net_io = psutil.net_io_counters()
            if net_io:
                self._network_bytes_sent = net_io.bytes_sent
                self._network_bytes_recv = net_io.bytes_recv

        now = self.time_service.now() if self.time_service else datetime.now(timezone.utc)
        hour_ago = now - timedelta(hours=1)
        day_ago = now - timedelta(days=1)
        self.snapshot.tokens_used_hour = sum(tokens for ts, tokens in self._token_history if ts > hour_ago)
        self.snapshot.tokens_used_day = sum(tokens for ts, tokens in self._token_history if ts > day_ago)
        self.snapshot.thoughts_active = self._count_active_thoughts()

    async def _check_limits(self) -> None:
        self.snapshot.warnings.clear()
        self.snapshot.critical.clear()
        self.snapshot.healthy = True
        await self._check_resource("memory_mb", self.snapshot.memory_mb)
        await self._check_resource("cpu_percent", self.snapshot.cpu_average_1m)
        await self._check_resource("tokens_hour", self.snapshot.tokens_used_hour)
        await self._check_resource("tokens_day", self.snapshot.tokens_used_day)
        await self._check_resource("thoughts_active", self.snapshot.thoughts_active)
        if self.snapshot.critical:
            self.snapshot.healthy = False

    async def _check_resource(self, name: str, current_value: int) -> None:
        limit_config: ResourceLimit = getattr(self.budget, name)
        if current_value >= limit_config.critical:
            self.snapshot.critical.append(f"{name}: {current_value}/{limit_config.limit}")
            await self._take_action(name, limit_config, "critical")
        elif current_value >= limit_config.warning:
            self.snapshot.warnings.append(f"{name}: {current_value}/{limit_config.limit}")
            await self._take_action(name, limit_config, "warning")

    async def _take_action(self, resource: str, config: ResourceLimit, level: str) -> None:
        last_action = self._last_action_time.get(f"{resource}_{level}")
        current_time = self.time_service.now() if self.time_service else datetime.now(timezone.utc)
        if last_action and current_time - last_action < timedelta(seconds=config.cooldown_seconds):
            return
        action = config.action
        logger.warning("Resource %s hit %s threshold, action: %s", resource, level, action)
        if action == ResourceAction.THROTTLE:
            await self.signal_bus.emit("throttle", resource)
        elif action == ResourceAction.DEFER:
            await self.signal_bus.emit("defer", resource)
        elif action == ResourceAction.REJECT:
            await self.signal_bus.emit("reject", resource)
        elif action == ResourceAction.SHUTDOWN:
            await self.signal_bus.emit("shutdown", resource)
        self._last_action_time[f"{resource}_{level}"] = current_time

    async def record_tokens(self, tokens: int) -> None:
        current_time = self.time_service.now() if self.time_service else datetime.now(timezone.utc)
        self._token_history.append((current_time, tokens))

    async def check_available(self, resource: str, amount: int = 0) -> bool:
        if resource == "memory_mb":
            return self.snapshot.memory_mb + amount < self.budget.memory_mb.warning
        if resource == "tokens_hour":
            return self.snapshot.tokens_used_hour + amount < self.budget.tokens_hour.warning
        if resource == "thoughts_active":
            return self.snapshot.thoughts_active + amount < self.budget.thoughts_active.warning
        return True

    def _count_active_thoughts(self) -> int:
        try:
            conn = get_db_connection(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM thoughts WHERE status IN ('pending', 'processing')")
            row = cursor.fetchone()
            return row[0] if row else 0
        except Exception:  # pragma: no cover - DB errors unlikely in tests
            return 0

    def _collect_custom_metrics(self) -> Dict[str, float]:
        """Collect resource monitoring metrics for v1.4.3 and backward compatibility."""
        # Calculate disk usage in GB
        disk_usage_gb = float(self.snapshot.disk_used_mb) / 1024.0

        # Calculate service uptime in seconds (resource_monitor_uptime_seconds)
        uptime_seconds = self._calculate_uptime()

        # Return both v1.4.3 required metrics and existing metrics for backward compatibility
        return {
            # v1.4.3 Required metrics (EXACTLY these 6 metrics)
            "cpu_percent": float(self.snapshot.cpu_percent),
            "memory_mb": float(self.snapshot.memory_mb),
            "disk_usage_gb": disk_usage_gb,
            "network_bytes_sent": float(self._network_bytes_sent),
            "network_bytes_recv": float(self._network_bytes_recv),
            "resource_monitor_uptime_seconds": uptime_seconds,
            # Existing metrics for backward compatibility
            "tokens_used_hour": float(self.snapshot.tokens_used_hour),
            "thoughts_active": float(self.snapshot.thoughts_active),
            "warnings": float(len(self.snapshot.warnings)),
            "critical": float(len(self.snapshot.critical)),
        }

    async def is_healthy(self) -> bool:
        """Check if service is healthy."""
        # Service is healthy if no critical resource issues
        return self.snapshot.healthy

    def get_status(self) -> ServiceStatus:
        """Get service status."""
        status = super().get_status()
        # Override service type for backward compatibility
        status.service_type = "infrastructure_service"
        # Use snapshot health status instead of started status
        status.is_healthy = self.snapshot.healthy
        return status
