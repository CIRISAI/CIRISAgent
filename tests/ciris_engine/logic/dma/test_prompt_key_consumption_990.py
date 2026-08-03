"""#990 — every populated prompt-YAML key must be consumed by its composer.

The defect this locks out, stated plainly: ``DMAPromptLoader.get_system_message``
is an **allowlist**. It renders a fixed set of fields off the ``PromptCollection``
and silently drops every other populated key. Adding a key to a prompt YAML
therefore *looks* like it works — the YAML parses, the loader accepts it, the
field is present on the collection, `localization` dutifully translates it into
29 languages — and it renders nowhere.

Three fields lived that way, undetected, across many releases:

======================================  ===========  ==========
field                                   inert since  age
======================================  ===========  ==========
``tsaspdma.closing_reminder``           v1.9.5       ~6 months
``dsdma_base.response_format``          v2.3.1       ~4 months
``idma.closing_reminder``               v2.6.0       ~3.5 months
======================================  ===========  ==========

``idma.closing_reminder`` is the propaganda-pattern final check — the block that
forces ``k_eff = 1.0``, ``phase = "rigidity"``, ``fragility_flag = TRUE`` on
contested geopolitical claims. ``dsdma_base.response_format`` is DSDMA's
LANGUAGE RULES block. Neither ever reached a model.

Why nothing caught it: existing tests assert *loading* (the field is on the
collection), never *rendering* (the text is in a composed message). Golden
tests capture composed output, but a golden written after a field was already
inert locks the absence in as correct — goldens detect change, not the absence
of something that was never there. And 29 translated copies of a block read, to
any reviewer, as proof that the block ships.

So this test asserts the inverse property nothing else does: for each template,
every populated key is either referenced by the DMA that owns it, composed by
the shared composer that DMA routes through, recognised metadata, or named in
``INERT_BY_DESIGN`` with a reason.

**Deliberately a lower bound.** Reachability is over-approximated (any matching
attribute access *or* string literal in the owning module counts), so the test
can produce a false PASS but never a false FAIL. A tighter analysis would need
to track composition data flow; this one is cheap, has no runtime dependency,
and catches the whole "authored but never wired in" class — which is the one
that actually bit us.
"""

from __future__ import annotations

import ast
import pathlib
from typing import Dict, Set

import pytest
import yaml

DMA_DIR = pathlib.Path("ciris_engine/logic/dma")
PROMPTS_DIR = DMA_DIR / "prompts"
LOADER = DMA_DIR / "prompt_loader.py"

#: Collection bookkeeping, not prompt text — never composed, correctly so.
METADATA_KEYS = {
    "component_name",
    "description",
    "version",
    "accord_header",
    "accord_mode",
    "supports_agent_modes",
    "agent_variations",
    "custom_prompts",
    "required_variables",
    "optional_variables",
}

#: Populated keys that are genuinely not composed, each with the reason it is
#: allowed to stay that way. Empty is the goal. A key belongs here only with
#: positive evidence it should exist and not render — "the probe says dark" is
#: not evidence, it is the question.
INERT_BY_DESIGN: Dict[str, str] = {}

#: Keys this test PROVED unwired, kept green under an open issue rather than
#: silently deleted or silently fixed. This is a ratchet: it may shrink, never
#: grow. A new unwired key is a failure, not an entry here.
#:
#: These two are a different and nastier shape than the #990 originals. The YAML
#: field exists, is translated into all 29 locales — and ``tsaspdma.py`` builds
#: the same text as a hardcoded English f-string (lines 381-388) and passes THAT
#: into the template slot. So the localized versions are shadowed: every user in
#: every language receives the English. A missing block is invisible; a block
#: silently served in the wrong language looks like it works.
KNOWN_UNWIRED: Dict[str, str] = {
    "tsaspdma.context_enrichment_section": (
        "CIRISAgent#991 — shadowed by the hardcoded English f-string at tsaspdma.py:383-388; "
        "all 29 localized copies are dead"
    ),
    "tsaspdma.tool_documentation_section": (
        "CIRISAgent#991 — built by _format_tool_documentation() in Python instead of read from "
        "the localized template"
    ),
    # Read NOWHERE in the repository — not by the evaluator, not by the context
    # builder, not by the loader (PromptCollection has no such field, so it is
    # dropped at load). This is the tool-hallucination guard: "Use the EXACT
    # tool name from the 'Available tools' list. Do NOT invent or modify tool
    # names." It sits in the action-selection template, the highest-consequence
    # prompt in the pipeline, and has never been sent to a model.
    "action_selection_pdma.tool_selection_guidance": (
        "CIRISAgent#993 — tool-hallucination guard, unread repo-wide; wiring it belongs in "
        "context_builder.py and is a deliberate behaviour change, not a cleanup"
    ),
}

