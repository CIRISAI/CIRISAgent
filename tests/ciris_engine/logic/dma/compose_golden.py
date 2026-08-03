"""Deterministic fixtures + capture harness for compose_messages golden-bytes tests (#972).

Protocol
--------
1. BEFORE the #972 seam extraction, this module was executed as a script
   (``python -m tests.ciris_engine.logic.dma.compose_golden``) against the
   unmodified tree. It drives each DMA's ``evaluate()`` path with fully
   deterministic fixture inputs, intercepts ``call_llm_structured`` to record
   the composed ``messages`` list (no LLM is ever called), and snapshots the
   result to ``golden/<dma>_messages.json``.
2. AFTER the extraction, ``test_compose_messages_golden.py`` replays the same
   fixtures through (a) the ``evaluate()`` path and (b) the new
   ``compose_messages()`` seams directly, asserting byte equality against the
   pre-refactor snapshots.

Determinism
-----------
- All fixture ids/timestamps are fixed constants.
- ``CIRIS_PREFERRED_LANGUAGE`` is pinned to ``en``.
- The disk-loaded prompt *content* helpers (accord / localized accord /
  language guidance / prohibition guidance) are patched to short sentinel
  strings so the snapshots stay small and machine-independent. The patches are
  applied identically at capture time and replay time, so byte equality still
  proves the composition logic (block ordering, interpolation, concatenation)
  is unchanged. Sentinels are NON-EMPTY so the optional append branches are
  exercised.
- Persistence access (``fetch_original_task``, ASPDMA context pre-caching) is
  replaced with fixed fixtures - that is data *gathering*, not composition.
"""

from __future__ import annotations

import json
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple
from unittest.mock import AsyncMock, Mock, patch

from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem, ThoughtContent
from ciris_engine.schemas.actions.parameters import DeferParams, PonderParams, SpeakParams
from ciris_engine.schemas.dma.faculty import EnhancedDMAInputs
from ciris_engine.schemas.dma.results import (
    ActionSelectionDMAResult,
    ASPDMALLMResult,
    CSDMAResult,
    DSDMAResult,
    EthicalDMAResult,
    IDMAResult,
)
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtStatus, ThoughtType
from ciris_engine.schemas.runtime.models import Task, Thought, ThoughtContext
from ciris_engine.schemas.runtime.system_context import SystemSnapshot
from ciris_engine.schemas.types import JSONDict

GOLDEN_DIR = Path(__file__).parent / "golden"

DMA_NAMES = ("pdma", "csdma", "idma", "dsdma", "aspdma", "dsaspdma")

#: The conscience-faculty steps (#986). Each composes the three-message list the
#: conscience hands to ``call_llm_structured``; the four YAMLs behind them are
#: the whole ``conscience_prompt`` override namespace (4 files x 3 text fields =
#: 12 keys), which no composition the dump drove could previously reach.
CONSCIENCE_STEP_NAMES = (
    "entropy_conscience",
    "coherence_conscience",
    "optimization_veto_conscience",
    "epistemic_humility_conscience",
)

#: The same four faculties composed WITH image context. ``get_user_prompt``
#: switches to a different overridable template when the evaluated thought
#: carried images (``user_prompt_with_image_template``), so these four steps are
#: what makes the other half of the ``conscience_prompt`` namespace reachable —
#: without them a manifest could replace all four image templates and no block
#: would move.
CONSCIENCE_IMAGE_STEP_NAMES = tuple(f"{name}_image" for name in CONSCIENCE_STEP_NAMES)

#: The conscience-override RETRY compositions (#986). A thought that trips a
#: conscience re-composes ASPDMA with a retry envelope built from the
#: ``conscience.*`` localization strings — a SECOND composition per thought that
#: the dump previously never saw. The two variants are the two mutually
#: exclusive branches of ``_build_retry_guidance``: with a new observation
#: (``retry_observation_intro``/``_outro``) and without it
#: (``retry_general_outro``). One step cannot render both.
RETRY_STEP_NAMES = ("aspdma_retry", "aspdma_retry_observation", "aspdma_ponder_notes")

#: The DMA-bounce compositions (#986) — the other recursion in the pipeline.
#: When a DMA self-rates below threshold the orchestrator re-runs it with a
#: localized bounce preamble prepended to the thought, and forwards a difficulty
#: advisory to ASPDMA if the bounce exhausted. Both are extra compositions per
#: thought built from `prompts.dma.bounce_*` strings.
BOUNCE_STEP_NAMES = ("csdma_bounce", "aspdma_bounce_advisory")

#: Every composition step the fixtures can drive. The #972 golden snapshots
#: cover ``DMA_NAMES`` (the six extraction sites) and are byte-frozen; TSASPDMA
#: already had seams pre-#972 so it has no pre/post golden pair. The retry and
#: conscience steps are #986 additions — the dump iterates the full set, the
#: goldens deliberately do not.
STEP_NAMES = (
    DMA_NAMES
    + ("tsaspdma", "tsaspdma_correction")
    + RETRY_STEP_NAMES
    + BOUNCE_STEP_NAMES
    + CONSCIENCE_STEP_NAMES
    + CONSCIENCE_IMAGE_STEP_NAMES
)

_FIXED_TS = "2026-01-01T00:00:00+00:00"
_THOUGHT_TEXT = "Should the agent reply with a summary of the weather report?"

