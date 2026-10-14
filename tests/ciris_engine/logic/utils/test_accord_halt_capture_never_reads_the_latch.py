"""Trace capture never reads the constitutional-halt latch (CC 4.2.1.1 A2).

Capture is a data door. Under a halt the agent's acts are refused by the act
gate, and the refusal's own ACTION_RESULT must still flow through capture to the
trace (CC 1.13.6; the node's capture stops reading the latch in 0.5.226). If any
part of the capture path consulted the latch, a refusal's terminal record would
be the thing it dropped.
"""

import ast
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List

import pytest

from ciris_engine.logic.utils import halt_latch
from ciris_engine.schemas.runtime.accord_halt import AccordHaltReading, AccordHaltState

pytestmark = pytest.mark.real_halt_latch

ROOT = Path(__file__).resolve().parents[4]

#: The reasoning-stream → trace path: step broadcast, the stream, the adapter.
CAPTURE_PATH = [
    "ciris_engine/logic/processors/core/step_decorators.py",
    "ciris_engine/logic/infrastructure/step_streaming.py",
    *sorted(str(p.relative_to(ROOT)) for p in (ROOT / "ciris_adapters" / "ciris_accord_metrics").rglob("*.py")),
]

#: Anything that would read the latch: the reader module, its read functions,
#: or the node route itself.
LATCH_NAMES = {"halt_latch", "read_halt_latch", "_read_from_node", "bus_backstop", "refuse_agent_send_under_halt"}
LATCH_ROUTE = "/v1/accord/halt-status"


def latch_references(source: str) -> List[str]:
    found: List[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.endswith("halt_latch"):
            found.append(f"from {node.module}")
        elif isinstance(node, ast.Import):
            found.extend(a.name for a in node.names if a.name.endswith("halt_latch"))
        elif isinstance(node, ast.Name) and node.id in LATCH_NAMES:
            found.append(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in LATCH_NAMES:
            found.append(node.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and LATCH_ROUTE in node.value:
            found.append(LATCH_ROUTE)
    return found


def test_capture_path_is_not_empty():
    assert len(CAPTURE_PATH) >= 4
    assert all((ROOT / rel).exists() for rel in CAPTURE_PATH)


@pytest.mark.parametrize("rel", CAPTURE_PATH)
def test_no_capture_module_reads_the_latch(rel):
    assert latch_references((ROOT / rel).read_text(encoding="utf-8")) == [], rel


@pytest.mark.parametrize(
    "source",
    [
        "from ciris_engine.logic.utils.halt_latch import read_halt_latch\n",
        "import ciris_engine.logic.utils.halt_latch\n",
        "async def f(m):\n    return await m.read_halt_latch()\n",
        "URL = 'http://127.0.0.1:4243/v1/accord/halt-status'\n",
    ],
)
def test_the_scan_is_not_vacuous(source):
    assert latch_references(source) != []


@pytest.mark.asyncio
async def test_an_action_result_is_broadcast_under_a_halt_without_reading_the_latch(monkeypatch):
    """Behaviourally: the ACTION_RESULT of a refused act reaches the stream, and the reader is never asked."""
    from ciris_engine.logic.infrastructure.step_streaming import reasoning_event_stream
    from ciris_engine.logic.processors.core.step_decorators import _broadcast_reasoning_event
    from ciris_engine.schemas.services.runtime_control import ActionCompleteStepData, ReasoningEvent, StepPoint

    reads: List[Any] = []

    async def halted() -> AccordHaltState:
        reads.append(1)
        return AccordHaltState(
            halted=True, reading=AccordHaltReading.IN_EFFECT, invocation_id="h", read_at=datetime.now(timezone.utc)
        )

    monkeypatch.setattr(halt_latch, "_read_from_node", halted)
    seen: List[Any] = []

    async def capture(event):
        seen.append(event)

    monkeypatch.setattr(reasoning_event_stream, "broadcast_reasoning_event", capture)

    step = ActionCompleteStepData(
        timestamp=datetime.now(timezone.utc).isoformat(),
        thought_id="th",
        task_id="t",
        processing_time_ms=0.0,
        error="accord_halt_in_effect:h",
        action_executed="speak",
        dispatch_success=False,
        handler_completed=True,
        audit_entry_id="a",
        audit_sequence_number=1,
        audit_entry_hash="h",
        audit_signature="s",
    )
    await _broadcast_reasoning_event(StepPoint.ACTION_COMPLETE, step)

    results = [e for e in seen if e.event_type == ReasoningEvent.ACTION_RESULT]
    assert len(results) == 1 and results[0].error == "accord_halt_in_effect:h"
    assert reads == []
