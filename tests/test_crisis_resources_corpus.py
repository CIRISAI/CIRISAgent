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
    "• For immediate danger: Call 911, or your local emergency number if not in the US"
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
    "For immediate danger: Contact 911, or your local emergency number if not in the US\n"
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
        # The legacy entries keep their exact order as the PREFIX; #1248 appends
        # country emergency entries after them (reachable only via an opted-in
        # location — the en default selection is GLOBAL-only and unchanged).
        assert list(registry.resources.keys())[: len(LEGACY_EN_RESOURCE_ORDER)] == LEGACY_EN_RESOURCE_ORDER
        assert all(k.startswith("emergency_") for k in list(registry.resources)[len(LEGACY_EN_RESOURCE_ORDER):])
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
        # #1248: the Ethiopia numbers are rendered under the emergency-services
        # label, never in the helpline list above it (the old first-line
        # position is exactly how 907 got relayed as a "mental-health helpline").
        lines = block.splitlines()
        header = next(i for i, l in enumerate(lines) if "Emergency services" in l and l.startswith("==="))
        ambulance = next(i for i, l in enumerate(lines) if "Ambulance" in l and "907" in l)
        assert header < ambulance
        assert not any("907" in l for l in lines[:header])
        assert "[Ethiopia]" in next(l for l in lines if "907" in l)  # labelled by country
        assert lines[-1] == (
            "• For immediate danger: Call the emergency number listed above for your country, "
            "or local emergency services"
        )

    def test_directory_only_locale_matches_en_content(self):
        # A locale whose emergency numbers are all below the sourcing bar carries
        # exactly the international directory set, and since #1248 its
        # immediate-danger line names NO number (the old line told everyone
        # "Call 911"). Built synthetically so it holds whatever the corpus data is.
        from ciris_engine.logic.formatters import crisis_resources as fmt

        en = load_crisis_registry("en")
        registry = CrisisResourceRegistry(
            locale="sw",
            needs_verified_entries=True,
            resources={k: en.resources[k] for k in ("findahelpline", "iasp", "local_search")},
        )
        import unittest.mock as um

        with um.patch.object(fmt, "load_crisis_registry", return_value=registry):
            block = fmt.format_crisis_resources_block(include_full_disclaimer=False, language="sw")
        assert block == GOLDEN_EN_SIMPLIFIED.replace(
            "Call 911, or your local emergency number if not in the US", "Call local emergency services"
        )

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




# ---------------------------------------------------------------------------
# CIRISAgent#1248 — emergency numbers: cited-sources standard + selection
# ---------------------------------------------------------------------------

import re as _re
import unittest.mock as _mock

from ciris_engine.schemas.resources.crisis import (
    COUNTRY_NAMES,
    EMERGENCY_SECTION_LABEL,
    LANGUAGE_COUNTRY_CAP,
    ResourceAvailability,
    country_label,
    country_token,
    emergency_index,
    resolve_location_country,
)

STAGED_DATE = "2026-10-29"
LEGACY_AVAILABILITY = {"global", "regional", "eu"}
LABELLED_LINE = _re.compile(r"^(?:• )?\[(?P<label>[^\]]+)\]")
LOCATION_ENV = ("CIRIS_USER_COUNTRY", "CIRIS_USER_LOCATION")


@pytest.fixture(autouse=False)
def no_location(monkeypatch):
    for key in LOCATION_ENV:
        monkeypatch.delenv(key, raising=False)


def _country_from_label(label: str) -> ResourceAvailability:
    name = label.replace(" — your location", "")
    return next(c for c, n in COUNTRY_NAMES.items() if n == name)


def _emittable_phones(country: ResourceAvailability) -> set:
    return {r.phone for r in emergency_index().get(country, [])}


def _blocks(lang: str, location=None) -> list:
    registry = load_crisis_registry(lang)
    regions = sorted({a for r in registry.resources.values() for a in r.availability}, key=lambda a: a.value)
    out = []
    for full in (False, True):
        out.append(format_crisis_resources_block(include_full_disclaimer=full, language=lang, location=location))
        out.append(format_crisis_resources_block(include_full_disclaimer=full, language=lang, regions=regions))
        out.append(
            format_crisis_resources_block(include_full_disclaimer=full, language=lang, resource_ids=list(registry.resources))
        )
    return out