#: Deterministic AgentTemplate fixture — see the file's own header for why the
#: `template` namespace can only be reached through a parsed YAML.
GOLDEN_TEMPLATE_PATH = Path(__file__).parent / "golden_template.yaml"

# --- Conscience-step fixture constants -------------------------------------
# The conscience builders interpolate plain strings. Production derives them
# from the action and the task (`_render_action_text`, `_extract_user_message`);
# here they are pinned constants, the same treatment every other dynamic slot
# gets in this fixture [I-2]. In particular production builds the EOV/EH
# description as f"{action.selected_action} {action.action_parameters}", which
# embeds a pydantic repr — pinning it keeps the dump byte-stable across
# unrelated schema edits.
_CONSCIENCE_ACTION_TEXT = "Golden fixture: the weather today is mild and clear."
_CONSCIENCE_ACTION_DESCRIPTION = "HandlerActionType.SPEAK content='Golden fixture response.'"
_CONSCIENCE_USER_MESSAGE = "Golden fixture: what is the weather like?"

# --- Retry-step fixture constants ------------------------------------------
_RETRY_ATTEMPTED_ACTION = "SPEAK"
_RETRY_NEW_OBSERVATION = "Golden fixture: the user has since asked about tomorrow instead."

#: Stands in for `_get_image_context_info`'s return value. Only truthiness
#: matters to the loader's template choice; the text is a fixture constant.
_CONSCIENCE_IMAGE_CONTEXT = "Golden fixture: the message included 1 image."


# ---------------------------------------------------------------------------
# Deterministic environment (identical at capture time and replay time)
# ---------------------------------------------------------------------------


def _sentinel_accord(mode: str = "default") -> str:
    return f"<GOLDEN-ACCORD mode={mode}>"


def _sentinel_localized_accord(lang: Any = None) -> str:
    return f"<GOLDEN-LOCALIZED-ACCORD lang={lang}>"


def _sentinel_language_guidance(lang_code: str) -> str:
    return f"<GOLDEN-LANGUAGE-GUIDANCE lang={lang_code}>"


def _sentinel_prohibition_guidance(lang_code: str) -> str:
    return f"<GOLDEN-PROHIBITION-GUIDANCE lang={lang_code}>"


@contextmanager
def prompt_content_environment(
    *,
    language: str = "en",
    accord: Callable[..., str],
    localized_accord: Callable[..., str],
    language_guidance: Callable[[str], str],
    prohibition_guidance: Callable[[str], str],
    user_message: Callable[..., str] | None = None,
    conscience_system_prompt: Callable[..., str] | None = None,
    conscience_user_prompt: Callable[..., str] | None = None,
) -> Iterator[None]:
    """Pin language + prompt-content loaders for byte-reproducible composition.

    Parameterized (#973) so the same patch set serves two callers:
    - the #972 golden harness passes short sentinel callables
      (:func:`deterministic_prompt_environment`), and
    - the #973 compose dump passes recording PASS-THROUGH wrappers around the
      real loaders, so block identification never guesses at positions.

    Patch targets cover every import style used by the DMAs:
    - lazy in-function imports resolve from the defining module at call time;
    - module-top ``from x import y`` imports need the per-module name patched.
    """
    with ExitStack() as stack:
        stack.enter_context(patch.dict("os.environ", {"CIRIS_PREFERRED_LANGUAGE": language}))
        # Source modules (covers all lazy in-function imports).
        stack.enter_context(patch("ciris_engine.logic.utils.constants.get_accord_text", accord))
        stack.enter_context(
            patch("ciris_engine.logic.utils.constants.get_localized_accord_text", localized_accord)
        )
        stack.enter_context(
            patch("ciris_engine.logic.utils.localization.get_language_guidance", language_guidance)
        )
        stack.enter_context(
            patch("ciris_engine.logic.utils.localization.get_prohibition_guidance", prohibition_guidance)
        )
        # Module-top imported names.
        stack.enter_context(patch("ciris_engine.logic.dma.idma.get_accord_text", accord))
        stack.enter_context(
            patch("ciris_engine.logic.dma.action_selection_pdma.get_localized_accord_text", localized_accord)
        )
        stack.enter_context(
            patch("ciris_engine.logic.dma.dsaspdma.get_localized_accord_text", localized_accord)
        )
        stack.enter_context(
            patch("ciris_engine.logic.dma.tsaspdma.get_localized_accord_text", localized_accord)
        )
        # Optional (#974): a recording pass-through around the loader's
        # user-message render seam, so the #973 dump can identify user
        # messages whose bytes are wholly the render of a routed
        # `context_integration` template. The #972 golden environment does
        # NOT pass this — the goldens exercise the unpatched render path.
        if user_message is not None:
            stack.enter_context(
                patch("ciris_engine.logic.dma.prompt_loader.DMAPromptLoader.get_user_message", user_message)
            )
        # Optional (#986): the conscience render seams, so the dump can source
        # a conscience block to the exact `conscience_prompt` key that produced
        # it. Same contract as `user_message` — the #972 goldens do not pass
        # these and so exercise the unpatched loader.
        if conscience_system_prompt is not None:
            stack.enter_context(
                patch(
                    "ciris_engine.logic.conscience.prompt_loader.ConsciencePromptLoader.get_system_prompt",
                    conscience_system_prompt,
                )
            )
        if conscience_user_prompt is not None:
            stack.enter_context(
                patch(
                    "ciris_engine.logic.conscience.prompt_loader.ConsciencePromptLoader.get_user_prompt",
                    conscience_user_prompt,
                )
            )
        yield


