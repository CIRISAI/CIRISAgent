"""Agent-template prompt-override policy — #996.

Two operations, and only two:

* **replace a field** — that field's text becomes the template's text.
* **disable a field** — that field composes as empty.

**Replacing one field must never disable another.** That is the whole policy,
and every defect here is a violation of it: an override named for one field
that swallowed the composition of several.

What each shipped override actually did before this module existed:

=======================  =====================================  ===============
override key             replaced                               fields disabled
                                                                as a side effect
=======================  =====================================  ===============
ASPDMA ``system_prompt``  ``DEFAULT_TEMPLATE`` (3 fields)        ``decision_format``,
                                                                ``closing_reminder``
CSDMA ``system_prompt``   ``get_system_message()`` (6 fields)    ``domain_principles``,
                                                                ``evaluation_steps``,
                                                                ``evaluation_criteria``,
                                                                ``response_format``,
                                                                ``response_guidance``
PDMA ``system_prompt``    ``get_system_message()`` (6 fields)    same five
ASPDMA ``user_prompt      the whole assembled user message       the entire
_template``                                                     integration layer
=======================  =====================================  ===============

The ASPDMA user case is the one that mattered most (#996): a 131 B override in
place of a ~7,932 B composition, taking the PDMA/CSDMA/DSDMA/IDMA summaries, the
conscience retry guidance, ponder notes, the final-attempt advisory and the
original task context with it. The ethical evaluation ran, produced a result,
and was discarded before the action was chosen.

**Fit for replacement = the field is static.** A field carrying live ``{slots}``
cannot be replaced without dropping whatever those slots render — that is
disabling content by side effect, in the same family. Fields that qualify are
named in :data:`REPLACEABLE_FIELDS` and re-verified static on every test run.
A field that does not qualify takes an *additive* override, which cannot
disable anything by construction.

Enforced by ``tests/ciris_engine/logic/dma/test_template_override_policy_996.py``.
"""

from __future__ import annotations

import re
from typing import Dict

#: Prompt template -> the single STATIC field a `system_prompt` override
#: replaces. Replacing it leaves every other composed field untouched.
#:
#: Deliberately absent, with reasons:
#:   * every ``context_integration`` — all three carry live slots (ASPDMA 22 of
#:     them). Replacing one would disable everything those slots render, so a
#:     ``user_prompt_template`` override is additive instead.
#:   * ``pdma_ethical.system_guidance_header`` — 8,240 B carrying
#:     ``{full_context_str}``. Replacing it drops the caller's context, so
#:     PDMA's ``system_prompt`` override is additive too.
REPLACEABLE_FIELDS: Dict[str, str] = {
    "csdma_common_sense": "system_guidance_header",
    "action_selection_pdma": "system_header",
}

#: A single-brace placeholder, ignoring `{{escaped}}` literals.
_SLOT = re.compile(r"(?<!\{)\{([a-z_][a-z0-9_]*)\}(?!\})")


def is_static(text: str) -> bool:
    """Fit for replacement only if nothing dynamic renders into it."""
    return not _SLOT.search(text or "")


def slots(text: str) -> set[str]:
    return set(_SLOT.findall(text or ""))


def additive(override_text: str, composed: str) -> str:
    """Compose an override that is not permitted to replace anything.

    The template's authored text leads — that position is why an author reaches
    for this knob — and the full composition follows, undiminished. The thought
    may appear twice, once in the authored framing and once in the structured
    composition; that is the cost of never disabling a field, and it is the
    right trade.
    """
    if not override_text:
        return composed
    if not composed:
        return override_text
    return f"{override_text}\n\n{composed}"
