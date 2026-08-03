"""#995 — the finding under the findings: **no prompt-bound text reaches a model
except through a loader.**

Six defects found this week, one shape. Every one is *a seam exists and
something bypasses it*:

=================================  ==================================================
seam                               bypass
=================================  ==================================================
``get_accord_text()``              ``conscience/core.py`` imported the ACCORD_TEXT constant
``{conscience_guidance}`` renderer ``_build_main_user_content`` short-circuits to the template
``__pydantic_extra__``             ``_extract_overrides`` copied ``__dict__``
``prompt_loader.get_user_message`` ``tsaspdma`` builds an inline f-string
``lang_code``                      ``get_string`` returned the override first
scanner prefix list                ``handlers.*`` keys
=================================  ==================================================

That is not six bugs. It is one failure mode with six instances, and patching
instances is whack-a-mole: the seventh arrives the next time someone writes a
prompt in Python because it was quicker than adding a YAML key.

So this test asserts the *rule*, mechanically: text that becomes the content of
an LLM message must come from a loader — not a string literal, not an f-string,
not a module constant bound at import. Two properties follow for free, and both
are things the codebase already promises elsewhere and could not enforce:

* **Localizable.** A loader resolves per-locale; an f-string is English forever.
  That is #991, #992 and #994 in one line.
* **Overridable.** A loader is where the research seam lives. A constant bound
  at import can never be reached by a manifest, which is #995 P0-1 — the arm
  that replaced the accord and still shipped it to all four consciences.

**Scope, stated honestly.** This is a syntactic check with one level of local
assignment resolution. It catches the shape that produced all six findings —
literal text flowing into a message — and it will not catch text laundered
through a helper function, a class attribute, or a container. It is a floor,
not a proof. The `KNOWN_BYPASSES` ratchet below carries what is left, each with
an issue, and may only shrink.
"""

from __future__ import annotations

import ast
import pathlib
from typing import Dict, List, Optional, Set, Tuple

import pytest

LOGIC = pathlib.Path("ciris_engine/logic")

#: Message constructors: `LLMMessage(role=..., content=...)` and the raw dict
#: form `{"role": ..., "content": ...}` that the DMAs append to a message list.
MESSAGE_CLASSES = {"LLMMessage"}

#: Names that are module-level prompt TEXT. Binding one of these at import is
#: the P0-1 shape: the value is captured before any seam can intercept it.
PROMPT_TEXT_CONSTANTS = {
    "ACCORD_TEXT",
    "ACCORD_TEXT_COMPRESSED",
}

#: Paths that send LLM messages which are NOT the agent reasoning. The setup
#: adapter probes a provider with `{"role": "user", "content": "Hi"}` and
#: `max_tokens=1` to check that a key and endpoint work. That is a credential
#: check, not a prompt: nobody reads it, it carries no doctrine, localizing it
#: would be meaningless, and a research manifest has no business reaching it.
#:
#: A category exemption, deliberately narrow and stated rather than parked in
#: the ratchet below — the ratchet is for debt, and this is not debt. Widening
#: this tuple is a review-worthy act.
NON_REASONING_PATHS = ("logic/adapters/api/routes/setup/",)

#: Sites that still bypass a loader, each with the issue that closes it.
#: A ratchet: it may shrink, never grow. A new bypass is a failure.
KNOWN_BYPASSES: Dict[str, str] = {
    "logic/dma/tsaspdma.py:_create_correction_mode_messages": (
        "CIRISAgent#995 P1-4 — the 523 B correction scaffold is an inline f-string that never "
        "passes through get_user_message; the equivalent literal in ActionSelectionContextBuilder "
        "was routed out by #974 step 1 and this one was missed. Pinned in RESIDUE_SITES so it "
        "cannot drift mid-campaign, but still unreachable by any manifest key."
    ),
}


def _py_files() -> List[pathlib.Path]:
    return sorted(
        p
        for p in LOGIC.rglob("*.py")
        if "__pycache__" not in p.parts
        and not any(skip in p.as_posix() for skip in NON_REASONING_PATHS)
    )


