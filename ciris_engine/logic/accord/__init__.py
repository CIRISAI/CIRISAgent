"""Accord: the agent's side of the CC 4.2.1.1 constitutional halt.

- ``ingress``: a v2 accord row seen in any channel is forwarded, unchanged, to
  the folded node, which verifies and latches it. The agent does no crypto.
- ``authorities``: the WA trust root for the signed emergency-shutdown command.

The latch reader and act gate live in ``ciris_engine.logic.utils.halt_latch``.
The legacy 77-byte stego ``AccordPayload`` kill switch is retired (CIRISAgent#1231).
"""

from ciris_engine.logic.accord.authorities import EmergencyAuthorities
from ciris_engine.logic.accord.ingress import extract_accord_row, forward_accord_row

__all__ = ["EmergencyAuthorities", "extract_accord_row", "forward_accord_row"]
