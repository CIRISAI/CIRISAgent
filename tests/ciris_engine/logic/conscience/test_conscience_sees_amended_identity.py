"""Every conscience reads the agent's identity, approved amendments included.

RATCHET Market 4 (run 43453725789, v2.21.0): the amended identity text was in
the prompt for action selection (376 calls) and the domain DMA (429), and in 0
of 387 coherence, 386 entropy, 395 epistemic-humility and 395 optimization-veto
calls. Refusals the approved amendment requires were overridden as
"hallucinated constraint", and the approved apply step was flagged as the agent
"unilaterally altering its core identity". Eric, 2026-11-13: the consciences load
the same identity as the DMAs, amendment included.
"""

from __future__ import annotations

import inspect
import json
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.conscience import core
from ciris_engine.logic.formatters.identity import agent_identity_of, identity_block_of
from ciris_engine.schemas.conscience.context import ConscienceCheckContext
from ciris_engine.schemas.conscience.core import OptimizationVetoResult
from tests.ciris_engine.logic.dma import compose_golden as cg

AMENDMENT = "End every reply with a short check-in question."
IDENTITY = {
    "agent_id": "ally",
    "description": "A helpful assistant.",
    "role": "Assistant",
    "approved_amendments": [{"content": AMENDMENT}],
}


def test_identity_block_carries_the_amendment_like_the_dmas():
    block = identity_block_of(IDENTITY, language="en")
    assert "ally" in block and AMENDMENT in block
    assert identity_block_of(None) == "" and identity_block_of({"description": "x"}) == ""


def test_identity_is_read_from_the_processing_context_snapshot():
    assert agent_identity_of({"system_snapshot": {"agent_identity": IDENTITY}}) is IDENTITY
    assert agent_identity_of(SimpleNamespace(system_snapshot=SimpleNamespace(agent_identity=IDENTITY))) is IDENTITY
    assert agent_identity_of(None) is None and agent_identity_of({}) is None


@pytest.mark.parametrize(
    "cls",
    [core.EntropyConscience, core.CoherenceConscience, core.OptimizationVetoConscience, core.EpistemicHumilityConscience],
)
def test_every_conscience_adds_the_identity(cls):
    assert "self._with_identity(messages, context" in inspect.getsource(cls.check)


@pytest.mark.asyncio
async def test_the_veto_prompt_carries_the_amended_identity():
    seen: Dict[str, Any] = {}

    async def _llm(_sink: Any, **kwargs: Any) -> Any:
        seen["messages"] = kwargs["messages"]
        return OptimizationVetoResult(
            decision="proceed", justification="j", entropy_reduction_ratio=0.0, affected_values=[]
        ), None

    conscience = object.__new__(core.OptimizationVetoConscience)
    conscience._time_service = Mock(now=Mock(return_value=datetime.now()))
    conscience._create_trace_correlation = Mock(return_value=None)
    conscience._update_trace_correlation = Mock()
    conscience._get_sink = AsyncMock(return_value=SimpleNamespace(llm=object()))
    conscience._call_llm_with_budget = _llm
    conscience._get_image_context_info = Mock(return_value=None)
    conscience._resolve_language = Mock(return_value="en")
    conscience.config = SimpleNamespace(optimization_veto_ratio=10.0)
    action = cg.make_memorize_aspdma_result()
    thought = SimpleNamespace(thought_id="t1", source_task_id="task1")

    await conscience.check(action, ConscienceCheckContext(thought=thought, agent_identity=IDENTITY))
    with_identity = seen["messages"]
    assert AMENDMENT in json.dumps([m.content for m in with_identity])
    assert with_identity[-1].role == "user"

    await conscience.check(action, ConscienceCheckContext(thought=thought))
    assert AMENDMENT not in json.dumps([m.content for m in seen["messages"]])
