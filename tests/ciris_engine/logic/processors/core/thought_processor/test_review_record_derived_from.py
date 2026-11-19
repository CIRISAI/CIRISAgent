"""A passed review record declares what its arguments derive from (rc21 §4 ``derived_from``).

The wire record carries the KINDS of untrusted input (``request``); the node-local entry carries their digests,
which the dispatch gate reads for ``effect_untrusted_unacknowledged``.
"""

import hashlib
from types import SimpleNamespace

from ciris_engine.logic.infrastructure.authorization.reviewed_action import (
    reset_admitted_records,
    review_record_digest,
    review_record_wire,
)
from ciris_engine.logic.processors.core.thought_processor.conscience_execution import ConscienceExecutionPhase
from ciris_engine.schemas.conscience.core import EpistemicData
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.actions.parameters import ToolParams
from ciris_engine.schemas.processors.core import ConscienceApplicationResult
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.runtime.reviewed_action_admission import REQUIRED_REVIEW_FACULTIES

REQUEST = "Please file a ticket titled 'printer'."


def _result() -> ConscienceApplicationResult:
    action = ActionSelectionDMAResult(
        selected_action=HandlerActionType.TOOL,
        action_parameters=ToolParams(name="file_ticket", parameters={"title": "printer"}, channel_id="ch-1"),
        rationale="r",
    )
    result = ConscienceApplicationResult(
        original_action=action,
        final_action=action,
        overridden=False,
        epistemic_data=EpistemicData(uncertainty_acknowledged=True, reasoning_transparency=1.0),
        reviewed_fingerprint="-16:" + "ab" * 32,
    )
    result.review_passes = sorted(REQUIRED_REVIEW_FACULTIES)
    return result


def _build(context: object) -> ConscienceApplicationResult:
    reset_admitted_records()
    result = _result()
    thought = SimpleNamespace(thought_id="th-derived-1", source_task_id="task-derived-1")
    ConscienceExecutionPhase._build_review_records(result, thought, context, [], [])
    return result


def test_the_passed_record_declares_the_request_kind_and_the_entry_its_digest() -> None:
    result = _build(SimpleNamespace(task=SimpleNamespace(description=REQUEST)))
    entry = result.review_candidate
    assert entry is not None
    assert entry.record.derived_from == ("request",)
    assert entry.derived_from == ("request:sha256:" + hashlib.sha256(REQUEST.encode()).hexdigest(),)
    assert review_record_wire(entry.record)["derived_from"] == ["request"]
    assert entry.digest == review_record_digest(entry.record)  # the declared kinds are inside the digest


def test_no_readable_request_declares_nothing_and_dispatch_will_refuse() -> None:
    entry = _build(SimpleNamespace(task=None)).review_candidate
    assert entry is not None
    assert entry.record.derived_from == () and entry.derived_from == ()
    assert "derived_from" not in review_record_wire(entry.record)
