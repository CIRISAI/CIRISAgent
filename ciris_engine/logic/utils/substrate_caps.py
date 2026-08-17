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
_AGENT_INSTALLS_SCRUBBER = True


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

    NOW TRUE (2.9.23). `persistence/db/core.py` constructs the Engine with
    `scrubber=egress_scrub`, so persist redacts what it stores and `full_traces`
    is no longer refused.

    WHY IT WAS HELD, and why that reasoning ended: the hold was never about the
    binding's availability — it has shipped on every pin since ciris-server
    0.5.174 and is in the 0.5.176 we pin. It was about the Engine field being
    engine-WIDE, which looked like it would redact the local original along with
    the shipped copy, and a self-scoped trace must stay full.

    That framed our Python path as a special case when it is simply the LAST one:
    the crate's scrubber was already wired into both Rust ingest paths, and the
    agent reaches persist through Python, so it alone never saw one. Scrubbing at
    persist is the design every other path already follows. Wiring it makes us
    consistent rather than divergent, and the honest-downgrade 5-tuple
    (persist v32.3.0 / CIRISPersist#701) means a level we cannot deliver is
    RELABELLED rather than claimed.

    If self-scoped traces later need to stay unredacted locally, that is a
    scope-aware scrubber in the substrate, not a Python-side opt-out — an agent
    that quietly stores more than it says it does is the failure this whole
    guard exists to prevent.
    """
    if not _AGENT_INSTALLS_SCRUBBER:
        return False

    # AND the binding must actually be importable. core.py imports egress_scrub
    # defensively and falls back to `scrubber=None` when it is absent, so on a
    # pin without it the Engine gets NullScrubber while this constant still says
    # True — the two halves of "the same fact stated twice" disagreeing, which is
    # the precise failure this module exists to prevent. Fail closed: an import
    # error is not evidence that scrubbing works.
    try:
        from ciris_server import egress_scrub  # noqa: F401
    except Exception:
        return False
    return True