@contextmanager
def deterministic_prompt_environment() -> Iterator[None]:
    """The #972 golden environment: language pinned to en, loaders to sentinels."""
    with prompt_content_environment(
        language="en",
        accord=_sentinel_accord,
        localized_accord=_sentinel_localized_accord,
        language_guidance=_sentinel_language_guidance,
        prohibition_guidance=_sentinel_prohibition_guidance,
    ):
        yield


# ---------------------------------------------------------------------------
# Fixed fixtures
# ---------------------------------------------------------------------------


def make_task() -> Task:
    return Task(
        task_id="golden-task-001",
        channel_id="golden-channel",
        description="Summarize today's weather report for the user",
        created_at=_FIXED_TS,
        updated_at=_FIXED_TS,
    )


def make_system_snapshot() -> SystemSnapshot:
    return SystemSnapshot(
        agent_identity={
            "agent_id": "golden_agent",
            "description": "Deterministic golden-fixture agent",
            "role": "Test fixture for compose_messages golden tests",
        },
        channel_id="golden-channel",
        agent_version="0.0.0-golden",
        system_counts={"total_tasks": 1, "total_thoughts": 1, "pending_tasks": 0, "pending_thoughts": 0},
    )


def make_context() -> SimpleNamespace:
    """Context object with a ``system_snapshot`` attribute (PDMA/CSDMA/IDMA)."""
    return SimpleNamespace(system_snapshot=make_system_snapshot())


def make_queue_item() -> ProcessingQueueItem:
    return ProcessingQueueItem(
        thought_id="golden-thought-001",
        source_task_id="golden-task-001",
        thought_type=ThoughtType.STANDARD,
        content=ThoughtContent(text=_THOUGHT_TEXT, metadata={}),
        thought_depth=1,
    )


def make_dsdma_queue_item() -> ProcessingQueueItem:
    """DSDMA (no DMAInputData path) reads identity from ``initial_context``."""
    return ProcessingQueueItem(
        thought_id="golden-thought-001",
        source_task_id="golden-task-001",
        thought_type=ThoughtType.STANDARD,
        content=ThoughtContent(text=_THOUGHT_TEXT, metadata={}),
        thought_depth=1,
        initial_context={"system_snapshot": make_system_snapshot().model_dump()},
    )


def make_thought() -> Thought:
    return Thought(
        thought_id="golden-thought-001",
        source_task_id="golden-task-001",
        content=_THOUGHT_TEXT,
        status=ThoughtStatus.PROCESSING,
        thought_type=ThoughtType.STANDARD,
        thought_depth=1,
        created_at=_FIXED_TS,
        updated_at=_FIXED_TS,
        context=ThoughtContext(task_id="golden-task-001", round_number=1, depth=1, correlation_id="golden-corr"),
    )


def make_ethical_result() -> EthicalDMAResult:
    return EthicalDMAResult(
        action=HandlerActionType.SPEAK,
        rationale="Golden fixture: replying is ethically unproblematic.",
        weight_alignment_score=0.8,
        ethical_alignment_score=0.9,
    )


def make_csdma_result() -> CSDMAResult:
    return CSDMAResult(plausibility_score=0.9, flags=["golden_flag"], reasoning="Golden fixture: plausible.")


def make_dsdma_result() -> DSDMAResult:
    return DSDMAResult(
        domain="golden_domain", domain_alignment=0.8, flags=[], reasoning="Golden fixture: aligned with domain."
    )


def make_enhanced_inputs() -> EnhancedDMAInputs:
    return EnhancedDMAInputs(
        original_thought=make_thought(),
        processing_context={"system_snapshot": make_system_snapshot().model_dump()},
        ethical_pdma_result=make_ethical_result(),
        csdma_result=make_csdma_result(),
        dsdma_result=make_dsdma_result(),
        permitted_actions=[
            HandlerActionType.OBSERVE,
            HandlerActionType.SPEAK,
            HandlerActionType.PONDER,
            HandlerActionType.DEFER,
            HandlerActionType.TASK_COMPLETE,
        ],
    )


def make_defer_aspdma_result() -> ActionSelectionDMAResult:
    return ActionSelectionDMAResult(
        selected_action=HandlerActionType.DEFER,
        action_parameters=DeferParams(
            reason="Golden fixture: needs wise-authority input",
            context={"stakes": "high", "topics": ["weather", "safety"]},
        ),
        rationale="Golden fixture: deferring for classification.",
    )


def pin_aspdma_context_builder(dma: Any) -> None:
    """Pin ASPDMA's context-builder cached state (data gathering, not composition)."""
    dma.context_builder.pre_cache_context = AsyncMock(return_value=0)
    dma.context_builder._tools_cached = True
    dma.context_builder._cached_task = None
    dma.context_builder._cached_installable_tools = ""


# ---------------------------------------------------------------------------
# Capture via evaluate() (works identically before and after the extraction)
# ---------------------------------------------------------------------------


def _recording_llm(captured: Dict[str, Any], result: Any) -> AsyncMock:
    async def _record(**kwargs: Any) -> Tuple[Any, Any]:
        captured["messages"] = kwargs["messages"]
        return (result, None)

    return AsyncMock(side_effect=_record)


