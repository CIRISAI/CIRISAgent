"""The #983 conscience-guidance mode, readable by every surface that must record it.

CIRISAgent#986 (research-team gate audit): the mode was read from the
environment at the retry site and recorded nowhere — not the trace, not the
CEG seal. TORQUE arm D's void condition is "trace audit finds torque-reading
leakage", and **an audit cannot read an environment variable that left no
trace**. Arm assignment must never rest on operator intention.

One function, one source of truth: the thought processor consults it to build
guidance, the accord-metrics batch header records it, the compose dump pins it
in its meta line. A regime auditor holding any of the three artifacts can
establish which side of the CC 3.4.5 line the process ran on.
"""

from __future__ import annotations

import os

VALID_MODES = ("full", "qualitative")


def conscience_guidance_mode() -> str:
    """`full` (default) or `qualitative` — refuses loudly on anything else.

    See ThoughtProcessor._conscience_guidance_mode for the full rationale
    (#983 / CC 3.4.5 / RATCHET#16 arm D). Unknown values raise rather than
    guess: a regime that believes it closed the score channel and typo'd the
    mode must not run.
    """
    mode = os.environ.get("CIRIS_CONSCIENCE_GUIDANCE_MODE", "full")
    if mode not in VALID_MODES:
        raise ValueError(
            f"CIRIS_CONSCIENCE_GUIDANCE_MODE must be one of {VALID_MODES}, got {mode!r} — "
            f"refusing to guess which side of the CC 3.4.5 line this run is on"
        )
    return mode
