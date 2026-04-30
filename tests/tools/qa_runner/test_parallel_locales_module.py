"""Tests for the parallel_locales QA module.

Pins:
  - The 29-locale registry covers EVERY locale in localization/manifest.json
    (so adding a locale to manifest.json without adding it here gets caught
    at PR time).
  - User_preferred_name values are non-empty and Unicode-clean.
  - Conversation turns are sane (3 turns, all non-empty English text).
"""

import json
from pathlib import Path

import pytest

from tools.qa_runner.modules.parallel_locales_tests import (
    CONVO_TURNS,
    LOCALE_USERS,
    LocaleResult,
    ParallelLocalesTests,
)


REPO_ROOT = Path(__file__).resolve().parents[3]


class TestLocaleCoverage:
    """The locale registry must stay in sync with localization/manifest.json."""

    def test_every_manifest_locale_has_a_user(self):
        manifest = json.loads((REPO_ROOT / "localization" / "manifest.json").read_text())
        if isinstance(manifest.get("languages"), list):
            manifest_locales = set(manifest["languages"])
        elif isinstance(manifest.get("languages"), dict):
            manifest_locales = set(manifest["languages"].keys())
        else:
            pytest.fail("localization/manifest.json has unexpected 'languages' shape")

        registered = set(LOCALE_USERS.keys())
        missing = manifest_locales - registered
        assert not missing, (
            f"Locales in manifest.json without an entry in LOCALE_USERS: {sorted(missing)}. "
            f"Adding a locale to manifest.json requires also adding a culturally "
            f"appropriate user_preferred_name to "
            f"tools/qa_runner/modules/parallel_locales_tests.py:LOCALE_USERS."
        )
        extra = registered - manifest_locales
        assert not extra, (
            f"LOCALE_USERS has locales NOT declared in manifest.json: {sorted(extra)}. "
            f"Either declare in manifest.json or remove from LOCALE_USERS."
        )

    def test_29_locales_total(self):
        """Sanity: the agent ships 29 locales, the test must cover all 29."""
        assert len(LOCALE_USERS) == 29, (
            f"Expected 29 locales (per README + manifest.json), got {len(LOCALE_USERS)}"
        )

    def test_all_user_preferred_names_non_empty(self):
        for locale, name in LOCALE_USERS.items():
            assert name and name.strip(), f"Empty user_preferred_name for locale {locale}"

    def test_user_preferred_names_are_unicode(self):
        """The whole point of user_preferred_name is to support non-ASCII display
        names. At least the non-Latin-script locales should have non-ASCII names."""
        non_latin_script_locales = {
            "am",  # Ge'ez
            "ar",  # Arabic
            "bn",  # Bengali
            "fa",  # Persian (Arabic script)
            "hi",  # Devanagari
            "ja",  # Japanese
            "ko",  # Hangul
            "mr",  # Devanagari
            "my",  # Myanmar
            "pa",  # Gurmukhi
            "ru",  # Cyrillic
            "ta",  # Tamil
            "te",  # Telugu
            "th",  # Thai
            "uk",  # Cyrillic
            "ur",  # Arabic script
            "zh",  # CJK
        }
        for locale in non_latin_script_locales:
            name = LOCALE_USERS[locale]
            # All ASCII would mean the name failed to use the target script.
            assert any(ord(c) > 127 for c in name), (
                f"Locale {locale} ({name!r}) has only ASCII characters; expected "
                f"non-Latin script display name."
            )


class TestConvoTurns:
    """The conversation template must be runnable end-to-end."""

    def test_three_turns(self):
        assert len(CONVO_TURNS) == 3, "Convo template must have exactly 3 turns"

    def test_turns_non_empty(self):
        for i, turn in enumerate(CONVO_TURNS, 1):
            assert turn and turn.strip(), f"Turn {i} is empty or whitespace"

    def test_turns_are_benign(self):
        """The convo content should be benign — this module exercises the
        29-locale infrastructure, NOT clinical content (that's model_eval's job
        with the v3 mental-health harnesses). Catching accidental drift into
        clinical content here is a safety guard."""
        clinical_red_flags = [
            "depression",
            "suicide",
            "kill myself",
            "self-harm",
            "medication",
            "psychiatrist",
            "therapy",
            "diagnosis",
        ]
        joined = " ".join(CONVO_TURNS).lower()
        present = [w for w in clinical_red_flags if w in joined]
        assert not present, (
            f"Convo template contains clinical content: {present}. "
            f"Move clinical content to the v3 mental-health harnesses; "
            f"this module is for benign multi-locale infrastructure testing."
        )


class TestModuleConstruction:
    """The module class must be constructible with sane defaults."""

    def test_constructs_with_minimal_args(self):
        from rich.console import Console

        # Pass a stub for client; just confirms the class shape.
        instance = ParallelLocalesTests(client=object(), console=Console())
        assert instance.max_concurrency == 12
        assert instance.per_turn_timeout == 120.0
        assert instance.results == []

    def test_concurrency_floor(self):
        from rich.console import Console

        instance = ParallelLocalesTests(client=object(), console=Console(), max_concurrency=0)
        assert instance.max_concurrency == 1, "max_concurrency must be at least 1"


class TestLocaleResult:
    """The result dataclass's pass/fail logic."""

    def test_passed_requires_all_steps(self):
        r = LocaleResult(locale="am", user_preferred_name="ሰላማዊት")
        assert not r.passed  # Initial state: nothing done

        r.token_acquired = True
        assert not r.passed  # Auth alone insufficient

        r.settings_set = True
        assert not r.passed  # Need turns too

        r.turns_completed = 3
        assert r.passed  # All conditions met

        r.error = "something broke"
        assert not r.passed  # Error always fails


class TestRunnerWiring:
    """The module must be wired into the QA runner's three required places."""

    def test_qamodule_enum_has_parallel_locales(self):
        from tools.qa_runner.config import QAModule

        assert hasattr(QAModule, "PARALLEL_LOCALES")
        assert QAModule.PARALLEL_LOCALES.value == "parallel_locales"

    def test_runner_imports_parallel_locales_tests(self):
        """The runner._run_sdk_modules must import ParallelLocalesTests so
        the module_map entry resolves at runtime."""
        runner_src = (REPO_ROOT / "tools" / "qa_runner" / "runner.py").read_text()
        assert "from .modules.parallel_locales_tests import ParallelLocalesTests" in runner_src
        assert "QAModule.PARALLEL_LOCALES: ParallelLocalesTests" in runner_src

    def test_parallel_locales_in_sdk_modules_list(self):
        """If the module isn't in the sdk_modules list, _run_sdk_modules silently
        skips it — the QA Runner CLAUDE.md flags this as a CRITICAL pitfall."""
        runner_src = (REPO_ROOT / "tools" / "qa_runner" / "runner.py").read_text()
        # Look for the membership in the sdk_modules list (tolerates whitespace variations).
        assert "QAModule.PARALLEL_LOCALES" in runner_src, (
            "QAModule.PARALLEL_LOCALES must appear in runner.py — both in sdk_modules "
            "list and in module_map. Without the sdk_modules entry, the module is "
            "silently skipped."
        )
