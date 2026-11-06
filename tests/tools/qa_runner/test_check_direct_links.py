"""The direct-link verdict, including the failures it exists to catch."""

from tools.qa_runner.check_direct_links import read_node, verdict

MUTUAL = "2026-11-04T10:00:00Z INFO contact_trace: CONTACT mutual owner=a"
EST = "2026-11-04T10:02:00Z INFO reticulum: direct link ESTABLISHED: the link runs over a punched interface link=" + "ab" * 16


def test_both_sides_on_one_link_after_mutual_passes() -> None:
    assert verdict(read_node([MUTUAL, EST]), read_node([MUTUAL, EST])) == []


def test_the_older_established_text_still_counts() -> None:
    line = "2026-11-04T10:02:00Z INFO direct link: established, link moved onto the direct interface link=" + "cd" * 16
    assert verdict(read_node([MUTUAL, line]), read_node([MUTUAL, line])) == []


def test_a_one_sided_move_fails() -> None:
    assert "one-sided" in verdict(read_node([MUTUAL, EST]), read_node([MUTUAL]))[0]


def test_a_one_sided_attempt_fails_even_after_a_good_retry() -> None:
    first = EST.replace(EST.rsplit("link=", 1)[1], "b" * 32)
    problems = verdict(read_node([MUTUAL, EST]), read_node([MUTUAL, first, EST]))
    assert len(problems) == 1 and "one-sided" in problems[0]


def test_no_direct_link_fails() -> None:
    assert verdict(read_node([MUTUAL]), read_node([MUTUAL])) == ["no direct link established"]


def test_going_direct_before_mutual_fails() -> None:
    late = "2026-11-04T10:05:00Z INFO contact_trace: CONTACT mutual owner=a"
    assert any("before the contact was accepted" in p for p in verdict(read_node([EST, late]), read_node([MUTUAL, EST])))


def test_the_accepting_side_logs_accept_not_mutual() -> None:
    accept = "2026-11-04T10:00:00Z INFO contact_trace: CONTACT accept owner=b"
    assert verdict(read_node([MUTUAL, EST]), read_node([accept, EST])) == []


def test_exhaustion_a_stall_close_or_a_lost_link_fails() -> None:
    for bad in (
        "2026-11-04T10:03:00Z WARN link closed: ChannelExhausted",
        "2026-11-04T10:03:00Z WARN stalled link closed (CIRISEdge#926) link=x",
        "2026-11-04T10:03:00Z WARN direct link LOST: the punched interface went down",
    ):
        peer_still_up = "2026-11-04T10:09:00Z INFO still running"
        assert verdict(read_node([MUTUAL, EST, bad]), read_node([MUTUAL, EST, peer_still_up])), bad


def test_a_loss_after_the_peer_stopped_does_not_count() -> None:
    bad = "2026-11-04T10:03:00Z WARN direct link LOST: the punched interface went down"
    assert verdict(read_node([MUTUAL, EST, bad]), read_node([MUTUAL, EST])) == []


def test_a_later_time_quoted_in_a_line_does_not_extend_the_peer() -> None:
    bad = "2026-11-04T10:03:00Z WARN direct link LOST: the punched interface went down"
    quoted = "2026-11-04T10:02:30Z INFO grant expires_at=2026-12-04T10:00:00Z"
    assert verdict(read_node([MUTUAL, EST, bad]), read_node([MUTUAL, EST, quoted])) == []

