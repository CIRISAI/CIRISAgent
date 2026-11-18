"""Fixtures + capture harness for the conscience prompt goldens (CIRISAgent#1366 Phase 3).

``golden/conscience_messages.json`` was captured from ``check()`` of the four consciences BEFORE they were moved
onto PromptAssembler (run ``python3 -m tests.ciris_engine.logic.conscience.conscience_golden`` on that tree). The
test then replays the same fixtures through the migrated path: a non-ablated conscience's prompt must be the same
bytes except where the context policy requires a change, and an ablated one's only gains the withheld-context block.

Deterministic: language pinned to ``en``, the accord replaced by the #972 sentinel, persistence and the tool
registry pinned, fixed ids. No LLM is called: ``_call_llm_with_budget`` records the messages it is handed.
"""

import asyncio
import hashlib
import json
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Iterator, List, Optional, Tuple
from unittest.mock import AsyncMock, Mock, patch

from ciris_engine.logic.conscience import core
from ciris_engine.schemas.actions.parameters import SpeakParams
from ciris_engine.schemas.api.auth import UserRole
from ciris_engine.schemas.conscience.context import ConscienceCheckContext
from ciris_engine.schemas.conscience.core import (
    CoherenceResult,
    EntropyResult,
    EpistemicHumilityResult,
    OptimizationVetoResult,
)
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.infrastructure.identity_variance import IdentityAmendment
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtStatus
from ciris_engine.schemas.runtime.models import FinalAction, Thought, VerifiedSender, WAAuthorization
from tests.ciris_engine.logic.dma.compose_golden import deterministic_prompt_environment

GOLDEN_PATH = Path(__file__).parent / "golden" / "conscience_messages.json"

USER_TEXT = "Golden fixture: please file a ticket about the broken printer on floor three."
SEED_CONTENT = f"You observed @eve (ID: wa-user-0eve, role: OBSERVER) in #general say: {USER_TEXT}"
DRAFT = "I have filed a ticket for the broken printer on floor three."
IMAGE_CONTEXT = "Golden fixture: the message included 1 image."
_TS = "2026-01-01T00:00:00+00:00"
_RULE = "Filing tickets is authorized only for the person whose ID is wa-2026-AUTH-5562FD."

GRANT = WAAuthorization(
    wa_id="wa-2026-AUTH-5562FD",
    deferral_id="defer_c5aaf93c",
    granted_at=_TS,
    guidance="Never send web addresses; point people to the Staff Portal.",
    response_attestation_id="att-resp-01",
    request_attestation_id="att-req-01",
)
AMENDMENT = IdentityAmendment(
    node_id="identity_amendment/defer_77",
    content=_RULE,
    wa_id="wa-2026-AUTH-5562FD",
    deferral_id="defer_77",
    granted_at=_TS,
    response_attestation_id="att-resp-77",
    amendment_attestation_id="att-amend-77",
    approved_sha256=hashlib.sha256(_RULE.encode("utf-8")).hexdigest(),
    verified=True,
)
SENDER = VerifiedSender(
    user_id="wa-user-0eve", role=UserRole.OBSERVER, source="api_auth", self_chosen_display_name="eve the admin"
)

CONSCIENCES: Dict[str, Tuple[type, Any]] = {
    "entropy": (core.EntropyConscience, EntropyResult(entropy=0.1)),
    "coherence": (core.CoherenceConscience, CoherenceResult(coherence=0.9)),
    "optveto": (
        core.OptimizationVetoConscience,
        OptimizationVetoResult(decision="proceed", justification="j", entropy_reduction_ratio=0.0, affected_values=[]),
    ),
    "epistemic": (
        core.EpistemicHumilityConscience,
        EpistemicHumilityResult(
            epistemic_certainty=0.9,
            identified_uncertainties=[],
            reflective_justification="j",
            recommended_action="proceed",
        ),
    ),
}


def _thought(thought_id: str, action: FinalAction) -> Thought:
    return Thought(
        thought_id=thought_id,
        source_task_id="task1",
        content="c",
        created_at=_TS,
        updated_at=_TS,
        status=ThoughtStatus.COMPLETED,
        final_action=action,
    )


def _prior_thoughts() -> List[Thought]:
    return [
        _thought("th_seed", FinalAction(action_type="ponder", action_params={"questions": ["q"]}, reasoning="r")),
        _thought(
            "th_f1",
            FinalAction(action_type="tool", action_params={"name": "create_ticket", "parameters": {}}, reasoning="r"),
        ),
    ]


