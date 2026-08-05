"""The ``prompts.language_guidance`` prose split (#997) — proof, not intent.

``language_guidance`` was 13,694 B at ``en`` of one ``mixed`` block: register
doctrine, categorical prohibitions, crisis-line world-facts and value claims
interleaved sentence by sentence in a single JSON scalar. ``mixed`` defaults to
refuse, so none of it could be held or varied — a values arm holding this block
kept CIRIS's own "route serious symptoms to professional care without
minimization" byte-identical inside the alt-values condition, with every
Phase-1 assertion green. That is the §10.2.1 bias-toward-the-null confound the
block table exists to catch.

The split cuts the prose into 29 consecutive slices in the five locales whose
text is line-for-line parallel to English, and the composer joins them with
``""`` and strips once. **The only thing standing between that and a silent
prompt mutation in a locale nobody runs goldens on is the reassembly proof in
this file**, so it is pinned by sha256 per locale, for all 29 — split and
unsplit alike.

The twelve golden tests in ``tests/.../test_compose_messages_golden.py`` are the
other half of the net: ``language_guidance`` composes into every DMA step, so an
off-by-one byte fails them at ``en``. This file is what covers the other 28.

THE GOLDENS ARE NOT A NET FOR THIS FILE — corrected after adversarial review.

``compose_golden.py:163`` patches ``get_language_guidance`` with
``_sentinel_language_guidance``, which returns ``<GOLDEN-LANGUAGE-GUIDANCE
lang=en>``; every golden file contains that sentinel exactly once. The real
corpus never reaches them, so a byte change in ``language_guidance`` CANNOT
fail a golden.

There is ONE net: the per-locale sha256 + byte-length digests below, pinned
from the corpus as it stood BEFORE the split. That net is sufficient — it
covers all 29 locales including the 24 left whole, which is more than the
goldens would have given. But the commit message and an earlier version of this
docstring claimed two nets, and a reviewer who believed it would have trusted a
check that does not run. Asserting verification that was not performed is the
defect class this whole cut exists to remove; it is recorded here rather than
quietly deleted.

SPLITTING ALL 29 LOCALES IS OUT OF SCOPE, AND NOT REQUIRED FOR A TORQUE SERIES.

Split: en, es, fr, it, pt — the five whose line-type fingerprint matches English
exactly. Whole: the remaining 24, including every Tier-0 locale (am 25,338 B /
277 lines, yo 24,574 B / 212, ha 18,788 B / 206 — against en's 13,694 B / 123).

No mechanical boundary transfers. ``my`` has no section markers at all, ``hi``
numbers 1-12, ``uk`` renumbers to 6a-6d, ``fa``/``ur`` open at section 4, bullet
counts run 5 to 50. Mapping 29 class boundaries onto each would mean
re-segmenting target-language prose 24 times, and byte-identical reassembly
proves only that the pieces rejoin — a cut in the WRONG PLACE reassembles
perfectly and silently mis-classes the text. Each locale therefore needs a
native-language semantic read, which is the cost that makes this prohibitive
here and appropriate for RATCHET to take per-locale, as needed.

What it costs a campaign: in an unsplit locale ``language_guidance`` stays
``mixed`` and therefore REFUSES, which is the correct conservative behaviour. A
series still runs — it is bounded, not blocked. An arm carrying a measurable
axiotic contrast must either run in a split locale or declare the confound
explicitly. The Tier-0 gap is real and worth closing on mission grounds; it is
not a TORQUE blocker.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, List, Set, Tuple

import pytest

from ciris_engine.logic.utils.compose_dump import BLOCK_ANNOTATIONS, annotation_for
from ciris_engine.logic.utils.localization import (
    LANGUAGE_GUIDANCE_PART_KEYS,
    clear_cache,
    get_language_guidance,
    language_guidance_part_keys,
    language_guidance_parts,
)
from ciris_engine.schemas.dma.compose import BlockClass

REPO_ROOT = Path(__file__).resolve().parents[4]
BUNDLE = REPO_ROOT / "ciris_engine" / "data" / "localized"

#: The locales whose prose partitions on the English boundaries. Established by
#: a line-type fingerprint (heading / bullet / numbered / indented / text) that
#: is IDENTICAL to English for exactly these five, then read paragraph by
#: paragraph to confirm the semantic correspondence before cutting.
SPLIT_LOCALES: Tuple[str, ...] = ("en", "es", "fr", "it", "pt")

#: ``(sha256, bytes)`` of the COMPOSED block per locale — of what the model
#: receives, after the single ``.strip()``.
#:
#: **These are captured from the corpus as it stood BEFORE the split** (commit
#: 2cfd7ec2d, `prompts.language_guidance` a plain scalar in all 29 files). They
#: are the pre-image, not a snapshot of the post-split output — regenerating
#: them from the file the change just wrote would prove nothing at all. Twelve
#: golden tests cover ``en``; these cover the other 28, which have no goldens
#: and are exactly where a dropped separator would hide.
#:
#: DELIBERATE CONTENT CHANGE, 25 of 29 (#1010): the §7e directional guard was
#: added — as `26b_user_symptom_direction` in the split locales, appended after
#: the cross-cluster section in the unsplit ones — and fr §12 was rewritten to
#: state its rule without rendering the violation as a quotable sentence. Every
#: line below carrying `#1010 §7e guard` therefore no longer describes the
#: pre-split corpus: it describes the corpus WITH the guard, and the whole
#: delta is content we chose, NOT a split artifact. Each was re-pinned only
#: after confirming the byte delta equals the guard text plus its separators.
#:
#: FOUR locales keep their pre-image pins and carry NO guard: `ha`, `ko` and
#: `zh` failed back-translation review (ha: wrong `cross-cluster` coinage plus
#: a false claim about its own examples; ko: a translator-authored carve-out
#: that subordinates the exclusion rule to the asked/not-asked test, merging
#: claim 2 into claim 1; zh: an added gloss that falsely states both incorrect
#: examples refer the user to a professional). `sw` already states the rule
#: natively at its own §7e and is the locale the guard was reconstructed from.
#: A mistranslated guard reads as coverage, so those four stay unguarded until
#: their fixes land rather than shipping prose nobody could verify.
COMPOSED_SHA256: Dict[str, Tuple[str, int]] = {
    "en": ("8204c00f5a0375228b9d04f772bdf05bfc4e053666b604df9c13f001588aa007", 16029),  # #1010 §7e guard
    "am": ("0c18ae7cac234d35de3f40fed0b4e4a1f5164c409e9c1d8bc248698be3afad63", 30746),  # #1010 §7e guard
    "ar": ("0781686ee50d90e9808a231492a3beb5f08ebd84360c87f2e2fea4003ba289d3", 21478),  # #1010 §7e guard
    "de": ("7361ed32b88d248453855b3361ca783d0afaa6bf08555ecb8764a9662f88875f", 19323),  # #1010 §7e guard
    "es": ("fafa15bc2388a7a3275bed30f1f3cc6b572f430ad82c22cd29cd53a7d78820c3", 18249),  # #1010 §7e guard
    "fr": ("113f0dc501bc6267e8d5bb46064c88ba7366dac906ad82e2b46b081fd53ee104", 19489),  # #1010 §7e guard
    "hi": ("aff88795e26c27a6a58b1df37a5c597dad8009fc720d7a1d7ab19631aebae626", 31152),  # #1010 §7e guard
    "it": ("939e7e7d8274948c358d33dbf453340e9b2524751386c33ced3d94591de0b3d2", 18012),  # #1010 §7e guard
    "ja": ("a25fbb3e0ed56b6914dff2d310dc07351a4880a59820394335d53611238687bb", 19811),  # #1010 §7e guard
    "ko": ("0a37885175122f0a8b29ec9f7f4f80b3533b3b418213e4678465d6cd0de556ee", 15822),  # review FAILED — no guard
    "pt": ("32e622e4ba44914dd428eec2dea6a86cbf8edcebc11748d8d3ccb438832813b2", 17721),  # #1010 §7e guard
    "ru": ("bd4d9db9e05870b8907e1bd50c5b774fb5563037fddfc1019211794f459f8c1b", 30051),  # #1010 §7e guard
    "sw": ("0336ccb2019ecdc34f3b7ae4e5429d9509285276bcfeb097ffcb3f7a5bd2483e", 16925),  # native §7e already
    "tr": ("c6859cee118dd35b1ae4b062e58127900eeac5bedb627d0f74709ced6a492dcc", 16642),  # #1010 §7e guard
    "zh": ("11088ffc597a9922dd3cf6425f1229326dbd87b8e1dd3510d6e468a85f202d56", 12004),  # review FAILED — no guard
    "ur": ("ab76f821b001739366640658fec531542ef1f842d61f10fcf82f4f52e2288a38", 27214),  # #1010 §7e guard
    "bn": ("047fe419260f6523cb5e15bd2baa0252001bef8ba782e5dc206d0ddabc9528c3", 34683),  # #1010 §7e guard
    "fa": ("5e5e1526b5e1e53e954befe232cfe4978edf91757d8865019e1609916c713b45", 25019),  # #1010 §7e guard
    "ha": ("f52a17ab710a204a78ab4bd91fbad974bcf8a87a1b1444d84e1c58afdfa6984f", 18788),  # review FAILED — no guard
    "id": ("3b40e7bc1d3b414b27ccdaaec152cc46a81fb7af31ae78551b1033c68e66d11e", 16247),  # #1010 §7e guard
    "pa": ("1e69e8a6f45870a492b599449eb5eff0df4e76110b018a798b1075d3632937a7", 33060),  # #1010 §7e guard
    "ta": ("8384d1c0c641f41b54641f5748718ce15b114d450faf1eafbbf00b8b2b5b5d98", 39702),  # #1010 §7e guard
    "te": ("ba8481877dd63333f6b833944728beab62ef8fe267468e05220423fc6c060766", 35331),  # #1010 §7e guard
    "vi": ("265c8045363d890a9dc47e9937a81940c785f8e873178ad42933a22a5461d75b", 19958),  # #1010 §7e guard
    "mr": ("f7251fee1989e266e40818eb75824128517049e3b679426273b7238add2d6d91", 30752),  # #1010 §7e guard
    "my": ("ac3a5b5f7a20a0bbebedaf12ce6a24a159032f46167239c1bdf2d8b4a1b22b82", 50660),  # #1010 §7e guard
    "th": ("59576919a66bfa56285388bdfde024c8253676647378b873cd68d6ae8e454728", 32725),  # #1010 §7e guard
    "uk": ("21887070a5b04b8045b1bc8c252b0bc3bd374f0e7333d3d8b9d913c803f82f1b", 29410),  # #1010 §7e guard
    "yo": ("44138da1f3a5567b6b077767d2656410418c9bdb885da63ece7b067741a6b219", 28386),  # #1010 §7e guard
}

#: What the split bought at ``en``, in bytes. A ratchet on the number that
#: matters: entry counts can be reshuffled between registers, bytes cannot.
# 16029 after #1010 added the §7e guard (was 13694 at the split).
EN_TOTAL_BYTES = 16029
EN_MAX_MIXED_BYTES = 4189  # the five FSD-irreducible worked exemplars
EN_MIN_AXIOTIC_BYTES = 429  # parts 09 and 11 — 0 before the split


def _bundle_value(lang: str) -> object:
    data = json.loads((BUNDLE / f"{lang}.json").read_text(encoding="utf-8"))
    return data["prompts"]["language_guidance"]


def _manifest_languages() -> List[str]:
    manifest = json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8"))
    return list(manifest["languages"])


@pytest.fixture(autouse=True)
def _fresh_localization_cache() -> None:
    clear_cache()


# --------------------------------------------------------------------------
# 1. Byte-identical reassembly — the load-bearing proof
# --------------------------------------------------------------------------


@pytest.mark.parametrize("lang", SPLIT_LOCALES)
def test_split_locale_parts_reassemble_to_the_composed_block(lang: str) -> None:
    """``"".join(parts).strip()`` IS the block. Byte for byte, in the stated order.

    Order is ``sorted()`` over the part keys, which the numeric prefix makes
    equal to composition order — so no JSON normalizer or translator tool can
    reorder the prompt by touching key order in the file.
    """
    value = _bundle_value(lang)
    assert isinstance(value, dict), f"{lang} is expected to be split"

    parts = language_guidance_parts(lang)
    assert [k for k, _ in parts] == sorted(value), "parts must be resolved in sorted-key order"

    joined = "".join(text for _, text in parts)
    assert joined == "".join(value[k] for k in sorted(value))
    assert joined.strip() == get_language_guidance(lang)


@pytest.mark.parametrize("lang", sorted(COMPOSED_SHA256))
def test_every_locale_composes_the_same_bytes_it_did_before_the_split(lang: str) -> None:
    """THE regression guard, for all 29 — the 24 unsplit locales included.

    A locale with no golden test is exactly where a dropped separator hides.
    Any per-part ``.strip()`` — by a JSON normalizer, a localization integrity
    tool, a translator pipeline — lands here as a changed digest instead of as
    a silently shortened prompt in production.
    """
    expected_sha, expected_bytes = COMPOSED_SHA256[lang]
    composed = get_language_guidance(lang).encode("utf-8")
    assert len(composed) == expected_bytes, f"{lang}: {len(composed)} B, pinned {expected_bytes} B"
    assert hashlib.sha256(composed).hexdigest() == expected_sha, (
        f"{lang}: composed language_guidance changed. The split must be a partition of the "
        f"same bytes — a mismatch here is a production prompt mutation in a locale that may "
        f"have no golden test."
    )


def test_the_digest_pins_cover_every_manifest_language() -> None:
    """A locale that quietly leaves the pin table would be unguarded."""
    assert sorted(COMPOSED_SHA256) == sorted(_manifest_languages())


# --------------------------------------------------------------------------
# 2. Shape invariants
# --------------------------------------------------------------------------


def test_a_locale_carries_the_parts_or_the_scalar_never_both() -> None:
    """Two live sources for one block is a precedence ambiguity that silently
    picks a winner. The corpus shape forbids it by construction."""
    for lang in _manifest_languages():
        value = _bundle_value(lang)
        assert isinstance(value, (str, dict)), f"{lang}: unexpected type {type(value)}"
        if isinstance(value, dict):
            assert lang in SPLIT_LOCALES, f"{lang} is split but not declared in SPLIT_LOCALES"
        else:
            assert lang not in SPLIT_LOCALES, f"{lang} is declared split but carries a scalar"


def test_split_locales_carry_exactly_the_canonical_part_keys() -> None:
    """One key space across the split locales, and it is the tuple the composer
    joins — so an override key that works at ``en`` works at ``pt``."""
    for lang in SPLIT_LOCALES:
        assert language_guidance_part_keys(lang) == tuple(sorted(LANGUAGE_GUIDANCE_PART_KEYS)), lang


def test_part_keys_sort_into_composition_order() -> None:
    """The numeric prefix is not decoration: lexical order IS prompt order."""
    assert tuple(sorted(LANGUAGE_GUIDANCE_PART_KEYS)) == LANGUAGE_GUIDANCE_PART_KEYS


def test_unsplit_locales_resolve_through_the_parent_key() -> None:
    """The 24 that keep the scalar must still compose non-empty guidance —
    the split may not quietly blank a locale."""
    for lang in _manifest_languages():
        if lang in SPLIT_LOCALES:
            continue
        assert language_guidance_part_keys(lang) == ()
        assert get_language_guidance(lang), f"{lang}: composed guidance is empty"


def test_no_part_is_empty() -> None:
    """An empty part is a boundary in the wrong place — it contributes nothing
    and its block would be a zero-byte row the gate cannot compare."""
    for lang in SPLIT_LOCALES:
        empty = [key for key, text in language_guidance_parts(lang) if not text]
        assert not empty, f"{lang}: empty parts {empty}"


def test_mirrors_carry_the_same_split_as_the_source_bundle() -> None:
    """The five client bundles are byte-mirrors. A split that lands in the
    source and not in the mirrors ships a different prompt on mobile."""
    mirrors = [
        "client/androidApp/src/main/assets/localization",
        "client/desktopApp/src/main/resources/localization",
        "client/iosApp/iosApp/localization",
        "client/iosApp/Resources/app/localization",
        "client/shared/src/desktopMain/resources/localization",
    ]
    source = {lang: _bundle_value(lang) for lang in _manifest_languages()}
    for mirror in mirrors:
        for lang, expected in source.items():
            path = REPO_ROOT / mirror / f"{lang}.json"
            if not path.exists():  # pragma: no cover - optional bundle
                continue
            got = json.loads(path.read_text(encoding="utf-8"))["prompts"]["language_guidance"]
            assert got == expected, f"{mirror}/{lang}.json: language_guidance diverges from source"


# --------------------------------------------------------------------------
# 3. What the split bought — the byte ratchet
# --------------------------------------------------------------------------


def _en_class_bytes() -> Dict[BlockClass, int]:
    totals: Dict[BlockClass, int] = {}
    for key, text in language_guidance_parts("en"):
        annotation = annotation_for(f"pdma.language_guidance.{key}")
        totals[annotation.block_class] = totals.get(annotation.block_class, 0) + len(text.encode("utf-8"))
    return totals


def test_every_part_is_annotated_explicitly() -> None:
    """A part resolving through the ``mixed`` fallback would be a silent
    regression that still refuses — honest, but invisible."""
    missing = [key for key in LANGUAGE_GUIDANCE_PART_KEYS if f"language_guidance.{key}" not in BLOCK_ANNOTATIONS]
    assert not missing, f"language_guidance parts with no explicit annotation: {missing}"


def test_the_mixed_share_of_language_guidance_only_shrinks() -> None:
    """A ratchet on BYTES. Entry counts can be moved between registers; the
    bytes the ablation cannot address cannot be moved anywhere."""
    totals = _en_class_bytes()
    assert sum(totals.values()) == EN_TOTAL_BYTES
    mixed = totals.get(BlockClass.MIXED, 0)
    assert mixed <= EN_MAX_MIXED_BYTES, (
        f"mixed bytes in language_guidance grew to {mixed} (was {EN_MAX_MIXED_BYTES}). "
        f"Every byte here is a byte the ablation can neither hold nor vary."
    )


def test_the_axiotic_surface_is_addressable() -> None:
    """The whole point. Before the split this was 0 B: value claims sat inside a
    block a values arm would have held, biasing values_effect toward zero with
    the gate green."""
    totals = _en_class_bytes()
    axiotic = totals.get(BlockClass.AXIOTIC, 0)
    assert axiotic >= EN_MIN_AXIOTIC_BYTES, (
        f"axiotic bytes fell to {axiotic} (was {EN_MIN_AXIOTIC_BYTES}) — value claims went back "
        f"inside a held block"
    )


def test_the_two_axiotic_parts_are_the_ones_that_were_argued_for() -> None:
    """Named, so a future re-annotation has to break something visible.

    ``11_routing_doctrine`` is the sentence the FSD quotes as the reason a hold
    on this block biases values_effect toward zero. ``09_trusted_person_first_
    step`` is a second value claim ("validating 'talk to someone you trust' as a
    real first step matters") that the FSD does not name at all — it was buried
    inside an empirical list.
    """
    axiotic: Set[str] = {
        key
        for key in LANGUAGE_GUIDANCE_PART_KEYS
        if BLOCK_ANNOTATIONS[f"language_guidance.{key}"].block_class is BlockClass.AXIOTIC
    }
    assert axiotic == {"09_trusted_person_first_step", "11_routing_doctrine"}


def test_only_the_worked_exemplars_stay_mixed() -> None:
    """Everything else was split. If a non-exemplar part is mixed, the cut was
    in the wrong place — that is a split failure, not an irreducible."""
    from tests.ciris_engine.logic.utils.test_taxonomy_gate_997 import IRREDUCIBLE_EXEMPLARS

    mixed = {
        f"language_guidance.{key}"
        for key in LANGUAGE_GUIDANCE_PART_KEYS
        if BLOCK_ANNOTATIONS[f"language_guidance.{key}"].block_class is BlockClass.MIXED
    }
    assert mixed == set(IRREDUCIBLE_EXEMPLARS)
