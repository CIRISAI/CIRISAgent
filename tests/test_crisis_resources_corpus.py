"""Corpus-backed crisis resources (CIRISAgent#971).

Three jobs:

1. GOLDEN — the en crisis blocks are byte-frozen. The safety battery scores
   resource naming (#969) and the DSDMA prompt is hot; the corpus refactor must
   be invisible at en. The constants below were captured from the pre-corpus
   hardcoded registry on release/2.9.9 and must NEVER be regenerated from the
   code under test — that would make the test a tautology.
2. FAIL-SAFE — unknown/hostile/corrupt locale input always yields the en base
   registry (international directories + en block): never empty, never KeyError.
3. CORPUS INTEGRITY — every manifest language has a valid corpus file, and no
   phone-carrying entry can be emitted without human verification. Fabricated
   crisis numbers must be structurally unable to reach a prompt.
"""

import json
from pathlib import Path

import pytest

from ciris_engine.logic.formatters.crisis_resources import format_crisis_resources_block
from ciris_engine.schemas.resources.crisis import (
    CrisisResource,
    CrisisResourceRegistry,
    CrisisResourceSource,
    CrisisResourceType,
    get_crisis_response_text,
    load_crisis_registry,
)

CORPUS_DIR = Path(__file__).parent.parent / "ciris_engine" / "data" / "localized"

# Locales whose findahelpline entry carries a verified country deep link
# (mapping rationale: CRISIS_RESOURCES_VERIFICATION_NEEDED.md).
DEEP_LINKS = {
    "hi": "in",
    "id": "id",
    "it": "it",
    "ja": "jp",
    "ko": "kr",
    "mr": "in",
    "my": "mm",
    "pa": "in",
    "te": "in",
    "th": "th",
    "tr": "tr",
    "uk": "ua",
    "vi": "vn",
    "yo": "ng",
    "zh": "cn",
}

# ---------------------------------------------------------------------------
# GOLDEN CONSTANTS — captured 2026-08-02 from the pre-corpus registry
# (release/2.9.9, commit 901266144). Do not regenerate from code under test.
# ---------------------------------------------------------------------------

GOLDEN_EN_SIMPLIFIED = (
    "=== Crisis Resources ===\n"
    "• Find a Helpline: International directory of crisis helplines\n"
    "• IASP Crisis Centers: International Association for Suicide Prevention resource directory\n"
    "• Local Crisis Services: Search for crisis services in your area\n"
    "• For immediate danger: Call 911 or local emergency services"
)

GOLDEN_EN_FULL = (
    "The information shared suggests professional support may be helpful.\n"
    "\n"
    "DISCLAIMER: I am an AI moderator, not a healthcare provider. The following\n"
    "is general information only, not medical advice or crisis intervention:\n"
    "\n"
    "This information is provided as-is without warranty. CIRIS L3C is not a\n"
    "healthcare provider and does not endorse these resources. Please seek\n"
    "qualified professional help.\n"
    "\n"
    "**General Crisis Resources (not endorsements):**\n"
    "\n"
    "**Find a Helpline**\n"
    "• Website: https://findahelpline.com/\n"
    "• International directory of crisis helplines\n"
    "\n"
    "**IASP Crisis Centers**\n"
    "• Website: https://iasp.info/resources/Crisis_Centres\n"
    "• International Association for Suicide Prevention resource directory\n"
    "\n"
    "**Local Crisis Services**\n"
    "• Search: 'crisis hotline [your location]'\n"
    "• Search for crisis services in your area\n"
    "\n"
    "For immediate danger: Contact 911 or local emergency services\n"
    "\n"
    "[DEFER TO HUMAN MODERATOR]"
)

# The exact resource-id insertion order of the pre-corpus registry.
LEGACY_EN_RESOURCE_ORDER = [
    "findahelpline",
    "iasp",
    "crisis_text_line",
    "988_lifeline",
    "samaritans",
    "local_search",
    "emergency_services",
    "ethiopia_police",
    "ethiopia_ambulance",
    "ethiopia_fire",
]


def manifest_languages() -> list:
    manifest = json.loads((CORPUS_DIR / "manifest.json").read_text(encoding="utf-8"))
    langs = manifest["languages"]
    if isinstance(langs, dict):
        return list(langs.keys())
    return [x["code"] if isinstance(x, dict) else x for x in langs]


