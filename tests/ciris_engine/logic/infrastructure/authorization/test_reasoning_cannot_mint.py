"""The reasoning loop cannot mint or widen its own envelope (CIRISAgent#938).

This is the load-bearing property of Phase 1: if the agent can mint or widen
its own envelope, everything built on it is theater.

**What these tests prove.**
1. Every minting entry point raises when called while the reasoning-scope
   marker is set, including from ``asyncio`` work the reasoning loop spawns
   (``contextvars`` are copied into child tasks).
2. ``ActionDispatcher.dispatch`` — the path from a model-selected action to a
   handler — really does set that marker, verified by executing it, not by
   reading the source.
3. ``ThoughtProcessor.process_thought`` enters the scope (source-level; a
   functional run needs the whole H3ERE pipeline).
4. No module under ``logic/dma/``, ``logic/conscience/`` or ``logic/handlers/``
   imports the issuer module at all.
5. Attenuation *is* permitted inside the scope and still cannot widen.

**What they do not prove.** This is a Python process: anything that can
``import`` can reach anything, and a determined edit can call
``contextvars.ContextVar.set`` or import the issuer under a different name. A
future processor that dispatches handlers without entering the scope would
evade (1) and (2), which is exactly why (4) exists as an independent check —
but (4) is a static grep over imports and a dynamic ``importlib`` call would
slip past it. The honest claim is: **an accidental mint from the reasoning path
fails loudly at runtime, and a deliberate one cannot be added without changing
a file these tests watch.** It is not a sandbox and must not be described as
one.
"""

import ast
import asyncio
import pathlib
from typing import List

import pytest

from ciris_engine.logic.infrastructure.authorization.enabled_tools import (
    prime_enabled_tools,
    reset_enabled_tools_cache,
)
from ciris_engine.logic.infrastructure.authorization.envelope_issuer import (
    EnvelopeIssuanceForbidden,
    attenuate_envelope,
    issue_authority_envelope,
    issue_deployment_envelope,
    issue_deployment_envelope_from_cache,
    issue_task_envelope_best_effort,
)
from ciris_engine.logic.infrastructure.authorization.reasoning_scope import (
    in_reasoning_scope,
    reasoning_scope,
)
from ciris_engine.schemas.runtime.enums import TaskStatus
from ciris_engine.schemas.runtime.models import Task, TaskContext
from ciris_engine.schemas.runtime.task_envelope import (
    EnvelopeIssuerKind,
    EnvelopeWideningError,
    ToolCapability,
)

def _repo_root() -> pathlib.Path:
    for parent in pathlib.Path(__file__).resolve().parents:
        if (parent / "ciris_engine").is_dir() and (parent / "tests").is_dir():
            return parent
    raise RuntimeError("repo root not found")


REPO_ROOT = _repo_root()
ISSUER_MODULE = "ciris_engine.logic.infrastructure.authorization.envelope_issuer"

# Directories that are, or run inside, the reasoning loop.
REASONING_PACKAGES = [
    "ciris_engine/logic/dma",
    "ciris_engine/logic/conscience",
    "ciris_engine/logic/handlers",
]


class StubToolInfo:
    def __init__(self, name: str) -> None:
        self.name = name


class StubToolSource:
    async def get_all_tool_info(self, handler_name: str = "default") -> List[StubToolInfo]:
        return [StubToolInfo("self_help"), StubToolInfo("weather")]


@pytest.fixture(autouse=True)
def clean_enabled_tools():
    reset_enabled_tools_cache()
    yield
    reset_enabled_tools_cache()


def make_task() -> Task:
    return Task(
        task_id="task_1",
        channel_id="c-1",
        agent_occurrence_id="default",
        description="d",
        status=TaskStatus.ACTIVE,
        created_at="2026-07-30T00:00:00+00:00",
        updated_at="2026-07-30T00:00:00+00:00",
        context=TaskContext(channel_id="c-1", correlation_id="corr-1"),
    )


# ------------------------------------------------------ (1) the runtime guard


async def test_deployment_issuance_is_forbidden_inside_the_reasoning_loop():
    with reasoning_scope(task_id="task_1", thought_id="th_1", phase="test"):
        with pytest.raises(EnvelopeIssuanceForbidden, match="issued from outside the reasoning loop"):
            await issue_deployment_envelope(task_id="task_1", tool_source=StubToolSource())


def test_sync_deployment_issuance_is_forbidden_inside_the_reasoning_loop():
    with reasoning_scope(task_id="task_1", thought_id="th_1", phase="test"):
        with pytest.raises(EnvelopeIssuanceForbidden):
            issue_deployment_envelope_from_cache(task_id="task_1")


