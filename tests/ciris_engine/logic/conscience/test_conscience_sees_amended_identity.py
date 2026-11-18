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
    # Verified: the input-ablated pair reads only verified amendments (#1366, rc21
    # profile; test_ablated_identity_verified_only.py).
    # Full provenance: a verified amendment is a rule in force, and the judges must read it as a signed rule
    # entry too (the context policy requires it, #1366 Phase 3).
    "approved_amendments": [
        {
            "content": AMENDMENT,
            "verified": True,
            "node_id": "identity_amendment/d1",
            "wa_id": "wa-1",
            "deferral_id": "d1",
            "granted_at": "2026-11-13T00:00:00+00:00",
            "approved_sha256": __import__("hashlib").sha256(AMENDMENT.encode("utf-8")).hexdigest(),
        }
    ],
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
    """Each check assembles its prompt through the one builder, which lays the identity segments out first."""
    from ciris_engine.logic.conscience import prompt_segments

    assert "self._assemble(" in inspect.getsource(cls.check)
    assert "identity_segments(identity, language" in inspect.getsource(prompt_segments.assemble_conscience_prompt)


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


def test_the_tool_step_reads_the_amended_identity():
    """Eric, 2026-11-13: the ethical DMA and the tool step load the same identity."""
    from ciris_engine.logic.dma.tsaspdma import TSASPDMAEvaluator

    from unittest.mock import PropertyMock, patch

    dma = object.__new__(TSASPDMAEvaluator)
    context = SimpleNamespace(system_snapshot=SimpleNamespace(agent_identity=IDENTITY))
    with patch.object(TSASPDMAEvaluator, "prompt_loader", new_callable=PropertyMock) as loader:
        loader.return_value = SimpleNamespace(language="en")
        assert dma._agent_identity(context) is IDENTITY
        assert dma._agent_identity(None) is None
        # ...and the identity, amendment included, is what the assembled prompt carries.
        system, _ = dma._system_segments("instr", IDENTITY, None, "t")
        assert AMENDMENT in "".join(s.text for s in system)


@pytest.mark.parametrize("module, needle", [
    ("ciris_engine.logic.dma.pdma", "identity_block=identity_block_of(agent_identity_of(context)"),
    ("ciris_engine.logic.dma.csdma", "identity_block=identity_block_of(agent_identity_of(context)"),
    ("ciris_engine.logic.dma.tsaspdma", "agent_identity = self._agent_identity(context)"),
])
def test_every_judging_dma_passes_the_shared_identity(module, needle):
    import importlib

    assert needle in inspect.getsource(importlib.import_module(module))
