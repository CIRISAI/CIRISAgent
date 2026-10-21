"""#998 — two gates against claiming work that was never done.

The dream processor announced *"Reflection complete. Wove N connections."* and
published an ``edges_created`` telemetry series. Both numbers came from
``edges_created += 3  # Each dream MEMORIZE creates 3 edges`` — a hardcoded
guess, describing a handler (``DreamMemorizeHandler``) that was registered
nowhere. It appeared exactly once repo-wide, its own class statement, while
``handler_registry.py`` mapped MEMORIZE to ``MemorizeHandler`` alone.

So the edges the dream exists to weave — CONNECTS, IMPLIES, ASPIRES_TO — were
never created, and the agent told users it had created them.

Two independent failures produced that, and each gets its own gate:

1. **A capability was defined and never reachable.** A complete handler, with
   tests, wired to nothing.
2. **A metric asserted a quantity nothing measured.** Not an off-by-one — a
   constant standing in for an observation.

Either alone is bad. Together they are the shape this whole cut keeps finding:
*the system reported success for work it never performed.* A manifest logging
replacements it did not make, vulture exiting 0 on a run it never did, six
prompt blocks translated into 29 languages and never composed, an emergency
endpoint reporting ``enabled: true`` while rejecting everything.

A metric may count an event it witnessed. It may not assert a quantity it did
not measure.
"""

from __future__ import annotations

import ast
import pathlib
from typing import Dict, List, Set

import pytest

LOGIC = pathlib.Path("ciris_engine/logic")
HANDLERS = LOGIC / "handlers"
REGISTRY = LOGIC / "infrastructure/handlers/handler_registry.py"

#: Handlers deliberately not reachable from the dispatcher, with the reason.
#: A ratchet: it may shrink, never grow. Empty is the goal.
UNREGISTERED_BY_DESIGN: Dict[str, str] = {}

#: Counter increments by a constant > 1 that are genuinely measurements, not
#: assertions. Empty is the goal; an entry needs the reason it is honest.
MEASURED_CONSTANT_INCREMENTS: Dict[str, str] = {}


def _py(root: pathlib.Path) -> List[pathlib.Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _handler_classes() -> Dict[str, pathlib.Path]:
    """Every concrete BaseActionHandler subclass and where it lives."""
    found: Dict[str, pathlib.Path] = {}
    for path in _py(HANDLERS):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            bases = {b.id if isinstance(b, ast.Name) else getattr(b, "attr", "") for b in node.bases}
            if "BaseActionHandler" in bases:
                found[node.name] = path
    return found


def test_every_action_handler_is_reachable_from_the_dispatcher() -> None:
    """A handler nothing can dispatch to is a capability that does not exist.

    Reachable means: named in the registry, or routed to by a handler that is.
    ``DreamMemorizeHandler`` is the second kind — ``MemorizeHandler`` dispatches
    to it on ``DreamConsolidationParams``, because one action must map to one
    registry entry for the dispatcher's benefit.
    """
    registry_src = REGISTRY.read_text(encoding="utf-8")
    handler_srcs = {p: p.read_text(encoding="utf-8") for p in _py(HANDLERS)}

    unreachable = []
    for name, path in _handler_classes().items():
        if name in UNREGISTERED_BY_DESIGN:
            continue
        if name in registry_src:
            continue
        # routed to by some OTHER handler module
        if any(name in src for other, src in handler_srcs.items() if other != path):
            continue
        unreachable.append(f"{name} ({path})")

    assert not unreachable, (
        f"handler classes nothing can dispatch to: {sorted(unreachable)}. "
        f"A complete handler wired to nothing is a capability the system claims and does not "
        f"have — register it, route to it from a registered handler, or name it in "
        f"UNREGISTERED_BY_DESIGN with the reason."
    )


def test_no_metric_asserts_a_quantity_it_did_not_measure() -> None:
    """``counter += <constant greater than 1>`` is an assertion, not a count.

    ``+= 1`` is fine: it counts one witnessed event. ``+= 3`` claims three
    somethings happened, on the authority of whoever typed the 3. When that
    number reaches a user (*"Wove 3 connections"*) or a telemetry series, the
    system is reporting work it never observed.

    Scoped to attribute targets (``self.session.edges_created += 3``) — the
    shape counters take — so ordinary local arithmetic is not swept in.
    """
    offenders: List[str] = []
    for path in _py(LOGIC):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.AugAssign) or not isinstance(node.op, ast.Add):
                continue
            if not isinstance(node.target, ast.Attribute):
                continue
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, int) and value.value > 1:
                key = f"{path.relative_to(LOGIC.parent).as_posix()}:{node.lineno}"
                if key not in MEASURED_CONSTANT_INCREMENTS:
                    offenders.append(f"{key} ({node.target.attr} += {value.value})")

    assert not offenders, (
        f"metrics incremented by a constant greater than 1: {sorted(offenders)}. "
        f"Count what you observed, or measure what you are claiming. If the constant really "
        f"is a measurement, name the site in MEASURED_CONSTANT_INCREMENTS with why."
    )


def test_the_ratchets_only_turn_one_way() -> None:
    assert not UNREGISTERED_BY_DESIGN, f"grew to {sorted(UNREGISTERED_BY_DESIGN)} — wire it, don't park it"
    assert not MEASURED_CONSTANT_INCREMENTS, f"grew to {sorted(MEASURED_CONSTANT_INCREMENTS)}"


def test_dream_consolidation_actually_routes() -> None:
    """The specific regression: MEMORIZE carrying DreamConsolidationParams must
    reach the handler that creates the three edges."""
    import inspect

    from ciris_engine.logic.handlers.memory.memorize_handler import MemorizeHandler

    source = inspect.getsource(MemorizeHandler.handle)
    assert "DreamConsolidationParams" in source and "DreamMemorizeHandler" in source, (
        "MemorizeHandler no longer routes dream consolidation — the three edges "
        "(CONNECTS / IMPLIES / ASPIRES_TO) are the dream's entire work product"
    )


def test_the_dream_no_longer_announces_unmeasured_edges() -> None:
    """The user-facing half. The announcement must not quote a number no code
    measured — that is fabrication in a string the user reads."""
    src = (LOGIC / "processors/states/minimal_dream_processor.py").read_text(encoding="utf-8")

    # NOT a substring check for `edges_created += 3`: the fix comment quotes the
    # old line to explain it, and a naive grep flags the explanation as the
    # defect. (It did — this test failed on its own docstring first time out,
    # which is a small live demonstration of why the repo-wide gate above is
    # AST-based and this one is narrow.) The increment itself is covered by
    # test_no_metric_asserts_a_quantity_it_did_not_measure; what is unique here
    # is the USER-FACING claim.
    assert "Wove {self.current_session.edges_created} connections" not in src, (
        "the dream is announcing an edge count to the user again"
    )
    assert "memorize_dispatched" in src, "the honest counter is gone"
