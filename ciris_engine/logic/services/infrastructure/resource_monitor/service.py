from __future__ import annotations

import asyncio
import logging
import os
import shutil
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Awaitable, Callable, Deque, Dict, List, Optional, Tuple

import psutil

from ciris_engine.constants import SERVER_MINIMUM_DISK_BYTES
from ciris_engine.logic.services.base_scheduled_service import BaseScheduledService
from ciris_engine.logic.utils.memory_release import release_memory as _release_process_memory
from ciris_engine.protocols.services.infrastructure.credit_gate import CreditGateProtocol
from ciris_engine.protocols.services.infrastructure.resource_monitor import ResourceMonitorServiceProtocol
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.core import ServiceStatus
from ciris_engine.schemas.services.credit_gate import (
    CreditAccount,
    CreditCheckResult,
    CreditContext,
    CreditSpendRequest,
    CreditSpendResult,
)
from ciris_engine.schemas.services.resources_core import (
    MemoryReleaseResult,
    PressureLevel,
    ResourceAction,
    ResourceBudget,
    ResourceLimit,
    ResourceSnapshot,
)

from .pressure import LATCHED_ACTIONS, LEVEL_ORDER, ResourcePressureGate, actions_for_level, level_rank, lifted_signal

#: Every pressure signal the monitor itself counts (and, for RECLAIM, acts on).
_PRESSURE_SIGNALS = (
    ResourceAction.RECLAIM.value,
    ResourceAction.THROTTLE.value,
    ResourceAction.SHED.value,
    ResourceAction.DRAIN.value,
    *(lifted_signal(action) for action in LATCHED_ACTIONS),
)

logger = logging.getLogger(__name__)


