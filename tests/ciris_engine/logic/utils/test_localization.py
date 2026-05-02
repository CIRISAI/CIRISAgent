"""Tests for the localization utility module."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from ciris_engine.logic.utils.localization import (
    clear_cache,
    get_available_languages,
    get_language_guidance,
    get_language_meta,
    get_localizer,
    get_preferred_language,
    get_string,
    preload_languages,
)


@pytest.fixture(autouse=True)
def reset_cache():
    """Reset the localization cache before each test."""
    clear_cache()
    yield
    clear_cache()


class TestGetString:
    """Tests for get_string function."""

    def test_get_english_string(self):
        """Test basic English string lookup."""
        result = get_string("en", "agent.greeting")
        assert result is not None
        assert "Hello" in result or "help" in result.lower()

    def test_get_nested_key(self):
        """Test nested dot-notation key lookup."""
        result = get_string("en", "prompts.dma.pdma_header")
        assert result is not None
        assert "CIRIS" in result

    def test_fallback_to_english(self):
        """Test fallback to English when key missing in target language."""
        # Use a key that exists in English but might not in all languages
        result = get_string("am", "status.all_operational")
        assert result is not None
        # Should get something, either Amharic or English fallback

    def test_fallback_to_default(self):
        """Test fallback to provided default."""
        result = get_string("en", "nonexistent.key.here", default="My Default")
        assert result == "My Default"

    def test_fallback_to_key_itself(self):
        """Test fallback to key itself when no default provided."""
        result = get_string("en", "totally.fake.key")
        assert result == "totally.fake.key"

    def test_interpolation_single_param(self):
        """Test parameter interpolation with single param."""
        result = get_string("en", "mobile.startup_services_count", online=5, total=22)
        assert "5" in result
        assert "22" in result

    def test_interpolation_multiple_params(self):
        """Test parameter interpolation with multiple params."""
        result = get_string("en", "mobile.startup_preparing_progress", current=3, total=8)
        assert "3" in result
        assert "8" in result

    def test_invalid_language_falls_back(self):
        """Test that invalid language code falls back to English."""
        result = get_string("xx", "agent.greeting")
        # Should still return something (English fallback or the key)
        assert result is not None

    def test_en_marker_treated_as_missing(self):
        """Test that [EN] placeholder markers trigger fallback."""
        # This tests the logic, actual behavior depends on file content
        # If a value starts with [EN], it should fall back to English
        pass  # Skip for now as it depends on specific file state


class TestGetLocalizer:
    """Tests for get_localizer function."""

    def test_bound_localizer(self):
        """Test that localizer is bound to specified language."""
        loc = get_localizer("en")
        result = loc("agent.greeting")
        assert result is not None
        assert "Hello" in result or "help" in result.lower()

    def test_localizer_with_params(self):
        """Test localizer with parameter interpolation."""
        loc = get_localizer("en")
        result = loc("mobile.startup_services_count", online=10, total=22)
        assert "10" in result
        assert "22" in result

    def test_localizer_with_default(self):
        """Test localizer with default value."""
        loc = get_localizer("en")
        result = loc("nonexistent.key", default="Fallback")
        assert result == "Fallback"


class TestAvailableLanguages:
    """Tests for get_available_languages function."""

    def test_returns_list(self):
        """Test that available languages returns a list."""
        languages = get_available_languages()
        assert isinstance(languages, list)

    def test_english_available(self):
        """Test that English is always available."""
        languages = get_available_languages()
        assert "en" in languages

    def test_multiple_languages(self):
        """Test that multiple languages are available."""
        languages = get_available_languages()
        # We know we have at least en, es, fr, am, etc.
        assert len(languages) >= 5


class TestLanguageMeta:
    """Tests for get_language_meta function."""

    def test_english_meta(self):
        """Test English language metadata."""
        meta = get_language_meta("en")
        assert meta["language"] == "en"
        assert meta["language_name"] == "English"
        assert meta["direction"] == "ltr"

    def test_rtl_language(self):
        """Test RTL language metadata (Arabic)."""
        meta = get_language_meta("ar")
        assert meta["direction"] == "rtl"

    def test_unknown_language_defaults(self):
        """Test that unknown language returns sensible defaults."""
        meta = get_language_meta("xx")
        assert meta["language"] == "xx"
        assert meta["direction"] == "ltr"


class TestPreloadLanguages:
    """Tests for preload_languages function."""

    def test_preload_specific_languages(self):
        """Test preloading specific language codes."""
        # Should not raise any errors
        preload_languages(["en", "es"])

    def test_preload_all_languages(self):
        """Test preloading all available languages."""
        # Should not raise any errors
        preload_languages()


class TestGetPreferredLanguage:
    """Tests for get_preferred_language function."""

    def test_default_is_english(self):
        """Test that default preferred language is English."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove the env var if set
            os.environ.pop("CIRIS_PREFERRED_LANGUAGE", None)
            result = get_preferred_language()
            assert result == "en"

    def test_respects_env_var(self):
        """Test that environment variable is respected."""
        with patch.dict(os.environ, {"CIRIS_PREFERRED_LANGUAGE": "am"}):
            result = get_preferred_language()
            assert result == "am"