def test_authority_issuance_is_forbidden_inside_the_reasoning_loop():
    with reasoning_scope(task_id="task_1", thought_id="th_1", phase="test"):
        with pytest.raises(EnvelopeIssuanceForbidden):
            issue_authority_envelope(
                task_id="task_1",
                issuer_kind=EnvelopeIssuerKind.WISE_AUTHORITY,
                issuer_id="wa-root",
                granted_tools=["tmux"],
                capabilities=[ToolCapability.EXECUTE_CODE],
            )


def test_best_effort_issuance_propagates_the_forbidden_error_rather_than_swallowing_it():
    """A mint attempt from the reasoning loop is a defect, not a transient error.

    ``issue_task_envelope_best_effort`` swallows ordinary failures on purpose —
    a task must not be dropped because issuance hiccupped — but it must never
    swallow this one.
    """
    with reasoning_scope(task_id="task_1", thought_id="th_1", phase="test"):
        with pytest.raises(EnvelopeIssuanceForbidden):
            issue_task_envelope_best_effort(make_task())


def test_the_error_names_the_reasoning_work_in_flight():
    with reasoning_scope(task_id="task_ABC", thought_id="th_XYZ", phase="action_dispatch"):
        with pytest.raises(EnvelopeIssuanceForbidden) as excinfo:
            issue_deployment_envelope_from_cache(task_id="task_ABC")
    message = str(excinfo.value)
    assert "task_ABC" in message and "th_XYZ" in message and "action_dispatch" in message


async def test_the_guard_reaches_asyncio_work_the_reasoning_loop_spawns():
    """contextvars are copied into child tasks, so a handler that offloads a
    mint onto ``asyncio.create_task`` does not escape the guard."""
    results = []

    async def child():
        try:
            issue_deployment_envelope_from_cache(task_id="task_1")
            results.append("MINTED")
        except EnvelopeIssuanceForbidden:
            results.append("BLOCKED")

    with reasoning_scope(task_id="task_1", thought_id="th_1", phase="test"):
        await asyncio.gather(asyncio.create_task(child()))
    assert results == ["BLOCKED"]


async def test_issuance_works_normally_outside_the_reasoning_loop():
    assert in_reasoning_scope() is False
    envelope = await issue_deployment_envelope(task_id="task_1", tool_source=StubToolSource())
    assert envelope.granted_tools == frozenset({"self_help", "weather"})


async def test_the_scope_is_released_after_the_block():
    with reasoning_scope(task_id="t", thought_id="th", phase="test"):
        assert in_reasoning_scope() is True
    assert in_reasoning_scope() is False
    await issue_deployment_envelope(task_id="task_1", tool_source=StubToolSource())


def test_nested_scopes_restore_correctly():
    with reasoning_scope(task_id="t", thought_id="th", phase="process_thought"):
        with reasoning_scope(task_id="t", thought_id="th", phase="action_dispatch"):
            assert in_reasoning_scope() is True
        assert in_reasoning_scope() is True
    assert in_reasoning_scope() is False


# ------------------------------------------ (2) the dispatcher really enters it


async def test_action_dispatcher_dispatch_executes_inside_the_reasoning_scope():
    """Functional, not source-level: run dispatch() and observe the marker."""
    from ciris_engine.logic.infrastructure.handlers.action_dispatcher import ActionDispatcher

    observed = {}

    class RecordingDispatcher(ActionDispatcher):
        async def _dispatch_inner(self, action_selection_result, thought, dispatch_context):  # type: ignore[override]
            observed["in_scope"] = in_reasoning_scope()
            observed["mint_blocked"] = False
            try:
                issue_deployment_envelope_from_cache(task_id="task_1")
            except EnvelopeIssuanceForbidden:
                observed["mint_blocked"] = True
            return "dispatched"

    class FakeThought:
        thought_id = "th_1"
        source_task_id = "task_1"

    class FakeDispatchContext:
        task_id = "task_1"

    dispatcher = RecordingDispatcher(handlers={})
    result = await dispatcher.dispatch(
        action_selection_result=None, thought=FakeThought(), dispatch_context=FakeDispatchContext()
    )
    assert result == "dispatched"
    assert observed["in_scope"] is True
    assert observed["mint_blocked"] is True
    # And the scope is gone once dispatch returns.
    assert in_reasoning_scope() is False


# --------------------------------------- (3) the thought processor enters it too


def _calls_reasoning_scope(path: pathlib.Path, func_name: str) -> bool:
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == func_name:
            for inner in ast.walk(node):
                if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name):
                    if inner.func.id == "reasoning_scope":
                        return True
    return False


