"""What can the pinned substrate actually do?

One place to ask, because the answer gates behaviour in unrelated layers — an
API route and an adapter's bootstrap — and two copies of a capability probe
drift the moment one of them is updated for a new substrate release.

Probing for a BINDING rather than comparing version numbers is deliberate: the
binding's presence IS the condition that makes the dependent feature safe, so
the gate lifts by itself on the release that adds it. A version pin would need
editing again on the very release that fixes the problem, and getting that edit
wrong silently restores the broken behaviour.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def substrate_can_scrub() -> bool:
    """True if the substrate exposes an egress scrubber we can hand to persist.

    The agent constructs persist's Engine from Python with ``scrubber=None``;
    persist fills that in with ``NullScrubber``, which redacts nothing and
    honestly reports ``ner_ran: false``. From persist v32.1.0 that combination
    is a HARD REJECTION at ``full_traces``::

        ValueError: ('scrub_treatment_mismatch', 'label=full_traces ...')

    Every batch refused — not degraded capture, ZERO traces persisted.
    ``detailed`` (production's level) still passes, which is why this is scoped
    to one level rather than being a release blocker.

    Fails CLOSED: an ImportError is not evidence that scrubbing works.
    """
    try:
        import ciris_server  # type: ignore[import-not-found, import-untyped, unused-ignore]

        return hasattr(ciris_server, "egress_scrub")
    except Exception:
        return False
