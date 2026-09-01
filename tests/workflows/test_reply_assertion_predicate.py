"""What counts as "the agent replied" — the rule that decides five platforms.

Every case below is a way this assertion has already gone green, or would have,
while the product was silent or broken. A gate is only worth having if it can
fail, and a predicate that accepts an error message is worse than no predicate:
it reports success at the exact moment the product stops working.
"""

from __future__ import annotations

import pytest

from tools.qa_runner.modules.web_ui.__main__ import _is_new_agent_reply

SENT = "Hello, can you hear me?"
REPLY = "Hello! Yes, I can hear you. How can I assist you today?"


def _msg(**kw):
    base = {"id": "m-new", "message_type": "agent", "content": REPLY}
    base.update(kw)
    return base


def test_a_new_agent_row_is_a_reply() -> None:
    assert _is_new_agent_reply(_msg(), set(), SENT)


def test_an_error_row_is_not_a_reply() -> None:
    """THE ONE THAT MATTERED MOST.

    routes/agent.py sets `is_agent = True` for message_type "system" AND "error"
    deliberately, so the agent does not re-observe its own notifications. The
    first version of this assertion keyed on `is_agent`, so the error text
    emitted when processing FAILED counted as proof that it had succeeded — the
    gate going green precisely when the product broke.
    """
    assert not _is_new_agent_reply(_msg(message_type="error"), set(), SENT)


def test_a_system_notification_is_not_a_reply() -> None:
    assert not _is_new_agent_reply(_msg(message_type="system"), set(), SENT)


def test_a_row_from_an_earlier_interaction_is_not_a_reply() -> None:
    """Without a pre-send baseline, "an agent row exists" is trivially true.

    Any prior conversation in the same channel satisfies it, so the gate would
    pass on a send that produced nothing at all.
    """
    assert not _is_new_agent_reply(_msg(id="m-old"), {"m-old"}, SENT)


def test_our_own_echo_is_not_a_reply() -> None:
    assert not _is_new_agent_reply(_msg(content=SENT), set(), SENT)


@pytest.mark.parametrize("content", ["", "   ", None])
def test_an_empty_row_is_not_a_reply(content) -> None:
    assert not _is_new_agent_reply(_msg(content=content), set(), SENT)


def test_a_user_row_is_not_a_reply() -> None:
    assert not _is_new_agent_reply(_msg(message_type="user", content="something else"), set(), SENT)


def test_the_predicate_does_not_key_on_is_agent() -> None:
    """Pin the distinction itself, not just its consequences.

    An error row carries is_agent=True and message_type="error". If someone
    later "simplifies" this back to `is_agent`, this row starts passing and the
    hole reopens silently — so assert the exact shape that would reopen it.
    """
    error_row = _msg(message_type="error", content="I encountered an issue processing your request.")
    error_row["is_agent"] = True
    assert not _is_new_agent_reply(error_row, set(), SENT)
