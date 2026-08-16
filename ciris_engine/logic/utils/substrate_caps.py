"""What the agent's substrate wiring can actually do.

One place to ask, because the answer gates behaviour in unrelated layers — an
API route and an adapter's bootstrap — and two copies of a capability probe
drift the moment one of them is updated for a new substrate release.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: Does the agent hand persist a real egress scrubber when it builds the Engine?
#:
#: THE ONE PLACE TO FLIP. `persistence/db/core.py` constructs
#: `Engine(dsn, signing_key_id, ...)` with no `scrubber=`, so persist installs
#: `NullScrubber`. Change that construction and change this together — they are
#: the same fact stated twice, and the whole point of the constant is that there
#: is exactly one of them.
_AGENT_INSTALLS_SCRUBBER = False


def substrate_can_scrub() -> bool:
    """True if traces we persist are actually being redacted.

    ASKS THE RIGHT QUESTION, which the first version of this did not. It probed
    `hasattr(ciris_server, "egress_scrub")` — whether the SUBSTRATE exposes a
    scrubber — and that is not the question. From 0.5.174 the binding exists on
    every supported pin, so the probe answers True while the agent still
    constructs `Engine(scrubber=None)`. persist then installs `NullScrubber`,
    and `full_traces` batches are refused outright:

        ValueError: ('scrub_treatment_mismatch', 'label=full_traces ...')

    That is the exact failure the 2.9.18 guards exist to prevent, and a probe of
    substrate capability would have re-enabled it the moment we bumped the pin —
    a guard silently disabled by an unrelated dependency bump.

    WHY THE SCRUBBER IS NOT WIRED (CIRISServer#418). `EgressScrubber` is not
    scope-aware: `cohort_scope`/`audience` appear nowhere in its logic, so it
    cannot tell a self-scoped trace from a federation-promoted one. Since
    persist's Python `receive_and_persist` takes no scrubber argument, the Engine
    field is the only lever, and it is engine-WIDE — redacting the local original
    along with the shipped copy. The self-scoped trace must stay full, so we hold
    until scrubbing can run at the scope-change seam.

    Consequence while False: `full_traces` is refused on the interactive route
    and downgraded to `detailed` at adapter bootstrap. Both are correct — nothing
    is being redacted, so nothing may claim it was.
    """
    return _AGENT_INSTALLS_SCRUBBER