async def capture_pdma() -> List[JSONDict]:
    from ciris_engine.logic.dma.pdma import EthicalPDMAEvaluator

    dma = EthicalPDMAEvaluator(service_registry=Mock())
    dma.fetch_original_task = AsyncMock(return_value=make_task())  # type: ignore[method-assign]
    captured: Dict[str, Any] = {}
    dma.call_llm_structured = _recording_llm(captured, make_ethical_result())  # type: ignore[method-assign]
    await dma.evaluate(make_queue_item(), make_context())
    return captured["messages"]  # type: ignore[no-any-return]


async def capture_csdma() -> List[JSONDict]:
    from ciris_engine.logic.dma.csdma import CSDMAEvaluator

    dma = CSDMAEvaluator(service_registry=Mock())
    dma.fetch_original_task = AsyncMock(return_value=make_task())  # type: ignore[method-assign]
    captured: Dict[str, Any] = {}
    dma.call_llm_structured = _recording_llm(captured, make_csdma_result())  # type: ignore[method-assign]
    await dma.evaluate(make_queue_item(), make_context())
    return captured["messages"]  # type: ignore[no-any-return]


async def capture_idma() -> List[JSONDict]:
    from ciris_engine.logic.dma.idma import IDMAEvaluator

    dma = IDMAEvaluator(service_registry=Mock())
    dma.fetch_original_task = AsyncMock(return_value=make_task())  # type: ignore[method-assign]
    captured: Dict[str, Any] = {}
    dma.call_llm_structured = _recording_llm(  # type: ignore[method-assign]
        captured,
        IDMAResult(
            k_eff=3.0,
            correlation_risk=0.2,
            phase="healthy",
            fragility_flag=False,
            reasoning="Golden fixture: diverse sources.",
        ),
    )
    await dma.evaluate(
        make_queue_item(),
        make_context(),
        ethical_result=make_ethical_result(),
        csdma_result=make_csdma_result(),
        dsdma_result=make_dsdma_result(),
    )
    return captured["messages"]  # type: ignore[no-any-return]


async def capture_dsdma() -> List[JSONDict]:
    from ciris_engine.logic.dma.dsdma_base import BaseDSDMA

    dma = BaseDSDMA(
        domain_name="golden_domain",
        service_registry=Mock(),
        domain_specific_knowledge={
            "rules_summary": "Golden rules: always be deterministic.",
            "escalation_paths": ["wise_authority", "human_operator"],
        },
    )
    dma.fetch_original_task = AsyncMock(return_value=make_task())  # type: ignore[method-assign]
    captured: Dict[str, Any] = {}
    dma.call_llm_structured = _recording_llm(captured, make_dsdma_result())  # type: ignore[method-assign]
    await dma.evaluate(make_dsdma_queue_item())
    return captured["messages"]  # type: ignore[no-any-return]


async def capture_aspdma() -> List[JSONDict]:
    from ciris_engine.logic.dma.action_selection_pdma import ActionSelectionPDMAEvaluator

    registry = Mock()
    registry.get_services_by_type.return_value = []
    dma = ActionSelectionPDMAEvaluator(service_registry=registry)
    pin_aspdma_context_builder(dma)
    captured: Dict[str, Any] = {}
    dma.call_llm_structured = _recording_llm(  # type: ignore[method-assign]
        captured,
        ASPDMALLMResult(
            selected_action=HandlerActionType.SPEAK,
            reasoning="Golden fixture: speak.",
            speak_content="Golden fixture response.",
        ),
    )
    await dma.evaluate(make_enhanced_inputs())
    return captured["messages"]  # type: ignore[no-any-return]


async def capture_dsaspdma() -> List[JSONDict]:
    from ciris_engine.logic.dma.dsaspdma import DSASPDMAEvaluator, DSASPDMALLMResult
    from ciris_engine.schemas.services.deferral_taxonomy import DeferralNeedCategory, DeferralOperationalReason

    dma = DSASPDMAEvaluator(service_registry=Mock())
    captured: Dict[str, Any] = {}
    dma.call_llm_structured = _recording_llm(  # type: ignore[method-assign]
        captured,
        DSASPDMALLMResult(
            reason_summary="Golden fixture deferral",
            operational_reason=list(DeferralOperationalReason)[0],
            primary_need_category=list(DeferralNeedCategory)[0],
        ),
    )
    await dma.evaluate(make_defer_aspdma_result(), make_queue_item(), context=None)
    return captured["messages"]  # type: ignore[no-any-return]


def make_tool_info() -> Any:
    """Deterministic ToolInfo fixture for the TSASPDMA steps (#973)."""
    from ciris_engine.schemas.adapters.tools import ToolInfo, ToolParameterSchema

    return ToolInfo(
        name="golden_tool",
        description="Deterministic golden fixture tool",
        parameters=ToolParameterSchema(
            type="object",
            properties={"target": {"type": "string", "description": "Golden target"}},
            required=["target"],
        ),
        when_to_use="Golden fixture only",
    )


async def capture_tsaspdma() -> List[JSONDict]:
    """Drive TSASPDMA's pre-existing seam (`_create_tsaspdma_messages`) via evaluate_tool_action."""
    from ciris_engine.logic.dma.tsaspdma import TSASPDMAEvaluator, TSASPDMALLMResult

    dma = TSASPDMAEvaluator(service_registry=Mock())
    captured: Dict[str, Any] = {}
    dma.call_llm_structured = _recording_llm(  # type: ignore[method-assign]
        captured,
        TSASPDMALLMResult(
            selected_action=HandlerActionType.PONDER,
            reasoning="Golden fixture: reconsider.",
            ponder_questions=["Golden fixture question?"],
        ),
    )
    await dma.evaluate_tool_action(
        tool_name="golden_tool",
        tool_info=make_tool_info(),
        aspdma_reasoning="Golden fixture: tool selected.",
        original_thought=make_queue_item(),
        context=None,
    )
    return captured["messages"]  # type: ignore[no-any-return]


