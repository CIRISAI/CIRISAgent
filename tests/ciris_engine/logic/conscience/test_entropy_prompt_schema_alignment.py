"""Localized entropy_conscience.yml prompts must agree with the
``EntropyResult`` Pydantic schema. This catches the regression where
prompts ask the LLM for a list field while the Python schema forbids
non-flat shapes — a class of bug that's invisible until the LLM bus
fails structured-output validation under load.

What this guards against:

- The English prompt was migrated to flat ``alternative_1/2/3`` fields
  (2.7.2) but localized prompts could be left on the old ``alternative_
  meanings: list[string]`` form. Pydantic ``EntropyResult`` has
  ``extra="forbid"`` so a list-shaped output from a localized run
  would fail validation, every time, silently degrading non-English
  consciences. The previous shape-bug shipped to all 28 non-English
  locales before this test existed; this test exists so that doesn't
  recur.

- Flat-mode locales (declared by listing one of the flat field names
  in the body) must list ALL three flat fields in their schema spec.
  A locale that mentions ``alternative_1`` but forgets ``alternative_3``
  would cause one alternative to never be requested.

- pt/ru/sw locales are still on the v1 single-key prompt ("entropy"
  field only); they're explicitly excluded from the flat-fields
  assertion. Their output is accepted by the new schema thanks to
  field defaults on the alt fields. When they're ported to v2 self-
  resampling, remove them from `_V1_GRANDFATHERED` and the test will
  enforce flat-fields parity automatically.
"""

from __future__ import annotations

from pathlib import Path
from typing import Set

import pytest
import yaml

LOCALIZED_DIR = (
    Path(__file__).resolve().parents[4]
    / "ciris_engine"
    / "logic"
    / "conscience"
    / "prompts"
    / "localized"
)

# Locales whose entropy_conscience.yml is on the pre-2.7.2 v1 single-
# key shape (asks LLM for `{"entropy": float}` only). Pydantic
# defaults absorb the missing alt fields. When these get ported to v2
# self-resampling, remove them from this set.
_V1_GRANDFATHERED: Set[str] = {"pt", "ru", "sw"}


def _all_locales() -> list[str]:
    return sorted(d.name for d in LOCALIZED_DIR.iterdir() if d.is_dir())


def _system_prompt(locale: str) -> str:
    f = LOCALIZED_DIR / locale / "entropy_conscience.yml"
    data = yaml.safe_load(f.read_text(encoding="utf-8"))
    return data.get("system_prompt", "")


@pytest.mark.parametrize("locale", _all_locales())
def test_entropy_prompt_does_not_ask_for_list_field(locale: str) -> None:
    """No localized prompt may ask the LLM for the legacy
    ``alternative_meanings: list[string]`` field — the Pydantic
    EntropyResult schema is flat (alternative_1/2/3) with extra=
    forbid, so a list response fails validation silently in
    production."""
    sp = _system_prompt(locale)
    assert "alternative_meanings: list" not in sp, (
        f"locale {locale}: entropy prompt still asks for the legacy "
        f"'alternative_meanings: list[string]' field. Pydantic "
        f"EntropyResult is now flat (alternative_1/2/3 + extra=forbid) "
        f"— LLM output for this locale will fail schema validation. "
        f"Update the schema spec in this YAML to declare three flat "
        f"alternative_N: string fields."
    )


@pytest.mark.parametrize("locale", _all_locales())
def test_v2_locales_declare_all_three_flat_fields(locale: str) -> None:
    """Locales on the v2 self-resampling shard must declare all three
    alternative_N fields in their schema spec. A locale that lists
    alternative_1 but forgets alternative_3 would only ever produce
    two alternatives — the cluster signal needs three."""
    if locale in _V1_GRANDFATHERED:
        pytest.skip(f"{locale} is on the v1 single-key shape (grandfathered)")
    sp = _system_prompt(locale)
    for n in (1, 2, 3):
        marker = f"alternative_{n}: string"
        assert marker in sp, (
            f"locale {locale}: missing flat field declaration "
            f"'{marker}' in entropy system prompt. v2 self-resampling "
            f"requires all three alternative_N fields to be declared "
            f"so the LLM enumerates a cluster of three."
        )


@pytest.mark.parametrize("locale", _all_locales())
def test_v2_locales_do_not_reference_removed_field_in_language_rules(locale: str) -> None:
    """The language-rules section ('JSON keys must remain in English:
    ...') must not list ``alternative_meanings`` as a key the LLM
    should produce — that field no longer exists in the schema. v2
    locales should list alternative_1/2/3; v1-grandfathered locales
    should not list alt fields at all."""
    if locale in _V1_GRANDFATHERED:
        pytest.skip(f"{locale} is on v1 — language-rules audit handled separately")
    sp = _system_prompt(locale)
    assert '"alternative_meanings"' not in sp, (
        f"locale {locale}: language-rules section still references "
        f"the removed 'alternative_meanings' JSON key. Replace with "
        f'"alternative_1", "alternative_2", "alternative_3" so the '
        f"LLM is told to keep the new flat keys in English."
    )


def test_grandfathered_v1_locales_actually_v1() -> None:
    """The set of v1-grandfathered locales must in fact be on v1 (no
    flat field declarations and no list-field declarations either —
    they ask for a single 'entropy' key). If a future port moves one
    of these to v2, the maintainer must remove it from
    ``_V1_GRANDFATHERED`` so the parity asserts above kick in."""
    for locale in _V1_GRANDFATHERED:
        sp = _system_prompt(locale)
        flat_present = any(f"alternative_{n}: string" in sp for n in (1, 2, 3))
        list_present = "alternative_meanings: list" in sp
        assert not flat_present and not list_present, (
            f"locale {locale} appears to have been ported to v2 (flat or "
            f"list shape detected in system prompt). Remove '{locale}' "
            f"from _V1_GRANDFATHERED in this test so the v2-parity "
            f"assertions enforce schema correctness for it."
        )
