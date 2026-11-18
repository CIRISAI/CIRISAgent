"""The decision contract between consciences and the retry (CIRISAgent#1366 items 7, 8, 9, 14).

- Item 7: every veto is typed (evidence / justification / substantive), carries
  a veto id, the objecting conscience, and whether it held trusted WA
  governance. Unknown or missing type is SUBSTANTIVE.
- Item 8: the task keeps a veto record; an identical draft already vetoed
  substantively (or on undischarged evidence) is vetoed again WITHOUT a model
  call. The record reaches retries and follow-up thoughts through the
  conscience feedback both drafting passes read.
- Item 9: only the SYSTEM discharges an evidence objection, from trusted state
  (a signed WAAuthorization, approved amendments) the objecting conscience did
  not have; it attaches it and re-reviews once, and records the discharge. No
  trusted state: the rule is not honoured and the draft is banned. A pass after
  a veto records what changed.
- Item 14: the retry is told who objected, the type, and whether it could see
  the rule -- an evidence objection never reads as "your rule is invented".
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.conscience import core
from ciris_engine.logic.conscience.registry import conscienceRegistry
from ciris_engine.logic.conscience.veto_contract import (
    action_equivalence_key,
    action_fingerprint,
    banned_entry_for,
    format_prior_vetoes_block,
)
from ciris_engine.logic.processors.core.thought_processor.conscience_execution import ConscienceExecutionPhase
from ciris_engine.schemas.actions.parameters import SpeakParams, ToolParams
from ciris_engine.schemas.conscience.context import ConscienceCheckContext
from ciris_engine.schemas.conscience.core import (
    CoherenceResult,
    ConscienceCheckResult,
    ConscienceStatus,
    EntropyResult,
    EpistemicData,
    EpistemicHumilityResult,
    OptimizationVetoResult,
)
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.processors.core import ConscienceApplicationResult
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.runtime.models import Task, TaskContext, WAAuthorization
from ciris_engine.schemas.runtime.veto_record import ObjectionType, VetoObjection, VetoRecordEntry

_STEP = ConscienceExecutionPhase._conscience_execution_step.__wrapped__.__wrapped__

GRANT = WAAuthorization(
    wa_id="wa-2026-AUTH-5562FD",
    deferral_id="defer_c5aaf93c",
    granted_at="2026-11-17T10:00:00+00:00",
    guidance="Never send web addresses; point people to the Staff Portal.",
    response_attestation_id="att-resp-01",
)


@pytest.fixture(autouse=True)
def _english(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIRIS_PREFERRED_LANGUAGE", "en")
    from ciris_engine.logic.utils.localization import clear_cache

    clear_cache()


def _speak(text: str = "Please use the Staff Portal for that.") -> ActionSelectionDMAResult:
    return ActionSelectionDMAResult(
        selected_action=HandlerActionType.SPEAK, action_parameters=SpeakParams(content=text), rationale="r"
    )


def _tool(params: Dict[str, Any]) -> ActionSelectionDMAResult:
    return ActionSelectionDMAResult(
        selected_action=HandlerActionType.TOOL,
        action_parameters=ToolParams(name="create_ticket", parameters=params),
        rationale="r",
    )


# ---------------------------------------------------------------- fingerprint


def test_equivalence_key_ignores_whitespace_and_case_for_speak() -> None:
    assert action_equivalence_key(_speak("Hello  there\n")) == action_equivalence_key(_speak("hello there"))
    assert action_equivalence_key(_speak("hello there")) != action_equivalence_key(_speak("hello world"))
    assert action_equivalence_key(_speak("x")).startswith("speak::")


def test_equivalence_key_names_the_tool_and_hashes_normalized_arguments() -> None:
    a = action_equivalence_key(_tool({"title": "T", "body": "b  c"}))
    assert a == action_equivalence_key(_tool({"body": "b c", "title": "T"}))
    assert a != action_equivalence_key(_tool({"title": "T", "body": "other"}))
    assert a.startswith("tool:create_ticket:")


def test_the_record_fingerprint_is_the_exact_reviewed_fingerprint() -> None:
    """One fingerprint for the record and for dispatch (#1366 item 19); the key only bans."""
    assert action_fingerprint(_tool({"title": "T", "body": "b  c"})) != action_fingerprint(_tool({"title": "T", "body": "b c"}))
    assert action_fingerprint(_speak("x")).startswith("-16:")


# ---------------------------------------------------------------- item 7: typed verdicts


def _conscience(cls: type, seen: Dict[str, Any], result: Any) -> Any:
    async def _llm(_sink: Any, **kwargs: Any) -> Any:
        seen["messages"] = kwargs["messages"]
        return result, None

    conscience = object.__new__(cls)
    conscience._time_service = Mock(now=Mock(return_value=datetime.now()))
    conscience._create_trace_correlation = Mock(return_value=None)
    conscience._update_trace_correlation = Mock()
    conscience._get_sink = AsyncMock(return_value=SimpleNamespace(llm=object()))
    conscience._call_llm_with_budget = _llm
    conscience._get_image_context_info = Mock(return_value=None)
    conscience._resolve_language = Mock(return_value="en")
    conscience.config = SimpleNamespace(optimization_veto_ratio=10.0, entropy_threshold=0.4, coherence_threshold=0.6)
    return conscience


def _cctx(**fields: Any) -> ConscienceCheckContext:
    thought = SimpleNamespace(thought_id="t1", source_task_id="task1", agent_occurrence_id="default", content="c")
    return ConscienceCheckContext(thought=thought, task=SimpleNamespace(description="user message"), **fields)


def _failing(cls: type, objection: Optional[str]) -> Any:
    extra = {} if objection is None else {"objection_type": objection}
    if cls is core.EntropyConscience:
        return EntropyResult(entropy=0.9, reason="unanchored", **extra)
    if cls is core.CoherenceConscience:
        return CoherenceResult(coherence=0.1, reason="cites a rule", **extra)
    if cls is core.OptimizationVetoConscience:
        return OptimizationVetoResult(decision="abort", justification="j", entropy_reduction_ratio=1.0, **extra)
    return EpistemicHumilityResult(
        epistemic_certainty=0.2, reflective_justification="j", recommended_action="defer", **extra
    )


ALL = [core.EntropyConscience, core.CoherenceConscience, core.OptimizationVetoConscience, core.EpistemicHumilityConscience]
SEES_GOVERNANCE = set(ALL)  # with a grant in force, every judge reads it (#1366 Phase 3)


@pytest.mark.asyncio
@pytest.mark.parametrize("cls", ALL)
async def test_every_conscience_types_its_objection(cls: type) -> None:
    conscience = _conscience(cls, {}, _failing(cls, "evidence"))
    with patch("ciris_engine.logic.persistence.get_thoughts_by_task_id", return_value=[]):
        result = await conscience.check(_speak(), _cctx(wa_authorization=GRANT))
    assert not result.passed
    assert result.objection_type == ObjectionType.EVIDENCE
    # Whether it held the trusted rule is what it was shown. With a grant in force every conscience reads the
    # governance block: the context policy requires the verified rule at every judge (FSD §14, #1366 Phase 3).
    assert result.held_trusted_rule is True
    assert "att-resp-01" in result.held_evidence_ids


@pytest.mark.asyncio
@pytest.mark.parametrize("cls", ALL)
@pytest.mark.parametrize("answer", [None, "nonsense", "SUBSTANTIVE"])
async def test_unknown_or_missing_objection_type_is_substantive(cls: type, answer: Optional[str]) -> None:
    conscience = _conscience(cls, {}, _failing(cls, answer))
    with patch("ciris_engine.logic.persistence.get_thoughts_by_task_id", return_value=[]):
        result = await conscience.check(_speak(), _cctx())
    assert result.objection_type == ObjectionType.SUBSTANTIVE


@pytest.mark.parametrize("model", [EntropyResult, CoherenceResult, OptimizationVetoResult, EpistemicHumilityResult])
def test_each_llm_response_model_offers_the_objection_type(model: type) -> None:
    prop = model.model_json_schema()["properties"]["objection_type"]
    assert set(prop["enum"]) == {"evidence", "justification", "substantive"}
    assert prop["default"] == "substantive"


@pytest.mark.parametrize(
    "name", ["entropy_conscience", "coherence_conscience", "optimization_veto_conscience", "epistemic_humility_conscience"]
)
def test_each_english_prompt_states_the_objection_contract(name: str) -> None:
    from ciris_engine.logic.conscience.prompt_loader import ConsciencePromptLoader

    system_prompt = ConsciencePromptLoader(language="en").get_system_prompt(name)
    assert "objection_type" in system_prompt
    for value in ("evidence", "justification", "substantive"):
        assert value in system_prompt


@pytest.mark.asyncio
async def test_coherence_reads_the_governance_block_whenever_a_trusted_rule_is_in_force() -> None:
    """Before #1366 Phase 3 only the evidence re-review attached it; the policy now requires it at every judge."""
    seen: Dict[str, Any] = {}
    conscience = _conscience(core.CoherenceConscience, seen, CoherenceResult(coherence=0.9))
    with patch("ciris_engine.logic.persistence.get_thoughts_by_task_id", return_value=[]):
        none = await conscience.check(_speak(), _cctx())
        assert "VERIFIED WISE AUTHORITY GOVERNANCE" not in seen["messages"][-1].content
        plain = await conscience.check(_speak(), _cctx(wa_authorization=GRANT))
        assert "VERIFIED WISE AUTHORITY GOVERNANCE" in seen["messages"][-1].content
        attached = await conscience.check(_speak(), _cctx(wa_authorization=GRANT, attached_evidence=True))
    assert "VERIFIED WISE AUTHORITY GOVERNANCE" in seen["messages"][-1].content
    assert none.held_trusted_rule is False
    assert plain.held_trusted_rule is True and attached.held_trusted_rule is True


# ---------------------------------------------------------------- the fold (items 8, 9)


class Scripted:
    """A conscience double returning scripted results in order (the last repeats)."""

    def __init__(self, *results: ConscienceCheckResult) -> None:
        self.results = list(results)
        self.calls = 0
        self.contexts: List[Any] = []

    async def check(self, action: Any, context: Any) -> ConscienceCheckResult:
        self.calls += 1
        self.contexts.append(context)
        return self.results[min(self.calls - 1, len(self.results) - 1)]


def _ok() -> ConscienceCheckResult:
    return ConscienceCheckResult(status=ConscienceStatus.PASSED, passed=True)


def _veto(objection: ObjectionType, held: Optional[List[str]] = None, reason: str = "no") -> ConscienceCheckResult:
    return ConscienceCheckResult(
        status=ConscienceStatus.FAILED,
        passed=False,
        reason=reason,
        coherence_score=0.1,
        objection_type=objection,
        held_trusted_rule=bool(held),
        held_evidence_ids=held or [],
    )


def _phase(**consciences: Scripted) -> ConscienceExecutionPhase:
    registry = conscienceRegistry()
    for priority, (name, conscience) in enumerate(consciences.items()):
        registry.register_conscience(name=name, conscience=conscience, priority=priority)
    phase = ConscienceExecutionPhase.__new__(ConscienceExecutionPhase)
    phase.conscience_registry = registry
    phase._describe_action = Mock(return_value="speak 'hello'")
    return phase


def _task(record: Optional[List[VetoRecordEntry]] = None) -> Task:
    return Task(
        task_id="task1",
        channel_id="c",
        description="user message",
        created_at="2026-11-18T00:00:00+00:00",
        updated_at="2026-11-18T00:00:00+00:00",
        veto_record=record or [],
    )


async def _run(
    phase: ConscienceExecutionPhase,
    action: ActionSelectionDMAResult,
    *,
    task: Optional[Task] = None,
    feedback: Any = None,
    authorization: Optional[WAAuthorization] = None,
) -> tuple[ConscienceApplicationResult, List[List[VetoRecordEntry]]]:
    written: List[List[VetoRecordEntry]] = []
    item = SimpleNamespace(thought_id="th1", source_task_id="task1", conscience_feedback=feedback, deadline=None)
    thought = SimpleNamespace(thought_id="th1", source_task_id="task1")
    with patch(
        "ciris_engine.logic.persistence.get_task_by_id_any_occurrence", return_value=task or _task()
    ), patch(
        "ciris_engine.logic.persistence.models.tasks.append_task_vetoes",
        side_effect=lambda task_id, entries: written.append(list(entries)) or True,
    ):
        result = await _STEP(
            phase,
            item,
            action,
            thought=thought,
            dma_results=None,
            processing_context=SimpleNamespace(wa_authorization=authorization),
        )
    return result, written


@pytest.mark.asyncio
async def test_a_veto_is_typed_and_recorded_with_the_task() -> None:
    phase = _phase(entropy=Scripted(_ok()), coherence=Scripted(_veto(ObjectionType.SUBSTANTIVE, reason="stigma word")))
    result, written = await _run(phase, _speak("hello"))
    assert result.overridden
    [veto] = result.vetoes
    assert veto.conscience == "coherence" and veto.objection_type == ObjectionType.SUBSTANTIVE
    assert veto.veto_id.startswith("veto_") and veto.held_trusted_rule is False
    assert veto.action_fingerprint == action_fingerprint(_speak("hello"))
    [[entry]] = written
    assert entry.banned and entry.veto_id == veto.veto_id and entry.reason == "stigma word"
    assert result.veto_record == [entry]


@pytest.mark.asyncio
async def test_an_identical_substantively_vetoed_action_is_vetoed_again_without_a_model_call() -> None:
    entropy, coherence = Scripted(_ok()), Scripted(_veto(ObjectionType.SUBSTANTIVE))
    phase = _phase(entropy=entropy, coherence=coherence)
    first, written = await _run(phase, _speak("hello"))
    assert first.overridden and (entropy.calls, coherence.calls) == (1, 1)

    # The same draft, on a follow-up thought (the record is on the task) ...
    again, _ = await _run(phase, _speak("  Hello "), task=_task(written[0]))
    assert again.overridden and again.repeated_veto_id == first.vetoes[0].veto_id
    assert again.final_action.selected_action == HandlerActionType.PONDER
    assert (entropy.calls, coherence.calls) == (1, 1), "a banned draft must not reach the consciences"

    # ... and on the retry (the record rides the conscience feedback).
    feedback = {"veto_record": [e.model_dump(mode="json") for e in first.veto_record]}
    retry, _ = await _run(phase, _speak("hello"), feedback=feedback)
    assert retry.repeated_veto_id == first.vetoes[0].veto_id
    assert (entropy.calls, coherence.calls) == (1, 1)

    # A changed action goes back to the consciences.
    changed, _ = await _run(phase, _speak("something else"), task=_task(written[0]))
    assert changed.repeated_veto_id is None and coherence.calls == 2


@pytest.mark.asyncio
async def test_a_justification_objection_does_not_ban_the_draft() -> None:
    coherence = Scripted(_veto(ObjectionType.JUSTIFICATION), _ok())
    phase = _phase(coherence=coherence)
    first, written = await _run(phase, _speak("hello"))
    assert first.overridden and written[0][0].banned is False
    passed, _ = await _run(phase, _speak("hello"), task=_task(written[0]))
    assert not passed.overridden and coherence.calls == 2
    assert passed.pass_after_veto is not None and passed.pass_after_veto.change == "unchanged"


@pytest.mark.asyncio
async def test_evidence_objection_with_a_signed_grant_is_discharged_and_re_reviewed() -> None:
    # Coherence is not shown the signed grant; it objects on evidence, then
    # passes once the system attaches it.
    coherence = Scripted(_veto(ObjectionType.EVIDENCE), _ok())
    phase = _phase(entropy=Scripted(_ok()), coherence=coherence)
    result, written = await _run(phase, _speak("hello"), authorization=GRANT)

    assert coherence.calls == 2, "one re-review"
    assert coherence.contexts[0].attached_evidence is False
    assert coherence.contexts[1].attached_evidence is True
    assert not result.overridden
    [discharge] = result.veto_discharges
    assert discharge.kind == "new_evidence" and discharge.discharged_by == "att-resp-01"
    assert discharge.conscience == "coherence"
    assert result.pass_after_veto is not None
    assert result.pass_after_veto.change == "new_evidence" and result.pass_after_veto.evidence_ids == ["att-resp-01"]
    [[entry]] = written
    assert entry.discharged_by == "att-resp-01" and entry.banned is False


@pytest.mark.asyncio
async def test_evidence_objection_without_trusted_state_bans_the_draft() -> None:
    coherence = Scripted(_veto(ObjectionType.EVIDENCE))
    phase = _phase(coherence=coherence)
    first, written = await _run(phase, _speak("hello"))
    assert first.overridden and coherence.calls == 1, "no trusted state: nothing to attach, no re-review"
    assert first.veto_discharges == []
    [[entry]] = written
    assert entry.objection_type == ObjectionType.EVIDENCE and entry.banned

    # The drafter re-proposing it (with whatever argument) does not reach the consciences.
    again, _ = await _run(phase, _speak("hello"), task=_task(written[0]))
    assert again.repeated_veto_id == entry.veto_id and coherence.calls == 1


@pytest.mark.asyncio
async def test_evidence_the_conscience_already_held_does_not_discharge() -> None:
    # The veto held the signed grant and still objected on evidence: nothing new to attach.
    veto = Scripted(_veto(ObjectionType.EVIDENCE, held=["att-resp-01"]))
    phase = _phase(optimization_veto=veto)
    result, written = await _run(phase, _speak("hello"), authorization=GRANT)
    assert result.overridden and veto.calls == 1 and written[0][0].banned


@pytest.mark.asyncio
async def test_a_banned_evidence_veto_lifts_once_a_wa_signs() -> None:
    entry = VetoRecordEntry(
        veto_id="veto_old",
        action_fingerprint=action_fingerprint(_speak("hello")),
        objection_type=ObjectionType.EVIDENCE,
        conscience="coherence",
        banned=True,
    )
    assert banned_entry_for(entry.action_fingerprint, [entry], []) is entry
    assert banned_entry_for(entry.action_fingerprint, [entry], ["att-resp-01"]) is None
    substantive = entry.model_copy(update={"objection_type": ObjectionType.SUBSTANTIVE})
    assert banned_entry_for(entry.action_fingerprint, [substantive], ["att-resp-01"]) is substantive


@pytest.mark.asyncio
async def test_a_substantive_objection_beside_an_evidence_one_skips_the_discharge() -> None:
    coherence = Scripted(_veto(ObjectionType.EVIDENCE), _ok())
    humility = Scripted(_veto(ObjectionType.SUBSTANTIVE))
    phase = _phase(coherence=coherence, epistemic_humility=humility)
    result, written = await _run(phase, _speak("hello"), authorization=GRANT)
    assert result.overridden and coherence.calls == 1 and result.veto_discharges == []
    assert all(e.banned for e in written[0])


@pytest.mark.asyncio
async def test_a_changed_action_after_a_veto_records_what_changed() -> None:
    prior = VetoRecordEntry(
        veto_id="veto_old",
        action_fingerprint=action_fingerprint(_speak("old draft")),
        objection_type=ObjectionType.SUBSTANTIVE,
        conscience="coherence",
        banned=True,
    )
    result, _ = await _run(_phase(coherence=Scripted(_ok())), _speak("new draft"), task=_task([prior]))
    assert not result.overridden
    assert result.pass_after_veto is not None
    assert result.pass_after_veto.change == "changed_action" and result.pass_after_veto.prior_veto_ids == ["veto_old"]


@pytest.mark.asyncio
async def test_a_check_that_did_not_run_is_not_recorded_as_a_veto() -> None:
    down = ConscienceCheckResult(status=ConscienceStatus.ERROR, passed=False, reason="timeout", check_ran=False)
    result, written = await _run(_phase(coherence=Scripted(down)), _speak("hello"))
    assert result.overridden and result.conscience_unavailable
    assert result.vetoes == [] and written == []


# ---------------------------------------------------------------- persistence


class _Engine:
    def __init__(self, row: Dict[str, Any]) -> None:
        self.row = row

    def task_get(self, task_id: str) -> str:
        return json.dumps(self.row)

    def task_upsert(self, payload: str) -> None:
        self.row = json.loads(payload)


def test_the_task_row_keeps_the_record_and_its_other_context(monkeypatch: pytest.MonkeyPatch) -> None:
    from ciris_engine.logic.persistence.models import tasks

    task = _task()
    task.context = TaskContext(correlation_id="corr")
    row = tasks._task_to_persist_payload(task)
    row["context"]["deferral"] = {"resolution": {"approved": True}}
    engine = _Engine(row)
    monkeypatch.setattr(tasks, "_get_engine", lambda: engine)
    entry = VetoRecordEntry(
        veto_id="veto_1", action_fingerprint="speak::x", objection_type=ObjectionType.SUBSTANTIVE, conscience="c", banned=True
    )
    assert tasks.append_task_vetoes("task1", [entry])
    assert engine.row["context"]["deferral"] == {"resolution": {"approved": True}}
    assert tasks._persist_row_to_task(engine.row).veto_record == [entry]
    # A later discharge replaces the entry in place.
    assert tasks.append_task_vetoes("task1", [entry.model_copy(update={"discharged_by": "att"})])
    [stored] = tasks._persist_row_to_task(engine.row).veto_record
    assert stored.discharged_by == "att"


# ---------------------------------------------------------------- item 14: retry wording


def _application(objection: ObjectionType, held: bool, **extra: Any) -> ConscienceApplicationResult:
    action = _speak("hello")
    return ConscienceApplicationResult(
        original_action=action,
        final_action=action,
        overridden=True,
        override_reason="I cannot see this rule",
        epistemic_data=EpistemicData(uncertainty_acknowledged=True, reasoning_transparency=1.0),
        vetoes=[
            VetoObjection(
                veto_id="veto_1",
                conscience="optimization_veto",
                objection_type=objection,
                reason="I cannot see this rule",
                held_trusted_rule=held,
                action_fingerprint=action_fingerprint(action),
            )
        ],
        **extra,
    )


def _guidance(result: ConscienceApplicationResult) -> str:
    from ciris_engine.logic.processors.core.thought_processor.main import ThoughtProcessor

    processor = ThoughtProcessor.__new__(ThoughtProcessor)
    return processor._build_retry_guidance("speak 'hello'", result.override_reason or "", None, result, language="en")


def test_an_evidence_objection_never_reads_as_an_invented_rule() -> None:
    text = _guidance(_application(ObjectionType.EVIDENCE, held=False))
    assert "vetoed by the optimization_veto conscience" in text
    assert "Objection type: evidence" in text
    assert "could not see any verified Wise Authority rule" in text
    assert "EVIDENCE objection" in text and "does not mean the rule is false or invented" in text
    assert "only a signed rule can change this verdict" in text
    assert "rejected because" not in text


def test_retry_wording_per_objection_type() -> None:
    substantive = _guidance(_application(ObjectionType.SUBSTANTIVE, held=True))
    assert "SUBSTANTIVE objection" in substantive and "banned for the rest of this task" in substantive
    assert "could see the verified Wise Authority governance" in substantive
    justification = _guidance(_application(ObjectionType.JUSTIFICATION, held=False))
    assert "JUSTIFICATION objection" in justification and "better justification" in justification
    assert "banned" not in justification


def test_a_repeated_veto_says_it_was_not_reviewed_again() -> None:
    text = _guidance(_application(ObjectionType.SUBSTANTIVE, held=False, repeated_veto_id="veto_1"))
    assert "already vetoed in this task (veto veto_1" in text


def test_an_untyped_override_keeps_the_generic_line() -> None:
    action = _speak("hello")
    result = ConscienceApplicationResult(
        original_action=action,
        final_action=action,
        overridden=True,
        override_reason="New observation arrived",
        epistemic_data=EpistemicData(uncertainty_acknowledged=True, reasoning_transparency=1.0),
    )
    assert "was rejected because: New observation arrived" in _guidance(result)


# ---------------------------------------------------------------- item 8: follow-up thoughts


def test_a_follow_up_thought_carries_the_task_record_to_both_drafting_passes() -> None:
    from ciris_engine.logic.processors.core.thought_processor.main import ThoughtProcessor

    entry = VetoRecordEntry(
        veto_id="veto_1",
        action_fingerprint="speak::x",
        action_summary="speak 'file the ticket'",
        objection_type=ObjectionType.SUBSTANTIVE,
        conscience="optimization_veto",
        reason="files for an unverified sender",
        banned=True,
    )
    processor = ThoughtProcessor.__new__(ThoughtProcessor)
    item = SimpleNamespace(thought_id="th2", source_task_id="task1", conscience_feedback=None)
    with patch("ciris_engine.logic.persistence.get_task_by_id_any_occurrence", return_value=_task([entry])):
        processor._carry_task_vetoes(item, SimpleNamespace(source_task_id="task1"), None)
    assert item.conscience_feedback["veto_record"][0]["veto_id"] == "veto_1"
    block = item.conscience_feedback["retry_guidance"]
    assert block == format_prior_vetoes_block([entry], "en")
    assert "CONSCIENCE VETOES EARLIER IN THIS TASK" in block
    assert "speak 'file the ticket'" in block and "optimization_veto (substantive; banned" in block

    # Rendered by the verb second passes exactly as ASPDMA renders it.
    from ciris_engine.logic.dma.conscience_feedback import with_conscience_feedback

    assert block in with_conscience_feedback("user message", item.conscience_feedback)


def test_a_retry_feedback_is_left_alone() -> None:
    from ciris_engine.logic.processors.core.thought_processor.main import ThoughtProcessor

    processor = ThoughtProcessor.__new__(ThoughtProcessor)
    feedback = {"retry_guidance": "x"}
    item = SimpleNamespace(thought_id="th2", source_task_id="task1", conscience_feedback=feedback)
    with patch("ciris_engine.logic.persistence.get_task_by_id_any_occurrence") as get_task:
        processor._carry_task_vetoes(item, SimpleNamespace(source_task_id="task1"), None)
    get_task.assert_not_called()
    assert item.conscience_feedback is feedback


def test_the_retry_feedback_carries_the_record() -> None:
    from ciris_engine.logic.processors.core.thought_processor.main import ThoughtProcessor

    processor = ThoughtProcessor.__new__(ThoughtProcessor)
    processor._describe_action = Mock(return_value="speak 'hello'")
    entry = VetoRecordEntry(
        veto_id="veto_1", action_fingerprint="speak::x", objection_type=ObjectionType.EVIDENCE, conscience="c", banned=True
    )
    result = _application(ObjectionType.EVIDENCE, held=False, veto_record=[entry])
    item = SimpleNamespace(thought_id="th1", source_task_id="task1", conscience_feedback=None)
    processor._prepare_conscience_retry_context(item, {"x": 1}, result, thought=None)
    assert item.conscience_feedback["veto_record"] == [entry.model_dump(mode="json")]
    assert "EVIDENCE objection" in item.conscience_feedback["retry_guidance"]