async def capture_tsaspdma_correction() -> List[JSONDict]:
    """Drive TSASPDMA's correction-mode seam (`_create_correction_mode_messages`)."""
    from ciris_engine.logic.dma.tsaspdma import TSASPDMAEvaluator, TSASPDMALLMResult

    dma = TSASPDMAEvaluator(service_registry=Mock())
    captured: Dict[str, Any] = {}
    dma.call_llm_structured = _recording_llm(  # type: ignore[method-assign]
        captured,
        TSASPDMALLMResult(
            selected_action=HandlerActionType.PONDER,
            reasoning="Golden fixture: reconsider.",
            ponder_questions=["Golden fixture question?"],
        ),
    )
    await dma.evaluate_tool_correction(
        requested_tool_name="missing_tool",
        available_tools=[make_tool_info()],
        aspdma_reasoning="Golden fixture: tool selected.",
        original_thought=make_queue_item(),
        context=None,
    )
    return captured["messages"]  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# #986 step 1: the template-carrying identity (the `template` namespace)
# ---------------------------------------------------------------------------


async def load_golden_template() -> Any:
    """Load the fixture AgentTemplate through the real production loader.

    ``profile_loader.load_template`` is where ``apply_template_overrides`` runs,
    so this — and not a hand-built AgentTemplate — is what puts the ``template``
    override namespace on the composed path.
    """
    from ciris_engine.logic.utils.profile_loader import load_template

    return await load_template(GOLDEN_TEMPLATE_PATH)


def make_templated_system_snapshot(template: Any) -> SystemSnapshot:
    """A snapshot whose identity prose comes from the loaded template.

    This reproduces the production hop faithfully, INCLUDING its rename: the
    template's ``role_description`` is seeded into the identity graph and read
    back out as ``role`` (``system_snapshot_helpers.py`` builds
    ``IdentityData(role=attrs["role_description"])``). The DMA identity
    formatter reads ``agent_id``/``description``/``role`` and nothing else, so
    those are the only three keys that matter here.

    Honest scope: in the live runtime the template->graph seeding happens on
    FIRST RUN ONLY (``identity_manager``: an existing identity node ignores the
    template entirely). A ``template.description``/``role_description`` override
    therefore moves prompt bytes against a fresh identity graph, which is what
    this fixture models.
    """
    return SystemSnapshot(
        agent_identity={
            "agent_id": template.name,
            "description": template.description,
            "role": template.role_description,
        },
        channel_id="golden-channel",
        agent_version="0.0.0-golden",
        system_counts={"total_tasks": 1, "total_thoughts": 1, "pending_tasks": 0, "pending_thoughts": 0},
    )


# ---------------------------------------------------------------------------
# #986 step 2: the conscience-override retry envelope (the `conscience.*` strings)
# ---------------------------------------------------------------------------


def make_conscience_application_result() -> Any:
    """A synthetic conscience override, shaped to render EVERY shard label.

    ``_build_structured_shard_detail`` only emits a shard's localized label when
    that shard's evidence list is non-empty, so each of the three evidence
    fields below is populated on purpose: an empty one silently drops the key it
    gates and the dump would under-report coverage.

    ``override_reason`` is not a literal — it is the REAL
    ``_repeated_speak_guidance()`` output, which is how production fills it
    (``ConscienceCheckResult.reason`` -> ``override_reason``). That is what puts
    ``conscience.repeated_speak_guidance`` inside the composed retry envelope.
    """
    from ciris_engine.logic.conscience.action_sequence_conscience import _repeated_speak_guidance
    from ciris_engine.schemas.conscience.core import (
        CoherenceCheckResult,
        EntropyCheckResult,
        EpistemicData,
        EpistemicHumilityResult,
        OptimizationVetoResult,
    )
    from ciris_engine.schemas.processors.core import ConscienceApplicationResult

    original = ActionSelectionDMAResult(
        selected_action=HandlerActionType.SPEAK,
        action_parameters=SpeakParams(content="Golden fixture response."),
        rationale="Golden fixture: speak.",
    )
    final = ActionSelectionDMAResult(
        selected_action=HandlerActionType.PONDER,
        action_parameters=PonderParams(questions=["Golden fixture: what did the conscience object to?"]),
        rationale="Golden fixture: conscience override.",
    )
    return ConscienceApplicationResult(
        original_action=original,
        final_action=final,
        overridden=True,
        override_reason=_repeated_speak_guidance(),
        epistemic_data=EpistemicData.create_neutral(),
        entropy_check=EntropyCheckResult(
            passed=False,
            entropy_score=0.7,
            threshold=0.4,
            message="Golden fixture: entropy above threshold.",
            alternative_meanings=[
                "Golden fixture alternative one.",
                "Golden fixture alternative two.",
                "Golden fixture alternative three.",
            ],
        ),
        coherence_check=CoherenceCheckResult(
            passed=True, coherence_score=0.8, threshold=0.6, message="Golden fixture: coherent."
        ),
        optimization_veto_check=OptimizationVetoResult(
            decision="proceed",
            justification="Golden fixture: no protected dimension is traded away.",
            entropy_reduction_ratio=1.0,
        ),
        epistemic_humility_check=EpistemicHumilityResult(
            epistemic_certainty=0.6,
            identified_uncertainties=[
                "Golden fixture uncertainty one.",
                "Golden fixture uncertainty two.",
            ],
            reflective_justification="Golden fixture: some uncertainty remains.",
            recommended_action="ponder",
        ),
    )


