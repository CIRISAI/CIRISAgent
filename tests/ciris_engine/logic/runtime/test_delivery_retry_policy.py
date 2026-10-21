"""When to reprime, and when to stop pretending waiting will help.

Both decisions come from one live run that failed: 141 anti-entropy rounds,
21 Key envelopes sent, ZERO envelopes received, KEX never landed, and the
delivery window torn down at 3m16s. Under the old flat 180s cadence that run
got exactly ONE reprime, and its log said "give it a round" the whole time —
to a peer that was never going to answer, because the canonical held no key
for that node and a fail-closed refusal is silent (CIRISServer#488).
"""

from __future__ import annotations

import pytest

from ciris_engine.logic.runtime.edge_runtime import (
    REPRIME_CADENCE,
    REPRIME_SCHEDULE,
    peer_is_silent,
    should_reprime,
)


class TestTheScheduleIsFrontLoaded:
    def test_the_first_nudge_lands_inside_a_short_window(self):
        """The failing run had ~196s of window after rooting. A first reprime
        at 180s leaves no room for a second; at 45s it leaves three."""
        assert REPRIME_SCHEDULE[0] < 60
        assert len(REPRIME_SCHEDULE) >= 3
        assert REPRIME_SCHEDULE == tuple(sorted(REPRIME_SCHEDULE)), "must be increasing"

    @pytest.mark.parametrize("waited", [0, 15, 30, 44])
    def test_nothing_fires_before_the_first_slot(self, waited):
        assert should_reprime(waited, reprimes_done=0, last_reprime=0) is False

    def test_the_first_slot_fires_at_45s(self):
        assert should_reprime(45, reprimes_done=0, last_reprime=0) is True

    def test_each_slot_fires_in_turn(self):
        # having done one at 45, the next waits for 120 — not 45+cadence
        assert should_reprime(60, reprimes_done=1, last_reprime=45) is False
        assert should_reprime(120, reprimes_done=1, last_reprime=45) is True
        assert should_reprime(299, reprimes_done=2, last_reprime=120) is False
        assert should_reprime(300, reprimes_done=2, last_reprime=120) is True

    def test_a_short_window_gets_more_than_the_single_attempt_it_used_to(self):
        """The regression this exists to prevent, walked at the probe's own
        15s step over the 196s the failing run actually had.

        The old flat 180s cadence fired ONCE, at 180 — 16 seconds before
        teardown. The schedule fires at 45 and 120: two real attempts, both
        early enough for a reply to come back. Not three — the third slot is
        at 300s, past this window — and asserting three would be asserting a
        number rather than the behaviour.
        """
        fired, done, last = [], 0, 0
        for waited in range(0, 196, 15):
            if should_reprime(waited, done, last):
                fired.append(waited)
                done += 1
                last = waited
        assert fired == [45, 120], f"expected two early attempts, got {fired}"

        # what the old policy managed over the same window, for contrast
        old_policy = [w for w in range(0, 196, 15) if w and w % 180 == 0]
        assert len(old_policy) == 1 and len(fired) > len(old_policy)

    def test_after_the_schedule_it_settles_to_the_steady_cadence(self):
        spent = len(REPRIME_SCHEDULE)
        assert should_reprime(400, reprimes_done=spent, last_reprime=300) is False
        assert should_reprime(300 + REPRIME_CADENCE, reprimes_done=spent, last_reprime=300) is True

    def test_the_steady_cadence_is_not_faster_than_the_last_slot(self):
        """Front-loading must not turn into hammering a peer that is simply slow."""
        assert REPRIME_CADENCE >= 120


class TestSilentVersusSlow:
    def test_inbound_traffic_means_slow_not_silent(self):
        """Rounds are flowing; KEX just has not landed. Waiting is correct."""
        assert peer_is_silent(received_total=1, reprimes_done=5) is False
        assert peer_is_silent(received_total=50, reprimes_done=9) is False

    def test_one_unanswered_reprime_is_not_yet_an_accusation(self):
        assert peer_is_silent(received_total=0, reprimes_done=0) is False
        assert peer_is_silent(received_total=0, reprimes_done=1) is False

    def test_two_unanswered_reprimes_with_nothing_received_is_silence(self):
        """The live failure exactly: zero inbound, asked more than once."""
        assert peer_is_silent(received_total=0, reprimes_done=2) is True
        assert peer_is_silent(received_total=0, reprimes_done=7) is True

    def test_a_single_late_reply_clears_the_verdict(self):
        """One envelope back is enough to say the peer is answering — the
        distinction is 'replies at all', not 'replies enough'."""
        assert peer_is_silent(received_total=1, reprimes_done=99) is False