def test_thought_processor_process_thought_enters_the_reasoning_scope():
    """Source-level: a functional run needs the whole H3ERE pipeline stood up.

    This is the weaker of the two checks and is called out as such — it asserts
    the call is present, not that it wraps every path through the function.
    """
    path = REPO_ROOT / "ciris_engine/logic/processors/core/thought_processor/main.py"
    assert _calls_reasoning_scope(path, "process_thought"), (
        "ThoughtProcessor.process_thought no longer enters a reasoning scope; "
        "envelope minting from DMA/conscience execution would stop being blocked"
    )


def test_action_dispatcher_dispatch_enters_the_reasoning_scope_in_source():
    path = REPO_ROOT / "ciris_engine/logic/infrastructure/handlers/action_dispatcher.py"
    assert _calls_reasoning_scope(path, "dispatch")


# ------------------------------------------------- (4) the import boundary


def _imports_issuer(path: pathlib.Path) -> bool:
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:  # pragma: no cover - would be a broken file, not our concern
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == ISSUER_MODULE for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == ISSUER_MODULE:
                return True
            # `from ...authorization import envelope_issuer`
            if module.endswith("infrastructure.authorization") and any(
                alias.name == "envelope_issuer" for alias in node.names
            ):
                return True
    return False


@pytest.mark.parametrize("package", REASONING_PACKAGES)
def test_no_reasoning_module_imports_the_issuer(package):
    """Static import boundary.

    Limit: a grep over imports. ``importlib.import_module`` at runtime would
    slip past it. It is here because it catches the realistic failure — someone
    adding a convenient import — without needing the pipeline to run.
    """
    offenders = []
    for path in (REPO_ROOT / package).rglob("*.py"):
        if _imports_issuer(path):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == [], (
        f"{package} imports the task-envelope issuer: {offenders}. "
        "The reasoning layer may read an envelope (envelope_reader) but must never mint one."
    )


def test_the_handler_layer_reads_envelopes_through_the_reader_module():
    """The tool handler needs the envelope; it must get it from the read-only
    module, which has no minting surface at all."""
    path = REPO_ROOT / "ciris_engine/logic/handlers/external/tool_handler.py"
    source = path.read_text()
    assert "envelope_reader import resolve_envelope_for_task_id" in source
    assert "envelope_issuer" not in source

    reader = REPO_ROOT / "ciris_engine/logic/infrastructure/authorization/envelope_reader.py"
    reader_source = reader.read_text()
    for minting_word in ("def issue_", "def attenuate", "TaskEnvelope("):
        assert minting_word not in reader_source, f"envelope_reader grew a minting surface: {minting_word}"


# --------------------------------------- (5) attenuation is allowed, and narrows


async def test_attenuation_is_permitted_inside_the_reasoning_loop():
    """Giving capability away is not privilege escalation."""
    envelope = await issue_deployment_envelope(task_id="task_1", tool_source=StubToolSource())
    with reasoning_scope(task_id="task_1", thought_id="th_1", phase="test"):
        narrowed = attenuate_envelope(envelope, granted_tools={"self_help"})
    assert narrowed.granted_tools == frozenset({"self_help"})


async def test_attenuation_inside_the_reasoning_loop_still_cannot_widen():
    envelope = await issue_deployment_envelope(task_id="task_1", tool_source=StubToolSource())
    # Start from an already-narrowed envelope so there is somewhere to widen to.
    narrow = attenuate_envelope(
        envelope, granted_tools={"self_help"}, capabilities={ToolCapability.OBSERVE_LOCAL}
    )
    with reasoning_scope(task_id="task_1", thought_id="th_1", phase="test"):
        with pytest.raises(EnvelopeWideningError, match="would add tools"):
            attenuate_envelope(narrow, granted_tools={"self_help", "weather"})
        with pytest.raises(EnvelopeWideningError, match="would add capabilities"):
            attenuate_envelope(
                narrow, capabilities={ToolCapability.OBSERVE_LOCAL, ToolCapability.EXECUTE_CODE}
            )
        # Not even back up to what the parent envelope held.
        with pytest.raises(EnvelopeWideningError):
            attenuate_envelope(narrow, capabilities=set(ToolCapability))


async def test_attenuation_cannot_be_used_to_rebind_to_another_task():
    envelope = await issue_deployment_envelope(task_id="task_1", tool_source=StubToolSource())
    narrowed = attenuate_envelope(envelope, granted_tools={"self_help"})
    assert narrowed.task_id == "task_1"
