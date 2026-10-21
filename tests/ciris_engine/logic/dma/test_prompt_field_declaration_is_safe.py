"""Declaring a schema field for a working prompt key must not blank it.

Two independent bugs made adding a `PromptCollection` field actively
destructive. Both were silent — no error, no warning, the prompt just lost a
section — and they were found only because five MSASPDMA blocks disappeared when
the fields were declared.

1. `get_prompt` tried the attribute first via `hasattr`, which is True for every
   DECLARED field including one nothing populated. An unset field returned its
   None default and the `custom_prompts` fallback was never reached.

2. `PromptLoader` hand-enumerated all 26 fields in the constructor call, so a new
   field was set nowhere — and the `custom_prompts` fallback explicitly skips
   anything already in `model_fields`, so the key was excluded from there too.

Together: a YAML key that worked (via custom_prompts) stopped working the moment
someone declared a field for it. That is the worst shape a change can have — it
punishes the person doing the tidier thing, and says nothing.

The fix is one rule in each place: a field that holds nothing is not an answer,
and the loader derives its fields from the schema instead of a parallel list.
"""

from __future__ import annotations

import pytest

from ciris_engine.logic.dma.prompt_loader import get_prompt_loader
from ciris_engine.schemas.dma.prompts import PromptCollection

BASE = dict(component_name="test", description="test collection")

# Every template shipped in ciris_engine/logic/dma/prompts/.
TEMPLATES = [
    "pdma_ethical",
    "csdma_common_sense",
    "dsdma_base",
    "idma",
    "action_selection_pdma",
    "tsaspdma",
    "dsaspdma",
    "msaspdma",
]

# The MSASPDMA blocks that vanished. Named explicitly because this is the
# regression, not a hypothetical.
MSASPDMA_BLOCKS = [
    "memory_model",
    "addressing_convention",
    "attribute_convention",
    "scope_convention",
    "memory_prohibitions",
    "system_guidance_header",
    "evaluation_steps",
    "context_integration",
    "response_format",
    "closing_reminder",
]


def test_unset_field_does_not_shadow_custom_prompts() -> None:
    """Bug 1, at its smallest."""
    pc = PromptCollection(**BASE, custom_prompts={"taxonomy_text": "FROM CUSTOM"})
    assert pc.get_prompt("taxonomy_text") == "FROM CUSTOM", (
        "a declared-but-unpopulated field returned its None default and hid the "
        "custom_prompts entry that actually had the content"
    )


def test_populated_field_still_wins_over_custom_prompts() -> None:
    """The precedence that was there for a reason must survive the fix."""
    pc = PromptCollection(
        **BASE, taxonomy_text="FROM FIELD", custom_prompts={"taxonomy_text": "FROM CUSTOM"}
    )
    assert pc.get_prompt("taxonomy_text") == "FROM FIELD"


def test_unknown_key_is_still_none() -> None:
    assert PromptCollection(**BASE).get_prompt("not_a_prompt") is None


@pytest.mark.parametrize("block", MSASPDMA_BLOCKS)
def test_every_msaspdma_block_loads(block: str) -> None:
    """Bug 2, as the user would meet it: a block silently missing from a prompt."""
    template = get_prompt_loader(language="en").load_prompt_template("msaspdma")
    value = template.get_prompt(block)
    assert value, f"msaspdma.{block} loaded empty — the block is missing from the prompt"


@pytest.mark.parametrize("name", TEMPLATES)
def test_declared_yaml_keys_reach_the_collection(name: str) -> None:
    """The general rule, across every shipped template.

    Any string key in the YAML that the schema declares must be readable through
    `get_prompt`. This is what the loader's hand-written field list could not
    guarantee, because it was a second copy of the schema kept in sync by hand.
    """
    import yaml
    from pathlib import Path

    path = Path("ciris_engine/logic/dma/prompts") / f"{name}.yml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    template = get_prompt_loader(language="en").load_prompt_template(name)

    skip = {"component_name", "description", "version", "accord_header", "supports_agent_modes"}
    for key, value in raw.items():
        if key in skip or not isinstance(value, str) or "_mode_" in key:
            continue
        assert template.get_prompt(key), (
            f"{name}.yml declares {key!r} but get_prompt returns nothing — the block "
            f"is silently absent from the composed prompt"
        )