class ResourceSignalBus:
    """Simple signal bus for resource events."""

    def __init__(self) -> None:
        # Handlers are `async def (signal, resource)`; what register() receives is
        # a coroutine function, i.e. a Callable returning an Awaitable, not a Future.
        self._handlers: Dict[str, List[Callable[[str, str], Awaitable[None]]]] = {
            **{signal: [] for signal in _PRESSURE_SIGNALS},  # see pressure.py for the contract
            "token_refreshed": [],  # ciris.ai token refresh signal
        }

    def register(self, signal: str, handler: Callable[[str, str], Awaitable[None]]) -> None:
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
        credit_provider: CreditGateProtocol | None = None,
        agent_occurrence_id: str = "default",
    ) -> None:
        super().__init__(run_interval_seconds=1.0, time_service=time_service)
        self.budget = budget
        self.db_path = db_path
        self.snapshot = ResourceSnapshot()
        self.signal_bus = signal_bus or ResourceSignalBus()
        self.credit_provider = credit_provider
        # Thought counts (thoughts_active) are this occurrence's own work.
        self.agent_occurrence_id = agent_occurrence_id
        # Make time_service a direct attribute to match protocol
        self.time_service: Optional[TimeServiceProtocol] = time_service

        self._token_history: Deque[Tuple[datetime, int]] = deque(maxlen=86400)
        self._cpu_history: Deque[float] = deque(maxlen=60)
        self._process = psutil.Process()
        self._monitoring = False  # For backward compatibility with tests

        # Network tracking for v1.4.3 metrics
        self._network_bytes_sent = 0
        self._network_bytes_recv = 0

        # Credit telemetry
        self._last_credit_result: CreditCheckResult | None = None
        self._last_credit_error: str | None = None
        self._last_credit_timestamp: float | None = None

        # Token refresh monitoring for ciris.ai
        self._env_file_mtime: float = 0.0  # Last known .env modification time
        self._token_refresh_signal_mtime: float = 0.0  # Last signal file mtime we processed
        self._ciris_home: Optional[Path] = None  # Cached CIRIS_HOME path

        # The monitor is its own first subscriber. Until it was, every
        # pressure signal it emitted went to an empty handler
        # list: crossing the memory warning produced one log line and nothing
        # else. Registering here, not in the initializer, means a monitor
        # constructed anywhere -- tests, node-only, a future host -- is wired.
        self._signal_counts: Dict[str, int] = {}
        self._last_release: Optional[MemoryReleaseResult] = None
        self._release_count = 0
        self._released_total_mb = 0
        for signal in _PRESSURE_SIGNALS:
            self.signal_bus.register(signal, self._on_resource_signal)

        # Current pressure level of every resource above NORMAL, and when it
        # last logged / reclaimed (the cooldown paces repeats within a level).
        self._levels: Dict[str, PressureLevel] = {}
        self._last_repeat: Dict[str, datetime] = {}

        # The subscriber that acts. Registered after the monitor's own handler
        # so on a shared emit the monitor counts first and the gate latches second.
        self.pressure = ResourcePressureGate(self.signal_bus)

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
        if self.credit_provider:
            await self.credit_provider.start()
        await super()._on_start()

    async def _on_stop(self) -> None:
        """Called when service stops."""
        self._monitoring = False
        await super()._on_stop()
        if self.credit_provider:
            await self.credit_provider.stop()

    async def _run_scheduled_task(self) -> None:
        """Update resource snapshot and check limits."""
        await self._update_snapshot()
        await self._check_limits()
        await self._check_token_refresh_signal()

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

        # Skip disk usage for PostgreSQL connection strings (not file paths)
        if psutil and not self.db_path.startswith(("postgresql://", "postgres://")):
            try:
                disk_usage = psutil.disk_usage(self.db_path)
                self.snapshot.disk_free_mb = disk_usage.free // 1024 // 1024
                self.snapshot.disk_used_mb = disk_usage.used // 1024 // 1024
            except OSError:
                # db_path may not be a valid filesystem path (e.g., connection string)
                self.snapshot.disk_free_mb = 0
                self.snapshot.disk_used_mb = 0
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
        # cpu_average_1m is only a 1-minute average once the window is full; at
        # boot it averages a handful of startup samples (startup is CPU-heavy by
        # nature), and throttling then only slows the start. Until the window
        # fills, CPU is reported but cannot change level.
        if self.cpu_window_full:
            await self._check_resource("cpu_percent", self.snapshot.cpu_average_1m)
        await self._check_resource("tokens_hour", self.snapshot.tokens_used_hour)
        await self._check_resource("tokens_day", self.snapshot.tokens_used_day)
        await self._check_resource("thoughts_active", self.snapshot.thoughts_active)
        if self.snapshot.critical:
            self.snapshot.healthy = False

    @property
    def cpu_window_full(self) -> bool:
        """True once the CPU history holds a full minute of samples."""
        return len(self._cpu_history) >= (self._cpu_history.maxlen or 0)

    async def _check_resource(self, name: str, current_value: int) -> None:
        limit_config: ResourceLimit = getattr(self.budget, name)
        # A resource capped at a non-acting level (LOG/WARN) is advisory: past
        # its critical threshold it is reported as a warning, never as
        # critical, so it cannot mark the monitor unhealthy or put a critical
        # resource alert into the prompt. Token budgets ship this way until
        # real budgets are decided.
        advisory = limit_config.action in (ResourceAction.LOG, ResourceAction.WARN)
        if current_value >= limit_config.critical and not advisory:
            self.snapshot.critical.append(f"{name}: {current_value}/{limit_config.limit}")
        elif current_value >= limit_config.warning:
            self.snapshot.warnings.append(f"{name}: {current_value}/{limit_config.limit}")

        previous = self._levels.get(name, PressureLevel.NORMAL)
        level = self._next_level(limit_config, previous, current_value)
        if level != previous:
            await self._change_level(name, limit_config, previous, level, current_value)
        elif level != PressureLevel.NORMAL:
            await self._repeat_level(name, limit_config, level, current_value)

    @staticmethod
    def _threshold(config: ResourceLimit, level: PressureLevel) -> int:
        if level == PressureLevel.CRITICAL:
            return config.limit
        if level == PressureLevel.HIGH:
            return config.critical
        return config.warning

    @staticmethod
    def _hysteresis(config: ResourceLimit) -> int:
        """How far below a level's threshold the value must fall to leave it.

        A quarter of the warning-to-limit band (at least 1), so a reading
        hovering on a threshold does not flap an action on and off every tick.
        """
        return max(1, (config.limit - config.warning) // 4)

    def _raw_level(self, config: ResourceLimit, value: int) -> PressureLevel:
        for level in reversed(LEVEL_ORDER[1:]):
            if value >= self._threshold(config, level):
                return level
        return PressureLevel.NORMAL

    def _next_level(self, config: ResourceLimit, previous: PressureLevel, value: int) -> PressureLevel:
        """Rise at once to the highest threshold met; fall one level at a time
        only while the value is clearly below the current level's threshold."""
        raw = self._raw_level(config, value)
        if level_rank(raw) >= level_rank(previous):
            return raw
        level = previous
        band = self._hysteresis(config)
        while level != PressureLevel.NORMAL and value < self._threshold(config, level) - band:
            level = LEVEL_ORDER[level_rank(level) - 1]
        return level

    async def _change_level(
        self, name: str, config: ResourceLimit, previous: PressureLevel, level: PressureLevel, value: int
    ) -> None:
        before = actions_for_level(previous, config)
        after = actions_for_level(level, config)
        if level == PressureLevel.NORMAL:
            self._levels.pop(name, None)
        else:
            self._levels[name] = level
        self._last_repeat[name] = self._now()

        rising = level_rank(level) > level_rank(previous)
        log = logger.warning if rising and config.action != ResourceAction.LOG else logger.info
        log(
            "Resource %s pressure %s -> %s (value %s; elevated %s / high %s / critical %s; cap %s); in force: %s",
            name,
            previous.value,
            level.value,
            value,
            config.warning,
            config.critical,
            config.limit,
            config.action.value,
            ", ".join(action.value for action in after) or "none",
        )
        for action in after:
            if action not in before:
                await self.signal_bus.emit(action.value, name)
        for action in before:
            if action not in after and action in LATCHED_ACTIONS:
                await self.signal_bus.emit(lifted_signal(action), name)

    async def _repeat_level(self, name: str, config: ResourceLimit, level: PressureLevel, value: int) -> None:
        """Still at a non-NORMAL level: once per cooldown, log again and re-RECLAIM.

        THROTTLE and SHED are latched and need no repeat; DRAIN is one-shot.
        RECLAIM is the one action that does its work per emit, so a resource
        that stays up keeps giving memory back.
        """
        now = self._now()
        last = self._last_repeat.get(name)
        if last and now - last < timedelta(seconds=config.cooldown_seconds):
            return
        self._last_repeat[name] = now
        actions = actions_for_level(level, config)
        logger.warning(
            "Resource %s still at %s pressure (value %s); in force: %s",
            name,
            level.value,
            value,
            ", ".join(action.value for action in actions) or "none",
        )
        if ResourceAction.RECLAIM in actions:
            await self.signal_bus.emit(ResourceAction.RECLAIM.value, name)

    def get_pressure_levels(self) -> Dict[str, PressureLevel]:
        """Resources currently above NORMAL and their level."""
        return dict(self._levels)

    async def _on_resource_signal(self, signal: str, resource: str) -> None:
        """Built-in subscriber for the monitor's own signals.

        RECLAIM is the monitor's own to perform: freed memory that the
        allocators are holding is not ours to keep on a phone. Every signal is
        counted so an emit is never silent; THROTTLE, SHED and DRAIN are acted
        on by the pressure gate's readers.
        """
        self._signal_counts[signal] = self._signal_counts.get(signal, 0) + 1
        if signal == ResourceAction.RECLAIM.value:
            await self.release_memory(trigger="resource_monitor:reclaim")

    def record_release(self, result: MemoryReleaseResult) -> None:
        """Fold a release into the monitor's state, wherever it was performed.

        Host callbacks release on their own thread (the loop may be frozen
        when the OS asks) and report here afterwards; the snapshot is updated
        so the next limit check, and the next prompt's resource alert, see the
        post-release number instead of a sample from before it.
        """
        self._last_release = result
        self._release_count += 1
        self._released_total_mb += max(0, result.reclaimed_mb)
        self.snapshot.memory_mb = result.rss_after_mb
        self.snapshot.memory_percent = min(100, self.snapshot.memory_mb * 100 // self.budget.memory_mb.limit)

    async def release_memory(self, trigger: str = "manual") -> MemoryReleaseResult:
        """Collect garbage and return the allocators' free pages to the OS."""
        result = _release_process_memory(trigger)
        self.record_release(result)
        return result

    async def handle_host_memory_pressure(self, level: str) -> MemoryReleaseResult:
        """The host OS asked for memory. No cooldown: refusing is how a process gets killed."""
        return await self.release_memory(trigger=f"host:{level}")

    async def _check_token_refresh_signal(self) -> None:
        """Check for token refresh signals from ciris.ai authentication.

        This monitors the .config_reload file written by Android's TokenRefreshManager
        after it has updated .env with a fresh Google ID token.

        Flow:
        1. Python LLM service gets 401 → writes .token_refresh_needed
        2. Android TokenRefreshManager detects signal, deletes it, refreshes token
        3. Android updates .env with new token
        4. Android writes .config_reload signal
        5. This method detects .config_reload → reloads .env → emits token_refreshed
        """
        try:
            # Get CIRIS_HOME (cached for performance)
            if self._ciris_home is None:
                ciris_home_str = os.environ.get("CIRIS_HOME")
                if ciris_home_str:
                    self._ciris_home = Path(ciris_home_str)
                else:
                    # Try path resolution helper
                    try:
                        from ciris_engine.logic.utils.path_resolution import get_ciris_home

                        self._ciris_home = get_ciris_home()
                    except Exception:
                        return  # No CIRIS_HOME, skip monitoring

            if not self._ciris_home:
                return

            # Watch for the client's answer. Filenames come from the shared
            # handshake module so this side and the client cannot disagree
            # about which files the conversation uses.
            from ciris_engine.logic.utils.token_handshake import CONFIG_RELOAD_SIGNAL_FILE, ENV_FILE

            config_reload_file = self._ciris_home / CONFIG_RELOAD_SIGNAL_FILE
            env_file = self._ciris_home / ENV_FILE

            # Check if config reload signal file exists
            if not config_reload_file.exists():
                return

            # Get signal file mtime
            signal_mtime = config_reload_file.stat().st_mtime
            if signal_mtime <= self._token_refresh_signal_mtime:
                # Already processed this signal
                return

            # New config reload signal detected!
            logger.info(
                "[TOKEN_HANDSHAKE] client answered: %s (mtime=%s) — reloading %s",
                config_reload_file,
                signal_mtime,
                env_file,
            )

            # Verify .env exists
            if not env_file.exists():
                logger.warning(f".env file not found at {env_file}")
                return

            # 1. Reload environment variables
            try:
                from dotenv import load_dotenv

                load_dotenv(env_file, override=True)
                logger.info(f"[OK] Reloaded environment from {env_file}")
            except Exception as e:
                logger.error(f"Failed to reload .env: {e}")
                return

            # 2. Emit token_refreshed signal (LLM service will reset circuit breaker)
            await self.signal_bus.emit("token_refreshed", "openai_api_key")
            logger.info("[TOKEN_HANDSHAKE] emitted token_refreshed — services will re-read the env")

            # 3. Mark signal as processed and clean up
            self._token_refresh_signal_mtime = signal_mtime
            try:
                config_reload_file.unlink()
                logger.info("[OK] Cleaned up config reload signal file")
            except Exception as e:
                logger.warning(f"Failed to clean up signal file: {e}")

            logger.info(" Token refresh cycle complete!")

        except Exception as e:
            logger.debug(f"Token refresh signal check error: {e}")

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

    async def check_credit(
        self,
        account: CreditAccount,
        context: CreditContext | None = None,
    ) -> CreditCheckResult:
        if not self.credit_provider:
            raise RuntimeError("No credit provider configured")
        self._track_request()
        try:
            result = await self.credit_provider.check_credit(account, context)
            self._last_credit_result = result
            self._last_credit_error = None
            self._last_credit_timestamp = self._now().timestamp()
            return result
        except Exception as exc:
            self._last_credit_error = str(exc)
            raise

    async def spend_credit(
        self,
        account: CreditAccount,
        request: CreditSpendRequest,
        context: CreditContext | None = None,
    ) -> CreditSpendResult:
        if not self.credit_provider:
            raise RuntimeError("No credit provider configured")
        self._track_request()
        try:
            result = await self.credit_provider.spend_credit(account, request, context)
            if result.succeeded:
                self._last_credit_result = None
            self._last_credit_error = None
            self._last_credit_timestamp = self._now().timestamp()
            return result
        except Exception as exc:
            self._last_credit_error = str(exc)
            raise

    def _count_active_thoughts(self) -> int:
        """Count this occurrence's thoughts in pending/processing status via persist substrate."""
        try:
            from ciris_engine.logic.persistence.models.thoughts import get_thoughts_by_status
            from ciris_engine.schemas.runtime.enums import ThoughtStatus

            pending = len(get_thoughts_by_status(ThoughtStatus.PENDING, self.agent_occurrence_id))
            processing = len(get_thoughts_by_status(ThoughtStatus.PROCESSING, self.agent_occurrence_id))
            return pending + processing
        except Exception:  # pragma: no cover - persist errors unlikely in tests
            return 0

    def _collect_custom_metrics(self) -> Dict[str, float]:
        """Collect resource monitoring metrics for v1.4.3 and backward compatibility."""
        # Calculate disk usage in GB
        disk_usage_gb = float(self.snapshot.disk_used_mb) / 1024.0

        # Calculate service uptime in seconds (resource_monitor_uptime_seconds)
        uptime_seconds = self._calculate_uptime()

        # Return both v1.4.3 required metrics and existing metrics for backward compatibility
        metrics = {
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
            # Memory give-back: proof the warning threshold does something.
            "memory_release_count": float(self._release_count),
            "memory_released_mb_total": float(self._released_total_mb),
            "memory_last_release_mb": float(self._last_release.reclaimed_mb if self._last_release else 0),
        }
        for signal, count in self._signal_counts.items():
            metrics[f"resource_signal_{signal}_total"] = float(count)
        metrics.update(self.pressure.collect_metrics())
        for resource in ("memory_mb", "cpu_percent", "tokens_hour", "tokens_day", "thoughts_active"):
            level = self._levels.get(resource, PressureLevel.NORMAL)
            metrics[f"resource_pressure_level_{resource}"] = float(level_rank(level))

        if self.credit_provider:
            metrics["credit_provider_enabled"] = 1.0
            if self._last_credit_result is not None:
                metrics["credit_last_available"] = 1.0 if self._last_credit_result.has_credit else 0.0
            else:
                metrics["credit_last_available"] = -1.0
            metrics["credit_error_flag"] = 1.0 if self._last_credit_error else 0.0
            metrics["credit_last_timestamp"] = self._last_credit_timestamp or 0.0
        else:
            metrics["credit_provider_enabled"] = 0.0
            metrics["credit_last_available"] = -1.0
            metrics["credit_error_flag"] = 0.0
            metrics["credit_last_timestamp"] = 0.0

        return metrics

    # ------------------------------------------------------------------ #
    # AgentMode disk gating (2.9.4)
    # ------------------------------------------------------------------ #
    # Free-disk readouts used to gate SERVER mode (see
    # `ciris_engine/schemas/runtime/agent_mode.py`). These are pure queries
    # — they do not touch `self.snapshot` so they stay safe to call from
    # the API layer without coordinating with the scheduled monitor loop.

    def get_available_disk_bytes(self, path: Optional[Path] = None) -> int:
        """Return free bytes on the filesystem hosting ``path``.

        Args:
            path: Filesystem path to measure. Defaults to the resolved data
                  directory (``get_data_dir()``). Falls back to ``self.db_path``
                  if the data dir is not resolvable.

        Returns:
            Free bytes. Returns 0 if the path is not a real filesystem path
            (e.g. when ``db_path`` is a Postgres connection string) or if
            the lookup raises OSError — never raises to the caller.
        """
        target: Path
        if path is not None:
            target = path
        else:
            try:
                from ciris_engine.logic.utils.path_resolution import get_data_dir

                target = get_data_dir()
            except Exception:
                # Path resolution can fail in unusual sandboxes; fall back
                # to db_path which is always set on this service.
                if isinstance(self.db_path, str) and self.db_path.startswith(("postgresql://", "postgres://")):
                    return 0
                target = Path(self.db_path)

        try:
            usage = shutil.disk_usage(str(target))
        except (OSError, ValueError):
            return 0
        return int(usage.free)

    def is_server_mode_eligible(self, path: Optional[Path] = None) -> bool:
        """True iff free disk at ``path`` meets the SERVER-mode minimum."""
        return self.get_available_disk_bytes(path) >= SERVER_MINIMUM_DISK_BYTES

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
