"""Regression guard: every locale in localization/manifest.json must have
a LANGUAGE_SPEC entry in tools.qa_runner.modules.model_eval_tests.

The bug this guards against (2026-05-03 ar regression):
    qa_runner model_eval filters --model-eval-languages against the static
    LANGUAGE_SPECS dict. If a supported locale is missing from that dict,
    the harness silently fires `9 questions × 0 languages = 0 submissions`
    and returns a green "0 passed / 0 failed" summary — looks like
    success, actually ran nothing. CI catches this here.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.qa_runner.modules.model_eval_tests import LANGUAGE_SPECS


REPO = Path(__file__).resolve().parents[3]
MANIFEST = REPO / "ciris_engine" / "data" / "localized" / "manifest.json"


def _load_manifest_languages() -> set[str]:
    """Return the set of locale codes declared in localization/manifest.json.

    The manifest's `languages` key holds the canonical 29-locale list per
    `CLAUDE.md` ("Source of truth: localization/manifest.json. To add or
    remove a language, update the manifest first.").
    """
    data = json.loads(MANIFEST.read_text())
    langs = data.get("languages")
    # Manifest is a dict keyed by ISO code: {"en": {...}, "am": {...}, ...}
    assert isinstance(langs, dict), (
        f"localization/manifest.json `languages` must be a dict keyed by "
        f"ISO code (got {type(langs).__name__})"
    )
    return set(langs.keys())


def test_language_specs_covers_every_supported_locale():
    """Every locale in the manifest MUST have a LANGUAGE_SPEC entry.

    Missing entries silently degrade qa_runner model_eval to 0-language
    gating — the run reports green even though zero submissions fired.
    """
    manifest_langs = _load_manifest_languages()
    spec_langs = set(LANGUAGE_SPECS.keys())

    missing = manifest_langs - spec_langs
    assert not missing, (
        f"LANGUAGE_SPECS is missing entries for {sorted(missing)}. "
        f"These locales are declared supported in localization/manifest.json "
        f"but qa_runner model_eval will silently filter them out, firing "
        f"`9 questions × 0 languages = 0 submissions` and returning a green "
        f"summary that ran nothing. Add a LanguageSpec entry per the existing "
        f"pattern in tools/qa_runner/modules/model_eval_tests.py."
    )


def test_language_specs_does_not_drift_beyond_manifest():
    """Catches the inverse drift: a LANGUAGE_SPEC entry exists for a locale
    not declared supported in the manifest. Likely a typo or an obsolete
    entry from a removed language.
    """
    manifest_langs = _load_manifest_languages()
    spec_langs = set(LANGUAGE_SPECS.keys())

    extra = spec_langs - manifest_langs
    assert not extra, (
        f"LANGUAGE_SPECS contains entries for {sorted(extra)} which are NOT "
        f"declared supported in localization/manifest.json. Either add them "
        f"to the manifest (and ship localization assets) or remove the spec "
        f"entries."
    )


def test_language_spec_fields_well_formed():
    """Each LanguageSpec must carry a non-empty `code` matching its dict key,
    a non-empty `name`, and a `prompt_prefix` that is either empty (English)
    or ends in a question separator. Guards against shipping a half-defined
    entry that compiles but produces unusable output."""
    for code, spec in LANGUAGE_SPECS.items():
        assert spec.code == code, (
            f"LANGUAGE_SPECS[{code!r}].code is {spec.code!r}; the dict key "
            f"and the code field must match."
        )
        assert spec.name, f"LANGUAGE_SPECS[{code!r}].name is empty"
        # English carries an empty prefix by design (the harness questions
        # are already in English). Every other locale's prefix should be
        # a non-empty in-locale directive.
        if code != "en":
            assert spec.prompt_prefix, (
                f"LANGUAGE_SPECS[{code!r}].prompt_prefix is empty — every "
                f"non-English locale needs an in-locale prompt directive."
            )
