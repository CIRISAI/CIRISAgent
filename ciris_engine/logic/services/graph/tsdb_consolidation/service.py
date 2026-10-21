"""TSDB Consolidation Service — thin cadence-caller over the persist substrate.

2.9.7 DRY purge (wave 2): ALL consolidation compute is substrate-owned.
Persist's `Engine.tsdb_consolidate_tasks/conversations/traces/audit` +
`telemetry_consolidate_period` produce the summary nodes AND the
TEMPORAL_NEXT edge chain (verified on the 0.5.114 wheel: consecutive-period
consolidation reports `edges_created` and writes `TEMPORAL_NEXT` rows into
`cirisgraph_edges`). The consolidators are idempotent (deterministic node
IDs, upsert semantics) and internally locked (`locked_by` +
`broke_stale_lock` in the outcome), so the agent needs NO period
bookkeeping, NO lock wrappers, NO summary assembly, and NO edge repair.

What legitimately remains agent-side until the substrate owns scheduling:
the 6h / weekly (Monday) / monthly (1st) cadence loop, which simply calls
the substrate consolidators for the relevant window at the relevant level,
plus retention pruning via `Engine.tsdb_prune_summaries`.
"""

import asyncio
import json
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from ciris_engine.logic.buses.memory_bus import MemoryBus
from ciris_engine.logic.services.base_graph_service import BaseGraphService
from ciris_engine.protocols.infrastructure.base import RegistryAwareServiceProtocol, ServiceRegistryProtocol
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
from ciris_engine.schemas.services.graph.consolidation import TSDBPeriodSummary
from ciris_engine.schemas.services.graph_core import NodeType

from .date_calculation_helpers import calculate_month_period, calculate_week_period, get_retention_cutoff_date
from .period_manager import PeriodManager

logger = logging.getLogger(__name__)


def _tenant_id() -> str:
    import os

    return os.environ.get("CIRIS_AGENT_TENANT", "agent-default")


def _locked_by() -> str:
    import os

    return f"ciris-agent-{os.environ.get('CIRIS_AGENT_ID', 'default')}"