class TestGoldenEnByteIdentity:
    """The en blocks must not change by a single byte."""

    def test_simplified_block_byte_identical(self):
        assert format_crisis_resources_block(include_full_disclaimer=False) == GOLDEN_EN_SIMPLIFIED

    def test_full_block_byte_identical(self):
        assert format_crisis_resources_block() == GOLDEN_EN_FULL

    def test_response_text_byte_identical(self):
        assert get_crisis_response_text() == GOLDEN_EN_FULL

    @pytest.mark.parametrize("language", [None, "en", "EN", "en-US", "en_GB"])
    def test_language_variants_resolve_to_golden(self, language):
        result = format_crisis_resources_block(include_full_disclaimer=False, language=language)
        assert result == GOLDEN_EN_SIMPLIFIED

    def test_en_corpus_preserves_legacy_registry(self):
        registry = load_crisis_registry("en")
        assert list(registry.resources.keys()) == LEGACY_EN_RESOURCE_ORDER
        # Load-bearing safety data pinned (mirrors test_crisis_resources.py)
        assert registry.resources["988_lifeline"].phone == "988"
        assert registry.resources["samaritans"].phone == "116 123"
        assert registry.resources["crisis_text_line"].text_number == "741741"
        assert registry.resources["ethiopia_ambulance"].phone == "907"


class TestFailSafeFallback:
    """Unknown/hostile locale input must yield the en block — never empty, never a KeyError."""

    @pytest.mark.parametrize(
        "language",
        ["xx", "zz", "", "  ", "klingon", "../../etc/passwd", "en/../am", "a", "1234", "\x00"],
    )
    def test_unknown_or_hostile_locale_falls_back_to_en(self, language):
        result = format_crisis_resources_block(include_full_disclaimer=False, language=language)
        assert result == GOLDEN_EN_SIMPLIFIED

    def test_non_string_language_falls_back_to_en(self):
        # DSDMA unit tests mock the prompt loader, so garbage can reach this
        # parameter; a crisis surface swallows it and serves en, never raises.
        result = format_crisis_resources_block(
            include_full_disclaimer=False, language=object()  # type: ignore[arg-type]
        )
        assert result == GOLDEN_EN_SIMPLIFIED

    def test_unknown_locale_registry_is_en(self):
        registry = load_crisis_registry("xx")
        assert registry.locale == "en"
        assert "findahelpline" in registry.resources

    def test_every_manifest_language_produces_a_block(self):
        for lang in manifest_languages():
            block = format_crisis_resources_block(include_full_disclaimer=False, language=lang)
            assert block.startswith("=== Crisis Resources ===")
            assert "findahelpline" in block.lower() or "Find a Helpline" in block
            assert len(block.splitlines()) >= 3

    def test_corrupt_locale_file_falls_back_to_en(self, tmp_path, monkeypatch):
        import ciris_engine.schemas.resources.crisis as crisis_mod

        bad = tmp_path / "crisis_resources_vi.json"
        bad.write_text("{not json", encoding="utf-8")
        good_en = CORPUS_DIR / "crisis_resources_en.json"
        (tmp_path / "crisis_resources_en.json").write_text(good_en.read_text(encoding="utf-8"), encoding="utf-8")

        monkeypatch.setattr(crisis_mod, "_CRISIS_CORPUS_DIR", tmp_path)
        # Force the path fallback (importlib.resources would hit the real package)
        monkeypatch.setattr(
            crisis_mod, "_read_corpus_text", lambda f: (tmp_path / f).read_text(encoding="utf-8") if (tmp_path / f).exists() else None
        )
        crisis_mod._load_crisis_registry_cached.cache_clear()
        try:
            registry = crisis_mod.load_crisis_registry("vi")
            assert registry.locale == "en"
        finally:
            crisis_mod._load_crisis_registry_cached.cache_clear()