def _numbers_in(line: str) -> list:
    return _re.findall(r"(?<![\d])\d{2,6}(?![\d])", line)


def _label_match(lines: list, i: int):
    """The [Country] label governing line i: on the line itself (simplified format)
    or on the entry's name line directly above it (full format)."""
    line = lines[i]
    if LABELLED_LINE.match(line):
        return LABELLED_LINE.match(line)
    head = next((l for l in reversed(lines[:i]) if l.startswith("[") or l.startswith("**")), "")
    return LABELLED_LINE.match(head)


def _countries_of(label: str) -> list:
    return [_country_from_label(part) for part in label.replace(" — your location", "").split(" / ")]


def _assert_every_number_is_labelled_and_emittable(block: str, lang: str) -> None:
    lines = block.splitlines()
    for i, line in enumerate(lines):
        if "Phone:" not in line and "Text:" not in line:
            continue
        m = _label_match(lines, i)
        if m is None:
            # Only non-emergency (helpline) entries may carry a number without a
            # country label — and only human-verified ones (en: 988 / Samaritans).
            continue
        for number in _numbers_in(line.split("Phone:")[-1]):
            assert any(number in _emittable_phones(c) for c in _countries_of(m.group("label"))), (
                f"{lang}: {number} under [{m.group('label')}] is not emittable"
            )