def _rfc3339(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


# Persist's `tsdb_query_summary_nodes` accepts ONLY these four `node_type`
# values; the cirisgraph-namespace string "tsdb_summary" silently returns
# zero rows (#788 root cause). To read a period's summaries we union across
# all four typed sub-tables.
_SUMMARY_NODE_TYPES = (
    "task_summary",
    "conversation_summary",
    "trace_summary",
    "audit_summary",
)

# The five substrate consolidators invoked per (period, level).
_CONSOLIDATOR_NAMES = (
    "telemetry_consolidate_period",
    "tsdb_consolidate_tasks",
    "tsdb_consolidate_conversations",
    "tsdb_consolidate_traces",
    "tsdb_consolidate_audit",
)


def query_typed_summaries(
    engine: Any,
    level: str,
    tenant_id: str,
    from_rfc3339: str,
    to_rfc3339: str,
) -> List[Dict[str, Any]]:
    """Return the union of summary rows across all 4 persist node_types.

    Best-effort per type: a Rust-side error on one sub-table doesn't fail
    the others; we log at WARNING and keep going. Returns [] if every type
    errors (the caller's `if not rows` branch still works).
    """
    aggregate: List[Dict[str, Any]] = []
    for node_type in _SUMMARY_NODE_TYPES:
        try:
            raw = engine.tsdb_query_summary_nodes(node_type, level, tenant_id, from_rfc3339, to_rfc3339)
            rows = json.loads(raw) if isinstance(raw, (bytes, str)) else (raw or [])
            if isinstance(rows, list):
                aggregate.extend(rows)
        except Exception as e:
            logger.warning(
                "tsdb_query_summary_nodes(node_type=%s, level=%s) failed: %s",
                node_type,
                level,
                e,
            )
    return aggregate


class TSDBConsolidationService(BaseGraphService, RegistryAwareServiceProtocol):
    """Thin cadence-caller: schedules the persist substrate's consolidators."""

    def __init__(
        self,
        memory_bus: Optional[MemoryBus] = None,
        time_service: Optional[TimeServiceProtocol] = None,
        consolidation_interval_hours: int = 6,
        raw_retention_hours: int = 24,
        db_path: Optional[str] = None,
    ) -> None:
        """
        Initialize the consolidation cadence.

        Args:
            memory_bus: Bus for memory operations (health reporting only)
            time_service: Time service for consistent timestamps
            consolidation_interval_hours: How often to run (default: 6)
            raw_retention_hours: How long to keep raw data (default: 24)
            db_path: Legacy parameter — persist owns the connection.
        """
        super().__init__(memory_bus=memory_bus, time_service=time_service)
        self.service_name = "TSDBConsolidationService"
        self.db_path = db_path

        self._period_manager = PeriodManager(consolidation_interval_hours)
        self._consolidation_interval = timedelta(hours=consolidation_interval_hours)
        self._raw_retention = timedelta(hours=raw_retention_hours)

        # Fixed cadence intervals for calendar alignment
        self._basic_interval = timedelta(hours=6)  # 00:00, 06:00, 12:00, 18:00 UTC
        self._extensive_interval = timedelta(days=7)  # Weekly on Mondays
        self._profound_interval = timedelta(days=30)  # Monthly on 1st
        self._profound_target_mb_per_day = 20.0

        # Task management
        self._consolidation_task: Optional[asyncio.Task[None]] = None
        self._running = False

        # Cadence telemetry
        self._last_consolidation: Optional[datetime] = None
        self._last_extensive_consolidation: Optional[datetime] = None
        self._last_profound_consolidation: Optional[datetime] = None
        self._start_time: Optional[datetime] = None
        self._basic_consolidations = 0
        self._extensive_consolidations = 0
        self._profound_consolidations = 0
        self._records_consolidated = 0
        self._records_deleted = 0

    async def attach_registry(self, registry: "ServiceRegistryProtocol") -> None:
        """Attach service registry for time-service discovery."""
        self._service_registry = registry
        if not self._time_service and registry:
            time_services = registry.get_services_by_type(ServiceType.TIME)
            if time_services:
                self._time_service = time_services[0]

    def _now(self) -> datetime:
        """Get current time from time service."""
        return self._time_service.now() if self._time_service else datetime.now(timezone.utc)

    def _engine(self) -> Any:
        """Resolve the wired persist engine (None if not wired)."""
        from ciris_engine.logic.persistence.models.graph import get_persist_engine

        return get_persist_engine()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the consolidation cadence."""
        if self._running:
            logger.warning("TSDBConsolidationService already running")
            return

        await super().start()
        self._running = True
        self._start_time = self._now()
        self._consolidation_task = asyncio.create_task(self._consolidation_loop())
        logger.info(
            f"TSDBConsolidationService started - Basic: {self._basic_interval}, "
            f"Extensive: {self._extensive_interval}, Profound: {self._profound_interval}"
        )

    async def stop(self) -> None:
        """Stop the consolidation cadence gracefully."""
        self._running = False

        if self._consolidation_task and not self._consolidation_task.done():
            logger.info("Cancelling ongoing consolidation task...")
            self._consolidation_task.cancel()
            try:
                await self._consolidation_task
            except asyncio.CancelledError:
                current = asyncio.current_task()
                if current and current.cancelled():
                    raise
            except Exception as e:
                logger.error(f"Error cancelling consolidation task: {e}")

        await super().stop()
        logger.info("TSDBConsolidationService stopped")

    async def _consolidation_loop(self) -> None:
        """Cadence loop: catch up at startup, then run at each 6h boundary.

        Substrate consolidators are idempotent and internally locked, so
        the catch-up pass is simply a normal run over the retention window
        — no missed-window bookkeeping needed.
        """
        try:
            print("[CONSOLIDATOR] Checking for missed windows...", flush=True)
            await self._run_consolidation()
            print("[CONSOLIDATOR] Complete", flush=True)
        except Exception as e:
            logger.error(f"Startup consolidation catch-up failed: {e}", exc_info=True)

        while self._running:
            try:
                next_run = self._period_manager.get_next_period_start(self._now())
                wait_seconds = (next_run - self._now()).total_seconds()
                if wait_seconds > 0:
                    logger.info(f"Next consolidation at {next_run} ({wait_seconds:.0f}s)")
                    await asyncio.sleep(wait_seconds)

                if self._running:
                    # Jitter to avoid a thundering herd across occurrences;
                    # the substrate's internal lock makes concurrent runs
                    # safe regardless.
                    await asyncio.sleep(random.randint(30, 600))

                if self._running:
                    await self._run_consolidation()

                    now = self._now()
                    if now.weekday() == 0:  # Monday
                        logger.info("It's Monday - running extensive consolidation")
                        await self._run_extensive_consolidation()
                    if now.day == 1:  # 1st of the month
                        logger.info("It's the 1st of the month - running profound consolidation")
                        await asyncio.to_thread(self._run_profound_consolidation)

            except asyncio.CancelledError:
                logger.debug("Consolidation loop cancelled")
                raise
            except Exception as e:
                logger.error(f"Consolidation loop error: {e}", exc_info=True)
                await asyncio.sleep(300)

    # ------------------------------------------------------------------
    # Basic (6h) tier
    # ------------------------------------------------------------------

    async def _run_consolidation(self) -> None:
        """Run the basic consolidators over every complete period in the
        raw-retention window, then prune expired summaries.

        Called by the cadence loop and by the runtime's final-consolidation
        shutdown hook. Safe to re-run: the substrate is idempotent.
        """
        started = self._now()
        logger.info("Starting TSDB consolidation cycle at %s", started.isoformat())

        now = self._now()
        period_start = self._period_manager.get_period_start(now - self._raw_retention)
        current_period_start = self._period_manager.get_period_start(now)

        total_summaries = 0
        periods_processed = 0
        while period_start < current_period_start:
            period_end = period_start + self._consolidation_interval
            summaries = await self._consolidate_period(period_start, period_end)
            total_summaries += len(summaries)
            periods_processed += 1
            period_start = period_end

        # Prune expired summaries (substrate cascades edges internally).
        deleted = await asyncio.to_thread(self._cleanup_old_data)

        self._last_consolidation = now
        duration = (self._now() - started).total_seconds()
        logger.info(
            "TSDB consolidation cycle complete in %.2fs: %d periods, %d summaries, %d pruned",
            duration,
            periods_processed,
            total_summaries,
            deleted,
        )

    async def _consolidate_period(self, period_start: datetime, period_end: datetime) -> List[Dict[str, Any]]:
        """Run persist's 5 consolidators for one period at `level=basic`,
        then read back the summary rows they produced.

        Kept as the manual-consolidation entry point for
        `tools/database/manual_consolidate.py`.
        """
        engine = self._engine()
        if engine is None:
            logger.warning("persist engine not wired — basic consolidation skipped")
            return []

        req_json = json.dumps(
            {
                "tenant_id": _tenant_id(),
                "period_start": _rfc3339(period_start),
                "period_end": _rfc3339(period_end),
                "locked_by": _locked_by(),
                "level": "basic",
            }
        )
        for name in _CONSOLIDATOR_NAMES:
            try:
                await asyncio.to_thread(getattr(engine, name), req_json)
            except Exception as e:
                logger.error(f"persist {name}(level=basic) failed: {e}", exc_info=True)

        try:
            summaries: List[Dict[str, Any]] = await asyncio.to_thread(
                query_typed_summaries,
                engine,
                "basic",
                _tenant_id(),
                _rfc3339(period_start),
                _rfc3339(period_end),
            )
        except Exception as e:
            logger.error(f"reading summaries for period failed: {e}", exc_info=True)
            summaries = []

        if summaries:
            self._basic_consolidations += 1
            self._records_consolidated += len(summaries)
        return summaries

    def _cleanup_old_data(self) -> int:
        """Prune summary nodes past retention via `tsdb_prune_summaries`.

        Persist cascades TEMPORAL_NEXT edges internally; the audit chain
        in `cirislens_audit_log` is untouched. 'monthly' summaries are
        retained for long-term archival.
        """
        try:
            engine = self._engine()
            if engine is None:
                return 0

            retention_cutoff = get_retention_cutoff_date(
                self._now(), int(self._raw_retention.total_seconds() / 3600)
            )
            cutoff_iso = _rfc3339(retention_cutoff)

            total_deleted = 0
            for level in ("basic", "daily", "weekly"):
                try:
                    total_deleted += int(engine.tsdb_prune_summaries(level, _tenant_id(), cutoff_iso))
                except Exception as e:
                    logger.warning(f"tsdb_prune_summaries({level}) failed: {e}")

            if total_deleted > 0:
                self._records_deleted += total_deleted
                logger.info(f"Cleanup complete: pruned {total_deleted} summary nodes")
            return total_deleted
        except Exception as e:
            logger.error(f"Error during cleanup: {e}", exc_info=True)
            return 0

    # ------------------------------------------------------------------
    # Extensive (weekly → level=daily) tier
    # ------------------------------------------------------------------

    async def _run_extensive_consolidation(self) -> None:
        """Weekly cadence: persist's consolidators at `level=daily` over the
        previous Monday-Sunday week. Locking is substrate-internal."""
        started = self._now()
        try:
            engine = self._engine()
            if engine is None:
                logger.warning("persist engine not wired — extensive consolidation skipped")
                return

            period_start, period_end = calculate_week_period(self._now())
            logger.info(f"Extensive consolidation: {period_start.isoformat()} → {period_end.isoformat()}")

            req_json = json.dumps(
                {
                    "tenant_id": _tenant_id(),
                    "period_start": _rfc3339(period_start),
                    "period_end": _rfc3339(period_end),
                    "locked_by": _locked_by(),
                    "level": "daily",
                }
            )
            outcomes: Dict[str, Any] = {}
            for name in _CONSOLIDATOR_NAMES:
                try:
                    raw = await asyncio.to_thread(getattr(engine, name), req_json)
                    outcomes[name] = json.loads(raw) if isinstance(raw, (bytes, str)) else raw
                except Exception as e:
                    logger.error(f"persist {name}(level=daily) failed: {e}", exc_info=True)
                    outcomes[name] = {"error": str(e)}

            self._extensive_consolidations += 1
            self._last_extensive_consolidation = self._now()
            duration = (self._now() - started).total_seconds()
            logger.info(f"Extensive consolidation complete in {duration:.2f}s: outcomes={outcomes}")
        except Exception as e:
            logger.error(f"Extensive consolidation failed: {e}", exc_info=True)

    # ------------------------------------------------------------------
    # Profound (monthly → level=weekly + monthly) tier
    # ------------------------------------------------------------------

    def _run_profound_consolidation(self) -> None:
        """Monthly cadence: persist's consolidators at `level=weekly` then
        `level=monthly` over the previous month, plus stale-basic pruning.
        Locking is substrate-internal."""
        started = self._now()
        try:
            engine = self._engine()
            if engine is None:
                logger.warning("persist engine not wired — profound consolidation skipped")
                return

            now = self._now()
            month_start, month_end = calculate_month_period(now)
            logger.info(f"Profound consolidation: {month_start.isoformat()} → {month_end.isoformat()}")

            base_req = {
                "tenant_id": _tenant_id(),
                "period_start": _rfc3339(month_start),
                "period_end": _rfc3339(month_end),
                "locked_by": _locked_by(),
            }
            outcomes: Dict[str, Any] = {}
            for level in ("weekly", "monthly"):
                req_json = json.dumps({**base_req, "level": level})
                for name in _CONSOLIDATOR_NAMES:
                    try:
                        raw = getattr(engine, name)(req_json)
                        outcomes[f"{level}/{name}"] = json.loads(raw) if isinstance(raw, (bytes, str)) else raw
                    except Exception as e:
                        logger.error(f"persist {name}(level={level}) failed: {e}", exc_info=True)
                        outcomes[f"{level}/{name}"] = {"error": str(e)}

            # Prune basic-tier summaries older than the monthly retention window.
            cleanup_cutoff = _rfc3339(now - timedelta(days=30))
            try:
                deleted = int(engine.tsdb_prune_summaries("basic", _tenant_id(), cleanup_cutoff))
                if deleted > 0:
                    logger.info(f"Pruned {deleted} stale basic summary nodes")
            except Exception as e:
                logger.warning(f"tsdb_prune_summaries(basic) failed: {e}")

            self._profound_consolidations += 1
            self._last_profound_consolidation = now
            duration = (self._now() - started).total_seconds()
            logger.info(f"Profound consolidation complete in {duration:.2f}s: outcomes={outcomes}")
        except Exception as e:
            logger.error(f"Profound consolidation failed: {e}", exc_info=True)

    # ------------------------------------------------------------------
    # Protocol surface
    # ------------------------------------------------------------------

    def get_summary_for_period(self, period_start: datetime, period_end: datetime) -> Optional[TSDBPeriodSummary]:
        """Get the consolidated summary for a specific period via persist."""
        try:
            engine = self._engine()
            if engine is None:
                return None

            from_iso = _rfc3339(period_start)
            to_iso = _rfc3339(period_end + timedelta(milliseconds=1))
            rows = query_typed_summaries(engine, "basic", _tenant_id(), from_iso, to_iso)
            if not rows:
                return None
            attrs = rows[0] if isinstance(rows[0], dict) else {}

            return TSDBPeriodSummary(
                metrics=attrs.get("metrics", {}),
                total_tokens=attrs.get("total_tokens", 0),
                total_cost_cents=attrs.get("total_cost_cents", 0),
                total_carbon_grams=attrs.get("total_carbon_grams", 0),
                total_energy_kwh=attrs.get("total_energy_kwh", 0),
                action_counts=attrs.get("action_counts", {}),
                source_node_count=attrs.get("source_node_count", 0),
                period_start=attrs.get("period_start", period_start.isoformat()),
                period_end=attrs.get("period_end", period_end.isoformat()),
                period_label=attrs.get("period_label", ""),
                conversations=attrs.get("conversations", []),
                traces=attrs.get("traces", []),
                audits=attrs.get("audits", []),
                tasks=attrs.get("tasks", []),
                memories=attrs.get("memories", []),
            )
        except Exception as e:
            logger.error(f"Error getting summary for period: {e}")
            return None

    async def is_healthy(self) -> bool:
        """Healthy iff running with a memory bus wired."""
        return self._running and self._memory_bus is not None

    def get_capabilities(self) -> ServiceCapabilities:
        """Get service capabilities."""
        return ServiceCapabilities(
            service_name="TSDBConsolidationService",
            actions=[
                "consolidate_tsdb_nodes",
                "consolidate_all_data",
                "create_6hour_summaries",
            ],
            version="3.0.0",
            dependencies=["MemoryService", "TimeService"],
            metadata=None,
        )

    def get_status(self) -> ServiceStatus:
        """Get service status."""
        current_time = self._now()
        uptime_seconds = 0.0
        if self._start_time:
            uptime_seconds = (current_time - self._start_time).total_seconds()

        task_running = 1.0 if (self._consolidation_task and not self._consolidation_task.done()) else 0.0
        return ServiceStatus(
            service_name="TSDBConsolidationService",
            service_type="graph_service",
            is_healthy=self._running and self._memory_bus is not None,
            uptime_seconds=uptime_seconds,
            metrics={
                "last_consolidation_timestamp": (
                    self._last_consolidation.timestamp() if self._last_consolidation else 0.0
                ),
                "task_running": task_running,
                "last_basic_consolidation": self._last_consolidation.timestamp() if self._last_consolidation else 0.0,
                "last_extensive_consolidation": (
                    self._last_extensive_consolidation.timestamp() if self._last_extensive_consolidation else 0.0
                ),
                "last_profound_consolidation": (
                    self._last_profound_consolidation.timestamp() if self._last_profound_consolidation else 0.0
                ),
                "consolidation_task_running": task_running,
            },
            last_error=None,
            last_health_check=current_time,
            custom_metrics={
                "basic_interval_hours": self._basic_interval.total_seconds() / 3600,
                "extensive_interval_days": self._extensive_interval.total_seconds() / 86400,
                "profound_interval_days": self._profound_interval.total_seconds() / 86400,
                "profound_target_mb_per_day": self._profound_target_mb_per_day,
            },
        )

    async def get_metrics(self) -> Dict[str, float]:
        """v1.4.3 API metrics: totals, datapoints, storage saved, uptime."""
        uptime_seconds = 0.0
        if self._start_time:
            uptime_seconds = (self._now() - self._start_time).total_seconds()

        total_consolidations = (
            self._basic_consolidations + self._extensive_consolidations + self._profound_consolidations
        )
        avg_record_size_kb = 2.0
        storage_saved_mb = (self._records_deleted * avg_record_size_kb) / 1024.0

        return {
            "tsdb_consolidations_total": float(total_consolidations),
            "tsdb_datapoints_processed": float(self._records_consolidated),
            "tsdb_storage_saved_mb": storage_saved_mb,
            "tsdb_uptime_seconds": uptime_seconds,
        }

    def get_node_type(self) -> NodeType:
        """Get the node type this service manages."""
        return NodeType.TSDB_SUMMARY

    def get_service_type(self) -> ServiceType:
        """Get the service type."""
        return ServiceType.TELEMETRY

    def _get_actions(self) -> List[str]:
        """Graph services don't handle actions through buses."""
        return []
