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
        assert state is not None
        assert state.key_id == "ciris-canonical-1-d7bdeu223k"
        assert state.knows_peer is True
        assert state.kex_present is True
        assert state.deliverable is True

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
        assert runner._peer_state_from_delivery_status(lambda: line).key_id == "canonical-1"

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


class TestTheFallbackCannotManufactureGreen:
    """Every way the delivery_status fallback could claim more than it knows."""

    def _status(self, targets, peers, phase="kex-present-await-ship"):
        return "[DELIVERY-STATUS] phase=%s %s" % (
            phase,
            json.dumps({"delivery_started": True, "edge_up": True, "canonical_targets": targets, "peers": peers}),
        )

    def test_an_unrelated_peer_is_never_substituted_for_the_canonical(self, runner):
        """The canonical is named. If it has not appeared in `peers` yet, that
        IS the finding — handing back some other rooted, KEX-ready federation
        peer would report the canonical's preconditions GREEN under exactly the
        missing-canonical condition being diagnosed."""
        line = self._status(
            targets=["ciris-canonical-1-d7bdeu223k"],
            peers=[{"key_id": "some-other-peer", "knows_peer": True, "kex_present": True, "deliverable": True}],
        )
        assert runner._peer_state_from_delivery_status(lambda: line) is None

    def test_with_no_named_target_the_single_peer_is_still_usable(self, runner):
        line = self._status(targets=[], peers=[{"key_id": "p1", "knows_peer": True}])
        state = runner._peer_state_from_delivery_status(lambda: line)
        assert state is not None and state.key_id == "p1"

    def test_absent_fields_stay_unknown_rather_than_false(self, runner):
        """The whole point of the change: unknown must not read as false."""
        line = self._status(targets=["c1"], peers=[{"key_id": "c1"}])
        state = runner._peer_state_from_delivery_status(lambda: line)
        assert state.knows_peer is None
        assert state.kex_present is None
        assert state.deliverable is None

    def test_the_state_is_a_typed_model_not_a_raw_dict(self, runner):
        from tools.qa_runner.runner import CanonicalPeerState

        line = self._status(targets=["c1"], peers=[{"key_id": "c1", "knows_peer": True, "junk": "ignored"}])
        state = runner._peer_state_from_delivery_status(lambda: line)
        assert isinstance(state, CanonicalPeerState)
        assert not hasattr(state, "junk"), "extra keys must be ignored, not absorbed untyped"


class TestDeliverableIsHonoured:
    """rooted + KEX does not imply deliverable, and the node says so itself."""

    def test_a_non_deliverable_peer_is_not_reported_as_sealable(self):
        from tools.qa_runner.runner import CanonicalPeerState

        # the shape: delivery not started / edge down, yet both booleans true
        state = CanonicalPeerState(key_id="c1", knows_peer=True, kex_present=True, deliverable=False)
        # mirrors the verdict logic: PRESENT requires deliverable is not False
        kex_state = "PRESENT" if (state.kex_present is True and state.deliverable is not False) else "not-deliverable"
        assert kex_state == "not-deliverable", (
            "reporting PRESENT here would print 'trace envelopes can seal' AND skip the "
            "diagnosis that names deliverable=false"
        )

    def test_the_source_gates_PRESENT_on_deliverable(self):
        from pathlib import Path

        src = (Path(__file__).resolve().parents[3] / "tools/qa_runner/runner.py").read_text(encoding="utf-8")
        assert "deliverable is not False" in src, (
            "the fallback must not set kex_state=PRESENT while the node says the peer is not deliverable"
        )


class TestSkipDoesNotFailTheRun:
    """The fix that was defeated by the aggregator."""

    def test_skip_counts_as_non_failing(self):
        from tools.qa_runner.runner import _is_non_failing

        assert _is_non_failing("✅ PASS") is True
        assert _is_non_failing("⏭️  SKIP") is True
        assert _is_non_failing("❌ FAIL") is False

    def test_the_aggregators_use_the_predicate(self):
        from pathlib import Path

        src = (Path(__file__).resolve().parents[3] / "tools/qa_runner/runner.py").read_text(encoding="utf-8")
        assert '"PASS" in result["status"]' not in src, "per-test aggregation still ignores SKIP"
        assert 'all("PASS" in r["status"] for r in results)' not in src, "module aggregation still ignores SKIP"
        assert src.count("_is_non_failing(") >= 3, "both aggregation sites must use the shared predicate"