class TestCorpusIntegrity:
    """Every manifest language has a valid corpus file with sane provenance."""

    @pytest.mark.parametrize("lang", manifest_languages())
    def test_corpus_file_exists_and_validates_directly(self, lang):
        # Direct validation — the loader's en-fallback must not hide breakage.
        path = CORPUS_DIR / f"crisis_resources_{lang}.json"
        assert path.exists(), f"missing corpus file for manifest language {lang!r}"
        data = json.loads(path.read_text(encoding="utf-8"))
        data.pop("_meta", None)
        registry = CrisisResourceRegistry.model_validate(data)
        assert registry.locale == lang, f"{path.name} declares locale {registry.locale!r}"

    @pytest.mark.parametrize("lang", manifest_languages())
    def test_international_directories_present_everywhere(self, lang):
        registry = load_crisis_registry(lang)
        for rid in ("findahelpline", "iasp", "local_search"):
            assert rid in registry.resources, f"{lang} corpus missing international entry {rid!r}"

    @pytest.mark.parametrize("lang", manifest_languages())
    def test_no_unverified_number_can_be_emitted(self, lang):
        """THE anti-fabrication gate.

        Corpus hygiene: a phone-carrying entry is either human-verified (with
        notes) or explicitly unverified-with-source (awaiting a human flip).
        Emission: default_prompt_resources never surfaces an unverified number.
        """
        registry = load_crisis_registry(lang)
        for rid, entry in registry.resources.items():
            if entry.phone or entry.text_number:
                if entry.verified:
                    assert entry.validation_notes, f"{lang}/{rid}: verified number without validation_notes"
                else:
                    assert entry.source_url, f"{lang}/{rid}: unverified number without source_url — forbidden"
        for entry in registry.default_prompt_resources():
            if entry.phone or entry.text_number:
                assert entry.verified, f"{lang}: unverified number emitted into prompt set"

    @pytest.mark.parametrize("lang", [l for l in manifest_languages() if l != "en"])
    def test_unverified_locales_are_marked(self, lang):
        registry = load_crisis_registry(lang)
        has_verified_national = any(
            r.verified and (r.phone or r.text_number) for r in registry.resources.values()
        )
        assert registry.needs_verified_entries or has_verified_national, (
            f"{lang}: no verified national entries and no needs_verified_entries marker"
        )

    def test_deep_links_where_mapping_unambiguous(self):
        for lang, cc in DEEP_LINKS.items():
            registry = load_crisis_registry(lang)
            url = str(registry.resources["findahelpline"].url)
            assert url.rstrip("/").endswith(f"/countries/{cc}"), f"{lang}: expected /countries/{cc} deep link, got {url}"

    def test_am_has_no_country_deep_link(self):
        # findahelpline.com/countries/et was a 404 at corpus cut — a broken
        # deep link on a crisis surface is exactly the failure class this
        # corpus exists to prevent.
        registry = load_crisis_registry("am")
        assert str(registry.resources["findahelpline"].url) == "https://findahelpline.com/"


class TestLocaleBlocks:
    """Locale-curated registries surface their verified national entries."""

    def test_am_block_surfaces_verified_ethiopia_numbers(self):
        block = format_crisis_resources_block(include_full_disclaimer=False, language="am")
        # National entries first, numbers rendered deterministically.
        assert "907" in block  # ambulance — primary medical/psych route
        assert "991" in block  # federal police
        assert "939" in block  # fire brigade
        assert "Find a Helpline" in block  # directories still present
        first_resource_line = block.splitlines()[1]
        assert "Ambulance" in first_resource_line

    def test_directory_only_locale_matches_en_content(self):
        # A locale with no verified national entries carries exactly the
        # international directory set — same lines as the en block.
        block = format_crisis_resources_block(include_full_disclaimer=False, language="sw")
        assert block == GOLDEN_EN_SIMPLIFIED.replace("=== Crisis Resources ===", "=== Crisis Resources ===")
        assert block == GOLDEN_EN_SIMPLIFIED

    def test_unverified_number_never_reaches_block(self):
        registry = CrisisResourceRegistry(
            locale="vi",
            needs_verified_entries=True,
            resources={
                "fake_hotline": CrisisResource(
                    id="fake_hotline",
                    name="Some Hotline",
                    type=CrisisResourceType.HOTLINE,
                    phone="123456",
                    description="Machine-cut, awaiting human verification",
                    source=CrisisResourceSource.THROUGHLINE,
                    verified=False,
                    source_url="https://example.org/snapshot",
                ),
                "directory": CrisisResource(
                    id="directory",
                    name="Directory",
                    type=CrisisResourceType.DIRECTORY,
                    url="https://findahelpline.com",
                    description="International directory of crisis helplines",
                    verified=True,
                ),
            },
        )
        emitted = registry.default_prompt_resources()
        assert [r.id for r in emitted] == ["directory"]
