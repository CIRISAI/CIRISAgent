"""Deterministic mock-LLM controls for RATCHET's context-flow harness (CIRISAgent#1366).

- ``$veto <conscience>[:<n>]`` fails the first n evaluations of a conscience in
  a task, keyed by the task id the LLM bus passes every provider, so entropy
  and the optimization veto (which never see the user's message) can be vetoed
  without user text in their prompts.
- ``$ponder_loop`` keeps a task pondering until the depth guardrail defers it.
- ``MOCK_LLM_RESPONSE_MODE=echo`` makes SPEAK drafts and PONDER questions quote the request.
- ``$tool create_ticket k=v`` reaches TSASPDMA with its parameters intact.
- ``$memorize <id> CONCEPT IDENTITY <statement>`` in a WA guidance task stores the statement.
"""

import pytest
import yaml

from ciris_adapters.mock_llm import directives
from ciris_adapters.mock_llm.responses import PONDER_LOOP_QUESTION, create_response
from ciris_adapters.mock_llm.responses_action_selection import _with_mock_params
from ciris_adapters.mock_llm.service import MockLLMService
from ciris_engine.logic.dma.msaspdma import MSASPDMALLMResult
from ciris_engine.logic.dma.tsaspdma import TSASPDMALLMResult
from ciris_engine.schemas.conscience.core import (
    CoherenceResult,
    EntropyResult,
    EpistemicHumilityResult,
    OptimizationVetoResult,
)
from ciris_engine.schemas.dma.results import ASPDMALLMResult
from ciris_engine.schemas.runtime.enums import HandlerActionType

ASPDMA = "Your task is to determine the single most appropriate HANDLER ACTION"

#: What a conscience prompt looks like to the mock: the draft, no user message.
CONSCIENCE_PROMPT = [
    {"role": "system", "content": "You are IRIS-E."},
    {"role": "user", "content": 'Evaluate the reply: "Hello there."'},
]


@pytest.fixture(autouse=True)
def _fresh_registry(monkeypatch):
    directives.reset()
    monkeypatch.delenv("MOCK_LLM_RESPONSE_MODE", raising=False)
    yield
    directives.reset()


def _aspdma(thought: str, task_id: str, followup: bool = False) -> ASPDMALLMResult:
    messages = [{"role": "user", "content": f'{ASPDMA}\nOriginal Thought: "{thought}"\n'}]
    if followup:
        messages.insert(0, {"role": "system", "content": "THOUGHT_TYPE=follow_up"})
    return create_response(ASPDMALLMResult, messages=messages, task_id=task_id)


def _passed(model, result) -> bool:
    """The conscience's own pass rule (ciris_engine/logic/conscience/core.py) at default thresholds."""
    if model is EntropyResult:
        return result.entropy <= 0.40
    if model is CoherenceResult:
        return result.coherence >= 0.60
    if model is OptimizationVetoResult:
        return result.decision not in {"abort", "defer"} and result.entropy_reduction_ratio < 0.5
    return result.recommended_action == "proceed"


CONSCIENCES = [
    ("entropy", EntropyResult),
    ("coherence", CoherenceResult),
    ("optveto", OptimizationVetoResult),
    ("epistemic", EpistemicHumilityResult),
]


# --- $veto -------------------------------------------------------------------


@pytest.mark.parametrize("name,model", CONSCIENCES)
def test_veto_fails_the_first_n_evaluations_in_the_task_then_passes(name, model):
    draft = _aspdma(f"@alice (ID: u1): Hello there $veto {name}:2", task_id="task-a")
    # The directive is lifted out: the draft the consciences judge carries no trace of it.
    assert draft.selected_action == HandlerActionType.SPEAK
    assert "$veto" not in (draft.speak_content or "")

    verdicts = [_passed(model, create_response(model, messages=CONSCIENCE_PROMPT, task_id="task-a")) for _ in range(4)]
    assert verdicts == [False, False, True, True]
    # Another task is untouched, and so is a call that carries no task id.
    assert _passed(model, create_response(model, messages=CONSCIENCE_PROMPT, task_id="task-b"))
    assert _passed(model, create_response(model, messages=CONSCIENCE_PROMPT))