def build_retry_guidance(*, updated_observation: Optional[str]) -> str:
    """Render the retry envelope through the REAL production builder.

    ``ThoughtProcessor._build_retry_guidance`` is a pure string builder — it
    reads no services — so it is driven here on an uninitialized instance
    rather than by standing up a processor. The fixture composes the envelope;
    it does not reimplement it, which is the whole point (a reimplementation
    would gate a copy of the text instead of the text).
    """
    from ciris_engine.logic.processors.core.thought_processor.main import ThoughtProcessor
    from ciris_engine.logic.utils.localization import get_preferred_language

    processor = ThoughtProcessor.__new__(ThoughtProcessor)
    return processor._build_retry_guidance(
        _RETRY_ATTEMPTED_ACTION,
        make_conscience_application_result().override_reason or "",
        updated_observation,
        make_conscience_application_result(),
        language=get_preferred_language(),
    )


async def _capture_aspdma_retry(*, updated_observation: Optional[str]) -> List[JSONDict]:
    """ASPDMA re-composed the way a conscience override re-composes it.

    Two things reach the prompt here that the first-pass ``aspdma`` step cannot:
    the retry envelope (via ``conscience_feedback['retry_guidance']``, read by
    ``ActionSelectionContextBuilder._build_conscience_guidance`` and rendered
    into the ``{conscience_guidance}`` slot), and the template-derived identity
    block in the system message.
    """
    from ciris_engine.logic.dma.action_selection_pdma import ActionSelectionPDMAEvaluator

    template = await load_golden_template()
    inputs = make_enhanced_inputs()
    inputs.processing_context = {"system_snapshot": make_templated_system_snapshot(template).model_dump()}
    inputs.conscience_feedback = {
        "failed_action": _RETRY_ATTEMPTED_ACTION,
        "failure_reason": make_conscience_application_result().override_reason,
        "retry_guidance": build_retry_guidance(updated_observation=updated_observation),
    }
    inputs.recursive_evaluation = True

    registry = Mock()
    registry.get_services_by_type.return_value = []
    dma = ActionSelectionPDMAEvaluator(service_registry=registry)
    pin_aspdma_context_builder(dma)
    captured: Dict[str, Any] = {}
    dma.call_llm_structured = _recording_llm(  # type: ignore[method-assign]
        captured,
        ASPDMALLMResult(
            selected_action=HandlerActionType.PONDER,
            reasoning="Golden fixture: reconsider after conscience override.",
            ponder_questions=["Golden fixture question?"],
        ),
    )
    await dma.evaluate(inputs)
    return captured["messages"]  # type: ignore[no-any-return]


async def capture_aspdma_retry() -> List[JSONDict]:
    """Retry with no new observation — the ``retry_general_outro`` branch."""
    return await _capture_aspdma_retry(updated_observation=None)


async def capture_aspdma_retry_observation() -> List[JSONDict]:
    """Retry with a new observation — the ``retry_observation_intro/_outro`` branch."""
    return await _capture_aspdma_retry(updated_observation=_RETRY_NEW_OBSERVATION)


# ---------------------------------------------------------------------------
# #986: the DMA-bounce compositions (the `prompts.dma.bounce_*` strings)
# ---------------------------------------------------------------------------


def make_bounce_summary() -> Any:
    """A bounce that TRIGGERED and EXHAUSTED — the state that reaches ASPDMA.

    ``any_exhausted`` is a property over the records, not a settable field, so
    the record below carries ``exhausted=True`` to make it true. A resolved
    bounce is invisible to ASPDMA by design (the better alternative simply
    replaced the original result), so only the exhausted case composes anything.
    """
    from ciris_engine.schemas.dma.bounce import BounceSummary, DMABounceAttempt, DMABounceRecord

    return BounceSummary(
        triggered_dmas=["csdma"],
        records=[
            DMABounceRecord(
                dma="csdma",
                field="plausibility_score",
                threshold=0.5,
                original_score=0.3,
                attempts=[DMABounceAttempt(attempt_index=0, score=0.4, reasoning="Golden fixture: still thin.")],
                chosen_attempt_index=0,
                final_score=0.4,
                exhausted=True,
            )
        ],
        composite_preamble=make_bounce_preamble(),
        difficulty_rationale="Golden fixture: no alternative cleared the plausibility threshold.",
    )


def make_bounce_preamble() -> str:
    """The localized bounce preamble, from the orchestrator's own builder.

    ``_build_composite_preamble`` is a staticmethod and is where four of the
    five ``prompts.dma.bounce_*`` strings are assembled, so it is called rather
    than imitated.
    """
    from ciris_engine.logic.processors.support.dma_orchestrator import DMAOrchestrator
    from ciris_engine.logic.utils.localization import get_preferred_language

    return DMAOrchestrator._build_composite_preamble([("csdma", 0.3, 0.5)], get_preferred_language())


