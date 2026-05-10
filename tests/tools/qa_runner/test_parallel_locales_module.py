"""Tests for the parallel_locales QA module.

Pins:
  - The 29-locale registry covers EVERY locale in localization/manifest.json
    (so adding a locale to manifest.json without adding it here gets caught
    at PR time).
  - User_preferred_name values are non-empty and Unicode-clean.
  - The benign question is non-empty and not clinical content.
  - Runner wiring is intact in all 3 required places.
"""

import json
from pathlib import Path

import pytest

from tools.qa_runner.modules.parallel_locales_tests import (
    CONVO_QUESTION,
    LOCALE_USERS,
    LocaleResult,
    ParallelLocalesTests,
)


REPO_ROOT = Path(__file__).resolve().parents[3]


class TestLocaleCoverage:
    """The locale registry must stay in sync with localization/manifest.json."""

    def test_every_manifest_locale_has_a_user(self):
        manifest = json.loads((REPO_ROOT / "ciris_engine" / "data" / "localized" / "manifest.json").read_text())
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


class TestQuestion:
    """The single question fanned out to all 29 channels."""

    def test_question_non_empty(self):
        assert CONVO_QUESTION and CONVO_QUESTION.strip()

    def test_question_is_benign(self):
        """The question is infrastructure-validation only — no clinical content.
        Clinical content belongs in the v3 mental-health harnesses, where the
        rubric review process catches misuse. Catching accidental drift here
        is a safety guard."""
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
        lower = CONVO_QUESTION.lower()
        present = [w for w in clinical_red_flags if w in lower]
        assert not present, (
            f"Question contains clinical content: {present}. "
            f"Move clinical content to the v3 mental-health harnesses; "
            f"this module is for benign multi-locale infrastructure testing."
        )


class TestModuleConstruction:
    """The module class must be constructible with sane defaults."""

    def test_constructs_with_minimal_args(self):
        from rich.console import Console

        instance = ParallelLocalesTests(client=object(), console=Console())
        assert instance.results == []

    def test_default_concurrency_runs_all_locales_in_parallel(self):
        """The whole point is parallel fan-out — default concurrency should be
        high enough to fan out all 29 locales at once. This is what mirrors a
        production phone deployment where 29 different users in 29 different
        timezones could all be hitting the agent simultaneously."""
        from rich.console import Console

        instance = ParallelLocalesTests(client=object(), console=Console())
        assert instance.max_concurrency >= len(LOCALE_USERS), (
            f"Default max_concurrency ({instance.max_concurrency}) must allow ALL "
            f"{len(LOCALE_USERS)} locales to run in parallel — that's the test's "
            f"value proposition (29-way concurrent load on the LLM backend)."
        )

    def test_concurrency_floor(self):
        from rich.console import Console

        instance = ParallelLocalesTests(client=object(), console=Console(), max_concurrency=0)
        assert instance.max_concurrency == 1, "max_concurrency must be at least 1"

    def test_no_pipeline_overrides(self):
        """The module class must NOT expose any knob that reduces the agent's
        DMA pipeline depth, conscience checks, or turn count. The whole point
        is to test the agent EXACTLY AS IT RUNS ON PHONE — full pipeline,
        no shortcuts. If a future contributor adds a `quick_mode` flag or
        similar, this test should fail to flag it."""
        from rich.console import Console

        instance = ParallelLocalesTests(client=object(), console=Console())
        forbidden_attrs = [
            "turns",
            "skip_conscience",
            "skip_dma",
            "quick_mode",
            "shallow_pipeline",
            "fast_mode",
        ]
        for attr in forbidden_attrs:
            assert not hasattr(instance, attr), (
                f"ParallelLocalesTests has `{attr}` — this module must NOT override "
                f"agent defaults. The test exists to validate phone-equivalent behavior."
            )


class TestLocaleResult:
    """The result dataclass's pass/fail logic."""

    def test_passed_requires_all_steps(self):
        r = LocaleResult(locale="am", user_preferred_name="ሰላማዊት")
        assert not r.passed  # Initial state: nothing done

        r.token_acquired = True
        assert not r.passed  # Auth alone insufficient

        r.settings_set = True
        assert not r.passed  # Need response too

        r.response_received = True
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
        assert "QAModule.PARALLEL_LOCALES" in runner_src, (
            "QAModule.PARALLEL_LOCALES must appear in runner.py — both in sdk_modules "
            "list and in module_map. Without the sdk_modules entry, the module is "
            "silently skipped."
        )