class TestCitedSourcesStandard1248:
    """Owner ruling 2026-10-29: >=2 independent agreeing sources, >=1 official, emergency numbers only."""

    @pytest.mark.parametrize("lang", manifest_languages())
    def test_every_emergency_entry_states_its_bar(self, lang):
        registry = load_crisis_registry(lang)
        for rid, e in registry.resources.items():
            if e.snapshot_date is None or e.snapshot_date.isoformat() != STAGED_DATE:
                continue
            assert e.type == CrisisResourceType.EMERGENCY, f"{lang}/{rid}"
            assert e.phone and " " not in e.phone, f"{lang}/{rid}: one entry per number"
            assert len(e.availability) == 1 and e.availability[0].value not in LEGACY_AVAILABILITY, f"{lang}/{rid}"
            assert e.source_url is not None, f"{lang}/{rid}: no source_url"
            if e.verified:
                assert e.source == CrisisResourceSource.MULTI_SOURCE_CITED, f"{lang}/{rid}: verified but not multi_source_cited"
                assert len(e.source_urls) >= 1, f"{lang}/{rid}: fewer than two sources"
                assert str(e.source_url) not in {str(u) for u in e.source_urls}, f"{lang}/{rid}: source counted twice"
                assert e.validation_notes.startswith(f"CITED {STAGED_DATE}"), f"{lang}/{rid}"
            else:
                assert e.source != CrisisResourceSource.MULTI_SOURCE_CITED, f"{lang}/{rid}"
                assert "BELOW the cited-sources bar" in e.validation_notes, f"{lang}/{rid}: below-bar reason missing"

    @pytest.mark.parametrize("lang", [l for l in manifest_languages() if l != "en"])
    def test_needs_verified_entries_marker_unchanged(self, lang):
        # needs_verified_entries tracks HOTLINES (still human-verified); citing
        # emergency numbers must never clear it.
        data = json.loads((CORPUS_DIR / f"crisis_resources_{lang}.json").read_text(encoding="utf-8"))
        assert data["needs_verified_entries"] is True, lang

    def test_multi_source_cited_is_refused_on_a_hotline(self):
        from pydantic import ValidationError

        with pytest.raises((ValidationError, ValueError)):
            CrisisResource(
                id="h", name="h", type=CrisisResourceType.HOTLINE, phone="123", description="d",
                source=CrisisResourceSource.MULTI_SOURCE_CITED, verified=True,
                source_url="https://example.gov/a", source_urls=["https://example.org/b"],
            )

    def test_multi_source_cited_needs_two_sources(self):
        from pydantic import ValidationError

        with pytest.raises((ValidationError, ValueError)):
            CrisisResource(
                id="e", name="e", type=CrisisResourceType.EMERGENCY, phone="112", description="d",
                source=CrisisResourceSource.MULTI_SOURCE_CITED, verified=True, source_url="https://example.gov/a",
            )

    @pytest.mark.parametrize("source", list(CrisisResourceSource))
    def test_unverified_number_is_never_emittable_whatever_its_source(self, source):
        kwargs = dict(source_url="https://example.gov/a", source_urls=["https://example.org/b"])
        e = CrisisResource(
            id="e", name="e", type=CrisisResourceType.EMERGENCY, phone="112", description="d",
            source=source, verified=False, **kwargs,
        )
        assert CrisisResourceRegistry.is_emittable(e) is False

    @pytest.mark.parametrize("lang", manifest_languages())
    def test_no_unverified_number_on_any_path_or_location(self, lang):
        registry = load_crisis_registry(lang)
        locations = [None, ResourceAvailability.DE, *registry.language_countries]
        for location in locations:
            for block in _blocks(lang, location):
                _assert_every_number_is_labelled_and_emittable(block, lang)

    @pytest.mark.parametrize("lang", manifest_languages())
    def test_911_only_under_a_country_whose_number_it_is(self, lang):
        for block in _blocks(lang):
            lines = block.splitlines()
            for i, line in enumerate(lines):
                if "911" not in line:
                    continue
                if line == "• For immediate danger: Call 911, or your local emergency number if not in the US" or line.startswith(
                    "For immediate danger: Contact 911"
                ):
                    # The legacy en line — byte-frozen golden; en's 911 is the
                    # human-verified US/Canada entry.
                    assert lang == "en"
                    en = load_crisis_registry("en").resources["emergency_services"]
                    assert en.verified and {a.value for a in en.availability} == {"us", "ca"}
                    continue
                m = _label_match(lines, i)
                assert m, f"{lang}: 911 without a country label: {line!r}"
                assert any("911" in _emittable_phones(c) for c in _countries_of(m.group("label"))), f"{lang}: {line!r}"

    @pytest.mark.parametrize("lang", manifest_languages())
    def test_same_number_is_identical_across_locale_files(self, lang):
        # IN 112 lives in seven files; a flip in one and not the others would make
        # emission depend on which language the user picked.
        mine = load_crisis_registry(lang)
        for other in manifest_languages():
            theirs = load_crisis_registry(other)
            for rid, e in mine.resources.items():
                t = theirs.resources.get(rid)
                if t is None or e.type != CrisisResourceType.EMERGENCY:
                    continue
                for field in ("phone", "verified", "source", "source_url", "description", "availability"):
                    assert getattr(e, field) == getattr(t, field), f"{rid}: {field} differs between {lang} and {other}"

    @pytest.mark.parametrize("lang", manifest_languages())
    def test_no_helpline_reuses_an_emergency_number(self, lang):
        registry = load_crisis_registry(lang)
        emergency = {r.phone for r in registry.resources.values() if r.type == CrisisResourceType.EMERGENCY}
        for r in registry.resources.values():
            if r.type != CrisisResourceType.EMERGENCY and r.phone:
                assert r.phone not in emergency, f"{lang}/{r.id}"


def _registry_with(entries, language_countries=(), locale="es") -> CrisisResourceRegistry:
    en = load_crisis_registry("en")
    resources = {k: en.resources[k] for k in ("findahelpline", "iasp", "local_search")}
    resources.update({e.id: e for e in entries})
    return CrisisResourceRegistry(locale=locale, needs_verified_entries=True, resources=resources,
                                  language_countries=list(language_countries))


def _em(rid, country, phone, verified=True, desc="Unified emergency number (police, ambulance, fire)"):
    return CrisisResource(
        id=rid, name="Emergency services", type=CrisisResourceType.EMERGENCY, phone=phone, description=desc,
        availability=[country], verified=verified,
        source=CrisisResourceSource.MULTI_SOURCE_CITED if verified else CrisisResourceSource.BUILTIN,
        source_url="https://www.gov.uk/foreign-travel-advice/x/getting-help",
        source_urls=["https://android.googlesource.com/x"] if verified else [], validation_notes="test",
    )


