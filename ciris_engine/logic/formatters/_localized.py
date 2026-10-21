"""Locale-bound label lookup for the prompt formatters (#991).

Every ``prompts.formatters.*`` key is a **bare label** — ``"System Snapshot"``,
``"Pending Tasks"``, ``"Agent ID"`` — never a decorated line. The decoration
(``=== … ===``, the trailing ``:``, the 🚨 banners, the value interpolation)
stays in Python, because that is layout, not text. Only the words are
translated, so a locale bundle can never break the block structure the DMAs and
the #972 goldens depend on.

Why a helper rather than raw ``get_string`` at each site: binding the localizer
once per formatter call resolves the language exactly once for a whole block,
and gives the research-override scanner
(``research_overrides._scan_module_for_keys``) a call name it already
recognises — ``localizer`` — so all 57 keys enter
``scan_reachable_string_keys()`` automatically instead of needing a hand-kept
list that can drift.

Every call site passes the current English text as the ``default``. That is the
byte-identity contract: at ``en`` the bundle value and the default are the same
string, so English output cannot move. The default is the floor if a key is ever
removed from the bundle, not a second source of truth.
"""

from typing import Callable, Optional

#: Prefix shared by every key this module serves. Call sites still spell the
#: FULL key literal — the override scanner only follows literal keys, and a
#: dynamically-joined prefix would make all 57 invisible to it again.
KEY_PREFIX = "prompts.formatters."


def label_localizer(language: Optional[str] = None) -> Callable[..., str]:
    """A ``(key, default) -> str`` lookup bound to one language.

    ``language`` is the caller's explicit choice; ``None`` falls through to
    ``get_preferred_language()`` (``CIRIS_PREFERRED_LANGUAGE``), matching what
    ``format_core_identity_block`` already does for ``prompts.identity_block``.
    """
    # Lazy import: the formatters package is imported by low-level context
    # builders, and the util layer imports back into it.
    from ciris_engine.logic.utils.localization import get_localizer, get_preferred_language

    return get_localizer(language or get_preferred_language())