#: Locale files carrying a key with no base counterpart. Unreachable by
#: construction (``PromptCollection`` has no such field), so the text renders
#: for nobody. Not deleted here: the content may belong in a real field, and
#: deciding that is a translation review, not a cleanup.
#: All four are a LANGUAGE RULES block a translator added where the English
#: base has none — independently, in three languages. That is not four typos;
#: it is four translators reaching the same conclusion that the base template
#: is missing something, and inventing a key to hold it. The key renders for
#: nobody, so the gap they were patching is still open.
KNOWN_LOCALE_ORPHANS: Dict[str, str] = {
    "csdma_common_sense.hi.language_rules": "CIRISAgent#992 — no base key, no schema field",
    "tsaspdma.hi.language_rules": "CIRISAgent#992 — no base key, no schema field",
    "tsaspdma.ja.language_rules": "CIRISAgent#992 — no base key, no schema field",
    "action_selection_pdma.it.language_rules_guidance": "CIRISAgent#992 — no base key, no schema field",
}

#: Methods on the shared loader whose ``template_data.<field>`` reads define
#: what a DMA gets for free by routing through them.
SHARED_COMPOSERS = ("get_system_message", "get_user_message")


def _parse(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _shared_composer_fields() -> Set[str]:
    """Fields the shared composer renders, read out of its AST.

    Derived rather than listed so the inventory cannot drift: wire a new field
    into ``get_system_message`` and it counts here automatically; add a YAML key
    without wiring it and this test fails.
    """
    fields: Set[str] = set()
    for node in ast.walk(_parse(LOADER)):
        if not isinstance(node, ast.FunctionDef) or node.name not in SHARED_COMPOSERS:
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name) and sub.value.id == "template_data":
                fields.add(sub.attr)
    return fields


def _module_names(path: pathlib.Path) -> Set[str]:
    """Every attribute name and string literal in a module.

    The over-approximation described in the module docstring: a field named in
    a docstring counts as referenced. That is the safe direction — this test
    must never fail on a field that IS composed.
    """
    names: Set[str] = set()
    for node in ast.walk(_parse(path)):
        if isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            names.add(node.value)
    return names


def _collaborators(path: pathlib.Path) -> Set[pathlib.Path]:
    """DMA-internal modules the owner delegates to, via its relative imports.

    A DMA does not have to read its own YAML fields in its own file.
    ``ActionSelectionPDMAEvaluator`` delegates composition to
    ``.action_selection`` — ``context_builder.py`` and
    ``action_instruction_generator.py`` do the reading. Those are part of the
    owner's composition surface and must count.

    Scoped to what the owner actually imports rather than to the whole package:
    "somebody under logic/dma/ mentions this name" would make
    ``idma.closing_reminder`` look reachable because *action_selection_pdma*
    reads a field of that name — which is the exact false PASS that let the
    original defect live for three releases.
    """
    found: Set[pathlib.Path] = set()
    for node in ast.walk(_parse(path)):
        if not isinstance(node, ast.ImportFrom) or not node.level or not node.module:
            continue
        target = DMA_DIR.joinpath(*node.module.split("."))
        if target.is_dir():
            found.update(target.rglob("*.py"))
        elif target.with_suffix(".py").is_file():
            found.add(target.with_suffix(".py"))
    return found


