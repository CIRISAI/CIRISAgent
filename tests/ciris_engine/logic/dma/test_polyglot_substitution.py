"""Tests for polyglot block substitution in DMAPromptLoader.

The polyglot substitution mechanism replaces ``{{POLYGLOT_<NAME>}}`` placeholders
in DMA prompt YAML files with the contents of ``data/localized/polyglot/<name>.txt``
at load time. This lets the conceptual cross-tradition framing live as a single
canonical artefact while each locale file translates only the operational tail
(output contract + language rules).

See ciris_engine/data/localized/polyglot/CLAUDE.md for the polyglot doctrine.
"""

from pathlib import Path

import pytest

from ciris_engine.logic.dma.prompt_loader import (
    POLYGLOT_DIR,
    POLYGLOT_PATTERN,
    DMAPromptLoader,
)


class TestPolyglotSubstitution:
    """Verify {{POLYGLOT_<NAME>}} placeholders resolve correctly at load time."""

    def test_polyglot_dir_exists(self) -> None:
        """The polyglot folder must exist in the engine data tree."""
        assert POLYGLOT_DIR.exists(), f"POLYGLOT_DIR missing: {POLYGLOT_DIR}"
        assert POLYGLOT_DIR.is_dir()

    def test_pdma_framing_block_exists(self) -> None:
        """The PDMA framing polyglot block must be present."""
        framing = POLYGLOT_DIR / "pdma_framing.txt"
        assert framing.exists(), f"pdma_framing.txt missing at {framing}"
        content = framing.read_text(encoding="utf-8")
        assert "=== I. WHERE THE TORQUE COMES FROM ===" in content
        assert "=== VIII." in content

    def test_pattern_matches_placeholder_with_indent(self) -> None:
        """The substitution regex captures placeholder + leading indent."""
        sample = "  {{POLYGLOT_PDMA_FRAMING}}\n"
        match = POLYGLOT_PATTERN.search(sample)
        assert match is not None
        assert match.group("indent") == "  "
        assert match.group("name") == "PDMA_FRAMING"

    def test_pattern_rejects_inline_placeholder(self) -> None:
        """Placeholders embedded inside other content must not match (own line only)."""
        # Trailing text after }} on the same line: should not match
        assert POLYGLOT_PATTERN.search("text {{POLYGLOT_X}} more text") is None

    def test_pdma_ethical_resolves_polyglot_block(self) -> None:
        """Loading pdma_ethical.yml expands the framing placeholder in-place."""
        loader = DMAPromptLoader(language="en")
        collection = loader.load_prompt_template("pdma_ethical")
        header = collection.system_guidance_header
        assert header is not None

        # No unsubstituted placeholders survive
        assert "{{POLYGLOT" not in header

        # Polyglot framing landed: §I through §VIII conceptual core
        for marker in (
            "=== I. WHERE THE TORQUE COMES FROM ===",
            "=== II. SUBJECT IDENTIFICATION",
            "=== III. THE SIX PRINCIPLES",
            "=== IV. PROPORTIONALITY CHECK",
            "=== V. RELATIONAL OBLIGATIONS",
            "=== VI. THE TORQUE FEEL",
            "=== VII. SCORE CALIBRATION",
            "=== VIII. עַל דַּם רֵעֶךָ",
        ):
            assert marker in header, f"polyglot marker missing: {marker!r}"

        # Tradition anchors that must survive YAML round-trip
        for anchor in (
            "ubuntu",
            "ahimsa",
            "alētheia",
            "sammā-vācā",
            "ma'at",
            "amae",
            "Bhagavad Gita 4.18",
            "kitman al-'ilm",
        ):
            assert anchor in header, f"tradition anchor missing: {anchor!r}"

    def test_local_tail_intact_post_substitution(self) -> None:
        """The LOCAL operational tail (walkthrough + §IX + §X) is untouched."""
        loader = DMAPromptLoader(language="en")
        header = loader.load_prompt_template("pdma_ethical").system_guidance_header
        assert header is not None

        for local_marker in (
            "Walk through the analysis internally:",
            "=== IX. OUTPUT CONTRACT · 4 FIELDS ===",
            "weight_alignment_score",
            "ethical_alignment_score",
            "=== X. LANGUAGE RULES",
            "Respond in English only.",
        ):
            assert local_marker in header, f"LOCAL marker missing: {local_marker!r}"

    def test_seam_polyglot_to_local_clean(self) -> None:
        """The boundary between §VIII (polyglot) and walkthrough (local) is clean."""
        loader = DMAPromptLoader(language="en")
        header = loader.load_prompt_template("pdma_ethical").system_guidance_header
        assert header is not None

        # §VIII closing aphorism flows directly into walkthrough start with one blank line
        assert (
            "*Evading-while-\nsounding-balanced* IS torque.\n\n"
            "Walk through the analysis internally:"
        ) in header

    def test_seam_local_to_polyglot_clean(self) -> None:
        """The boundary between header opening (local) and §I (polyglot) is clean."""
        loader = DMAPromptLoader(language="en")
        header = loader.load_prompt_template("pdma_ethical").system_guidance_header
        assert header is not None

        assert (
            "your assessment of the specific thought.\n\n"
            "=== I. WHERE THE TORQUE COMES FROM ==="
        ) in header

    def test_indent_preserved_through_yaml_block_scalar(self) -> None:
        """Polyglot lines re-indent to the placeholder's column, then YAML strips it."""
        loader = DMAPromptLoader(language="en")
        header = loader.load_prompt_template("pdma_ethical").system_guidance_header
        assert header is not None

        # Six Principles entries from §III: bullet-style strings whose leading
        # markdown-bold marker would be corrupted by indent loss.
        for principle_anchor in (
            "**善行 · सेवा · eudaimonia — Beneficence (Do Good)**",
            "**無危害 · अहिंसा · ahimsa — Non-maleficence (Avoid Harm)**",
            "**ታማኝነት · אֱמֶת · alētheia — Integrity (Act Ethically)**",
            "**חֶסֶד · 정 · sammā-vācā — Fidelity & Transparency (Be Honest)**",
            "**स्वायत्तता · imago Dei · amae — Respect Autonomy**",
            "**العدالة · ma'at · igwe-bụ-ike — Justice (Ensure Fairness)**",
        ):
            assert principle_anchor in header, f"principle anchor lost indent: {principle_anchor!r}"

    def test_missing_polyglot_block_raises(self, tmp_path: Path) -> None:
        """Referencing a non-existent polyglot block raises FileNotFoundError."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        broken = prompts_dir / "broken.yml"
        broken.write_text(
            "system_guidance_header: |\n"
            "  preface\n"
            "  {{POLYGLOT_DOES_NOT_EXIST}}\n"
            "  postface\n",
            encoding="utf-8",
        )

        loader = DMAPromptLoader(prompts_dir=str(prompts_dir), language="en")
        with pytest.raises(FileNotFoundError, match="POLYGLOT_DOES_NOT_EXIST"):
            loader.load_prompt_template("broken")

    def test_substitution_idempotent_under_repeat_loads(self) -> None:
        """Loading the same template twice yields byte-identical resolved headers."""
        loader = DMAPromptLoader(language="en")
        first = loader.load_prompt_template("pdma_ethical").system_guidance_header
        second = loader.load_prompt_template("pdma_ethical").system_guidance_header
        assert first == second

    def test_spanish_locale_uses_same_polyglot_block(self) -> None:
        """The Spanish locale shares the polyglot framing with English byte-for-byte.

        Locale files translate only the LOCAL operational tail (header opening,
        walkthrough, output contract, language rules). The {{POLYGLOT_PDMA_FRAMING}}
        block resolves to the same content regardless of locale — that is the
        whole point of the placeholder pattern.
        """
        en = DMAPromptLoader(language="en").load_prompt_template("pdma_ethical")
        es = DMAPromptLoader(language="es").load_prompt_template("pdma_ethical")

        assert en.system_guidance_header is not None
        assert es.system_guidance_header is not None

        # Both locales must contain the same polyglot core
        for marker in (
            "=== I. WHERE THE TORQUE COMES FROM ===",
            "=== III. THE SIX PRINCIPLES",
            "=== VIII. עַל דַּם רֵעֶךָ",
            "**善行 · सेवा · eudaimonia — Beneficence (Do Good)**",
            "Bhagavad Gita 4.18",
            "Difficulty is not torque. Fluency is not torque.",
        ):
            assert marker in en.system_guidance_header, f"missing in en: {marker!r}"
            assert marker in es.system_guidance_header, f"missing in es: {marker!r}"

        # Spanish-specific LOCAL anchors that must NOT be in English
        for spanish_only in (
            "Eres PDMA, el componente de razonamiento ético",
            "=== IX. CONTRATO DE SALIDA · 4 CAMPOS ===",
            "**Responde solo en español.**",
        ):
            assert spanish_only in es.system_guidance_header, f"missing es-local: {spanish_only!r}"
            assert spanish_only not in en.system_guidance_header, (
                f"Spanish text leaked into English locale: {spanish_only!r}"
            )

        # English-specific LOCAL anchors that must NOT be in Spanish
        for english_only in (
            "Walk through the analysis internally:",
            "=== IX. OUTPUT CONTRACT · 4 FIELDS ===",
            "**Respond in English only.**",
        ):
            assert english_only in en.system_guidance_header, f"missing en-local: {english_only!r}"
            assert english_only not in es.system_guidance_header, (
                f"English text leaked into Spanish locale: {english_only!r}"
            )

        # context_integration field is also locale-translated
        assert en.context_integration is not None
        assert es.context_integration is not None
        assert "Thought to Evaluate:" in en.context_integration
        assert "Pensamiento a Evaluar:" in es.context_integration

        # English JSON keys + action verb names preserved across locales
        for english_technical in (
            '"action"',
            '"rationale"',
            '"weight_alignment_score"',
            '"ethical_alignment_score"',
            "HandlerActionType",
        ):
            assert english_technical in en.system_guidance_header
            assert english_technical in es.system_guidance_header, (
                f"English technical term lost in Spanish locale: {english_technical!r}"
            )

        # No unsubstituted placeholder leakage in either locale
        assert "{{POLYGLOT" not in en.system_guidance_header
        assert "{{POLYGLOT" not in es.system_guidance_header


class TestCSDMARelationalRealismFanout:
    """Regression tests for #792 — CSDMA scope expansion to relational realism.

    Step 10 (Relational Persistence Check) introduced three new flag identifiers
    that must appear identically (English) in all 29 locale files. The flag IDs
    travel as part of the response_format example list AND as in-prose markers
    inside the step 10 sub-bullets. Both surfaces must round-trip the loader.

    Flag IDs stay in English per the LANGUAGE RULES in each file (JSON keys and
    flag identifiers are English; only surrounding prose is translated). This
    test pins that contract so future locale updates can't accidentally
    translate the identifiers.
    """

    RELATIONAL_FLAGS = (
        "Family_Relational_Footprint_Ignored",
        "Labor_Displacement_Unacknowledged",
        "Institutional_Capacity_Overestimated",
    )

    # All 29 supported locales (en = base prompt, others = localized).
    # Source of truth is the manifest at ciris_engine/data/localized/manifest.json
    # but we hard-code here so test failure surfaces a *missing locale* rather
    # than a manifest drift cascade.
    SUPPORTED_LOCALES = (
        "en",
        "am", "ar", "bn", "de", "es", "fa", "fr", "ha", "hi",
        "id", "it", "ja", "ko", "mr", "my", "pa", "pt", "ru", "sw",
        "ta", "te", "th", "tr", "uk", "ur", "vi", "yo", "zh",
    )

    @pytest.mark.parametrize("lang", SUPPORTED_LOCALES)
    def test_all_three_flags_present_in_locale(self, lang: str) -> None:
        """Every locale's csdma_common_sense prompt must contain all three
        new relational-realism flag identifiers, byte-identical English."""
        loader = DMAPromptLoader(language=lang)
        collection = loader.load_prompt_template("csdma_common_sense")

        # Concatenate every text-bearing field — flags can appear in
        # evaluation_steps (in the sub-bullet prose) AND response_format
        # (in the documented flag-list example).
        haystack = " ".join(
            str(getattr(collection, field, "") or "")
            for field in (
                "system_guidance_header",
                "evaluation_steps",
                "response_format",
                "context_integration",
            )
        )

        for flag in self.RELATIONAL_FLAGS:
            assert flag in haystack, (
                f"Flag {flag!r} missing from locale {lang!r}. "
                f"Per #792, all 29 locales must carry the relational-realism "
                f"flag identifiers in English (LANGUAGE RULES: JSON keys and "
                f"flag identifiers remain in English even when prose is "
                f"translated). Re-run the fanout script or hand-port."
            )

    @pytest.mark.parametrize("lang", SUPPORTED_LOCALES)
    def test_evaluation_steps_includes_relational_check(self, lang: str) -> None:
        """Step 10's identifying anchors — at least one flag plus the
        scope-note keyword — must land in evaluation_steps specifically
        (not just response_format), so the LLM evaluator actually applies
        the new check. Response_format alone documents the schema; the
        LLM only acts on what evaluation_steps tells it to act on."""
        loader = DMAPromptLoader(language=lang)
        collection = loader.load_prompt_template("csdma_common_sense")
        steps = collection.evaluation_steps or ""
        # All three flags should appear in the steps (one per sub-bullet)
        for flag in self.RELATIONAL_FLAGS:
            assert flag in steps, (
                f"Locale {lang}: flag {flag!r} missing from evaluation_steps "
                f"(found only in response_format means the LLM won't apply "
                f"the check — only document it)."
            )

    def test_base_english_step_numbering_continuous(self) -> None:
        """The base prompt's evaluation_steps lists numbered steps 1-10.
        Step 10 must be present and step numbering must not skip — a
        regression here suggests step 10 was inserted at the wrong yaml
        anchor and ended up outside the numbered-list block."""
        loader = DMAPromptLoader(language="en")
        collection = loader.load_prompt_template("csdma_common_sense")
        steps = collection.evaluation_steps or ""
        # Each step starts with `N.` at the start of a line (after indent)
        # We just check sentinel substrings for the numbered preamble of
        # steps 1, 2, 9, and 10 to confirm continuity.
        for marker in ("1. Context Grounding", "2. Physical Plausibility",
                       "9. **TEMPORAL/CAUSAL", "10. **RELATIONAL PERSISTENCE"):
            assert marker in steps, f"step marker missing: {marker!r}"

    def test_existing_flags_not_clobbered(self) -> None:
        """The fanout appends — it must not remove pre-existing flags.
        Spot-check Weak_Reasoning_Insufficient_Causation (the anchor we
        used to find the insertion point) is still present everywhere."""
        for lang in self.SUPPORTED_LOCALES:
            loader = DMAPromptLoader(language=lang)
            collection = loader.load_prompt_template("csdma_common_sense")
            rf = collection.response_format or ""
            assert "Weak_Reasoning_Insufficient_Causation" in rf, (
                f"Anchor flag wiped from {lang} response_format — the "
                f"fanout corrupted this file."
            )
