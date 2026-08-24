"""The federation-delivery verdict must not invent facts it does not have.

A live run against the canonical peer reported:

    transport-rooted : ❓ probe verdict not found  (edge.knows_peer — authoritative)
    ❌ Canonical NOT transport-rooted (edge.knows_peer=false) — neither rounds
       nor trace envelopes can flow. Check the canonical boot-prime + bootstrap dial.
    delivery_status  : phase=kex-present-await-ship started=True edge_up=True
    → deliverable=true but trace not landing

Three sentences, and the middle one contradicts both its neighbours. The node
log for that same run showed the peer rooted from its baked KeyRecord, 300
anti-entropy rounds, 50 inbound envelopes and zero dropped frames — the
transport was fine. What had actually happened is that the `[DELIVERY-PROBE]`
line never landed, and an absent verdict was rendered as `false`.

That is worse than no verdict: it points the reader at the boot-prime and the
bootstrap dial, which were healthy, and away from the ship stage, which was
not. So: unknown is its own outcome, and when the probe line is missing the
verdict comes from `delivery_status()` — the same value the node acts on.
"""

from __future__ import annotations

import json

import pytest

STATUS_LINE = (
    "[DELIVERY-STATUS] phase=kex-present-await-ship "
    + json.dumps(
        {
            "delivery_started": True,
            "edge_up": True,
            "canonical_targets": ["ciris-canonical-1-d7bdeu223k"],
            "peers": [
                {
                    "key_id": "ciris-canonical-1-d7bdeu223k",
                    "knows_peer": True,
                    "kex_present": True,
                    "deliverable": True,
                }
            ],
        }
    )
)


@pytest.fixture
def runner():
    from tools.qa_runner.runner import QARunner

    return QARunner.__new__(QARunner)


class TestPeerStateFromDeliveryStatus:
    def test_it_reads_the_canonical_peer_entry(self, runner):
        state = runner._peer_state_from_delivery_status(lambda: STATUS_LINE)
        assert state == {
            "key_id": "ciris-canonical-1-d7bdeu223k",
            "knows_peer": True,
            "kex_present": True,
            "deliverable": True,
        }

    def test_it_prefers_the_canonical_target_over_the_first_peer(self, runner):
        line = "[DELIVERY-STATUS] phase=x " + json.dumps(
            {
                "canonical_targets": ["canonical-1"],
                "peers": [
                    {"key_id": "some-other-peer", "knows_peer": False},
                    {"key_id": "canonical-1", "knows_peer": True},
                ],
            }
        )
        assert runner._peer_state_from_delivery_status(lambda: line)["key_id"] == "canonical-1"

    @pytest.mark.parametrize(
        "log",
        ["", "nothing of interest here", "[DELIVERY-STATUS] phase=x not-json-at-all"],
    )
    def test_it_returns_None_rather_than_raising(self, runner, log):
        assert runner._peer_state_from_delivery_status(lambda: log) is None

    def test_a_reader_that_explodes_is_survivable(self, runner):
        """Diagnostics must never be the thing that fails a run."""

        def boom() -> str:
            raise OSError("log went away")

        assert runner._peer_state_from_delivery_status(boom) is None


class TestUnknownIsNotFalse:
    """The verdict text itself — the part that misled."""

    def test_the_source_no_longer_claims_knows_peer_false_on_an_absent_verdict(self):
        from pathlib import Path

        src = Path(__file__).resolve().parents[3] / "tools/qa_runner/runner.py"
        text = src.read_text(encoding="utf-8")
        claim = "Canonical NOT transport-rooted (edge.knows_peer=false)"
        # The claim may still exist — but only under an explicit `is False`.
        idx = text.index(claim)
        preceding = text[:idx]
        guard = preceding.rsplit("elif ", 1)[-1].split("\n", 1)[0]
        assert "transport_rooted is False" in guard, (
            "the hard 'knows_peer=false' verdict must be reachable only when the probe "
            f"actually said False; it is currently guarded by: {guard!r}"
        )

    def test_there_is_a_distinct_unverified_verdict(self):
        from pathlib import Path

        src = Path(__file__).resolve().parents[3] / "tools/qa_runner/runner.py"
        text = src.read_text(encoding="utf-8")
        assert "UNVERIFIED" in text, "an absent verdict needs its own outcome, not a false one"
        # contiguous in the source; the full sentence spans a string concatenation
        assert "evidence of a broken transport" in text.lower(), (
            "the unverified verdict must say plainly that it is not a failure, or readers will "
            "treat the yellow as red and chase a healthy transport again"
        )