def _calls_shared_composer(path: pathlib.Path) -> bool:
    """True if the module actually CALLS the shared composer.

    An AST call check, not a grep: a comment or docstring mentioning
    ``get_system_message`` must not grant a module the composer's whole field
    set. (This is not hypothetical — adding a comment naming the method was
    enough to make a `grep -l` sweep report the wrong answer while writing
    this.)
    """
    for node in ast.walk(_parse(path)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in SHARED_COMPOSERS:
            return True
    return False


def _template_owners() -> Dict[str, pathlib.Path]:
    """template name -> owning DMA module, derived from the source.

    Two binding forms: ``self._prompt_template_name = "<name>"`` (loader path)
    and ``PROMPT_FILE = ... / "<name>.yml"`` (BaseDMA path).
    """
    owners: Dict[str, pathlib.Path] = {}
    for path in sorted(DMA_DIR.glob("*.py")):
        for node in ast.walk(_parse(path)):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                is_template_name = (
                    isinstance(target, ast.Attribute) and target.attr == "_prompt_template_name"
                ) or (isinstance(target, ast.Name) and target.id == "PROMPT_FILE")
                if not is_template_name:
                    continue
                for sub in ast.walk(node.value):
                    if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                        owners[sub.value.removesuffix(".yml")] = path
    return owners


def _populated_keys(path: pathlib.Path) -> Set[str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {k for k, v in data.items() if isinstance(v, str) and v.strip()}


BASE_TEMPLATES = sorted(p.stem for p in PROMPTS_DIR.glob("*.yml"))


def test_every_template_has_an_identifiable_owner() -> None:
    """A prompt file no DMA claims is 100% inert by construction."""
    owners = _template_owners()
    orphans = [t for t in BASE_TEMPLATES if t not in owners]
    assert not orphans, f"prompt templates with no owning DMA: {orphans}"


@pytest.mark.parametrize("template", BASE_TEMPLATES)
def test_every_populated_key_is_consumed(template: str) -> None:
    owners = _template_owners()
    owner = owners.get(template)
    assert owner is not None, f"{template}.yml has no owning DMA module"

    reachable = _module_names(owner) | METADATA_KEYS
    for collaborator in _collaborators(owner):
        reachable |= _module_names(collaborator)
    if _calls_shared_composer(owner):
        reachable |= _shared_composer_fields()

    known = {k.split(".", 1)[1] for k in KNOWN_UNWIRED if k.startswith(f"{template}.")}
    unconsumed = sorted(_populated_keys(PROMPTS_DIR / f"{template}.yml") - reachable - set(INERT_BY_DESIGN) - known)
    assert not unconsumed, (
        f"{template}.yml populates {unconsumed}, and {owner.name} never reads them — "
        f"neither directly nor via the shared composer it routes through. The text is "
        f"authored, translated, and never sent to a model. Wire it into the composer, "
        f"or add it to INERT_BY_DESIGN with the reason it should exist and not render."
    )


@pytest.mark.parametrize("template", BASE_TEMPLATES)
def test_locales_introduce_no_keys_the_base_lacks(template: str) -> None:
    """A locale key with no base counterpart is unreachable in exactly the same
    way, and worse: it renders for some users and not others. Translation drift
    is the likely cause, so catch it at the same boundary."""
    base_keys = set(yaml.safe_load((PROMPTS_DIR / f"{template}.yml").read_text(encoding="utf-8")) or {})
    offenders: Dict[str, Set[str]] = {}
    for localized in sorted(PROMPTS_DIR.glob(f"localized/*/{template}.yml")):
        locale = localized.parent.name
        extra = {
            key
            for key in set(yaml.safe_load(localized.read_text(encoding="utf-8")) or {}) - base_keys
            if f"{template}.{locale}.{key}" not in KNOWN_LOCALE_ORPHANS
        }
        if extra:
            offenders[locale] = extra
    assert not offenders, f"{template}.yml: locales carry keys the base does not: {offenders}"


def test_the_unwired_ratchet_only_turns_one_way() -> None:
    """Both inventories are debt registers, and debt registers rot into
    permanent exemption lists unless something asserts on their size. These
    counts come down as the issues close; a rise means a key was parked here
    instead of wired in."""
    assert len(KNOWN_UNWIRED) <= 3, f"KNOWN_UNWIRED grew to {sorted(KNOWN_UNWIRED)} — wire it, don't park it"
    assert len(KNOWN_LOCALE_ORPHANS) <= 4, f"KNOWN_LOCALE_ORPHANS grew to {sorted(KNOWN_LOCALE_ORPHANS)}"
    assert all(v.startswith("CIRISAgent#") for v in {**KNOWN_UNWIRED, **KNOWN_LOCALE_ORPHANS}.values()), (
        "every parked key needs a tracking issue — an unexplained exemption is how the original "
        "three-release defect stayed invisible"
    )
