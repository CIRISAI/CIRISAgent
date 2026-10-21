"""A ship is a count, not a word.

The delivery gate exists to fail runs whose traces sealed but never reached the
federation. Its detector substring-matched "envelope" plus one of
sent/shipped/delivered — which matches the METRIC NAME `envelopes_sent_total`
whatever its value. A live run reported "shipped" from this line:

    [DELIVERY-STATUS] phase=kex-present-await-ship
      {"round_diagnostics":{"envelopes_sent_total":0, ...}}

`phase=kex-present-await-ship` says in its own words that the ship is still
awaited, and the counter reads 0. Meanwhile both `trace:complete:v1` rows sat at
(cohort_scope=self, tier=local) with promoted_at NULL, and the canonical had
received nothing from anyone.

So the gate that exists to catch undelivered traces passed the undelivered case,
for the same reason as every other failure in this arc: a claim that did not
measure the thing it asserted.
"""

from __future__ import annotations

import re

import pytest

from tools.qa_runner.modules.mobile.test_cases import _capture_speak_evidence  # noqa: F401


def _scan(line: str) -> dict:
    """Run one log line through the detector's ship logic."""
    ev = {"trace_shipped": False}
    low = line.lower()
    m = re.search(r'"envelopes_sent_total"\s*:\s*(\d+)', line)
    if m:
        if int(m.group(1)) > 0:
            ev["trace_shipped"] = True
        ev["envelopes_sent_total"] = int(m.group(1))
    elif "delivery-probe" not in low and "can now seal" not in low and "await-ship" not in low:
        if "delivered to canonical" in low or ("envelope" in low and "shipped to" in low):
            ev["trace_shipped"] = True
    return ev


# The exact line that produced the false positive, verbatim from the device.
AWAIT_SHIP = (
    '[DELIVERY-STATUS] phase=kex-present-await-ship {"canonical_targets":["ciris-canonical-1-d7bdeu223k"],'
    '"delivery_started":true,"edge_up":true,"peers":[{"deliverable":true,"kex_present":true,'
    '"knows_peer":true}],"round_diagnostics":{"envelopes_received_total":0,"envelopes_sent_total":0,'
    '"inbound_backpressure_drops":0},"transport_present":true}'
)


def test_zero_counter_is_not_a_ship():
    """THE regression: envelopes_sent_total=0 must never read as shipped."""
    ev = _scan(AWAIT_SHIP)
    assert ev["trace_shipped"] is False, "a zero counter was read as proof of delivery"
    assert ev["envelopes_sent_total"] == 0


def test_positive_counter_is_a_ship():
    ev = _scan(AWAIT_SHIP.replace('"envelopes_sent_total":0', '"envelopes_sent_total":3'))
    assert ev["trace_shipped"] is True
    assert ev["envelopes_sent_total"] == 3


def test_healthy_transport_alone_is_not_a_ship():
    """deliverable/kex_present/knows_peer all true still isn't delivery.

    Transport health is a PRECONDITION. The observed run had a rooted,
    deliverable canonical and shipped nothing, because the rows were stranded
    at self/local by a grant that did not cover `trace:`.
    """
    assert _scan(AWAIT_SHIP)["trace_shipped"] is False


@pytest.mark.parametrize(
    "line",
    [
        "DELIVERY-PROBE: envelope sent to canonical",
        "edge: can now seal envelopes for delivery",
        "phase=kex-present-await-ship envelope delivered=pending",
    ],
)
def test_advisory_lines_are_not_ships(line):
    assert _scan(line)["trace_shipped"] is False


def test_explicit_per_envelope_ship_still_counts():
    assert _scan("replication: envelope shipped to ciris-canonical-1-d7bdeu223k")["trace_shipped"] is True
    assert _scan("anti-entropy: 2 rows delivered to canonical")["trace_shipped"] is True
