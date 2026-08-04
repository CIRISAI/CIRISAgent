"""#996 — replacing one field must never disable another.

An agent-template prompt override does exactly one of two things: it **replaces
a field**, or it is **additive**. What it may never do is take out neighbours.
Every defect in this family was an override named for one field that swallowed
the composition of several:

========================  =====================================  ==============
override                  replaced                               also disabled
========================  =====================================  ==============
ASPDMA ``system_prompt``   ``DEFAULT_TEMPLATE`` (3 fields)        decision_format,
                                                                 closing_reminder
CSDMA ``system_prompt``    ``get_system_message()`` (6 fields)    five siblings
PDMA ``system_prompt``     ``get_system_message()`` (6 fields)    five siblings
ASPDMA ``user_prompt       the whole assembled user message       the entire
_template``                                                      integration layer
CSDMA ``user_prompt        an 80 B framing field                  context_summary
_template``
========================  =====================================  ==============

The shape is always the same in source: ``if override: <use it> else:
<compose>``. The composer sits in the else, so supplying an override deletes
everything the composer would have produced. That is the thing this file makes
impossible to write again.
"""

from __future__ import annotations

import ast
import glob
import pathlib
import re
from typing import Dict, List, Set

import pytest
import yaml

from ciris_engine.logic.dma.template_overrides import REPLACEABLE_FIELDS, is_static, slots

DMA_DIR = pathlib.Path("ciris_engine/logic/dma")
PROMPTS = DMA_DIR / "prompts"

#: The functions that turn fields into a message. If one of these is reachable
#: only when no override is present, an override is disabling fields.
COMPOSERS = {"get_system_message", "get_user_message", "build_main_user_content"}

#: Modules carrying template-override branches.
OVERRIDE_MODULES = ("action_selection_pdma.py", "csdma.py", "pdma.py")

#: Slot values each DMA passes to a template override's `.format()`. A template
#: using anything else raises KeyError at prompt-build time, in production.
SUPPLIED_SLOTS: Dict[str, Set[str]] = {
    "action_selection_pdma_overrides": {"thought_content", "available_actions"},
    "csdma_overrides": {"thought_content", "context_summary"},
    "pdma_overrides": {"original_thought_content", "thought_content", "full_context_str"},
}


def _override_ifs(tree: ast.AST) -> List[ast.If]:
    """`if <something_override>:` blocks."""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and isinstance(node.test, ast.Name) and "override" in node.test.id:
            out.append(node)
    return out


def _calls_in(node: ast.AST) -> Set[str]:
    return {
        n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", "")
        for n in ast.walk(node)
        if isinstance(n, ast.Call)
    }


@pytest.mark.parametrize("module", OVERRIDE_MODULES)
def test_no_composer_hides_in_an_override_else_branch(module: str) -> None:
    """The defect shape, banned outright.

    `if override: ... else: <compose>` means supplying an override deletes the
    entire composition. Every one of the five findings had exactly this
    structure. The composer must run unconditionally; an override then either
    replaces one field feeding it, or is added to its output.
    """
    path = DMA_DIR / module
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offenders = [
        f"{module}: composer {sorted(_calls_in_else)} reachable only when no override is set"
        for node in _override_ifs(tree)
        if node.orelse and (_calls_in_else := {c for c in _calls_in(ast.Module(body=node.orelse, type_ignores=[]))} & COMPOSERS)
    ]
    assert not offenders, "\n".join(offenders) + (
        "\n\nMove the composer out of the else so it always runs. An override replaces a FIELD "
        "(REPLACEABLE_FIELDS) or is additive() — it never stands in for the composition."
    )


@pytest.mark.parametrize("module", OVERRIDE_MODULES)
def test_an_override_branch_never_returns_uncomposed_text(module: str) -> None:
    """A `return` inside an override branch must carry the composition with it."""
    path = DMA_DIR / module
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    bad = []
    for node in _override_ifs(tree):
        for stmt in ast.walk(ast.Module(body=node.body, type_ignores=[])):
            if isinstance(stmt, ast.Return) and stmt.value is not None:
                if not ({"additive"} | COMPOSERS) & _calls_in(stmt.value):
                    bad.append(f"{module}:{getattr(stmt, 'lineno', '?')}")
    assert not bad, (
        f"override branches return text that never met the composer: {bad}. "
        f"Return additive(framing, composed), or replace a field and let the composer run."
    )


# ---------------------------------------------------------------------------
# Fit for replacement = static
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("template,field", sorted(REPLACEABLE_FIELDS.items()))
def test_a_replaceable_field_is_static(template: str, field: str) -> None:
    """A field carrying live `{slots}` cannot be replaced without dropping
    whatever those slots render — disabling content by side effect, the same
    defect one level down. Promotion into REPLACEABLE_FIELDS is gated on this."""
    data = yaml.safe_load((PROMPTS / f"{template}.yml").read_text(encoding="utf-8")) or {}
    text = data.get(field)
    assert text, f"{template}.yml has no {field} to replace"
    assert is_static(text), (
        f"{template}.{field} carries {sorted(slots(text))} — not fit for replacement. "
        f"Remove it from REPLACEABLE_FIELDS and make that override additive()."
    )


def test_no_context_integration_is_ever_declared_replaceable() -> None:
    """All three carry live slots — ASPDMA's has 22, including every prior-DMA
    summary. Replacing one is #996."""
    assert not [t for t, f in REPLACEABLE_FIELDS.items() if f == "context_integration"]


# ---------------------------------------------------------------------------
# Template data hygiene
# ---------------------------------------------------------------------------

AGENT_TEMPLATES = sorted(glob.glob("ciris_engine/ciris_templates/*.yaml"))


@pytest.mark.parametrize("template_path", AGENT_TEMPLATES)
def test_template_overrides_only_use_slots_their_dma_supplies(template_path: str) -> None:
    """An unsupplied slot is a `KeyError` at prompt-build time, in production.
    Today every shipped template happens to be safe; that is luck, not a
    guarantee, and this converts it into one."""
    data = yaml.safe_load(pathlib.Path(template_path).read_text(encoding="utf-8")) or {}
    problems = []
    for key, supplied in SUPPLIED_SLOTS.items():
        override = (data.get(key) or {}).get("user_prompt_template")
        if not override:
            continue
        used = set(re.findall(r"(?<!\{)\{([a-z_][a-z0-9_]*)\}(?!\})", override))
        missing = sorted(used - supplied)
        if missing:
            problems.append(f"{key}.user_prompt_template uses {missing}; DMA supplies {sorted(supplied)}")
    assert not problems, f"{template_path}: " + "; ".join(problems)
