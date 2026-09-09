"""`client:` floors — version-legible, never version-pinned (CIRISClient#39), plus the
strict form for surfaces no released client carries yet (CIRISClient#45)."""

from __future__ import annotations

import pytest

from tools.qa_runner.modules.web_ui.flow_spec import check_client_floor


@pytest.mark.parametrize(
    "floor,actual,refused",
    [
        (">=0.5.208", "0.5.212", False),
        (">=0.5.208", "0.5.208+preview.g8d77177", False),  # a build OF the release satisfies >=
        (">=0.5.208", "0.5.207", True),
        (">0.5.212", "0.5.212", True),  # strict: 0.5.212 itself does not carry it
        (">0.5.212", "0.5.212+preview.gabcdef0", True),  # nor does a preview of it
        (">0.5.212", "0.5.213", False),
        # `unreleased` refuses on ANY client -- that is the point: a numeric floor
        # stops refusing on the next cut (0.5.213 did exactly that).
        ("unreleased", "0.5.213", True),
        ("unreleased", "9.9.9", True),
        ("unreleased", None, True),
        (">0.5.212", None, False),  # unknown client: do not invent a refusal
        (None, "0.5.1", False),
    ],
)
def test_floor_semantics(floor, actual, refused) -> None:
    out = check_client_floor(floor, actual)
    assert bool(out) is refused, out


def test_an_unreadable_floor_is_refused_with_the_accepted_forms() -> None:
    out = check_client_floor("~=0.5", "0.5.212")
    assert out and ">=0.5.208" in out and ">0.5.212" in out


def test_the_strict_refusal_says_why() -> None:
    out = check_client_floor(">0.5.212", "0.5.212")
    assert out and "no released client at or below 0.5.212" in out and "cannot start" in out


def test_unreleased_refuses_every_client_and_says_why() -> None:
    out = check_client_floor("unreleased", "0.5.213")
    assert out and "no released client carries" in out and "Origin" in out


def test_unreleased_is_case_insensitive() -> None:
    assert check_client_floor("UNRELEASED", "0.5.213")