def _enclosing_function(tree: ast.Module) -> Dict[ast.AST, str]:
    """Map every node to the name of the function that contains it."""
    owner: Dict[ast.AST, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for sub in ast.walk(node):
                owner.setdefault(sub, node.name)
    return owner


def _literal_assignments(tree: ast.Module) -> Dict[Tuple[str, str], ast.AST]:
    """(function, variable) -> the literal/f-string it was assigned, if any.

    One level of resolution. It is what catches a triple-quoted f-string
    assigned to `user_message` and then appended as
    `{"role": ..., "content": user_message}` — the tsaspdma shape.
    """
    found: Dict[Tuple[str, str], ast.AST] = {}
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(fn):
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if isinstance(target, ast.Name) and isinstance(node.value, (ast.JoinedStr, ast.Constant)):
                if isinstance(node.value, ast.Constant) and not isinstance(node.value.value, str):
                    continue
                found[(fn.name, target.id)] = node.value
    return found


def _content_expressions(tree: ast.Module) -> List[Tuple[ast.AST, ast.AST]]:
    """Every expression used as the `content` of an LLM message."""
    out: List[Tuple[ast.AST, ast.AST]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name in MESSAGE_CLASSES:
                for kw in node.keywords:
                    if kw.arg == "content":
                        out.append((node, kw.value))
        elif isinstance(node, ast.Dict):
            keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
            if "role" in keys and "content" in keys:
                for key, value in zip(node.keys, node.values):
                    if isinstance(key, ast.Constant) and key.value == "content":
                        out.append((node, value))
    return out


def _classify(
    expr: ast.AST, fn_name: str, literals: Dict[Tuple[str, str], ast.AST]
) -> Optional[str]:
    """None = routed (or unprovable, which this test treats as routed).
    A string = why it is a bypass."""
    if isinstance(expr, ast.JoinedStr):
        return "an f-string built in Python — not localizable, not overridable"
    if isinstance(expr, ast.Constant) and isinstance(expr.value, str) and expr.value.strip():
        return "a string literal — not localizable, not overridable"
    if isinstance(expr, ast.Name):
        if expr.id in PROMPT_TEXT_CONSTANTS:
            return f"the module constant {expr.id}, bound at import and past every seam"
        if (fn_name, expr.id) in literals:
            kind = "f-string" if isinstance(literals[(fn_name, expr.id)], ast.JoinedStr) else "literal"
            return f"a local {kind} assigned to `{expr.id}` — not localizable, not overridable"
    return None


def _violations() -> Dict[str, str]:
    found: Dict[str, str] = {}
    for path in _py_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:  # pragma: no cover - defensive
            continue
        owner = _enclosing_function(tree)
        literals = _literal_assignments(tree)
        for site, expr in _content_expressions(tree):
            fn_name = owner.get(site, "<module>")
            why = _classify(expr, fn_name, literals)
            if why:
                rel = path.relative_to(LOGIC.parent).as_posix()
                found[f"{rel}:{fn_name}"] = why
    return found


def test_no_prompt_text_reaches_a_model_except_through_a_loader() -> None:
    unexpected = {k: v for k, v in _violations().items() if k not in KNOWN_BYPASSES}
    assert not unexpected, (
        "prompt text reaches an LLM message without passing through a loader:\n"
        + "\n".join(f"  {k}\n      {v}" for k, v in sorted(unexpected.items()))
        + "\n\nRoute it through the prompt loader (a YAML key + get_system_message / "
        "get_user_message / get_string). Text written in Python is English forever and "
        "invisible to every research manifest — the shape behind #991, #992, #994 and #995 P0-1."
    )


def test_no_module_that_builds_messages_binds_prompt_text_at_import() -> None:
    """The P0-1 shape, checked directly.

    `from ...constants import ACCORD_TEXT` captures the value at import, so the
    corpus substitution inside `get_accord_text()` can never intercept it.
    Four faculties took the accord that way: an arm that blanked the accord
    still delivered ~722 KB/thought of it, and reported clean.
    """
    offenders: Dict[str, Set[str]] = {}
    for path in _py_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:  # pragma: no cover - defensive
            continue
        if not _content_expressions(tree):
            continue
        bound = {
            alias.asname or alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        } & PROMPT_TEXT_CONSTANTS
        if bound:
            offenders[path.relative_to(LOGIC.parent).as_posix()] = bound
    assert not offenders, (
        f"modules that build LLM messages bind prompt text at import: {offenders}. "
        f"Call the accessor (get_accord_text('force_full')) so the research seam applies."
    )


def test_the_bypass_ratchet_only_turns_one_way() -> None:
    """A debt register with nothing asserting on its size becomes a permanent
    exemption list. These shrink as the issues close."""
    assert len(KNOWN_BYPASSES) <= 1, f"KNOWN_BYPASSES grew to {sorted(KNOWN_BYPASSES)} — route it, don't park it"
    assert all(v.startswith("CIRISAgent#") for v in KNOWN_BYPASSES.values())


@pytest.mark.parametrize("known", sorted(KNOWN_BYPASSES))
def test_every_parked_bypass_still_exists(known: str) -> None:
    """If a parked site is fixed, this fails and forces the entry out — the
    ratchet cannot silently carry a stale exemption that would let a NEW
    bypass hide behind the same key."""
    assert known in _violations(), f"{known} no longer bypasses a loader — remove it from KNOWN_BYPASSES"
