"""
EdgeCommunicationService — CommunicationServiceProtocol implementation
backed by the CIRISEdge inline-text federation transport.

This is the Tier 2 surface (CIRISEdge#22, Edge v0.9.1):
    - send_message(channel_id="edge:{key_id}", content) → edge.send_durable_inline_text
    - fetch_messages(channel_id="edge:{key_id}") → buffered inbound messages
      delivered via Edge.register_inline_text_handler

Tier 3 (peer_reachability / list_peers) and Tier 4 (ContentFetch /
VerifiedEnvelope feed) are deferred to Edge v0.10.0 / v0.11.0, which
unlock The Commons + remaining federation UI surfaces in
CIRISAgent 2.9.6+.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional

from ciris_engine.logic.services.base_service import BaseService
from ciris_engine.protocols.services.governance.communication import CommunicationServiceProtocol
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.messages import FetchedMessage, MessageType

logger = logging.getLogger(__name__)

EDGE_CHANNEL_PREFIX = "edge:"
_INBOUND_BUFFER_MAX = 256


def _parse_channel(channel_id: str) -> Optional[str]:
    """Extract the recipient key_id from a channel_id like 'edge:{key_id}'."""
    if not channel_id.startswith(EDGE_CHANNEL_PREFIX):
        return None
    return channel_id[len(EDGE_CHANNEL_PREFIX):] or None


class EdgeCommunicationService(BaseService, CommunicationServiceProtocol):
    """Routes inline-text federation messages through the Edge runtime."""

    def __init__(self, time_service: Optional[Any] = None) -> None:
        super().__init__(time_service=time_service, service_name="EdgeCommunicationService")
        # Per-channel ring buffer of inbound messages, keyed by sender key_id
        # (the "channel" from the bus's perspective is the peer).
        self._inbound: Dict[str, Deque[FetchedMessage]] = defaultdict(
            lambda: deque(maxlen=_INBOUND_BUFFER_MAX)
        )
        self._subscription_handle: Optional[Any] = None
        self._messages_sent = 0
        self._messages_received = 0

    async def start(self) -> None:
        """Register the inline-text handler with the Edge runtime."""
        await super().start()

        from ciris_engine.logic.runtime import edge_runtime

        if not edge_runtime.is_available():
            logger.warning(
                "EdgeCommunicationService starting without Edge runtime — "
                "send/fetch will reject. Set CIRIS_EDGE_DISABLED=false to enable."
            )
            return

        edge = edge_runtime.get_edge()
        try:
            self._subscription_handle = edge.register_inline_text_handler(
                self._on_inbound_inline_text
            )
            logger.info("EdgeCommunicationService registered inline-text handler")
        except Exception as e:
            logger.exception("Failed to register inline-text handler: %s", e)

    async def stop(self) -> None:
        """Unsubscribe from inline-text handler."""
        if self._subscription_handle is not None:
            try:
                self._subscription_handle.unsubscribe()
            except Exception as e:
                logger.warning("Subscription unsubscribe failed: %s", e)
            self._subscription_handle = None
        await super().stop()

    def _on_inbound_inline_text(self, sender_key_id: str, body_text: str) -> None:
        """Handler callback — Edge invokes this when a peer's inline text arrives."""
        now = datetime.now(timezone.utc)
        msg = FetchedMessage(
            message_id=f"edge:{sender_key_id}:{now.isoformat()}",
            author_id=sender_key_id,
            author_name=sender_key_id,
            content=body_text,
            timestamp=now.isoformat(),
            is_bot=False,
            message_type=MessageType.INLINE_TEXT.value,
        )
        self._inbound[sender_key_id].append(msg)
        self._messages_received += 1
        logger.debug(
            "Edge inbound inline_text from %s (%d bytes)", sender_key_id, len(body_text)
        )

    async def send_message(self, channel_id: str, content: str) -> bool:
        """Send inline text to a federation peer.

        channel_id format: `edge:{recipient_key_id}`.
        Returns True if Edge accepted the durable send (queued for delivery).
        """
        key_id = _parse_channel(channel_id)
        if key_id is None:
            logger.error("EdgeCommunicationService rejected channel_id %r (no edge: prefix)", channel_id)
            return False

        from ciris_engine.logic.runtime import edge_runtime

        if not edge_runtime.is_available():
            logger.error("EdgeCommunicationService send_message: Edge runtime unavailable")
            return False

        edge = edge_runtime.get_edge()
        try:
            handle = edge.send_durable_inline_text(key_id, content)
        except Exception as e:
            logger.exception("Edge.send_durable_inline_text(%s) failed: %s", key_id, e)
            return False

        # Persist the body_sha256 so callers can correlate ACK later.
        # body_sha256 is computed from the post-scrub body; useful for telemetry.
        body_sha = getattr(handle, "body_sha256", None)
        self._messages_sent += 1
        logger.debug("Edge send_durable_inline_text(%s) → body_sha256=%s", key_id, body_sha)
        return True

    async def fetch_messages(
        self,
        channel_id: str,
        *,
        limit: int = 50,
        before: Optional[datetime] = None,
    ) -> List[FetchedMessage]:
        """Return buffered inbound messages from the federation peer keyed by channel_id."""
        key_id = _parse_channel(channel_id)
        if key_id is None:
            return []

        buf = list(self._inbound.get(key_id, ()))

        if before is not None:
            before_iso = before.isoformat() if isinstance(before, datetime) else str(before)
            buf = [m for m in buf if (m.timestamp or "") < before_iso]

        return buf[-limit:] if limit > 0 else buf

    async def get_default_channel(self) -> Optional[str]:
        """Edge has no default channel — addressing is always per-peer."""
        return None

    # ─── BaseService abstract method implementations ────────────────────────

    def _check_dependencies(self) -> bool:
        """Edge runtime must be initialized before this service can route messages."""
        from ciris_engine.logic.runtime import edge_runtime

        return edge_runtime.is_available()

    def _get_actions(self) -> List[str]:
        # Actions list flows through BaseService.get_capabilities() which
        # wraps it in a ServiceCapabilities pydantic model. Previously
        # this file also overrode get_capabilities → list[str], which is
        # incompatible with the BaseService / ServiceProtocol contract
        # (ServiceCapabilities). Removed the override; the base does the
        # right thing now, and `federation:inline_text` is folded into
        # the actions list returned from here.
        return ["send_message", "fetch_messages", "federation:inline_text"]

    def get_service_type(self) -> ServiceType:
        return ServiceType.ADAPTER

    def get_home_channel_id(self) -> Optional[str]:
        """The local agent's own federation address — `edge:{signer_key_id}`."""
        from ciris_engine.logic.runtime import edge_runtime

        addr = edge_runtime.get_federation_address()
        if not addr:
            return None
        return f"{EDGE_CHANNEL_PREFIX}{addr}"