class TestTheTracePlaneComesFromTheSubstrate:
    """Ask the node, do not re-derive it — and READ the answer, do not call it.

    Three derivations were tried and all three were wrong:

      * `kind=Trace` on the wire — no such envelope kind exists; carriers ride
        the Attestation plane, so the histogram cannot answer the question.
      * `LIKE '%trace:%'` over the attestations — read 4 against a true 3, and
        at a 1:1 carrier ratio that inflation is enough to report carriers on a
        node that holds none. `trace:` and `trace_summary:` are different
        namespaces and only one crosses the wire; the trailing colon decides,
        because `covers()` is a prefix test.
      * `trace_events.cohort_scope` — a read-time projection in a different
        table, downstream of the attestation's own scope. 71 rows at
        `federation` there is fully consistent with carriers sitting at `self`.

    And a fourth mistake, mine: calling `node_state()` from the runner. It is
    in-process to the server, which this runner boots as a subprocess, so the
    call returns nothing however healthy the node is. The node logs the value;
    the runner reads the line.
    """

    def _line(self, plane: dict, phase: str = "kex-present-await-ship") -> str:
        return f"[TRACE-PLANE] phase={phase} " + json.dumps(plane)

    def test_it_parses_the_logged_standing(self, runner):
        line = self._line(
            {"standing": "live", "band": "green", "carriers": 3,
             "last_admitted_at": "2026-08-24T14:41:00Z", "extra": "ignored"}
        )
        plane = runner._trace_plane_from_node_state(lambda: line)
        assert plane is not None
        assert (plane.standing, plane.band, plane.carriers) == ("live", "green", 3)
        assert not hasattr(plane, "extra"), "extra keys ignored, not absorbed untyped"

    def test_a_dark_plane_is_reported_not_swallowed(self, runner):
        line = self._line({"standing": "unreadable", "band": "dark", "carriers": 0})
        plane = runner._trace_plane_from_node_state(lambda: line)
        assert plane.band == "dark" and plane.carriers == 0

    def test_the_last_line_wins(self, runner):
        log = "\n".join(
            [self._line({"carriers": 0}, "kex-none-repriming"), self._line({"carriers": 4}, "ship-confirmed")]
        )
        assert runner._trace_plane_from_node_state(lambda: log).carriers == 4

    @pytest.mark.parametrize("log", ["", "no such line here", "[TRACE-PLANE] phase=x not-json"])
    def test_no_line_is_None_not_an_invented_zero(self, runner, log):
        """Saying carriers=0 when nothing reported is the same mistake as
        reading an absent probe verdict as knows_peer=false."""
        assert runner._trace_plane_from_node_state(lambda: log) is None

    def test_an_unreadable_log_is_survivable(self, runner):
        def boom() -> str:
            raise OSError("log went away")

        assert runner._trace_plane_from_node_state(boom) is None

    def test_the_node_logs_it_because_the_runner_cannot_call_it(self):
        """The agent side of the pattern must exist, or the runner reads nothing."""
        from pathlib import Path

        src = (
            Path(__file__).resolve().parents[3]
            / "ciris_engine/logic/runtime/edge_runtime.py"
        ).read_text(encoding="utf-8")
        assert "def _log_trace_plane" in src
        assert "[TRACE-PLANE]" in src
        # logged wherever delivery status is, since the two are read together
        assert src.count("_log_trace_plane(") >= 6, "every [DELIVERY-STATUS] point needs its twin"

    def test_the_harness_does_not_count_trace_kind_envelopes(self):
        """The wire histogram cannot answer this, so no CODE should ask it to.

        Checked against executable statements only — the docstrings above name
        these wrong derivations on purpose, so the next person to reach for one
        finds out why it does not work before writing it.
        """
        import ast
        from pathlib import Path

        src = (Path(__file__).resolve().parents[3] / "tools/qa_runner/runner.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        literals = {
            node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node, clean=False)
                if doc:
                    docstrings.add(doc)
        for banned in ("kind=Trace", "LIKE '%trace:%'", "trace_events.cohort_scope"):
            offenders = [lit for lit in literals - docstrings if banned in lit]
            assert not offenders, f"{banned!r} appears in executable code: {offenders}"

    def test_the_value_still_originates_from_the_substrate(self):
        """The runner reads a line, but the line must carry node_state()'s own
        answer — not something the agent computed for itself either."""
        from pathlib import Path

        agent = (
            Path(__file__).resolve().parents[3]
            / "ciris_engine/logic/runtime/edge_runtime.py"
        ).read_text(encoding="utf-8")
        assert "node_state" in agent and "trace_plane" in agent
