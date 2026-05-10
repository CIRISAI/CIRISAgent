"""Test: every localized language has all 4 conscience prompt files.

Why this test exists:

  In April 2026 we discovered that 13 of 28 supported languages had only 2
  of the 4 conscience prompt files on disk (`entropy_conscience.yml` +
  `epistemic_humility_conscience.yml`), missing `coherence_conscience.yml`
  and `optimization_veto_conscience.yml`. Production agents serving those
  locales were silently falling back to English for half their conscience
  prompts — meaning the conscience justifications and gating signals weren't
  in the user's language, downstream `retry_guidance` was incoherent, and
  the audit trail wasn't legible to operators.

  Every language in the manifest is a first-class deployment target. CIRIS
  agents serve roughly 95% of world population through these locales; an
  English-fallback for a non-English agent is a silent quality regression
  that no test was catching until this one.

  This test asserts: for every locale in `localization/manifest.json`
  (excluding `en`, which IS the base), the localized conscience prompt
  directory exists and contains exactly the same 4 conscience YAML files
  as the English base directory. If a future change adds a new conscience
  type, it must add a localized version in every supported language.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "ciris_engine" / "data" / "localized" / "manifest.json"
EN_BASE = REPO_ROOT / "ciris_engine" / "logic" / "conscience" / "prompts"
LOCALIZED_ROOT = EN_BASE / "localized"

# Conscience prompts that are POLYGLOT — load universally regardless of
# user-preferred locale, so per-locale mirrors are NOT expected (and would
# silently shadow the base, breaking polyglot uplifts; see polyglot/CLAUDE.md
# §6 + memory anchor `feedback_polyglot_artifacts_universal`). Locales MUST
# NOT have files for these — the per-locale-coverage assertion below
# excludes them, and a separate assertion below catches stale per-locale
# mirrors that would silently shadow the base.
#
# `optimization_veto_conscience.yml` was lifted to polyglot v3.0 in commit
# 5a340b8e9 (canonical-encoding triangulation); the 28 stale localized
# mirrors were deliberately removed in commit 0c6a962f1.
POLYGLOT_PROMPTS: frozenset[str] = frozenset({
    "optimization_veto_conscience.yml",
})

# All conscience prompt files expected per language. Derived from the
# English base directory at module-load time so adding a new conscience
# (e.g. epistemic_charity_conscience.yml) automatically expands the
# coverage requirement — the test will fail until every locale gains the
# new prompt. POLYGLOT_PROMPTS are excluded — they don't have per-locale
# variants by design.
EXPECTED_PROMPTS: list[str] = sorted(
    p.name for p in EN_BASE.glob("*.yml")
    if p.is_file() and p.name not in POLYGLOT_PROMPTS
)

# Languages from the localization manifest, excluding `en` (the base).
with MANIFEST.open(encoding="utf-8") as f:
    _manifest = json.load(f)
LOCALES: list[str] = sorted(
    code for code in _manifest["languages"].keys() if code != "en"
)


def test_expected_prompts_known() -> None:
    """Sanity-check: the English base contains the conscience set we expect.

    If this test ever fails, a conscience prompt was renamed or added in
    the en base. Update the assertion to reflect the new reality, but be
    aware: every change here cascades to a coverage requirement on all
    28 localized directories.
    """
    # The 3 per-locale-required consciences. EXPECTED_PROMPTS excludes
    # POLYGLOT_PROMPTS (i.e. EOV) since polyglot prompts are loaded
    # universally — locales must NOT have per-locale variants that would
    # shadow the base.
    assert "entropy_conscience.yml" in EXPECTED_PROMPTS
    assert "coherence_conscience.yml" in EXPECTED_PROMPTS
    assert "epistemic_humility_conscience.yml" in EXPECTED_PROMPTS
    # EOV is polyglot — should be in en base but excluded from EXPECTED.
    assert (EN_BASE / "optimization_veto_conscience.yml").is_file(), (
        "Polyglot EOV prompt missing from en base"
    )
    assert "optimization_veto_conscience.yml" not in EXPECTED_PROMPTS, (
        "EOV is a polyglot conscience and must NOT be in EXPECTED_PROMPTS — "
        "per-locale mirrors silently shadow the polyglot base."
    )
    assert len(EXPECTED_PROMPTS) >= 3, (
        f"At least 3 per-locale-required conscience prompts expected, "
        f"found {len(EXPECTED_PROMPTS)}: {EXPECTED_PROMPTS}"
    )


@pytest.mark.parametrize("locale", LOCALES)
def test_locale_has_complete_conscience_prompt_set(locale: str) -> None:
    """Every supported locale must have all 4 conscience prompt files.

    A non-English production agent without a localized conscience prompt
    silently falls back to English, breaking the agent's locale-coherent
    audit trail and downstream conscience-feedback retry guidance. There
    is no such thing as a partially-supported language — every conscience
    speaks every language CIRIS supports.
    """
    locale_dir = LOCALIZED_ROOT / locale
    assert locale_dir.is_dir(), (
        f"Localized conscience directory missing for '{locale}': "
        f"{locale_dir}. Every language in localization/manifest.json must "
        f"have a localized conscience prompt directory."
    )

    actual = sorted(p.name for p in locale_dir.glob("*.yml") if p.is_file())
    missing = sorted(set(EXPECTED_PROMPTS) - set(actual))
    extra = sorted(set(actual) - set(EXPECTED_PROMPTS))

    assert not missing, (
        f"Locale '{locale}' is missing conscience prompts: {missing}. "
        f"Every locale must have all 4 conscience prompts (currently "
        f"{EXPECTED_PROMPTS}). Falling back to English breaks "
        f"locale-coherent agent operation. Translate from "
        f"ciris_engine/logic/conscience/prompts/{{conscience}}.yml — "
        f"see existing translations in localized/zh/ or localized/de/ "
        f"for format and language-rule block conventions."
    )
    # `extra` here is computed against EXPECTED_PROMPTS (which excludes
    # POLYGLOT_PROMPTS). So if a locale dir contains EOV, it shows up here
    # as "extra" — and that IS the violation we want to catch (stale
    # polyglot mirror shadowing the base). Surface it with a polyglot-
    # specific message when applicable.
    polyglot_extras = sorted(set(extra) & POLYGLOT_PROMPTS)
    other_extras = sorted(set(extra) - POLYGLOT_PROMPTS)
    assert not polyglot_extras, (
        f"Locale '{locale}' has stale POLYGLOT mirror(s) that shadow the "
        f"polyglot base: {polyglot_extras}. Polyglot consciences load "
        f"universally regardless of user-preferred locale; per-locale "
        f"mirrors silently pre-empt the base prompt and break polyglot "
        f"uplifts. See polyglot/CLAUDE.md §6 + commit 0c6a962f1 (which "
        f"removed 28 stale EOV mirrors after polyglot v3.0 uplift)."
    )
    assert not other_extras, (
        f"Locale '{locale}' has unexpected conscience prompt files "
        f"(not present in en base): {other_extras}. Either the file is "
        f"misnamed or a corresponding en base file is missing. The en "
        f"base is the source of truth for which conscience prompts exist."
    )


@pytest.mark.parametrize("locale", LOCALES)
def test_locale_conscience_prompts_parse_as_yaml(locale: str) -> None:
    """Every localized conscience prompt must be valid YAML.

    Defends against translation work that accidentally introduces YAML
    syntax errors (mismatched quotes, broken `|` block scalars, stray
    tabs, etc.). A broken localized prompt fails silently in production —
    the prompt loader catches the exception and falls back to English,
    leaving operators puzzled why the agent is responding in en.
    """
    locale_dir = LOCALIZED_ROOT / locale
    if not locale_dir.is_dir():
        pytest.skip(f"locale {locale} directory missing — caught by coverage test")

    for yml in sorted(locale_dir.glob("*.yml")):
        with yml.open(encoding="utf-8") as f:
            try:
                data = yaml.safe_load(f)
            except yaml.YAMLError as exc:
                pytest.fail(f"YAML parse error in {yml.relative_to(REPO_ROOT)}: {exc}")
        assert isinstance(data, dict), f"{yml} must be a YAML mapping"
        assert "system_prompt" in data, (
            f"{yml.relative_to(REPO_ROOT)} missing required 'system_prompt' key"
        )
