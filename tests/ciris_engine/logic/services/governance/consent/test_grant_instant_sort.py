"""asserted_at is an instant; its rendering is not stable across persist releases (CIRISAgent#1136)."""

from __future__ import annotations

from datetime import datetime, timezone

from ciris_engine.logic.services.governance.consent.attestation import _instant


def test_a_later_microsecond_row_beats_an_earlier_millisecond_row() -> None:
    """The exact inversion: pre-v39 '.049840Z' (later) vs post-v39 '.049Z' (earlier)."""
    pre_v39_later = {"asserted_at": "2026-08-14T14:48:29.049840Z"}
    post_v39_earlier = {"asserted_at": "2026-08-14T14:48:29.049Z"}
    # the string order is WRONG ...
    assert pre_v39_later["asserted_at"] < post_v39_earlier["asserted_at"]
    # ... the instant order is right
    assert _instant(pre_v39_later) > _instant(post_v39_earlier)
    ordered = sorted([post_v39_earlier, pre_v39_later], key=_instant, reverse=True)
    assert ordered[0] is pre_v39_later


def test_both_renderings_of_one_instant_compare_equal() -> None:
    assert _instant({"asserted_at": "2026-08-14T14:48:29.049000Z"}) == _instant({"asserted_at": "2026-08-14T14:48:29.049Z"})


def test_unparseable_or_missing_sorts_last() -> None:
    floor = datetime.min.replace(tzinfo=timezone.utc)
    assert _instant({}) == floor
    assert _instant({"asserted_at": "not a time"}) == floor
    assert _instant({"asserted_at": "2026-01-01T00:00:00Z"}) > floor
