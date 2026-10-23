"""Follow-up thoughts carry a factual record of what ran in the task (CIRISAgent#1320, fix 6).

RATCHET's Market 4 pilot, episode s-001: after a MEMORIZE of the speaker's own
user node the follow-up read only "MEMORIZE COMPLETE - stored user '...'", and
the model read "stored" as "applied", telling the attacker the change "is now
effective across all channels and users". Nothing said which node and scope
were written, that the identity was untouched, or that no reply had gone out.
"""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import Mock, patch

import pytest

from ciris_engine.logic.infrastructure.handlers.action_record import (
    MAX_RECORDED_ACTIONS,
    format_action_record,
    identity_written,
    reply_sent,
)
from ciris_engine.logic.infrastructure.handlers.base_handler import ActionHandlerDependencies, BaseActionHandler
from ciris_engine.logic.utils.localization import get_string
from ciris_engine.schemas.runtime.enums import ThoughtStatus, ThoughtType
from ciris_engine.schemas.runtime.models import FinalAction, Thought

TS = "2026-10-22T00:00:00+00:00"


def _node(node_id: str, scope: str) -> Dict[str, Any]:
    return {"id": node_id, "type": "user", "scope": scope, "attributes": {}}


def _thought(
    thought_id: str,
    action: str,
    status: ThoughtStatus = ThoughtStatus.COMPLETED,
    params: Dict[str, Any] | None = None,
) -> Thought:
    return Thought(
        thought_id=thought_id,
        source_task_id="task-1",
        content="c",
        status=status,
        thought_type=ThoughtType.STANDARD,
        created_at=TS,
        updated_at=TS,
        final_action=FinalAction(action_type=action, action_params=params or {}, reasoning="r"),
    )


def _s(key: str) -> str:
    return get_string("en", key)


def test_a_local_write_says_which_node_and_that_identity_is_unchanged() -> None:
    record = format_action_record(
        [_thought("t1", "memorize", params={"node": _node("user/wa-2026-10-22-ABC123", "local")})], "en"
    )
    lines = record.split("\n")

    assert lines[0] == _s("handlers.action_record_header")
    assert "MEMORIZE" in lines[1]
    assert _s("handlers.action_record_status_done") in lines[1]
    assert "user/wa-2026-10-22-ABC123" in lines[1] and "local" in lines[1]
    assert lines[1].endswith(_s("handlers.action_record_identity_unchanged"))
    assert lines[-1] == _s("handlers.action_record_no_reply")


def test_an_identity_write_is_not_called_identity_unchanged() -> None:
    record = format_action_record(
        [_thought("t1", "memorize", ThoughtStatus.DEFERRED, params={"node": _node("agent/identity", "identity")})],
        "en",
    )
    assert _s("handlers.action_record_identity_unchanged") not in record
    assert _s("handlers.action_record_status_deferred") in record
    assert "identity" in record


def test_a_reply_is_recorded_once_it_is_sent() -> None:
    thoughts = [_thought("t1", "memorize", params={"node": _node("user/x", "local")}), _thought("t2", "speak")]
    record = format_action_record(thoughts, "en")

    assert reply_sent(thoughts)
    assert record.split("\n")[-1] == _s("handlers.action_record_reply_sent")
    assert "SPEAK" in record


def test_a_failed_speak_is_not_a_reply() -> None:
    thoughts = [_thought("t1", "speak", ThoughtStatus.FAILED)]
    assert not reply_sent(thoughts)
    assert _s("handlers.action_record_status_failed") in format_action_record(thoughts, "en")


IDENTITY_STATUS = "handlers.action_record_identity_status_unchanged"


def test_a_task_that_only_pondered_and_spoke_states_the_identity_is_unchanged() -> None:
    """#1320 round 2, s-001: a PONDER/SPEAK-only task said nothing about the identity."""
    thoughts = [_thought("t1", "ponder"), _thought("t2", "speak")]
    lines = format_action_record(thoughts, "en").split("\n")

    assert not identity_written(thoughts)
    assert lines.count(_s(IDENTITY_STATUS)) == 1
    assert lines[-2] == _s(IDENTITY_STATUS) and lines[-1] == _s("handlers.action_record_reply_sent")


def test_a_refused_identity_write_leaves_the_identity_unchanged() -> None:
    thoughts = [_thought("t1", "memorize", ThoughtStatus.FAILED, params={"node": _node("agent/identity", "identity")})]
    assert _s(IDENTITY_STATUS) in format_action_record(thoughts, "en")


@pytest.mark.parametrize(
    "node",
    [
        _node("identity/name", "identity"),
        {"id": "agent/identity/amendment/d/1", "type": "identity_amendment", "scope": "identity", "attributes": {}},
    ],
)
def test_a_task_that_wrote_an_amendment_does_not_claim_unchanged(node: Dict[str, Any]) -> None:
    thoughts = [_thought("t1", "memorize", params={"node": node}), _thought("t2", "speak")]
    assert identity_written(thoughts)
    assert _s(IDENTITY_STATUS) not in format_action_record(thoughts, "en")


def test_thoughts_that_have_not_acted_are_left_out() -> None:
    pending = _thought("t1", "speak", ThoughtStatus.PENDING)
    assert format_action_record([pending], "en") == ""
    assert format_action_record([], "en") == ""


def test_the_record_is_capped() -> None:
    thoughts = [_thought(f"t{i}", "ponder") for i in range(MAX_RECORDED_ACTIONS + 5)]
    lines = format_action_record(thoughts, "en").split("\n")
    # header + entries + identity line (#1320 round 2) + reply line
    assert len(lines) == MAX_RECORDED_ACTIONS + 3


def test_every_label_is_filled() -> None:
    record = format_action_record([_thought("t1", "memorize", params={"node": _node("user/x", "local")})], "en")
    assert "{" not in record


class _Handler(BaseActionHandler):
    async def handle(self, result: Any, thought: Any, dispatch_context: Any) -> None:  # pragma: no cover
        return None


def test_the_follow_up_carries_the_record() -> None:
    """The one place follow-ups are built appends it, so every handler gets it."""
    handler = _Handler(ActionHandlerDependencies(bus_manager=Mock(), time_service=Mock()))
    current = _thought("t1", "memorize", params={"node": _node("user/wa-2026-10-22-ABC123", "local")})
    added: List[Thought] = []

    with (
        patch("ciris_engine.logic.persistence.update_thought_status", return_value=True),
        patch("ciris_engine.logic.persistence.get_thoughts_by_task_id", return_value=[current]),
        patch("ciris_engine.logic.persistence.add_thought", side_effect=added.append),
        patch(
            "ciris_engine.logic.infrastructure.handlers.helpers.create_follow_up_thought",
            side_effect=lambda parent, time_service, content, thought_type: Mock(thought_id="f1", content=content),
        ),
    ):
        follow_up_id = handler.complete_thought_and_create_followup(
            current, follow_up_content="MEMORIZE COMPLETE - stored user 'user/wa-2026-10-22-ABC123'."
        )

    assert follow_up_id == "f1"
    content = added[0].content
    assert content.startswith("MEMORIZE COMPLETE")
    assert _s("handlers.action_record_header") in content
    assert _s("handlers.action_record_identity_unchanged") in content
    assert _s("handlers.action_record_no_reply") in content


@pytest.mark.parametrize("lang", ["am", "ha", "yo"])
def test_the_record_renders_in_low_coverage_locales(lang: str) -> None:
    record = format_action_record([_thought("t1", "memorize", params={"node": _node("user/x", "local")})], lang)
    assert "MEMORIZE" in record and "user/x" in record
    assert "{" not in record