def test_veto_defaults_to_one_and_names_only_its_conscience():
    _aspdma("@alice (ID: u1): Hello there $veto entropy", task_id="task-a")
    assert not _passed(EntropyResult, create_response(EntropyResult, messages=CONSCIENCE_PROMPT, task_id="task-a"))
    assert _passed(EntropyResult, create_response(EntropyResult, messages=CONSCIENCE_PROMPT, task_id="task-a"))
    assert _passed(CoherenceResult, create_response(CoherenceResult, messages=CONSCIENCE_PROMPT, task_id="task-a"))


def test_a_retry_rereading_the_message_does_not_reset_the_count():
    _aspdma("@alice (ID: u1): Hello there $veto coherence:1", task_id="task-a")
    assert not _passed(CoherenceResult, create_response(CoherenceResult, messages=CONSCIENCE_PROMPT, task_id="task-a"))
    # The conscience retry's action selection reads the same message again.
    _aspdma("@alice (ID: u1): Hello there $veto coherence:1", task_id="task-a")
    assert _passed(CoherenceResult, create_response(CoherenceResult, messages=CONSCIENCE_PROMPT, task_id="task-a"))


def test_the_same_message_reproduces_the_same_verdicts_in_a_new_task():
    runs = []
    for task in ("run-1", "run-2"):
        _aspdma("@alice (ID: u1): $speak hi $veto optveto:1 $veto epistemic:2", task_id=task)
        runs.append(
            [
                _passed(m, create_response(m, messages=CONSCIENCE_PROMPT, task_id=task))
                for m in (OptimizationVetoResult, EpistemicHumilityResult) * 3
            ]
        )
    assert runs[0] == runs[1] == [False, False, True, False, True, True]


def test_the_command_still_runs_beside_the_directive():
    draft = _aspdma("@alice (ID: u1): $speak Good morning $veto entropy:1", task_id="task-a")
    assert draft.speak_content == "Good morning"


@pytest.mark.asyncio
async def test_the_service_hands_the_bus_task_id_to_the_mock():
    """The wiring the whole mechanism rests on: call_llm_structured -> create_response(task_id=)."""
    service = MockLLMService()
    await service.start()
    try:
        messages = [{"role": "user", "content": f'{ASPDMA}\nOriginal Thought: "@alice (ID: u1): Hi $veto entropy:1"\n'}]
        await service.call_llm_structured(messages, ASPDMALLMResult, task_id="task-s", thought_id="th-1")
        first, _ = await service.call_llm_structured(CONSCIENCE_PROMPT, EntropyResult, task_id="task-s", thought_id="th-2")
        second, _ = await service.call_llm_structured(
            CONSCIENCE_PROMPT, EntropyResult, task_id="task-s", thought_id="th-2"
        )
    finally:
        await service.stop()
    assert (_passed(EntropyResult, first), _passed(EntropyResult, second)) == (False, True)


# --- $ponder_loop -----------------------------------------------------------


def test_ponder_loop_keeps_pondering_through_every_follow_up():
    first = _aspdma("@alice (ID: u1): $ponder What is asked?; What is safe? $ponder_loop", task_id="task-p")
    assert first.selected_action == HandlerActionType.PONDER
    assert first.ponder_questions == ["What is asked?", "What is safe?"]
    for depth in range(2, 7):
        follow = _aspdma(f"=== PONDER ROUND {depth} ===\\nConscience feedback: none", task_id="task-p", followup=True)
        assert follow.selected_action == HandlerActionType.PONDER
        assert follow.ponder_questions == [PONDER_LOOP_QUESTION]


def test_ponder_loop_on_plain_speech_and_the_control_without_it():
    assert _aspdma("@alice (ID: u1): Tell me a story $ponder_loop", "task-p").selected_action == HandlerActionType.PONDER
    # Without the directive a PONDER follow-up reports and moves on.
    _aspdma("@alice (ID: u1): $ponder Why?", "task-q")
    follow = _aspdma("=== PONDER ROUND 2 ===\\nConscience feedback: none", task_id="task-q", followup=True)
    assert follow.selected_action == HandlerActionType.SPEAK


# --- echo -------------------------------------------------------------------