class TestEmergencySelection1248:
    def _simple(self, registry, location=None):
        from ciris_engine.logic.formatters import crisis_resources as fmt

        with _mock.patch.object(fmt, "load_crisis_registry", return_value=registry):
            return fmt.format_crisis_resources_block(include_full_disclaimer=False, language=registry.locale, location=location)

    def _labels(self, block):
        return [m.group("label") for m in map(LABELLED_LINE.match, block.splitlines()) if m]

    def test_language_path_orders_by_speaker_population(self, no_location):
        block = format_crisis_resources_block(include_full_disclaimer=False, language="es")
        labels = list(dict.fromkeys(self._labels(block)))
        expected = [COUNTRY_NAMES[c] for c in load_crisis_registry("es").language_countries if emergency_index().get(c)]
        assert labels == expected[:LANGUAGE_COUNTRY_CAP]

    def test_location_in_language_set_comes_first_labelled(self):
        mx = ResourceAvailability.MX
        block = format_crisis_resources_block(include_full_disclaimer=False, language="es", location=mx)
        labels = list(dict.fromkeys(self._labels(block)))
        assert labels[0] == "Mexico — your location"
        assert "Mexico" not in labels[1:]  # not repeated in the language list

    def test_location_outside_language_set_first_then_language(self):
        registry = _registry_with([_em("es_112", "es", "112")], ["es"])
        index = {ResourceAvailability.DE: [_em("de_112", "de", "112")]}
        with _mock.patch("ciris_engine.schemas.resources.crisis.emergency_index", return_value=index):
            block = self._simple(registry, location=ResourceAvailability.DE)
        assert self._labels(block) == ["Germany — your location", "Spain"]

    def test_location_without_entries_falls_back_to_language(self):
        registry = _registry_with([_em("es_112", "es", "112")], ["es"])
        with _mock.patch("ciris_engine.schemas.resources.crisis.emergency_index", return_value={}):
            block = self._simple(registry, location=ResourceAvailability.DE)
        assert self._labels(block) == ["Spain"]

    def test_nothing_emittable_names_no_number(self):
        registry = _registry_with([_em("es_112", "es", "112", verified=False)], ["es"])
        with _mock.patch("ciris_engine.schemas.resources.crisis.emergency_index", return_value={}):
            block = self._simple(registry, location=ResourceAvailability.DE)
        assert "112" not in block
        assert block.splitlines()[-1] == "• For immediate danger: Call local emergency services"

    def test_language_countries_are_capped(self):
        countries = ["mx", "co", "es", "ar", "fr", "de", "it", "pt"]
        entries = [_em(f"e_{c}", c, "112") for c in countries]
        registry = _registry_with(entries, countries)
        block = self._simple(registry)
        assert len(set(self._labels(block))) == LANGUAGE_COUNTRY_CAP == 6

    def test_emergency_rendered_under_emergency_label_not_hotline(self):
        hotline = CrisisResource(id="h", name="Some Helpline", type=CrisisResourceType.HOTLINE, phone="024",
                                 description="Crisis support line", availability=["es"], verified=True,
                                 validation_notes="t")
        registry = _registry_with([hotline, _em("es_112", "es", "112")], ["es"])
        simple = self._simple(registry).splitlines()
        label = simple.index(f"=== {EMERGENCY_SECTION_LABEL} ===")
        assert "NOT mental-health or crisis helplines" in EMERGENCY_SECTION_LABEL
        assert next(i for i, l in enumerate(simple) if "Some Helpline" in l) < label
        assert next(i for i, l in enumerate(simple) if "112" in l) > label
        assert simple[label + 1].startswith("• [Spain] ")
        full = registry.format_crisis_response()
        assert full.index("Some Helpline") < full.index(f"**{EMERGENCY_SECTION_LABEL}:**") < full.index("[Spain]")

    def test_line_resolution_per_locale(self, no_location):
        last = lambda lang: format_crisis_resources_block(include_full_disclaimer=False, language=lang).splitlines()[-1]
        listed = "• For immediate danger: Call the emergency number listed above for your country, or local emergency services"
        assert last("en") == "• For immediate danger: Call 911, or your local emergency number if not in the US"  # golden
        assert last("am") == listed
        assert last("es") == listed

    def test_en_changes_only_when_location_is_set(self):
        assert format_crisis_resources_block(include_full_disclaimer=False, language="en") == GOLDEN_EN_SIMPLIFIED
        with_loc = format_crisis_resources_block(
            include_full_disclaimer=False, language="en", location=ResourceAvailability.US
        )
        assert "[United States / Canada — your location]" in with_loc and "911" in with_loc


