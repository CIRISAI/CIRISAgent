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
COMPOSED_SHA256: Dict[str, Tuple[str, int]] = {
    "en": ("cf7b52f0bca30d299d861f0895d0076d0db9dc9fb5de4be02426227b8a53f6d4", 13694),
    "am": ("51872672ed8702ed850315120a1ab59baab812915da8fb7f2bbd7ba12b64a31c", 25337),
    "ar": ("2fd152e980915ae34a5852f37e17a7833f62c0ff2014bb401faf82a5505eda54", 17595),
    "de": ("2bba0f6ba2c749d54ae8dd199855f637ecfca27e45036b7661224b641957aaea", 15408),
    "es": ("89eeb759297b3ad0ba85c817d594dfec5a77ac5e42f2b8db0431b0ec012c3f75", 15587),
    "fr": ("1623d43160d97c1b27fd4fab4810a64195ed6dfc737ddc3d0d0cef0d55ff11fc", 16541),
    "hi": ("d0a292f177e5928ccc28539689ef4e79e60e4c16e78e5267c47612b4c1eac34f", 24802),
    "it": ("8c8182b30048ce5e3e014a80cb681a935c2e22952c7d99da99c256d491f269b5", 15333),
    "ja": ("f3d3e56eba9f1114b1aad8402697cd58bc80e8039d94859c1236969d100b1685", 16145),
    "ko": ("0a37885175122f0a8b29ec9f7f4f80b3533b3b418213e4678465d6cd0de556ee", 15822),
    "pt": ("bbab7ba8304f4b397f461f4b6decf1a582a2e30820ed5a95eec52c9174789a6e", 15084),
    "ru": ("c7d1b48de70d42ee56b9b1d3dc5a6af7105321f1abc742f249fc5bd60cba08f8", 24755),
    "sw": ("0336ccb2019ecdc34f3b7ae4e5429d9509285276bcfeb097ffcb3f7a5bd2483e", 16925),
    "tr": ("8d26bd113ff85b4f6e1bd3ff5997965dcdf7f82f7d8f9cf49ff486c7a8b0b99f", 13575),
    "zh": ("11088ffc597a9922dd3cf6425f1229326dbd87b8e1dd3510d6e468a85f202d56", 12004),
    "ur": ("fabfb6751ea195fc8164ac79045b5cc89cdbe292bd0ec18d987c2f878ebff42d", 22480),
    "bn": ("e603f336c478f2eebca48c2f0c3459c3658a6cca8bbf14d53a97fe325cf6d79a", 28079),
    "fa": ("0746b0779fc7881af1ed1a7ced3f6c19985debc9c67836cc36c074acbe65f000", 20725),
    "ha": ("f52a17ab710a204a78ab4bd91fbad974bcf8a87a1b1444d84e1c58afdfa6984f", 18788),
    "id": ("7ef729b068437071bd3cbfbc33bc1374dc90bbaab022555abc782fe717ce4d68", 13185),
    "pa": ("e42eb28fcd159bb0f00eec83beb7bfcb3ac7626d4ac933761400c86990ffd0c2", 25942),
    "ta": ("25923944ebe135b80d4d211c4027870d0da1c1f5e0e508f296de49c85dd91fe3", 31660),
    "te": ("3235f739b3033b087d1d7a81078e0bfbd70942eb641a73025b462443627cd3b6", 27614),
    "vi": ("295e67b48bab02543ee1a5a385bf4e26b35a0bb2b19d140ba62c61b45f94cfde", 15754),
    "mr": ("eaa7d574a8dce16b3beb2f006774369f09afb417803a754484f08f6ae3fe9b6e", 24122),
    "my": ("094c236a5962a18d8b244e189529216d8fafd371d138db91ba810047912afa32", 41231),
    "th": ("06ab5a8bd527fae713323e0cdab1b424c410debe325530dd8c3eb965b6ad0a12", 25734),
    "uk": ("b71fd67da0a92cce748c1f783b653c336917fdf371d824227cc6be4c7c4e9a43", 25080),
    "yo": ("87658e84df55b14c0fa0510c4bc7a3d8215a48e4732864d29da88ba38e08cd75", 24574),
}

#: What the split bought at ``en``, in bytes. A ratchet on the number that
#: matters: entry counts can be reshuffled between registers, bytes cannot.
EN_TOTAL_BYTES = 13694
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
