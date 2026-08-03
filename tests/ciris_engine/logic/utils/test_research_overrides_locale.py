"""``string`` overrides are LOCALIZED — one value cannot stand for every locale.

The regression these pin: ``baseline_manifest()`` captured every ``string`` key
at ``get_string("en", key)``, and ``get_string`` returned the override before it
ever consulted ``lang_code``. A baseline-derived manifest — the *documented*
workflow, whose docstring promises "every other key round-trips to its current
value" — therefore pinned English text for all 29 locales.

On v2.9.9-stable that was 44 of 46 string keys: every ``prompts.prohibitions.*``
(21), every ``conscience.*`` retry string (16), the five ``prompts.dma.bounce_*``
keys and ``prompts.language_guidance``. A compose dump across am/ja/en under a
baseline manifest returned 13,694 B of English guidance for all three; the same
dump with no manifest returned 25,337 / 16,145 / 13,694 correctly.

It defeated an invariant the codebase states twice — ``get_prohibition_guidance``
deliberately bypasses the English fallback chain because it "would serve English
into every non-English prompt and pollute it", and R4 refuses ``[EN]``
laundering. The override registry was the hole in both.
"""

import json

import pytest

from ciris_engine.logic.utils import research_overrides as ro
from ciris_engine.logic.utils.localization import get_string
from ciris_engine.logic.utils.research_overrides import ENV_ANCHOR, ENV_MANIFEST

_KEY = "prompts.language_guidance"


@pytest.fixture(autouse=True)
def _clean_override_state():
    ro.reset_research_overrides()
    yield
    ro.reset_research_overrides()


def _activate(monkeypatch, tmp_path, string_overrides):
    manifest = {
        "manifest_version": "1",
        "experiment_id": "locale-regression",
        "condition": "c",
        "base_locale": "en",
        "mode": "additive",
        "residue_digest": ro.compute_residue_digest(),
        "overrides": {
            "string": string_overrides,
            "dma_prompt": {},
            "conscience_prompt": {},
            "corpus": {},
            "template": {},
        },
        "research_hashes": {},
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setenv(ENV_MANIFEST, str(path))
    monkeypatch.setenv(ENV_ANCHOR, "true")
    ro.reset_research_overrides()


class TestPerLocaleOverrides:
    def test_mapping_resolves_the_requested_locale(self, monkeypatch, tmp_path):
        _activate(monkeypatch, tmp_path, {_KEY: {"en": "ENGLISH", "ja": "JAPANESE", "am": "AMHARIC"}})

        assert get_string("en", _KEY) == "ENGLISH"
        assert get_string("ja", _KEY) == "JAPANESE"
        assert get_string("am", _KEY) == "AMHARIC"

    def test_scalar_still_applies_to_every_locale(self, monkeypatch, tmp_path):
        """A single string is a legitimate, DELIBERATE 'same text everywhere'."""
        _activate(monkeypatch, tmp_path, {_KEY: "ONE TEXT"})

        for lang in ("en", "ja", "am"):
            assert get_string(lang, _KEY) == "ONE TEXT"

    def test_missing_locale_refuses_instead_of_serving_english(self, monkeypatch, tmp_path):
        """The bug's exact shape: silence here put English in an Amharic prompt."""
        _activate(monkeypatch, tmp_path, {_KEY: {"en": "ENGLISH", "ja": "JAPANESE"}})

        with pytest.raises(RuntimeError, match=r"no entry for locale 'am'"):
            get_string("am", _KEY)

    def test_prohibitions_localize_too(self, monkeypatch, tmp_path):
        """get_prohibition_guidance reads the registry directly, bypassing
        get_string — so it needed the same fix, and 21 of the 44 flattened keys
        were prohibition text."""
        from ciris_engine.logic.utils.localization import get_prohibition_guidance

        key = "prompts.prohibitions.MEDICAL"
        _activate(monkeypatch, tmp_path, {key: {"en": "EN-MEDICAL", "ja": "JA-MEDICAL"}})

        assert "EN-MEDICAL" in get_prohibition_guidance("en")
        assert "JA-MEDICAL" in get_prohibition_guidance("ja")
        assert "EN-MEDICAL" not in get_prohibition_guidance("ja")


class TestBaselineRoundTrip:
    def test_baseline_captures_per_locale_not_english_only(self):
        manifest = ro.baseline_manifest(["en", "ja", "am"])
        value = manifest["overrides"]["string"][_KEY]

        assert isinstance(value, dict), "a localized key captured as a scalar is the regression"
        assert set(value) == {"en", "ja", "am"}
        # Three different languages must not round-trip to one text.
        assert len(set(value.values())) == 3

    def test_invariant_keys_stay_scalar(self):
        """Collapsing to a scalar keeps the manifest small — but only where the
        key genuinely does not vary, never by standing one locale in for another."""
        manifest = ro.baseline_manifest(["en", "ja", "am"])
        values = manifest["overrides"]["string"].values()

        assert any(isinstance(v, str) for v in values), "expected at least one invariant key"
        for value in values:
            if isinstance(value, dict):
                assert len(set(value.values())) > 1, "a mapping whose values are identical should be scalar"

    def test_baseline_output_validates_as_a_manifest(self, tmp_path):
        """`baseline > m.json && validate m.json` used to fail on `_baseline_note`
        — a key baseline itself added, which `extra="forbid"` then rejected."""
        manifest = ro.baseline_manifest(["en"])

        assert "_baseline_note" not in manifest
        path = tmp_path / "m.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        # Unresolved REPLACE:: markers are reported separately, never inline.
        assert ro.baseline_unresolved(manifest), "the value-bearing keys should stay unfilled"

    def test_default_captures_every_bundled_locale(self):
        """No hardcoded locale list: a locale added to the bundle later is picked
        up here with no change to this module."""
        from ciris_engine.logic.utils.localization import get_available_languages

        manifest = ro.baseline_manifest()
        mappings = [v for v in manifest["overrides"]["string"].values() if isinstance(v, dict)]

        assert mappings, "expected localized keys to be captured as mappings"
        available = set(get_available_languages())
        for mapping in mappings:
            assert set(mapping) >= available - {"en"} or set(mapping) <= available
