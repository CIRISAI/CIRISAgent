"""Managed user attributes: block MODIFICATION, not mere presence.

THE OBSERVED FAILURE

On a live Android run the user said "Remember this: my favorite color is
chartreuse." The agent replied "Noted: your favorite color is chartreuse." One
turn later, asked "What is my favorite color?", it answered:

    "I do not have that information stored yet — I haven't had the chance to
     learn your favorite color."

Truthful, and caused entirely by this guard. Its MEMORIZE had been refused:

    Blocked memorize attempt on managed attribute for node '61cf4076-…'

WHY IT REFUSED

`check_managed_attributes` tested PRESENCE:

    for attr_name, rationale in MANAGED_USER_ATTRIBUTES.items():
        if attr_name in attrs_to_check:      # ← blocks
            return "MEMORIZE BLOCKED: …"

Recall-modify-write-back is the natural way to add a fact about a user, and the
node returned by a recall already carries every managed attribute the system has
set — `last_seen`, `oauth_email`, `trust_level`, and the rest. So the write was
refused because of fields the agent never touched and merely carried along, and
adding any new fact to a user node was structurally impossible.

The guard's actual rule — the agent must not change system-managed fields — is
unaffected: those still refuse, and now the message says what the stored value
was.
"""

from __future__ import annotations

import pytest

from ciris_engine.logic.infrastructure.handlers.shared_helpers import (
    MANAGED_USER_ATTRIBUTES,
    check_managed_attributes,
)
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType


def _user_node(**attrs: object) -> GraphNode:
    return GraphNode(
        id="user_alice",
        type=NodeType.USER,
        scope=GraphScope.LOCAL,
        attributes=dict(attrs),
    )


def test_carrying_managed_attributes_through_unchanged_is_allowed() -> None:
    """The regression: recall → add a fact → write back must succeed."""
    stored = _user_node(last_seen="2026-08-09T20:00:00Z", oauth_email="a@b.c", trust_level=0.5)
    # What a recall hands back, plus the one new fact the agent learned.
    incoming = _user_node(
        last_seen="2026-08-09T20:00:00Z",
        oauth_email="a@b.c",
        trust_level=0.5,
        favorite_color="chartreuse",
    )

    assert check_managed_attributes(incoming, stored) is None, (
        "unchanged managed attributes carried through a recall were treated as an "
        "attempt to modify them — this is what stopped the agent remembering anything "
        "about a user"
    )


def test_actually_changing_a_managed_attribute_is_still_blocked() -> None:
    stored = _user_node(trust_level=0.5)
    incoming = _user_node(trust_level=0.99)

    err = check_managed_attributes(incoming, stored)
    assert err is not None, "the guard's real job must still work"
    assert "trust_level" in err
    assert "0.99" in err, "must state what was attempted"
    assert "0.5" in err, "must state the current value, so the diff is visible"


def test_setting_a_managed_attribute_that_was_not_stored_is_blocked() -> None:
    """Adding one where none exists is authoring it, not carrying it."""
    err = check_managed_attributes(_user_node(is_wa=True), _user_node(favorite_color="blue"))
    assert err is not None and "is_wa" in err


def test_presence_still_blocks_when_there_is_nothing_to_compare_against() -> None:
    """No stored node → conservative. A recall failure must not weaken the guard."""
    err = check_managed_attributes(_user_node(permissions=["admin"]), None)
    assert err is not None and "permissions" in err


def test_unmanaged_attributes_are_never_blocked() -> None:
    assert check_managed_attributes(_user_node(favorite_color="chartreuse"), None) is None


def test_non_user_nodes_are_out_of_scope() -> None:
    node = GraphNode(
        id="concept_x",
        type=NodeType.CONCEPT,
        scope=GraphScope.LOCAL,
        attributes={"trust_level": 0.9},
    )
    assert check_managed_attributes(node, None) is None


@pytest.mark.parametrize("attr", sorted(MANAGED_USER_ATTRIBUTES))
def test_every_managed_attribute_follows_the_same_rule(attr: str) -> None:
    """No attribute is special-cased in either direction."""
    stored = _user_node(**{attr: "original"})

    assert check_managed_attributes(_user_node(**{attr: "original"}), stored) is None, (
        f"{attr}: unchanged value must pass"
    )
    err = check_managed_attributes(_user_node(**{attr: "changed"}), stored)
    assert err is not None and attr in err, f"{attr}: a real change must be refused"
