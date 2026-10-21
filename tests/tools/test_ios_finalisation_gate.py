"""One failed iOS leg must stop the whole iOS finalisation.

`Resources.zip` is a single tree that every substrate library writes into, and
`main()` rebuilds it once at the end for whichever libraries succeeded. That is
the trap: a library whose binding refresh failed has ALREADY copied its new
native module into that shared tree. Rebuilding the zip because a *different*
library succeeded therefore commits a mixed bundle — new native module beside a
stale Python wrapper — over a committed artifact, and then writes
`substrate.lock.json` asserting the successful library is current inside it.

The run does exit nonzero afterwards. That does not undo a replaced bundle.
"""

from __future__ import annotations

import tools.update_substrate_libs as usl

OK = usl.UpdateStatus.SUCCESS
BAD = usl.UpdateStatus.FAILED
PEND = usl.UpdateStatus.PENDING


def test_a_failed_leg_is_reported_even_when_another_succeeded() -> None:
    """THE CASE. Mixed results are what make the shared tree unsafe."""
    results = [("server", "ios", OK), ("verify", "ios", BAD)]
    assert usl.ios_legs_that_failed(results) == ["verify"]


def test_an_all_green_run_finalises() -> None:
    """The gate must not block the good path, or refreshes simply stop working."""
    assert usl.ios_legs_that_failed([("server", "ios", OK), ("verify", "ios", OK)]) == []


def test_an_android_failure_does_not_block_ios() -> None:
    """Android writes nowhere near Resources.zip; blocking on it would be
    superstition rather than a rule about the shared tree."""
    assert usl.ios_legs_that_failed([("server", "ios", OK), ("server", "android", BAD)]) == []


def test_pending_is_not_failure() -> None:
    """PENDING means upstream has not published yet — nothing was written to the
    tree, so it cannot have poisoned it."""
    assert usl.ios_legs_that_failed([("server", "ios", OK), ("lens", "ios", PEND)]) == []