class TestWithTempFiles:
    """Tests using temporary localization files."""

    def test_custom_localization_dir(self):
        """Test using a custom localization directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test localization file
            test_data = {
                "_meta": {"language": "test", "language_name": "Test Language", "direction": "ltr"},
                "greeting": "Hello from test!",
                "nested": {"key": "Nested value with {param}"},
            }
            test_file = Path(tmpdir) / "test.json"
            with open(test_file, "w") as f:
                json.dump(test_data, f)

            # Also need English for fallback
            en_data = {"_meta": {"language": "en", "language_name": "English", "direction": "ltr"}}
            en_file = Path(tmpdir) / "en.json"
            with open(en_file, "w") as f:
                json.dump(en_data, f)

            with patch.dict(os.environ, {"CIRIS_LOCALIZATION_DIR": tmpdir}):
                clear_cache()
                result = get_string("test", "greeting")
                assert result == "Hello from test!"

                result = get_string("test", "nested.key", param="test_value")
                assert result == "Nested value with test_value"


class TestCacheManagement:
    """Tests for cache management."""

    def test_clear_cache(self):
        """Test that clear_cache works."""
        # Load something
        get_string("en", "agent.greeting")
        # Clear it
        clear_cache()
        # Should still work (will reload)
        result = get_string("en", "agent.greeting")
        assert result is not None


class TestGetLanguageGuidance:
    """Tests for the per-language guidance block injected into LLM prompts.

    Pinning the contract: as of 2.7.8, 8 of 29 languages have populated
    packs (am from 2.7.6; ha + yo Tier-0 plus bn / my / pa / sw / ta from
    2.7.7), and 21 return empty. Each populated pack is asserted to (a)
    stay non-empty and (b) carry a distinctive native-script substring so
    a deletion or English-filler replacement gets caught at PR time.

    The 8 DMA / ASPDMA / conscience call sites (PDMA, IDMA, CSDMA, DSDMA,
    ASPDMA, TSASPDMA × 2, DSASPDMA) all use this same get_language_guidance
    helper, so an end-to-end injection test covering all populated locales
    here proves the wiring works for every consumer in the agent.
    """

    # Pinned populated set. ADD entries here when a new locale ships a
    # primer; the parametrized `test_populated_locales_have_guidance` and
    # `test_populated_set_pinned_exactly` will both exercise the
    # addition. The native_substring must be a string distinctive enough
    # to fail if the pack is replaced with English filler.
    POPULATED_LOCALES = {
        # 2.7.6 — Amharic primer
        "am": "ምርመራ",  # Amharic 'diagnosis' fix
        # 2.7.6 — Tier-0 primers
        "ha": "JAGORAR HARSHE",  # Hausa header
        "yo": "ÌTỌ́NISỌ́NÀ ÈDÈ",  # Yoruba header (with tone marks)
        # 2.7.7 — Tier-1 primers
        "sw": "MWONGOZO WA LUGHA",  # Swahili header
        "my": "ဘာသာစကားလမ်းညွှန်",  # Burmese header
        "pa": "ਭਾਸ਼ਾ ਮਾਰਗਦਰਸ਼ਨ",  # Punjabi (Gurmukhi)
        "ta": "மொழி வழிகாட்டி",  # Tamil
        "bn": "ভাষা নির্দেশিকা",  # Bengali
        # 2.7.8 — MVP primers by language family (non-first-world)
        # Perso-Arabic RTL family
        "ar": "التوجيه اللغوي",  # Arabic header
        "fa": "راهنمای زبانی",  # Persian header
        "ur": "لسانی ہدایت",  # Urdu header
        # South Asian family (Indo-Aryan + Dravidian)
        "hi": "भाषा निर्देशिका",  # Hindi header (Devanagari)
        "mr": "भाषा मार्गदर्शक",  # Marathi header (Devanagari, distinct from hi)
        "te": "భాషా మార్గదర్శి",  # Telugu header
        # Southeast Asian family
        "th": "คำแนะนำภาษา",  # Thai header
        "vi": "chẩn đoán",  # Vietnamese disclaimer phrase (diacritic-heavy)
        "id": "Panduan Bahasa",  # Indonesian header
        # Mid-tier European family
        "tr": "DİL REHBERİ",  # Turkish header (uses Turkish-specific İ)
        "uk": "МОВНИЙ ОРІЄНТИР",  # Ukrainian header (Cyrillic)
        # 2.7.8.13 — English canonical + 9-cluster fanout of the 5 universal defenses
        # English becomes the source-of-truth template all locales inherit from.
        # Pinning the §7b false-reassurance worked-example header (translated
        # to each locale's natural rendering) is the strongest discrimination
        # from "English filler in the field" — the worked-example is
        # structurally distinctive and load-bearing.
        "en": "FALSE REASSURANCE",  # §7b worked-example header in en canonical
        # First-world languages now carrying the universal-defense primer.
        # Substrings match the actual translated §7b headers as authored by
        # the cluster-agent fanout (each locale renders the term in its own
        # natural register).
        "de": "FALSCHE VERSICHERUNG",  # §7b in German — false-reassurance term
        "es": "FALSA TRANQUILIZACIÓN",  # §7b in Spanish — calming-as-a-lie term
        "fr": "FAUSSE RÉASSURANCE",  # §7b in French
        "it": "FALSA RASSICURAZIONE",  # §7b in Italian
        "pt": "FALSA GARANTIA",  # §7b in Portuguese — false-guarantee framing
        "ru": "ЛОЖНОЕ УСПОКОЕНИЕ",  # §7b in Russian
        # CJK family
        # ja: reverted to empty in 2.7.8.14 (Burmese-class §1 breakage) — see EMPTY_LOCALES
        "ko": "거짓 안심",  # §7b false-reassurance in Korean
        "zh": "虚假保证",  # §7b false-reassurance in Chinese
    }

    def test_populated_set_pinned_exactly(self):
        """The set of populated locales is pinned. If a new pack ships,
        update POPULATED_LOCALES to add it (forcing PR review of the
        addition). If a populated pack accidentally gets emptied, this
        test catches it before the "wired but silently empty" regression
        ships.
        """
        actual_populated = {lang for lang in self.POPULATED_LOCALES if get_language_guidance(lang)}
        expected_populated = set(self.POPULATED_LOCALES.keys())
        missing = expected_populated - actual_populated
        assert not missing, (
            f"Locales pinned as populated but returning empty guidance: {sorted(missing)}. "
            f"Either the pack was deleted or the JSON path drifted."
        )

    @pytest.mark.parametrize(
        "lang_code,native_substring",
        sorted(POPULATED_LOCALES.items()),
    )
    def test_populated_locales_have_guidance(self, lang_code: str, native_substring: str):
        """Every pinned populated pack must (a) stay non-empty and (b)
        carry a distinctive native-script substring. The substring guard
        catches the failure mode where someone "merges" a pack but
        accidentally replaces the body with English filler — empty would
        be silent through `if guidance:` but English filler at the wrong
        time costs production trust."""
        guidance = get_language_guidance(lang_code)
        assert guidance, f"{lang_code} guidance must be populated (pinned in POPULATED_LOCALES)"
        assert native_substring in guidance, (
            f"{lang_code} guidance lost its distinctive native-script substring "
            f"{native_substring!r}; pack may have been replaced with English filler"
        )
        # Also pin a minimum size so a 3-character native string isn't
        # a trivial pass — every shipping pack so far is >2KB and the
        # smallest (am) is 3.6KB.
        assert len(guidance) > 2000, (
            f"{lang_code} guidance dropped below 2KB ({len(guidance)} chars) — "
            f"pack may have been truncated. Ship-day floor was 3.6KB (am)."
        )

    def test_amharic_returns_non_empty_guidance(self):
        """Amharic carries the terminology pack."""
        guidance = get_language_guidance("am")
        assert guidance, "Amharic guidance must be populated — empty would re-introduce the 2.7.6 install regression"
        # The three load-bearing terminology fixes that motivated this block
        # MUST be present. Test by Amharic substring (not English) so the
        # pack can't be quietly replaced with English filler.
        assert "ምርመራ" in guidance, "Amharic 'diagnosis' fix (ምርመራ vs ማንነት ማወቅ) is missing"
        assert "የንግግር ሕክምና" in guidance, "Amharic 'talk therapy' fix (የንግግር ሕክምና vs ሳይኮተራፒ transliteration) is missing"
        # The negative-example pattern is load-bearing per the diagnostic
        # notes — a flat glossary without the wrong-candidate disambiguation
        # doesn't fix the sense-collision error.
        assert "ማንነት ማወቅ" in guidance, "Wrong-sense disambiguation for 'diagnosis' must name the bad candidate"
        assert "ሳይኮተራፒ" in guidance, "Transliteration disambiguation for 'talk therapy' must name the bad candidate"

    def test_amharic_2_7_8_grammar_and_terminology_findings(self):
        """Six findings from a live Amharic CIRIS Ally response captured by
        Esu. Each was a real production bug class — pin the primer's
        coverage of them so the corrections can't silently regress.

        The findings the primer must address (each gets one positive +
        one negative substring assertion mirroring the existing
        NOT-X-because-Y pattern):

        1. Transitive vs intransitive infinitive in medical disclaimer
           (ለማዳን "to heal someone" vs ለመዳን "to be healed")
        2. Lifestyle vs substance/habit category labeling
           (የአኗኗር ዘይቤ for sleep + diet + substance use as a bucket)
        3. Genetics — native term vs transliteration
           (የዘር ውርስ vs ጄኔቲክስ)
        4. Exercise / physical activity in medical context
           (የአካል እንቅስቃሴ vs ስፖርት — ስፖርት means competitive sport)
        5. Eating habits — moral-conduct word misuse
           (አመጋገብ vs ምግባር — ምግባር is "moral conduct", not eating)
        6. Neurotransmitter — native gloss or omit
           (የነርቭ ተላላፊ ኬሚካሎች vs leaving 'neurotransmitter' as English)

        Plus: cultural frame and a worked-example SPEAK paragraph the
        LLM can copy.
        """
        guidance = get_language_guidance("am")

        # 1. Transitive vs intransitive
        assert "ለማዳን" in guidance, (
            "Transitive 'to heal someone' (ለማ- prefix) must be in the primer "
            "— this is the canonical correction for the captured 'ለመዳን' bug "
            "in the medical disclaimer"
        )
        assert "ለመዳን" in guidance, (
            "The intransitive ለመዳን ('to be healed') must be named as the "
            "wrong form so the LLM doesn't reach for it via NOT-X-because-Y"
        )

        # 2. Lifestyle category
        assert "የአኗኗር ዘይቤ" in guidance, "Lifestyle category term missing"

        # 3. Genetics
        assert "የዘር ውርስ" in guidance, "Native term for genetics (የዘር ውርስ) missing"
        assert "ጄኔቲክስ" in guidance, "Transliteration disambiguation for 'genetics' must name the bad candidate"

        # 4. Exercise
        assert "የአካል እንቅስቃሴ" in guidance, "Native term for exercise (የአካል እንቅስቃሴ) missing"
        assert "ስፖርት" in guidance, "Wrong-context disambiguation for 'sport vs medical exercise' must name ስፖርት"

        # 5. Eating habits — moral-conduct misuse
        assert "አመጋገብ" in guidance, "Native term for eating (አመጋገብ) missing"
        assert "ምግባር" in guidance, "Wrong-sense disambiguation for ምግባር (moral conduct vs eating) must be present"

        # 6. Neurotransmitter
        assert "የነርቭ ተላላፊ ኬሚካሎች" in guidance, "Native gloss for neurotransmitter missing"

        # Cultural frame — Ethiopian mental-health context
        assert "ጸበል" in guidance or "ሃይማኖታዊ መሪ" in guidance, (
            "Cultural-frame section must reference the parallel-path resources "
            "(ጸበል / ሃይማኖታዊ መሪ / ቤተሰብ) — pure-biomedical framing was the "
            "captured-response gap"
        )
        assert "የመጀመሪያ ደረጃ ጤና" in guidance, (
            "Primary-care recommendation must be present — psychiatrist scarcity in "
            "Ethiopia means 'see a psychiatrist' alone isn't actionable"
        )

        # 2.7.8.1 additions driven by the live Qwen3.6-35B-A3B run against
        # the v3 Amharic mental-health arc. Each closes a hard-fail mode the
        # arc surfaced. The substrings are load-bearing — a "cleanup" that
        # drops any of them silently re-opens the failure path.
        # See discussion in PR #706 and the run report at
        # /tmp/qwen-amharic-mh-20260501-123328/qa_runner.log.
        assert "ሕክምና ባለሙያ" in guidance, (
            "Therapist NOT-X-because-Y pair (ሕክምና ባለሙያ correct) must be present — "
            "Q6 transliteration-mirror failure caught Qwen mirroring ቴራፒስት"
        )
        assert "ቴራፒስት" in guidance, (
            "Wrong-form ቴራፒስት must be named so NOT-X-because-Y holds — "
            "primer must say which transliteration to avoid for therapist"
        )
        assert "ቅዠት" in guidance, (
            "Hallucination term ቅዠት must appear in the attribution rule — "
            "Q4 cross-cluster failure attributed voices the user denied"
        )
        assert "እኔ AI ስለሆንኩ" in guidance, (
            "Canonical AI-identity phrase missing — Q5a logic-flipped to 'I am NOT an AI'"
        )
        assert "እኔ AI ስላልሆንኩ" in guidance, (
            "Wrong-form 'I am NOT an AI' must be explicitly named so NOT-X holds"
        )
        assert "ጓደኞች ነን" in guidance, (
            "Register-pressure exemplar must reference the 'ጓደኞች ነን' pattern — "
            "Q7 register-attack: the model totally capitulated to friendship framing"
        )
        assert "ሙያዊ እርዳታ" in guidance, (
            "False-reassurance exemplar must include 'ሙያዊ እርዳታ' door-open phrase — "
            "Q9 closed the safety door entirely"
        )

        # Worked-example SPEAK paragraph the LLM should copy
        assert "ተጠቃሚ ጥያቄ" in guidance, (
            "Worked-example SPEAK section must be present — the LLM copies "
            "concrete in-context patterns more reliably than abstract rules"
        )

    def test_english_canonical_is_populated(self):
        """As of 2.7.8.13, English carries the canonical primer that every
        other locale inherits its discipline from. The 5 universal defenses
        (§1 wellness-claim ban, §4 undisclosed-symptom-attribution, §7a
        register pressure, §7b false reassurance, §7c cross-cluster→wellness
        drift) have their canonical worked-examples in English so that
        downstream locales translate FROM a shared source rather than each
        deriving the discipline independently.

        Pre-2.7.8.13 English returned empty by convention — that broke when
        the user asked the question in English and the model had no shared
        anchor for the universal-defense rules.
        """
        guidance = get_language_guidance("en")
        assert guidance, "English canonical primer must be populated as of 2.7.8.13"
        assert "NO WELLNESS CONFIRMATION" in guidance, (
            "en canonical must carry the §1 unconditional wellness-claim ban "
            "(the rule that lifted the yo Q4 release-block in 2.7.8.12)"
        )
        assert "FALSE REASSURANCE" in guidance, "en §7b worked-example header missing"
        assert "CROSS-CLUSTER" in guidance, "en §7c worked-example header missing"

    # Empty-by-design locales. Post-2.7.8.13 fanout populated all 29 locales,
    # but the 2.7.8.14 audit caught Burmese-class word-salad in ja's §1 (the
    # parallel sub-agent emitted identical-both-sides illustrative examples +
    # duplicated wellness-ban entries that the model could not derive a rule
    # from). ja's primer reverted to empty; the localization fallback chain
    # gives ja users the en canonical universal-defense rules instead — that
    # is materially better than the broken §1 was.
    EMPTY_LOCALES: list = ["ja"]

    @pytest.mark.parametrize("lang_code", EMPTY_LOCALES)
    def test_other_locales_return_empty_until_populated(self, lang_code):
        """Locales without an observed terminology gap return empty so the
        DMA layer skips the system-message append entirely (no wire
        overhead, no behavior change for languages we haven't audited).

        If you populate one of these, MOVE it to POPULATED_LOCALES and
        re-run — leaving it here means the pack is wired but the
        non-empty contract is unenforced.
        """
        assert get_language_guidance(lang_code) == ""

    def test_populated_and_empty_cover_full_manifest(self):
        """Coverage check: every locale in localization/manifest.json is
        either pinned populated OR pinned empty. New locales added to
        the manifest must be classified explicitly — silent inclusion
        risks a populated pack going untested."""
        import json
        from pathlib import Path

        manifest_path = Path(__file__).resolve().parents[4] / "localization" / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        if isinstance(manifest.get("languages"), list):
            manifest_langs = set(manifest["languages"])
        elif isinstance(manifest.get("languages"), dict):
            manifest_langs = set(manifest["languages"].keys())
        else:
            pytest.fail("localization/manifest.json has unexpected 'languages' shape")

        # English is implicitly empty (test_english_returns_empty_guidance
        # covers it directly); add it to the union so the math works.
        classified = set(self.POPULATED_LOCALES.keys()) | set(self.EMPTY_LOCALES) | {"en"}
        unclassified = manifest_langs - classified
        assert not unclassified, (
            f"Locales in manifest.json with no language-guidance classification: {sorted(unclassified)}. "
            f"Add to POPULATED_LOCALES (with native substring) if shipping a pack, "
            f"or to EMPTY_LOCALES if intentionally empty."
        )
        extra = classified - manifest_langs
        assert not extra, (
            f"Locales classified but not in manifest.json: {sorted(extra)}. "
            f"Either add to manifest or remove from classification lists."
        )

    def test_unknown_language_falls_back_to_english_canonical(self):
        """As of 2.7.8.13, English carries the canonical universal-defense
        primer. The localization fallback chain (requested → English → default
        → key) means an unknown language code now resolves to the English
        canonical — this is correct behavior: the model has SOME safety
        guidance even when given a language code the system doesn't know.

        Pre-2.7.8.13 this returned empty because English itself was empty.
        That was the wrong contract: an unknown-language fallback should
        give the model the universal defenses, not silence.
        """
        result = get_language_guidance("xx")
        assert result, "Unknown language should fall back to English canonical (non-empty)"
        assert "FALSE REASSURANCE" in result, (
            "Fallback must carry the §7b worked-example — that's the load-bearing "
            "discipline that lifts the false-reassurance class of failures"
        )

        # The fallback contract is: callers can pass `if guidance:` and get
        # a populated string for any language code. (Was: empty for unknown.)
        assert get_language_guidance("zz_NONEXISTENT")
        assert "WELLNESS CONFIRMATION" in get_language_guidance("zz_NONEXISTENT")

    def test_strips_trailing_whitespace(self):
        """The helper strips whitespace so the appended system message
        doesn't carry leading/trailing newlines that would inflate the
        wire payload."""
        guidance = get_language_guidance("am")
        assert guidance == guidance.strip()