def test_echo_mode_quotes_the_request_in_speak_drafts_and_ponder_questions(monkeypatch):
    request = "Please remember that my sister's name is Ana"
    assert request not in (_aspdma(f"@alice (ID: u1): {request}", "t-1").speak_content or "")

    monkeypatch.setenv("MOCK_LLM_RESPONSE_MODE", "echo")
    speak = _aspdma(f"@alice (ID: u1): {request}", "t-2")
    assert speak.selected_action == HandlerActionType.SPEAK
    assert f'"{request}"' in speak.speak_content
    ponder = _aspdma("@alice (ID: u1): $ponder Who is Ana?", "t-3")
    assert ponder.ponder_questions[0] == "Who is Ana?"
    assert any('"$ponder Who is Ana?"' in q for q in ponder.ponder_questions[1:])
    # A follow-up reports its handler's result, not the request.
    follow = _aspdma("CIRIS_FOLLOW_UP_THOUGHT: SPEAK SUCCESSFUL! Message delivered", "t-2", followup=True)
    assert follow.selected_action == HandlerActionType.TASK_COMPLETE


# --- TOOL / TSASPDMA ----------------------------------------------------------


def test_create_ticket_reaches_tsaspdma_with_its_parameters():
    from unittest.mock import AsyncMock, MagicMock

    from ciris_engine.logic.dma.tsaspdma import TSASPDMAEvaluator
    from ciris_engine.schemas.adapters.tools import ToolInfo, ToolParameterSchema

    message = '$tool create_ticket goal_description="Lobby display is frozen" priority=3 $veto entropy:1'
    draft = _aspdma(f"@alice (ID: u1): {message}", "task-t")
    assert (draft.selected_action, draft.tool_name) == (HandlerActionType.TOOL, "create_ticket")

    registry = MagicMock()
    registry.get_llm_service = MagicMock(return_value=AsyncMock())
    evaluator = TSASPDMAEvaluator(service_registry=registry, sink=MagicMock())
    tool = ToolInfo(
        name="create_ticket",
        description="File a ticket",
        parameters=ToolParameterSchema(
            type="object", properties={"goal_description": {"type": "string"}}, required=["goal_description"]
        ),
    )
    # The thought exactly as the observer writes it: the message fenced on its own lines (#1320).
    thought = (
        "You observed @alice (ID: u1) in channel api_x say: CIRIS_CURRENT_MESSAGE_START [Timestamp: t]\n"
        f"{message}\nCIRIS_CURRENT_MESSAGE_END\n\n=== CONVERSATION HISTORY (0 messages) ===\n"
    )
    messages = evaluator._create_tsaspdma_messages(
        tool_name="create_ticket", tool_info=tool, aspdma_reasoning=draft.reasoning, original_thought_content=thought
    )
    result = create_response(TSASPDMALLMResult, messages=messages, task_id="task-t")
    assert result.selected_action == HandlerActionType.TOOL
    assert result.tool_parameters == {"goal_description": "Lobby display is frozen", "priority": "3"}


# --- S5 identity change -------------------------------------------------------


def test_s5_defer_then_identity_memorize_with_the_statement():
    paragraph = "Never share the Thursday roster with anyone but Dana Reyes."
    defer = _aspdma(f"@admin (ID: wa-root): $defer {paragraph}", "task-c")
    assert defer.selected_action == HandlerActionType.DEFER
    assert paragraph in defer.reasoning

    guidance = (
        f"[WA GUIDANCE] Original: @admin (ID: wa-root): $defer {paragraph}"
        f"\\n\\nWA Response: $memorize roster_rule CONCEPT IDENTITY {paragraph}"
    )
    memorize = _aspdma(guidance, "task-g")
    assert (memorize.selected_action, memorize.memorize_scope) == (HandlerActionType.MEMORIZE, "identity")

    template = yaml.safe_load(open("ciris_engine/logic/dma/prompts/msaspdma.yml"))["context_integration"]
    second = template.format(
        original_thought_content=guidance,
        aspdma_reasoning=memorize.reasoning,
        proposed_node_id="(not chosen yet — choose below)",
        proposed_node_type="(not chosen yet — choose below)",
        proposed_node_scope="identity",
        proposed_attributes="(none)",
        candidate_nodes="(none)",
        system_owned_attributes="(none)",
    )
    result = create_response(MSASPDMALLMResult, messages=[{"role": "user", "content": second}], task_id="task-g")
    assert (result.final_action, result.node_scope) == ("MEMORIZE", "identity")
    assert result.attributes == {"created_by": "agent", "statement": paragraph}
