"""The research gate's shadow map must track the DMAs' actual override policy.

`assert_no_template_conflict` refuses a manifest whose keys an AgentTemplate
`*_overrides` block would beat. To do that it needs to know what a block ACTUALLY
beats — and it used to answer from a hand-written table.

That table described the pre-#996 world, where a `system_prompt` override was
returned in place of `get_system_message()` and therefore disabled all six
composed fields. #996 made overrides FIELD-scoped: a `system_prompt` replaces one
static field, and any field carrying live slots takes an *additive* override
instead, which cannot disable anything by construction.

The table was never updated. The gate went on refusing configurations that are
provably safe — including `pdma_ethical.system_guidance_header`, which PDMA
composes ADDITIVELY, and which a live research campaign was varying. The campaign
was told its manifest conflicted with a template that does not beat it, and the
only remedies offered were to drop the varied key or run a template CIRIS does
not ship.

Two maps that must agree, one silently stale, refusing correct work in the name
of safety. So the map is now derived, and these tests hold it to the derivation.
"""

from __future__ import annotations

import pytest

from ciris_engine.logic.dma.template_overrides import REPLACEABLE_FIELDS
from ciris_engine.logic.utils.research_overrides import (
    _TEMPLATE_OVERRIDE_BASE,
    _template_override_shadows,
)


def test_shadow_map_is_derived_from_replaceable_fields() -> None:
    """A shadow exists only where a replacement really happens."""
    shadows = _template_override_shadows()
    assert set(shadows) == set(_TEMPLATE_OVERRIDE_BASE)

    for attr, (base, fields) in shadows.items():
        replaced = REPLACEABLE_FIELDS.get(base)
        if replaced is None:
            assert fields == {}, (
                f"{attr} targets {base}, which is NOT in REPLACEABLE_FIELDS — its "
                f"override is additive and can shadow nothing, but the map claims {fields}"
            )
        else:
            assert fields == {"system_prompt": (replaced,)}, (
                f"{attr} must shadow exactly the one field the DMA replaces ({replaced})"
            )


def test_user_prompt_template_shadows_nothing() -> None:
    """All three `context_integration` fields carry live slots, so the override
    is additive. A `user_prompt_template` entry in the shadow map would refuse
    manifests over a replacement that never happens."""
    for _attr, (_base, fields) in _template_override_shadows().items():
        assert "user_prompt_template" not in fields


def test_pdma_system_guidance_header_is_not_shadowed() -> None:
    """The regression that blocked a live campaign.

    `pdma_ethical.system_guidance_header` is 8,240 B carrying `{full_context_str}`.
    PDMA composes the override alongside it rather than replacing it, precisely so
    the caller's context is not dropped — so a manifest varying this key does not
    conflict with a template that sets `pdma_overrides.system_prompt`.
    """
    _base, fields = _template_override_shadows()["pdma_overrides"]
    shadowed = fields.get("system_prompt", ())
    assert "system_guidance_header" not in shadowed
    assert fields == {}, "PDMA's system_prompt override is additive; it shadows nothing"


def test_genuine_replacements_are_still_refused() -> None:
    """Loosening the map must not disarm it.

    CSDMA and ASPDMA really do replace one static field each. Those conflicts are
    real and must keep being refused, or the manifest is silently beaten — the
    failure the gate exists to prevent.
    """
    shadows = _template_override_shadows()
    assert shadows["csdma_overrides"][1] == {"system_prompt": ("system_guidance_header",)}
    assert shadows["action_selection_pdma_overrides"][1] == {"system_prompt": ("system_header",)}


@pytest.mark.parametrize("base,expected_replaced", sorted(REPLACEABLE_FIELDS.items()))
def test_every_replaceable_field_has_a_shadow_entry(base: str, expected_replaced: str) -> None:
    """The derivation must not silently drop a real replacement.

    If a DMA gains a replaceable field, the gate has to start refusing manifests
    that name it — automatically, without anyone remembering this file exists.
    """
    matching = [
        fields
        for attr, (b, fields) in _template_override_shadows().items()
        if b == base
    ]
    assert matching, f"REPLACEABLE_FIELDS names {base} but no *_overrides block maps to it"
    assert matching[0] == {"system_prompt": (expected_replaced,)}
