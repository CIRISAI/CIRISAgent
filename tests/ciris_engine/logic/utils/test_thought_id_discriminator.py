"""A follow-up's id must name WHICH parent, not just the parent's type.

`generate_thought_id` built follow-up ids as
``f"th_followup_{parent_thought_id[:8]}_..."``. For a seed parent that slice
returns the literal ``"th_seed_"`` — the prefix is exactly 8 characters, so the
"discriminator" carried zero identity and every follow-up of every seed was
named ``th_followup_th_seed__<uuid12>``. The double underscore is the tell: an
empty field between two separators.

The seed branch uses the same ``[:8]`` idiom on ``task_id``, a bare UUID with no
prefix, where it is correct. Same operation, two differently-shaped inputs.

This was found on a real Android filmstrip run whose two traces reached the
canonical complete and in order — the causal graph was intact because linkage
rides on ``task_id``. What failed was reading it: searching the canonical for
``th_followup_th_seed_7d4fb7ea…`` can never match, because that id cannot exist.
So these tests assert on the *observable* property that failed — that a
follow-up id contains something identifying about its specific parent.
"""

from __future__ import annotations

import pytest

from ciris_engine.logic.utils.thought_utils import generate_thought_id
from ciris_engine.schemas.runtime.enums import ThoughtType

# The exact ids from the run that surfaced this (task 7d4fb7ea-6203-...).
REAL_SEED_ID = "th_seed_7d4fb7ea_b450ed65-50f"


def _followup_of(parent: str) -> str:
    return generate_thought_id(ThoughtType.FOLLOW_UP, parent_thought_id=parent)


def test_followup_of_a_seed_is_not_the_empty_discriminator() -> None:
    """The regression itself: `th_followup_th_seed__…` must never be minted."""
    child = _followup_of(REAL_SEED_ID)

    assert not child.startswith("th_followup_th_seed_"), (
        f"follow-up id {child!r} carries the parent's TYPE PREFIX as its "
        f"discriminator instead of the parent's identity — this is the "
        f"parent_thought_id[:8] defect"
    )
    assert "__" not in child, (
        f"{child!r} has an empty field between separators, which is what an "
        f"all-prefix discriminator looks like"
    )


def test_followup_id_names_its_specific_parent() -> None:
    """The property that actually matters: the id is traceable to THIS seed."""
    child = _followup_of(REAL_SEED_ID)
    assert "7d4fb7ea" in child, (
        f"{child!r} does not contain the parent's discriminator, so it cannot "
        f"be matched back to the seed it came from"
    )


def test_two_seeds_do_not_produce_indistinguishable_followups() -> None:
    """Before the fix EVERY seed's follow-ups shared one prefix — the bug's
    practical cost, stated without reference to the implementation."""
    a = _followup_of("th_seed_aaaaaaaa_111111111-11")
    b = _followup_of("th_seed_bbbbbbbb_222222222-22")

    prefix_a = a.rsplit("_", 1)[0]
    prefix_b = b.rsplit("_", 1)[0]
    assert prefix_a != prefix_b, (
        f"follow-ups of two different seeds are indistinguishable up to the "
        f"random tail ({prefix_a!r}); the parent is unidentifiable"
    )


@pytest.mark.parametrize(
    "parent",
    [
        "th_seed_7d4fb7ea_b450ed65-50f",
        "th_std_550e8400-e29b-41d4-a716-446655440000",
        "th_ponder_550e8400-e29b-41d4-a716-446655440000",
        "th_obs_550e8400-e29b-41d4-a716-446655440000",
        "th_followup_7d4fb7ea_f0342b2e-81b",  # a follow-up of a follow-up
    ],
)
def test_no_parent_shape_yields_an_empty_discriminator(parent: str) -> None:
    """Every id this module mints starts `th_<type>_`, so every one of them was
    a candidate for the same truncation bug — not only seeds."""
    child = _followup_of(parent)
    assert "__" not in child, f"empty discriminator for parent {parent!r}: {child!r}"
    middle = child[len("th_followup_") :].rsplit("_", 1)[0]
    assert middle, f"no discriminator at all for parent {parent!r}: {child!r}"
    assert not middle.startswith("th_"), (
        f"discriminator {middle!r} is a type prefix, not identity, for parent {parent!r}"
    )


def test_seed_ids_still_carry_the_task_discriminator() -> None:
    """The seed branch was already correct; do not regress it while fixing the
    follow-up branch."""
    task_id = "7d4fb7ea-6203-458e-b57e-bd33c18b67ca"
    seed = generate_thought_id(ThoughtType.STANDARD, task_id=task_id, is_seed=True)
    assert seed.startswith("th_seed_7d4fb7ea_")


def test_followup_ids_are_unique() -> None:
    """Embedding the parent must not cost collision resistance."""
    ids = {_followup_of(REAL_SEED_ID) for _ in range(200)}
    assert len(ids) == 200
