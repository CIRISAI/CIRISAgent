"""Every verb either has a second-pass evaluator or is listed as not needing one.

ASPDMA selects a verb without the domain knowledge needed to fill that verb's
parameters. TOOL has had a second pass (TSASPDMA) that supplies the tool's
documentation, and DEFER one (DSASPDMA) that supplies the rights taxonomy. The
other eight verbs had nothing, and nothing said so.

What that cost, observed live: the agent was told "my favorite color is
chartreuse", replied "Noted: your favorite color is chartreuse", then emitted a
MEMORIZE onto a freshly-minted UUID node. Nothing queries such a node — user
enrichment reads `user/{user_id}` and only that — so the fact would have been
stored and permanently unreachable. The write also carried `created_at`, a
system-managed attribute, so the handler refused it; the agent PONDERed, retried
with another fresh UUID, and looped. ~73k tokens to not remember a colour.

Neither mistake is a reasoning failure — they are missing conventions, exactly
what a second pass exists to supply. MSASPDMA now does for MEMORIZE what TSASPDMA
does for TOOL.

This test exists so the NEXT gap is a CI failure rather than a production loop
(#1027). A verb with no second pass is a legitimate state; a verb nobody has
thought about is not. Adding a verb to HandlerActionType forces a decision here.
"""

from __future__ import annotations

import pytest

from ciris_engine.logic.processors.core.thought_processor.main import ThoughtProcessor
from ciris_engine.schemas.runtime.enums import HandlerActionType

# Verbs deliberately without a second pass, each with the reason. Moving a verb
# OUT of this set means writing its evaluator; moving one IN means writing down
# why it needs no conventions beyond what ASPDMA already had.
NO_SECOND_PASS_NEEDED = {
    HandlerActionType.SPEAK: "content is the agent's own words; the conscience layer reviews it",
    HandlerActionType.PONDER: "reconsidering is itself the second look",
    HandlerActionType.OBSERVE: "read-only; a malformed observe returns nothing rather than writing wrongly",
    HandlerActionType.REJECT: "terminal refusal, no parameters to get wrong",
    HandlerActionType.TASK_COMPLETE: "terminal, no parameters to get wrong",
    HandlerActionType.RECALL: "read-only today — REVISIT: it shares MEMORIZE's node-addressing problem, "
    "so a bad id silently returns nothing (#1027)",
    HandlerActionType.FORGET: "REVISIT: destructive AND shares the addressing problem — strongest "
    "remaining candidate for a second pass (#1027)",
}


def test_every_verb_is_accounted_for() -> None:
    """The point of the file: no verb may be silently unconsidered."""
    registered = set(ThoughtProcessor._VERB_SECOND_PASS)
    declared = set(NO_SECOND_PASS_NEEDED)
    unaccounted = set(HandlerActionType) - registered - declared

    assert not unaccounted, (
        f"verbs with neither a second-pass evaluator nor a documented reason for not "
        f"having one: {sorted(v.value for v in unaccounted)}. Add an evaluator, or add "
        f"it to NO_SECOND_PASS_NEEDED with the reason."
    )


def test_a_verb_is_not_in_both_lists() -> None:
    overlap = set(ThoughtProcessor._VERB_SECOND_PASS) & set(NO_SECOND_PASS_NEEDED)
    assert not overlap, f"registered AND declared unnecessary: {sorted(v.value for v in overlap)}"


@pytest.mark.parametrize(
    "verb", [HandlerActionType.TOOL, HandlerActionType.DEFER, HandlerActionType.MEMORIZE]
)
def test_the_three_evaluated_verbs_are_registered(verb: HandlerActionType) -> None:
    assert verb in ThoughtProcessor._VERB_SECOND_PASS


def test_memorize_is_registered_because_of_the_orphaned_write() -> None:
    """Named separately: this is the regression the incident produced."""
    assert HandlerActionType.MEMORIZE in ThoughtProcessor._VERB_SECOND_PASS, (
        "MEMORIZE lost its second pass — the agent can again write user facts to "
        "unreadable node ids and loop retrying"
    )


def test_registry_entries_are_callable() -> None:
    for verb, handler in ThoughtProcessor._VERB_SECOND_PASS.items():
        assert callable(handler), f"{verb.value} maps to a non-callable"


def test_reasons_are_written_down_not_blank() -> None:
    """A verb listed with an empty reason is the same as an unconsidered verb."""
    for verb, reason in NO_SECOND_PASS_NEEDED.items():
        assert reason and len(reason) > 20, f"{verb.value} needs a real reason, got {reason!r}"