async def capture_csdma_bounce() -> List[JSONDict]:
    """CSDMA re-composed on a bounced thought — the preamble rides in the content."""
    from ciris_engine.logic.dma.csdma import CSDMAEvaluator
    from ciris_engine.logic.processors.support.dma_orchestrator import DMAOrchestrator

    bounced = DMAOrchestrator._make_bounce_thought_item(make_queue_item(), make_bounce_preamble())
    dma = CSDMAEvaluator(service_registry=Mock())
    dma.fetch_original_task = AsyncMock(return_value=make_task())  # type: ignore[method-assign]
    captured: Dict[str, Any] = {}
    dma.call_llm_structured = _recording_llm(captured, make_csdma_result())  # type: ignore[method-assign]
    await dma.evaluate(bounced, make_context())
    return captured["messages"]  # type: ignore[no-any-return]


async def capture_aspdma_bounce_advisory() -> List[JSONDict]:
    """ASPDMA carrying the exhausted-bounce difficulty advisory.

    The advisory (``prompts.dma.bounce_advisory_aspdma``) is folded into the
    same ``{conscience_guidance}`` slot the retry envelope uses, so this step
    keeps it separate from the retry steps: one slot, two independent writers,
    and a probe needs to be able to attribute a moved block to exactly one.
    """
    from ciris_engine.logic.dma.action_selection_pdma import ActionSelectionPDMAEvaluator

    inputs = make_enhanced_inputs()
    inputs.bounce_summary = make_bounce_summary()

    registry = Mock()
    registry.get_services_by_type.return_value = []
    dma = ActionSelectionPDMAEvaluator(service_registry=registry)
    pin_aspdma_context_builder(dma)
    captured: Dict[str, Any] = {}
    dma.call_llm_structured = _recording_llm(  # type: ignore[method-assign]
        captured,
        ASPDMALLMResult(
            selected_action=HandlerActionType.SPEAK,
            reasoning="Golden fixture: speak despite a difficult bounce.",
            speak_content="Golden fixture response.",
        ),
    )
    await dma.evaluate(inputs)
    return captured["messages"]  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# #986 step 3: the conscience faculties (the `conscience_prompt` namespace)
# ---------------------------------------------------------------------------


def _make_conscience(conscience_cls: Any) -> Any:
    """Construct a conscience for message composition only.

    The four ``_create_*_messages`` builders are synchronous and touch no
    service — only the YAML prompt loader — so a mock registry and a mock clock
    are enough. ``time_service`` is not optional: ``_BaseConscience.__init__``
    refuses without one.
    """
    from ciris_engine.logic.conscience.core import ConscienceConfig

    return conscience_cls(service_registry=Mock(), config=ConscienceConfig(), time_service=Mock(), sink=None)


def _as_messages(built: Tuple[List[Any], str]) -> List[JSONDict]:
    """The conscience builders return (messages, user_prompt); keep the messages."""
    messages, _user_prompt = built
    return [message.model_dump() for message in messages]


async def _capture_entropy(image: Optional[str]) -> List[JSONDict]:
    from ciris_engine.logic.conscience.core import EntropyConscience

    conscience = _make_conscience(EntropyConscience)
    return _as_messages(conscience._create_entropy_messages(_CONSCIENCE_ACTION_TEXT, image_context=image))


async def _capture_coherence(image: Optional[str]) -> List[JSONDict]:
    from ciris_engine.logic.conscience.core import CoherenceConscience

    conscience = _make_conscience(CoherenceConscience)
    return _as_messages(
        conscience._create_coherence_messages(
            _CONSCIENCE_ACTION_TEXT, image_context=image, user_message=_CONSCIENCE_USER_MESSAGE
        )
    )


async def _capture_optimization_veto(image: Optional[str]) -> List[JSONDict]:
    from ciris_engine.logic.conscience.core import OptimizationVetoConscience

    conscience = _make_conscience(OptimizationVetoConscience)
    return _as_messages(
        conscience._create_optimization_veto_messages(_CONSCIENCE_ACTION_DESCRIPTION, image_context=image)
    )


async def _capture_epistemic_humility(image: Optional[str]) -> List[JSONDict]:
    from ciris_engine.logic.conscience.core import EpistemicHumilityConscience

    conscience = _make_conscience(EpistemicHumilityConscience)
    return _as_messages(
        conscience._create_epistemic_humility_messages(
            _CONSCIENCE_ACTION_DESCRIPTION, image_context=image, user_message=_CONSCIENCE_USER_MESSAGE
        )
    )


async def capture_entropy_conscience() -> List[JSONDict]:
    return await _capture_entropy(None)


async def capture_coherence_conscience() -> List[JSONDict]:
    return await _capture_coherence(None)


async def capture_optimization_veto_conscience() -> List[JSONDict]:
    return await _capture_optimization_veto(None)


async def capture_epistemic_humility_conscience() -> List[JSONDict]:
    return await _capture_epistemic_humility(None)


async def capture_entropy_conscience_image() -> List[JSONDict]:
    return await _capture_entropy(_CONSCIENCE_IMAGE_CONTEXT)


async def capture_coherence_conscience_image() -> List[JSONDict]:
    return await _capture_coherence(_CONSCIENCE_IMAGE_CONTEXT)


async def capture_optimization_veto_conscience_image() -> List[JSONDict]:
    return await _capture_optimization_veto(_CONSCIENCE_IMAGE_CONTEXT)