class TestLocationResolution1248:
    def test_country_code_env_wins(self, monkeypatch):
        monkeypatch.setenv("CIRIS_USER_COUNTRY", "DE")
        monkeypatch.setenv("CIRIS_USER_LOCATION", "Spain, Madrid")
        assert resolve_location_country() == ResourceAvailability.DE

    def test_location_string_country(self, monkeypatch):
        monkeypatch.delenv("CIRIS_USER_COUNTRY", raising=False)
        monkeypatch.setenv("CIRIS_USER_LOCATION", "Germany, Bavaria, Munich")
        assert resolve_location_country() == ResourceAvailability.DE

    def test_city_first_location_string(self, monkeypatch):
        # setup/complete.py writes "city, region, country"
        monkeypatch.delenv("CIRIS_USER_COUNTRY", raising=False)
        monkeypatch.setenv("CIRIS_USER_LOCATION", "Lagos, Lagos State, Nigeria")
        assert resolve_location_country() == ResourceAvailability.NG

    @pytest.mark.parametrize("value", ["", "Atlantis", "XX", "global", "eu"])
    def test_unknown_location_is_none(self, monkeypatch, value):
        monkeypatch.setenv("CIRIS_USER_COUNTRY", value)
        monkeypatch.setenv("CIRIS_USER_LOCATION", value)
        assert resolve_location_country() is None

    def test_system_block_reads_location(self, monkeypatch):
        from ciris_engine.logic.formatters.crisis_resources import get_crisis_resources_system_block

        monkeypatch.setenv("CIRIS_USER_COUNTRY", "DE")
        block = get_crisis_resources_system_block("es")
        first = next(l for l in block.splitlines() if l.startswith("• ["))
        assert first.startswith("• [Germany — your location]")

    @pytest.mark.parametrize(
        "value,expected", [("US", "us"), ("United Kingdom", "uk"), ("GB", "uk"), ("Türkiye", "tr"), ("Turkey", "tr"),
                           ("ua", "ua"), ("Ivory Coast", "ci"), ("Viet Nam", "vn")]
    )
    def test_country_token(self, value, expected):
        assert country_token(value).value == expected


class TestCountryAvailabilitySchema1248:
    def test_schema_accepts_iso_country_codes_and_legacy_tokens(self):
        r = CrisisResource(
            id="x", name="x", type=CrisisResourceType.EMERGENCY, phone="112", description="d",
            availability=["es", "ng", "ua", "in", "us", "uk", "eu", "global", "et"],
        )
        assert ResourceAvailability.ES in r.availability and ResourceAvailability.UA in r.availability

    @pytest.mark.parametrize("bad", ["xx", "gb", "ES ", "spain", "ukr"])
    def test_schema_rejects_unknown_country_tokens(self, bad):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CrisisResource(id="x", name="x", type=CrisisResourceType.EMERGENCY, phone="112", description="d",
                           availability=[bad])

    def test_every_country_member_is_alpha2_and_named(self):
        for member in ResourceAvailability:
            if member.value in LEGACY_AVAILABILITY:
                continue
            assert _re.fullmatch(r"[a-z]{2}", member.value), member
            assert member in COUNTRY_NAMES, f"{member} has no display name — it could render unlabelled"
            assert country_label(member)
