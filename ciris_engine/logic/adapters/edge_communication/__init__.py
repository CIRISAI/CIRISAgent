"""
CIRISEdge CommunicationService adapter.

Bridges CIRIS CommunicationBus to the Edge inline-text federation
surface (CIRISEdge#22 Tier 2, v0.9.0+). Channel prefix: `edge:`.

Channel format: `edge:{recipient_key_id}` — outbound messages route to
the federation peer keyed by `recipient_key_id` via Reticulum transport;
inbound messages are surfaced via the per-channel inbound buffer
populated by Edge's register_inline_text_handler callback.

Required at boot — see ciris_engine.logic.runtime.edge_runtime for the
foundation-layer init pattern.
"""

from .service import EdgeCommunicationService

__all__ = ["EdgeCommunicationService"]