async def capture_epistemic_humility_conscience_image() -> List[JSONDict]:
    return await _capture_epistemic_humility(_CONSCIENCE_IMAGE_CONTEXT)


# ---------------------------------------------------------------------------
# #986 step 4: the follow-up thought after a conscience-forced PONDER
# ---------------------------------------------------------------------------


def make_conscience_ponder_notes() -> List[str]:
    """The PONDER questions a conscience override writes, from the real builder.

    ``_create_ponder_fallback_action`` is where three ``conscience.ponder_*``
    strings are assembled into ``PonderParams.questions``. Those questions
    become the follow-up thought's ``ponder_notes``, which
    ``ActionSelectionContextBuilder._build_ponder_context`` renders into the
    NEXT ASPDMA user message — so this is the composition that carries them to
    an LLM, one thought later than the override itself.
    """
    from ciris_engine.logic.processors.core.thought_processor.main import ThoughtProcessor

    processor = ThoughtProcessor.__new__(ThoughtProcessor)
    action = ActionSelectionDMAResult(
        selected_action=HandlerActionType.SPEAK,
        action_parameters=SpeakParams(content="Golden fixture response."),
        rationale="Golden fixture: speak.",
    )
    fallback = processor._create_ponder_fallback_action(action, "GoldenFixtureConscience", None)
    questions: List[str] = list(getattr(fallback.action_parameters, "questions", []))
    return questions


async def capture_aspdma_ponder_notes() -> List[JSONDict]:
    """ASPDMA on a thought that already carries conscience-authored ponder notes."""
    from ciris_engine.logic.dma.action_selection_pdma import ActionSelectionPDMAEvaluator

    thought = make_thought()
    thought.ponder_notes = make_conscience_ponder_notes()
    thought.thought_depth = 2

    inputs = make_enhanced_inputs()
    inputs.original_thought = thought

    registry = Mock()
    registry.get_services_by_type.return_value = []
    dma = ActionSelectionPDMAEvaluator(service_registry=registry)
    pin_aspdma_context_builder(dma)
    captured: Dict[str, Any] = {}
    dma.call_llm_structured = _recording_llm(  # type: ignore[method-assign]
        captured,
        ASPDMALLMResult(
            selected_action=HandlerActionType.SPEAK,
            reasoning="Golden fixture: speak after pondering.",
            speak_content="Golden fixture response.",
        ),
    )
    await dma.evaluate(inputs)
    return captured["messages"]  # type: ignore[no-any-return]


_CAPTURE_FNS = {
    "pdma": capture_pdma,
    "csdma": capture_csdma,
    "idma": capture_idma,
    "dsdma": capture_dsdma,
    "aspdma": capture_aspdma,
    "dsaspdma": capture_dsaspdma,
    "tsaspdma": capture_tsaspdma,
    "tsaspdma_correction": capture_tsaspdma_correction,
    "aspdma_retry": capture_aspdma_retry,
    "aspdma_retry_observation": capture_aspdma_retry_observation,
    "aspdma_ponder_notes": capture_aspdma_ponder_notes,
    "csdma_bounce": capture_csdma_bounce,
    "aspdma_bounce_advisory": capture_aspdma_bounce_advisory,
    "entropy_conscience": capture_entropy_conscience,
    "coherence_conscience": capture_coherence_conscience,
    "optimization_veto_conscience": capture_optimization_veto_conscience,
    "epistemic_humility_conscience": capture_epistemic_humility_conscience,
    "entropy_conscience_image": capture_entropy_conscience_image,
    "coherence_conscience_image": capture_coherence_conscience_image,
    "optimization_veto_conscience_image": capture_optimization_veto_conscience_image,
    "epistemic_humility_conscience_image": capture_epistemic_humility_conscience_image,
}


async def capture_step(name: str) -> List[JSONDict]:
    """Run the named step's evaluate path under the CALLER'S environment (#973).

    Unlike :func:`capture_via_evaluate`, no prompt environment is applied here —
    the compose dump wraps this in :func:`prompt_content_environment` with real
    pass-through loaders and a per-locale language pin.
    """
    return await _CAPTURE_FNS[name]()


async def capture_via_evaluate(name: str) -> List[JSONDict]:
    """Run the named DMA's evaluate() path and return the composed messages."""
    with deterministic_prompt_environment():
        return await _CAPTURE_FNS[name]()


# ---------------------------------------------------------------------------
# Golden snapshot IO
# ---------------------------------------------------------------------------


def canonical_json(messages: List[JSONDict]) -> str:
    """Canonical byte-comparable serialization of a message list."""
    return json.dumps(messages, ensure_ascii=False, sort_keys=True, indent=2)


def golden_path(name: str) -> Path:
    return GOLDEN_DIR / f"{name}_messages.json"


def load_golden(name: str) -> List[JSONDict]:
    with open(golden_path(name), encoding="utf-8") as f:
        loaded: List[JSONDict] = json.load(f)
    return loaded


def write_golden(name: str, messages: List[JSONDict]) -> None:
    GOLDEN_DIR.mkdir(exist_ok=True)
    with open(golden_path(name), "w", encoding="utf-8") as f:
        f.write(canonical_json(messages))
        f.write("\n")


def _main() -> None:
    import asyncio

    for name in DMA_NAMES:
        messages = asyncio.run(capture_via_evaluate(name))
        write_golden(name, messages)
        print(f"captured {name}: {len(messages)} messages -> {golden_path(name)}")


if __name__ == "__main__":
    _main()
