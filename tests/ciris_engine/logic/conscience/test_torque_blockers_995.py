"""#995 — the three RATCHET findings that would make an ablation measure wrong.

Each test below fails on the code as it stood at `v2.9.9-stable`.

P0-1 is the one that matters most. `conscience/core.py` imported the module
constant ``ACCORD_TEXT`` and injected it as a system message at four sites, one
per epistemic faculty. The research corpus substitution lives *inside*
``get_accord_text()``; a direct constant reference never enters that function.
So ``corpus:accord.*`` could not reach any faculty and ``ACCORD_MODE`` could not
blank them: **an arm that replaced or removed the accord still delivered the
full accord to all four consciences** — ~722 KB/thought of the treatment held
constant across a c−b contrast, reporting clean. Not a coverage gap. A
value-ablation arm that does not ablate values.
"""

from __future__ import annotations

import ast
import glob
import pathlib

import pytest
import yaml

CORE = pathlib.Path("ciris_engine/logic/conscience/core.py")


def _calls(path: pathlib.Path, func: str) -> list[ast.Call]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == func
    ]


def test_conscience_does_not_bind_the_accord_constant() -> None:
    """The import itself is the defect: binding at import time is what takes
    the value out of reach of the override seam. Assert on the import, not on
    the call sites, because re-introducing the import is how this regresses."""
    tree = ast.parse(CORE.read_text(encoding="utf-8"), filename=str(CORE))
    bound = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "ACCORD_TEXT" not in bound, (
        "conscience/core.py binds ACCORD_TEXT at import — the corpus override applies inside "
        "get_accord_text(), so a bound constant is unreachable by any manifest"
    )


def test_all_four_faculties_take_the_accord_through_the_seam() -> None:
    """Four faculties: entropy, coherence, optimization veto, epistemic humility."""
    calls = _calls(CORE, "get_accord_text")
    assert len(calls) == 4, f"expected 4 seam-routed accord injections, found {len(calls)}"


def test_the_seam_call_forces_full_not_the_default_mode() -> None:
    """`force_full` is load-bearing and easy to get wrong.

    ACCORD_MODE defaults to "compressed", so a bare ``get_accord_text()`` would
    hand the faculties the 6,190-char compressed slice in place of the
    128,302-char polyglot canon — a 95% cut to what the consciences judge
    against, which is a far worse bug than the one being fixed. The polyglot
    rationale at core.py is about language, not overridability; force_full
    keeps it exactly.
    """
    for call in _calls(CORE, "get_accord_text"):
        assert call.args, "get_accord_text() called with no mode — defaults to compressed"
        arg = call.args[0]
        assert isinstance(arg, ast.Constant) and arg.value == "force_full", (
            f"accord injected with mode={getattr(arg, 'value', '<expr>')!r}; must be 'force_full' "
            f"or the faculties silently lose 95% of the canon"
        )


def test_force_full_is_byte_identical_with_the_gate_closed() -> None:
    """Production must not move. The whole point is that the seam is a no-op
    until a manifest is active."""
    from ciris_engine.logic.utils.constants import ACCORD_TEXT, get_accord_text

    assert get_accord_text("force_full") == ACCORD_TEXT


# ---------------------------------------------------------------------------
# P0-2 — template prompt overrides silently discarded
# ---------------------------------------------------------------------------

TEMPLATES = sorted(glob.glob("ciris_engine/ciris_templates/*.yaml"))


@pytest.mark.parametrize("template_path", TEMPLATES)
def test_every_declared_template_override_survives_extraction(template_path: str) -> None:
    """`__dict__` holds DECLARED fields only under Pydantic v2; with
    ``extra="allow"`` the undeclared keys live in ``__pydantic_extra__``.

    Since template prompt overrides are free-form YAML keys, every template's
    `system_header` and bespoke guidance was dropped, and five templates
    (echo, echo-core, echo-speculative, sage, scout) extracted to `{}` —
    losing their overrides entirely. A template that configures the agent's
    prompts and has no effect is worse than one that cannot: the operator
    reads the YAML and believes it applied.
    """
    from ciris_engine.logic.runtime.identity_manager import IdentityManager
    from ciris_engine.schemas.config.agent import ActionSelectionOverrides

    raw = (yaml.safe_load(pathlib.Path(template_path).read_text(encoding="utf-8")) or {}).get(
        "action_selection_pdma_overrides"
    )
    if not raw:
        pytest.skip("template declares no action-selection overrides")

    extracted = IdentityManager._extract_overrides(None, ActionSelectionOverrides(**raw))  # type: ignore[arg-type]
    missing = sorted(set(raw) - set(extracted))
    assert not missing, f"{template_path}: declared overrides silently discarded: {missing}"


# ---------------------------------------------------------------------------
# P1-4 — the correction scaffold is pinned
# ---------------------------------------------------------------------------


def test_the_tsaspdma_correction_scaffold_is_pinned() -> None:
    """`tsaspdma_correction.user` is reachable by no override key — overriding
    all 101 keys moves 34 of 35 blocks and leaves this one byte-identical.

    Being outside the manifest is a coverage gap. Being outside `residue_digest`
    as well meant it could drift mid-campaign without stopping the run, which is
    exactly what the digest exists to prevent.
    """
    from ciris_engine.logic.utils.research_overrides import RESIDUE_SITES

    assert (
        "logic/dma/tsaspdma.py",
        "TSASPDMAEvaluator._create_correction_mode_messages",
    ) in RESIDUE_SITES