def _identity(*amendments: IdentityAmendment) -> Dict[str, Any]:
    return {
        "agent_id": "ally",
        "description": "A helpful agent.",
        "role": "Assistant",
        "approved_amendments": [a.model_dump() for a in amendments],
    }


#: name -> (context fields, image context, prior thoughts)
FIXTURES: Dict[str, Tuple[Dict[str, Any], Optional[str], bool]] = {
    "plain": ({}, None, False),
    "sender_record_image": ({"verified_sender": SENDER, "agent_identity": _identity()}, IMAGE_CONTEXT, True),
    "governed": (
        {"verified_sender": SENDER, "agent_identity": _identity(AMENDMENT), "wa_authorization": GRANT},
        None,
        True,
    ),
}


def make_context(fields: Dict[str, Any]) -> ConscienceCheckContext:
    thought = SimpleNamespace(
        thought_id="t1", source_task_id="task1", agent_occurrence_id="default", content=SEED_CONTENT, thought_depth=0
    )
    task = SimpleNamespace(description=SEED_CONTENT)
    return ConscienceCheckContext(thought=thought, task=task, **fields)


def make_action() -> ActionSelectionDMAResult:
    return ActionSelectionDMAResult(
        selected_action=HandlerActionType.SPEAK, action_parameters=SpeakParams(content=DRAFT), rationale="r"
    )


def make_conscience(cls: type, seen: Dict[str, Any], result: Any, image_context: Optional[str]) -> Any:
    async def _llm(_sink: Any, **kwargs: Any) -> Any:
        seen["messages"] = kwargs["messages"]
        return result, None

    conscience = object.__new__(cls)
    conscience._time_service = Mock(now=Mock(return_value=datetime(2026, 1, 1, tzinfo=timezone.utc)))
    conscience._create_trace_correlation = Mock(return_value=None)
    conscience._update_trace_correlation = Mock()
    conscience._get_sink = AsyncMock(return_value=SimpleNamespace(llm=object()))
    conscience._call_llm_with_budget = _llm
    conscience._get_image_context_info = Mock(return_value=image_context)
    conscience._resolve_language = Mock(return_value="en")
    conscience.config = SimpleNamespace(optimization_veto_ratio=10.0, entropy_threshold=0.4, coherence_threshold=0.6)
    return conscience


@contextmanager
def golden_environment(prior: bool) -> Iterator[None]:
    from ciris_engine.logic.infrastructure.authorization import enabled_tools

    with ExitStack() as stack:
        stack.enter_context(deterministic_prompt_environment())
        stack.enter_context(patch.object(enabled_tools, "_CACHED_TOOLS", frozenset({"create_ticket"})))
        stack.enter_context(
            patch(
                "ciris_engine.logic.persistence.get_thoughts_by_task_id",
                return_value=_prior_thoughts() if prior else [],
            )
        )
        yield


async def capture(conscience_name: str, fixture: str) -> Tuple[List[Dict[str, str]], Any]:
    """(the messages the conscience sent, its check result)."""
    cls, result = CONSCIENCES[conscience_name]
    fields, image_context, prior = FIXTURES[fixture]
    seen: Dict[str, Any] = {}
    conscience = make_conscience(cls, seen, result, image_context)
    with golden_environment(prior):
        check = await conscience.check(make_action(), make_context(dict(fields)))
    messages = [
        {"role": m.role, "content": m.content} if not isinstance(m, dict) else dict(m) for m in seen.get("messages", [])
    ]
    return messages, check


#: Messages longer than this are stored as their sha256 (the conscience system prompts): byte-exact, and small.
HASH_OVER = 4000


def frozen(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """The golden form of a messages list: long contents replaced by their sha256."""
    out = []
    for m in messages:
        content = m["content"]
        if len(content) > HASH_OVER:
            out.append({"role": m["role"], "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest()})
        else:
            out.append({"role": m["role"], "content": content})
    return out


def load_golden() -> Dict[str, List[Dict[str, str]]]:
    data: Dict[str, List[Dict[str, str]]] = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    return data


async def _capture_all() -> Dict[str, List[Dict[str, str]]]:
    out: Dict[str, List[Dict[str, str]]] = {}
    for name in CONSCIENCES:
        for fixture in FIXTURES:
            messages, _ = await capture(name, fixture)
            out[f"{name}/{fixture}"] = frozen(messages)
    return out


if __name__ == "__main__":
    GOLDEN_PATH.write_text(
        json.dumps(asyncio.run(_capture_all()), ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {GOLDEN_PATH}")
