"""
CIRISNode service — deferral routing and accord trace forwarding.

Provides:
1. WiseBus-compatible interface for receiving deferrals (send_deferral)
2. Polls CIRISNode for WBD resolution status
3. Subscribes to reasoning_event_stream for trace capture
4. Batches and forwards Ed25519-signed traces to CIRISNode in Lens format
5. Signs deferrals with agent's Ed25519 key for CIRISNode signature-based auth

Auth model: All data sent to CIRISNode is signed with the agent's Ed25519 key.
Keys are registered via CIRISPortal (portal.ciris.ai) → CIRISRegistry.
CIRISNode verifies signatures against registry-verified keys (no header auth).
"""

import asyncio
import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ciris_adapters.cirisnode.client import CIRISNodeClient
from ciris_engine.schemas.services.authority_core import DeferralRequest

logger = logging.getLogger(__name__)


# Re-use the canonical types from accord_metrics to guarantee Lens format compatibility
from ciris_adapters.ciris_accord_metrics.services import (
    CompleteTrace,
    Ed25519TraceSigner,
    SimpleCapabilities,
    TraceComponent,
    TraceDetailLevel,
    _strip_empty,
)


class CIRISNodeService:
    """WiseAuthority service for CIRISNode deferral routing and trace forwarding.

    Registers as WISE_AUTHORITY via the adapter's get_services_to_register().
    No tools — purely for oversight integration.
    """

    # Same event→component map as accord_metrics
    EVENT_TO_COMPONENT = {
        "THOUGHT_START": "observation",
        "SNAPSHOT_AND_CONTEXT": "context",
        "DMA_RESULTS": "rationale",
        "IDMA_RESULT": "rationale",
        "ASPDMA_RESULT": "rationale",
        "TSASPDMA_RESULT": "rationale",
        "CONSCIENCE_RESULT": "conscience",
        "ACTION_RESULT": "action",
        "ReasoningEvent.THOUGHT_START": "observation",
        "ReasoningEvent.SNAPSHOT_AND_CONTEXT": "context",
        "ReasoningEvent.DMA_RESULTS": "rationale",
        "ReasoningEvent.IDMA_RESULT": "rationale",
        "ReasoningEvent.ASPDMA_RESULT": "rationale",
        "ReasoningEvent.TSASPDMA_RESULT": "rationale",
        "ReasoningEvent.CONSCIENCE_RESULT": "conscience",
        "ReasoningEvent.ACTION_RESULT": "action",
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {}
        self._client: Optional[CIRISNodeClient] = None

        # Deferral state: thought_id -> {wbd_task_id, agent_task_id}
        self._pending_deferrals: Dict[str, Dict[str, str]] = {}
        self._poll_task: Optional[asyncio.Task[None]] = None
        self._running = False
        self._poll_interval = float(self.config.get("poll_interval", 30))

        # Trace forwarding config
        self._batch_size = int(self.config.get("batch_size", 10))
        self._flush_interval = float(self.config.get("flush_interval", 60))

        # Trace detail level — check env var first, then config
        level_str = str(
            os.environ.get("CIRISNODE_TRACE_LEVEL", "") or self.config.get("trace_level", "generic")
        ).lower()
        try:
            self._trace_level = TraceDetailLevel(level_str)
        except ValueError:
            logger.warning(f"Invalid trace_level '{level_str}', defaulting to 'generic'")
            self._trace_level = TraceDetailLevel.GENERIC

        # Event queue and batching
        self._event_queue: List[Dict[str, Any]] = []
        self._queue_lock = asyncio.Lock()
        self._flush_task: Optional[asyncio.Task[None]] = None

        # Reasoning event stream
        self._reasoning_queue: Optional[asyncio.Queue[Any]] = None
        self._reasoning_task: Optional[asyncio.Task[None]] = None

        # Active traces being built
        self._active_traces: Dict[str, CompleteTrace] = {}
        self._traces_lock = asyncio.Lock()

        # Agent ID (set by adapter from runtime)
        self._agent_id_hash: Optional[str] = None

        # Ed25519 trace signer (same unified key as audit + accord_metrics)
        self._signer = Ed25519TraceSigner()

        # Metrics
        self._events_received = 0
        self._events_sent = 0
        self._traces_completed = 0

    def set_agent_id(self, agent_id: str) -> None:
        """Set and hash the agent ID for trace anonymization."""
        self._agent_id_hash = hashlib.sha256(agent_id.encode()).hexdigest()[:16]
        logger.info(f"CIRISNodeService agent_id_hash set: {self._agent_id_hash}")

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start(self) -> None:
        """Start client, polling, and trace capture."""
        self._client = CIRISNodeClient(
            base_url=self.config.get("base_url"),
            auth_token=self.config.get("auth_token"),
            agent_token=self.config.get("agent_token"),
            timeout=self.config.get("timeout", 30),
            max_retries=self.config.get("max_retries", 3),
        )
        await self._client.start()
        self._running = True

        # Start deferral resolution polling
        self._poll_task = asyncio.create_task(self._poll_resolutions())

        # Subscribe to reasoning event stream for trace capture
        try:
            from ciris_engine.logic.infrastructure.step_streaming import reasoning_event_stream

            self._reasoning_queue = asyncio.Queue(maxsize=1000)
            reasoning_event_stream.subscribe(self._reasoning_queue)
            self._reasoning_task = asyncio.create_task(self._process_reasoning_events())
            logger.info("CIRISNodeService subscribed to reasoning_event_stream")
        except Exception as e:
            logger.warning(f"Could not subscribe to reasoning_event_stream: {e}")

        # Start periodic flush for trace batches
        self._flush_task = asyncio.create_task(self._periodic_flush())

        # Register public key with CIRISNode for signature verification
        await self._register_public_key()

        logger.info(
            f"CIRISNodeService started (trace_level={self._trace_level.value}, "
            f"batch_size={self._batch_size}, flush_interval={self._flush_interval}s)"
        )

    async def stop(self) -> None:
        """Stop all tasks and flush remaining events."""
        self._running = False

        # Unsubscribe from reasoning stream
        if self._reasoning_queue:
            try:
                from ciris_engine.logic.infrastructure.step_streaming import reasoning_event_stream

                reasoning_event_stream.unsubscribe(self._reasoning_queue)
            except Exception:
                pass

        # Cancel background tasks
        for task in [self._poll_task, self._reasoning_task, self._flush_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Final flush
        await self._flush_events()

        if self._client:
            await self._client.stop()
            self._client = None

        if self._pending_deferrals:
            logger.warning(f"CIRISNodeService stopped with {len(self._pending_deferrals)} pending deferrals")
        logger.info(f"CIRISNodeService stopped (traces={self._traces_completed}, " f"events_sent={self._events_sent})")

    # =========================================================================
    # WiseBus Interface (Duck-typed)
    # =========================================================================

    def get_capabilities(self) -> SimpleCapabilities:
        """Return capabilities for WiseBus discovery."""
        return SimpleCapabilities(
            actions=["send_deferral", "cirisnode_traces"],
            scopes=["cirisnode_oversight"],
        )

    async def send_deferral(self, request: DeferralRequest) -> str:
        """Forward deferral to CIRISNode via signed WBD submit.

        The deferral payload is signed with the agent's Ed25519 key
        (registered via CIRISPortal/CIRISRegistry). CIRISNode verifies
        the signature against the registered key before accepting.
        """
        if not self._client:
            return "CIRISNode client not started - deferral not forwarded"

        payload = json.dumps(
            {
                "reason": request.reason,
                "task_id": request.task_id,
                "thought_id": request.thought_id,
                "defer_until": request.defer_until.isoformat() if request.defer_until else None,
                "context": request.context,
            }
        )

        domain_hint = request.context.get("domain_hint") if request.context else None

        # Sign the deferral with the agent's Ed25519 key
        signature = None
        signature_key_id = None
        try:
            from ciris_engine.logic.audit.signing_protocol import get_unified_signing_key

            unified_key = get_unified_signing_key()
            # Canonical message: same fields that CIRISNode will reconstruct
            signed_payload: Dict[str, Any] = {
                "agent_task_id": request.thought_id,
                "payload": payload,
            }
            if domain_hint:
                signed_payload["domain_hint"] = domain_hint
            message = json.dumps(signed_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            signature = unified_key.sign_base64(message)
            signature_key_id = unified_key.key_id
            logger.debug(f"Deferral signed with key_id={signature_key_id}")
        except Exception as e:
            logger.warning(f"Could not sign deferral: {e}")

        try:
            result = await self._client.wbd_submit(
                agent_task_id=request.thought_id,
                payload=payload,
                domain_hint=domain_hint,
                signature=signature,
                signature_key_id=signature_key_id,
            )

            task_id = result.get("task_id") or result.get("id", "unknown")
            self._pending_deferrals[request.thought_id] = {
                "wbd_task_id": task_id,
                "agent_task_id": request.task_id,
            }

            logger.info(
                f"Deferral forwarded to CIRISNode: thought={request.thought_id} "
                f"-> task_id={task_id} signed_by={signature_key_id} (reason: {request.reason[:80]})"
            )
            return f"Submitted to CIRISNode: task_id={task_id}"

        except Exception as e:
            logger.error(f"Failed to forward deferral to CIRISNode: {e}")
            return f"Failed to submit to CIRISNode: {e}"

    async def fetch_guidance(self, context: Any) -> Optional[str]:
        """Not implemented — this service forwards deferrals, not guidance."""
        return None

    def get_service_metadata(self) -> Dict[str, Any]:
        return {"data_source": False, "service_type": "oversight"}

    def get_metrics(self) -> Dict[str, Any]:
        """Return service metrics."""
        return {
            "events_received": self._events_received,
            "events_sent": self._events_sent,
            "traces_completed": self._traces_completed,
            "pending_deferrals": len(self._pending_deferrals),
            "queue_size": len(self._event_queue),
            "trace_level": self._trace_level.value,
        }

    # =========================================================================
    # Public Key Registration
    # =========================================================================

    async def _register_public_key(self) -> None:
        """Register agent's Ed25519 public key with CIRISNode."""
        if not self._client:
            return

        if not self._signer.has_signing_key:
            logger.warning("No signing key available — cannot register public key with CIRISNode")
            return

        try:
            from ciris_engine.logic.audit.signing_protocol import get_unified_signing_key

            unified_key = get_unified_signing_key()
            payload = unified_key.get_registration_payload("CIRISNode oversight adapter")

            result = await self._client.register_public_key(payload)
            logger.info(
                f"Public key registered with CIRISNode: key_id={payload['key_id']} "
                f"result={result.get('status', 'unknown')}"
            )
        except Exception as e:
            logger.warning(f"Could not register public key with CIRISNode: {e}")

    # =========================================================================
    # Deferral Resolution Polling
    # =========================================================================

    async def _poll_resolutions(self) -> None:
        """Background: poll CIRISNode for resolved deferrals."""
        while self._running:
            try:
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break

            if not self._pending_deferrals or not self._client:
                continue

            for thought_id, deferral_info in list(self._pending_deferrals.items()):
                wbd_task_id = deferral_info["wbd_task_id"]
                agent_task_id = deferral_info["agent_task_id"]

                try:
                    result = await self._client.wbd_get_task(wbd_task_id)
                    task = result.get("task", result)
                    status = task.get("status", "")

                    if status == "resolved":
                        decision = task.get("decision", "unknown")
                        comment = task.get("comment", "")
                        logger.info(
                            f"WBD task {wbd_task_id} resolved: decision={decision}"
                            f"{f' comment={comment[:80]}' if comment else ''}"
                        )
                        del self._pending_deferrals[thought_id]

                        # Event 1: Send signed resolution accord trace
                        await self._send_resolution_trace(
                            thought_id=thought_id,
                            agent_task_id=agent_task_id,
                            wbd_task_id=wbd_task_id,
                            decision=decision,
                            comment=comment,
                        )

                        # Event 2: Reactivate the deferred task via WiseAuthorityService
                        await self._reactivate_deferred_task(
                            agent_task_id=agent_task_id,
                            thought_id=thought_id,
                            decision=decision,
                            comment=comment,
                        )

                except Exception as e:
                    logger.debug(f"Failed to poll WBD task {wbd_task_id}: {e}")

    async def _send_resolution_trace(
        self,
        thought_id: str,
        agent_task_id: str,
        wbd_task_id: str,
        decision: str,
        comment: str,
    ) -> None:
        """Send a signed accord trace for WBD resolution."""
        timestamp = datetime.now(timezone.utc).isoformat()

        resolution_trace = CompleteTrace(
            trace_id=f"wbd-resolution-{wbd_task_id}-{timestamp}",
            thought_id=thought_id,
            task_id=agent_task_id,
            agent_id_hash=self._agent_id_hash or "unknown",
            started_at=timestamp,
            completed_at=timestamp,
        )

        resolution_trace.components.append(
            TraceComponent(
                component_type="wbd_resolution",
                event_type="wbd_resolved",
                timestamp=timestamp,
                data={
                    "wbd_task_id": wbd_task_id,
                    "decision": decision,
                    "comment": comment,
                    "trace_level": self._trace_level.value,
                },
            )
        )

        if not self._signer.sign_trace(resolution_trace):
            resolution_trace.signature = ""
            resolution_trace.signature_key_id = ""

        event_payload = {
            "event_type": "wbd_resolution",
            "trace": resolution_trace.to_dict(),
        }
        await self._queue_event(event_payload)
        await self._flush_events()
        logger.info(f"Resolution trace queued for WBD task {wbd_task_id}")

    async def _reactivate_deferred_task(
        self,
        agent_task_id: str,
        thought_id: str,
        decision: str,
        comment: str,
    ) -> None:
        """Call resolve_deferral on WiseAuthorityService to reactivate the task."""
        try:
            from ciris_engine.logic.registries.base import get_global_registry
            from ciris_engine.schemas.runtime.enums import ServiceType
            from ciris_engine.schemas.services.authority_core import DeferralResponse

            registry = get_global_registry()
            wa_services = registry.get_services_by_type(ServiceType.WISE_AUTHORITY)

            # Find a WA service that has resolve_deferral (skip self)
            target_wa = None
            for svc in wa_services:
                if svc is self:
                    continue
                if hasattr(svc, "resolve_deferral"):
                    target_wa = svc
                    break

            if not target_wa:
                logger.warning("No WiseAuthorityService with resolve_deferral found")
                return

            deferral_id = f"defer_{agent_task_id}"

            # Sign the resolution response
            signature = ""
            try:
                from ciris_engine.logic.audit.signing_protocol import get_unified_signing_key

                unified_key = get_unified_signing_key()
                sig_msg = json.dumps(
                    {"deferral_id": deferral_id, "decision": decision},
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                signature = unified_key.sign_base64(sig_msg)
            except Exception:
                pass

            response = DeferralResponse(
                approved=(decision in ("approve", "approved")),
                reason=comment or f"WBD resolution: {decision}",
                wa_id="cirisnode_wa",
                signature=signature,
            )

            resolved = await target_wa.resolve_deferral(deferral_id, response)
            if resolved:
                logger.info(f"Deferred task reactivated: deferral_id={deferral_id} " f"decision={decision}")
            else:
                logger.warning(f"resolve_deferral returned False for {deferral_id}")

        except Exception as e:
            logger.error(f"Failed to reactivate deferred task: {e}")

    # =========================================================================
    # Trace Capture (from reasoning_event_stream)
    # =========================================================================

    async def _process_reasoning_events(self) -> None:
        """Consume reasoning events and build traces."""
        if self._reasoning_queue is None:
            return

        while True:
            try:
                try:
                    event_data = await asyncio.wait_for(self._reasoning_queue.get(), timeout=1.0)
                    events = event_data.get("events", [])
                    for event in events:
                        await self._process_single_event(event)
                except asyncio.TimeoutError:
                    continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                err_str = str(e).lower()
                if "no running event loop" in err_str or "event loop is closed" in err_str:
                    break
                logger.error(f"Error processing reasoning event: {e}")

    async def _process_single_event(self, event: Dict[str, Any]) -> None:
        """Process a single reasoning event into a trace component."""
        raw_event_type = event.get("event_type", "")
        if hasattr(raw_event_type, "value"):
            event_type = raw_event_type.value.upper()
        else:
            event_type = str(raw_event_type).replace("ReasoningEvent.", "")

        thought_id = event.get("thought_id", "")
        task_id = event.get("task_id")
        timestamp = event.get("timestamp", datetime.now(timezone.utc).isoformat())

        if not thought_id:
            return

        self._events_received += 1

        # Get or create trace
        async with self._traces_lock:
            if thought_id not in self._active_traces:
                trace_id = f"trace-{thought_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
                self._active_traces[thought_id] = CompleteTrace(
                    trace_id=trace_id,
                    thought_id=thought_id,
                    task_id=task_id,
                    agent_id_hash=self._agent_id_hash or "unknown",
                    started_at=timestamp,
                )
            trace = self._active_traces[thought_id]

        # Map event to component type
        component_type = self.EVENT_TO_COMPONENT.get(event_type, "unknown")

        # Extract component data using the accord_metrics extraction logic
        component_data = self._extract_component_data(event_type, event)

        component = TraceComponent(
            component_type=component_type,
            event_type=event_type,
            timestamp=timestamp,
            data=component_data,
        )

        async with self._traces_lock:
            trace.components.append(component)

        # ACTION_RESULT marks trace completion
        if event_type in ("ACTION_RESULT", "ReasoningEvent.ACTION_RESULT"):
            await self._complete_trace(thought_id, timestamp)

    def _extract_component_data(self, event_type: str, event: Dict[str, Any]) -> Dict[str, Any]:
        """Extract component data at the configured trace level.

        Delegates to the accord_metrics extraction logic for format compatibility.
        """
        try:
            from ciris_adapters.ciris_accord_metrics.services import AccordMetricsService

            # Use a throwaway instance to access _extract_component_data
            # This is a classmethod-like pattern — the method only uses self._trace_level
            extractor = AccordMetricsService.__new__(AccordMetricsService)
            extractor._trace_level = self._trace_level
            return extractor._extract_component_data(event_type, event)
        except Exception:
            # Fallback: forward raw event data (minus internal fields)
            return {k: v for k, v in event.items() if k not in ("event_type", "thought_id", "task_id", "timestamp")}

    async def _complete_trace(self, thought_id: str, timestamp: str) -> None:
        """Finalize a trace and queue it for sending."""
        async with self._traces_lock:
            trace = self._active_traces.pop(thought_id, None)
        if not trace:
            return

        trace.completed_at = timestamp
        trace.trace_level = self._trace_level.value

        # Sign trace with Ed25519 unified key
        if not self._signer.sign_trace(trace):
            logger.warning(f"Could not sign trace {trace.trace_id} — no signing key available")

        self._traces_completed += 1

        # Queue as event in Lens format
        event_payload = {
            "event_type": "accord_trace",
            "trace": trace.to_dict(),
        }
        await self._queue_event(event_payload)

    async def _queue_event(self, event: Dict[str, Any]) -> None:
        """Add event to queue, flush if batch full."""
        events_to_send: List[Dict[str, Any]] = []

        async with self._queue_lock:
            self._event_queue.append(event)
            if len(self._event_queue) >= self._batch_size:
                events_to_send = self._event_queue.copy()
                self._event_queue.clear()

        if events_to_send:
            await self._send_batch(events_to_send)

    # =========================================================================
    # Batch Sending
    # =========================================================================

    async def _periodic_flush(self) -> None:
        """Periodically flush events even if batch not full."""
        while True:
            try:
                await asyncio.sleep(self._flush_interval)
                await self._flush_events()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic flush: {e}")

    async def _flush_events(self) -> None:
        """Flush all queued events."""
        async with self._queue_lock:
            if not self._event_queue:
                return
            events_to_send = self._event_queue.copy()
            self._event_queue.clear()

        await self._send_batch(events_to_send)

    async def _send_batch(self, events: List[Dict[str, Any]]) -> None:
        """Send a batch of events to CIRISNode."""
        if not self._client:
            logger.warning("Cannot send batch — client not started")
            return

        payload = {
            "events": events,
            "batch_timestamp": datetime.now(timezone.utc).isoformat(),
            "trace_level": self._trace_level.value,
        }

        try:
            result = await self._client.post_accord_events(payload)
            self._events_sent += len(events)
            logger.info(
                f"Sent {len(events)} accord events to CIRISNode "
                f"(total={self._events_sent}, result={result.get('status', 'unknown')})"
            )
        except Exception as e:
            logger.error(f"Failed to send accord events to CIRISNode: {e}")
            # Re-queue on failure (with limit)
            async with self._queue_lock:
                if len(self._event_queue) < self._batch_size * 10:
                    self._event_queue = events + self._event_queue
