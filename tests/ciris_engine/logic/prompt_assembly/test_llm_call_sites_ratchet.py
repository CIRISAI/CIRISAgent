"""Lint ratchet: every DMA / conscience LLM call goes through PromptAssembler (FSD/PROMPT_CONTEXT_PROVENANCE.md §12.1).

A call site counts as migrated when it is lexically inside ``with prompt_manifest_scope(...)``: only the assembler
produces a manifest, and the scope is what attaches it to the call's ``llm_call`` trace event. Every other call to
``call_llm_structured`` / ``_call_llm_with_budget`` in ``logic/dma`` and ``logic/conscience`` must be listed in
``unmigrated_llm_call_sites.txt``. The test fails when a NEW unmigrated site appears, and when a listed site is
migrated or gone (delete its line): the list only shrinks, to zero in Phase 3.

Site keys are ``path::Class.function::callee`` (``#n`` for the n-th in one function), stable across line churn.
"""

import ast
import pathlib
from typing import Iterator, List, Optional, Set

REPO = pathlib.Path(__file__).resolve().parents[4]
SCANNED_DIRS = ("ciris_engine/logic/dma", "ciris_engine/logic/conscience")
LLM_CALLEES = {"call_llm_structured", "_call_llm_with_budget"}
ALLOWLIST = pathlib.Path(__file__).with_name("unmigrated_llm_call_sites.txt")

#: The two funnels every stage calls through: they forward the caller's messages and never build them, so the
#: manifest scope of the caller covers them (the ContextVar flows through).
FUNNELS = {
    "ciris_engine/logic/dma/base_dma.py::BaseDMA.call_llm_structured::call_llm_structured",
    "ciris_engine/logic/conscience/core.py::_BaseConscience._call_llm_with_budget.one_attempt::call_llm_structured",
}


def _callee(node: ast.Call) -> Optional[str]:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _is_manifest_scope(with_node: ast.AST) -> bool:
    items = getattr(with_node, "items", [])
    return any(isinstance(i.context_expr, ast.Call) and _callee(i.context_expr) == "prompt_manifest_scope" for i in items)


def _sites(tree: ast.Module, rel: str) -> Iterator[tuple[str, bool]]:
    """(site key, migrated) for each LLM call in a module."""
    counts: dict[str, int] = {}

    def walk(node: ast.AST, qual: List[str], scoped: bool) -> Iterator[tuple[str, bool]]:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                yield from walk(child, qual + [child.name], scoped)
                continue
            child_scoped = scoped or (isinstance(child, (ast.With, ast.AsyncWith)) and _is_manifest_scope(child))
            if isinstance(child, ast.Call) and _callee(child) in LLM_CALLEES:
                base = f"{rel}::{'.'.join(qual) or '<module>'}::{_callee(child)}"
                counts[base] = counts.get(base, 0) + 1
                yield (base if counts[base] == 1 else f"{base}#{counts[base]}"), scoped
            yield from walk(child, qual, child_scoped)

    yield from walk(tree, [], False)


def scan(repo: pathlib.Path = REPO) -> tuple[Set[str], Set[str]]:
    """(unmigrated, migrated) site keys, funnels excluded."""
    unmigrated: Set[str] = set()
    migrated: Set[str] = set()
    for d in SCANNED_DIRS:
        for path in sorted((repo / d).rglob("*.py")):
            rel = path.relative_to(repo).as_posix()
            for key, scoped in _sites(ast.parse(path.read_text(encoding="utf-8")), rel):
                if key in FUNNELS:
                    continue
                (migrated if scoped else unmigrated).add(key)
    return unmigrated, migrated


def _allowlist() -> Set[str]:
    lines = ALLOWLIST.read_text(encoding="utf-8").splitlines()
    return {ln.strip() for ln in lines if ln.strip() and not ln.lstrip().startswith("#")}


def test_no_new_llm_call_site_bypasses_the_assembler():
    unmigrated, _ = scan()
    new = sorted(unmigrated - _allowlist())
    assert not new, (
        "LLM call sites that do not go through PromptAssembler (build segments, call inside "
        "prompt_manifest_scope(manifest)):\n  " + "\n  ".join(new)
    )


def test_the_allowlist_only_shrinks():
    unmigrated, _ = scan()
    stale = sorted(_allowlist() - unmigrated)
    assert not stale, "migrated or removed: delete these lines from unmigrated_llm_call_sites.txt:\n  " + "\n  ".join(
        stale
    )


def test_the_funnels_still_exist():
    """If a funnel is renamed the ratchet must not silently start counting it, or stop seeing its callers."""
    found: Set[str] = set()
    for d in SCANNED_DIRS:
        for path in sorted((REPO / d).rglob("*.py")):
            rel = path.relative_to(REPO).as_posix()
            found |= {k for k, _ in _sites(ast.parse(path.read_text(encoding="utf-8")), rel)}
    assert FUNNELS <= found


def test_the_scan_sees_a_scoped_call_as_migrated(tmp_path):
    """The detector itself: a call inside the scope is migrated, the same call outside is not."""
    pkg = tmp_path / "ciris_engine/logic/dma"
    pkg.mkdir(parents=True)
    (tmp_path / "ciris_engine/logic/conscience").mkdir(parents=True)
    (pkg / "x.py").write_text(
        "class X:\n"
        "    async def a(self):\n"
        "        with prompt_manifest_scope(m):\n"
        "            await self.call_llm_structured(messages=msgs)\n"
        "    async def b(self):\n"
        "        await self.call_llm_structured(messages=msgs)\n"
        "        await self.call_llm_structured(messages=msgs)\n"
    )
    unmigrated, migrated = scan(tmp_path)
    assert migrated == {"ciris_engine/logic/dma/x.py::X.a::call_llm_structured"}
    assert unmigrated == {
        "ciris_engine/logic/dma/x.py::X.b::call_llm_structured",
        "ciris_engine/logic/dma/x.py::X.b::call_llm_structured#2",
    }
