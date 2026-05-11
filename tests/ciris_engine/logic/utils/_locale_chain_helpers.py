"""Per-locale chain integrity tests for the agent's runtime prompt set.

Generates a parameterized test suite for any of CIRIS's 28 non-English
locales. Each locale gets the same checks: no [EN] residuals, natural-
language strings actually in the target script (or for Latin-script
locales, free of English-stopword domination), retry-string completeness,
and preservation of {format} placeholders.

Why this exists: the agent loads YAML prompts at runtime keyed by locale.
If a file under `localized/{lang}/` falls back to English text — because
someone added a new prompt and forgot to translate, or a translation pass
silently dropped a section — the agent ends up reasoning in English
inside a non-English conversation. This test catches the drift before it
ships, on a per-locale, per-file basis so a sub-agent can fix and re-run
its slice in isolation.

Usage from a thin per-locale test file:

    from tests.ciris_engine.logic.utils._locale_chain_helpers import register_locale_tests
    register_locale_tests(globals(), locale="am")
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]


# ---------------------------------------------------------------------------
# Per-locale specifications
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LocaleSpec:
    code: str
    name: str
    native_name: str
    script: str
    # List of inclusive (start, end) Unicode codepoint ranges that count as
    # "in the locale's script". Empty for Latin-script locales — those use
    # English-stopword density instead.
    script_ranges: Tuple[Tuple[int, int], ...] = field(default_factory=tuple)

    @property
    def is_latin(self) -> bool:
        return self.script == "Latin"

    @property
    def script_re(self) -> Optional[re.Pattern[str]]:
        if not self.script_ranges:
            return None
        parts = "".join(f"\\u{lo:04X}-\\u{hi:04X}" for lo, hi in self.script_ranges)
        return re.compile(f"[{parts}]")


# Unicode block references:
#   Ethiopic            U+1200..U+137F  (+ extensions 1380..139F, 2D80..2DDF)
#   Arabic              U+0600..U+06FF  (+ supplement 0750..077F, presentation FB50..FDFF / FE70..FEFF)
#   Bengali             U+0980..U+09FF
#   Devanagari          U+0900..U+097F
#   Hiragana/Katakana   U+3040..U+30FF
#   CJK Unified         U+4E00..U+9FFF (+ extension A 3400..4DBF)
#   Hangul Syllables    U+AC00..U+D7AF (+ Jamo 1100..11FF)
#   Myanmar             U+1000..U+109F (+ extension AA60..AA7F)
#   Gurmukhi            U+0A00..U+0A7F
#   Cyrillic            U+0400..U+04FF (+ supplement 0500..052F)
#   Tamil               U+0B80..U+0BFF
#   Telugu              U+0C00..U+0C7F
#   Thai                U+0E00..U+0E7F

LANGUAGE_SPECS: Dict[str, LocaleSpec] = {
    "am": LocaleSpec("am", "Amharic", "አማርኛ", "Ethiopic",
                     ((0x1200, 0x137F), (0x1380, 0x139F), (0x2D80, 0x2DDF))),
    "ar": LocaleSpec("ar", "Arabic", "العربية", "Arabic",
                     ((0x0600, 0x06FF), (0x0750, 0x077F), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF))),
    "bn": LocaleSpec("bn", "Bengali", "বাংলা", "Bengali", ((0x0980, 0x09FF),)),
    "fa": LocaleSpec("fa", "Persian", "فارسی", "Arabic",
                     ((0x0600, 0x06FF), (0x0750, 0x077F), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF))),
    "hi": LocaleSpec("hi", "Hindi", "हिन्दी", "Devanagari", ((0x0900, 0x097F),)),
    "ja": LocaleSpec("ja", "Japanese", "日本語", "CJK+Kana",
                     ((0x3040, 0x309F), (0x30A0, 0x30FF), (0x4E00, 0x9FFF), (0x3400, 0x4DBF))),
    "ko": LocaleSpec("ko", "Korean", "한국어", "Hangul", ((0xAC00, 0xD7AF), (0x1100, 0x11FF))),
    "mr": LocaleSpec("mr", "Marathi", "मराठी", "Devanagari", ((0x0900, 0x097F),)),
    "my": LocaleSpec("my", "Burmese", "မြန်မာ", "Myanmar", ((0x1000, 0x109F), (0xAA60, 0xAA7F))),
    "pa": LocaleSpec("pa", "Punjabi", "ਪੰਜਾਬੀ", "Gurmukhi", ((0x0A00, 0x0A7F),)),
    "ru": LocaleSpec("ru", "Russian", "Русский", "Cyrillic", ((0x0400, 0x04FF), (0x0500, 0x052F))),
    "ta": LocaleSpec("ta", "Tamil", "தமிழ்", "Tamil", ((0x0B80, 0x0BFF),)),
    "te": LocaleSpec("te", "Telugu", "తెలుగు", "Telugu", ((0x0C00, 0x0C7F),)),
    "th": LocaleSpec("th", "Thai", "ไทย", "Thai", ((0x0E00, 0x0E7F),)),
    "uk": LocaleSpec("uk", "Ukrainian", "Українська", "Cyrillic", ((0x0400, 0x04FF), (0x0500, 0x052F))),
    "ur": LocaleSpec("ur", "Urdu", "اردو", "Arabic",
                     ((0x0600, 0x06FF), (0x0750, 0x077F), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF))),
    "zh": LocaleSpec("zh", "Chinese (Simplified)", "中文", "CJK", ((0x4E00, 0x9FFF), (0x3400, 0x4DBF))),

    # Latin-script locales — script_ranges is empty marker; English-stopword density check.
    "de": LocaleSpec("de", "German", "Deutsch", "Latin"),
    "es": LocaleSpec("es", "Spanish", "Español", "Latin"),
    "fr": LocaleSpec("fr", "French", "Français", "Latin"),
    "ha": LocaleSpec("ha", "Hausa", "Hausa", "Latin"),
    "id": LocaleSpec("id", "Indonesian", "Bahasa Indonesia", "Latin"),
    "it": LocaleSpec("it", "Italian", "Italiano", "Latin"),
    "pt": LocaleSpec("pt", "Portuguese", "Português", "Latin"),
    "sw": LocaleSpec("sw", "Swahili", "Kiswahili", "Latin"),
    "tr": LocaleSpec("tr", "Turkish", "Türkçe", "Latin"),
    "vi": LocaleSpec("vi", "Vietnamese", "Tiếng Việt", "Latin"),
    "yo": LocaleSpec("yo", "Yoruba", "Yorùbá", "Latin"),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

LATIN_RE = re.compile(r"[A-Za-zÀ-ɏ]")

# Common English words that won't be a false-positive hit in romance / germanic
# / turkic / austronesian languages with their own forms. We exclude shared
# articles like "a" because they collide with "a" in many languages.
ENGLISH_STOPWORDS = re.compile(
    r"\b(?:the|and|of|to|in|that|this|with|for|from|you|your|are|is|was|were|"
    r"will|would|could|should|must|have|has|been|being|when|what|which|where|"
    r"who|why|how|but|or|not|all|any|some|one|two|three|each|every|may|might|"
    r"can|do|does|did|if|then|than|because|while|after|before|during|"
    r"about|into|through|under|over|between|against|without|within|"
    r"return|provide|include|alternative|response|reasoning|justification|"
    r"output|require|reference|consider|evaluate|principle|priority|"
    r"following|recall|select|read|write|content|message|action|reason|"
    r"system|prompt|user|assistant|answer|question)\b",
    re.IGNORECASE,
)

# Technical tokens that legitimately stay ASCII in any locale prompt — engine
# identifiers, Pydantic schema field names, and section labels the LLM is
# expected to echo verbatim.
TOKEN_WHITELIST = {
    # Action verbs (HandlerActionType enum values)
    "SPEAK", "PONDER", "DEFER", "TOOL", "REJECT", "OBSERVE",
    "MEMORIZE", "RECALL", "FORGET", "TASK_COMPLETE",
    # IRIS shard identifiers
    "IRIS-E", "IRIS-C", "IRIS-O", "IRIS-H", "IRIS-EH", "IRIS-EOV",
    # DMA / engine identifiers
    "ASPDMA", "TSASPDMA", "DSASPDMA", "PDMA", "CSDMA", "DSDMA", "IDMA",
    "CIRIS", "ACCORD", "CONSCIENCE",
    # Phase / format literals (the schema accepts these exact strings)
    "chaos", "healthy", "rigidity", "proceed", "abort", "ponder",
    "TRUE", "FALSE", "true", "false", "null",
    # Schema field names — appear in prompts as JSON examples
    "selected_action", "rationale", "reasoning", "speak_content",
    "ponder_questions", "reject_reason", "defer_reason", "tool_name",
    "observe_active", "memorize_node_type", "memorize_content",
    "memorize_scope", "recall_query", "recall_node_type", "recall_scope",
    "recall_limit", "forget_node_id", "forget_reason", "completion_reason",
    "k_eff", "correlation_risk", "phase", "fragility_flag",
    "alternative_meanings", "actual_is_representative", "entropy",
    "coherence", "decision", "justification", "entropy_reduction_ratio",
    "affected_values", "epistemic_certainty", "identified_uncertainties",
    "reflective_justification", "recommended_action",
    "Wise", "Authority",
    # Common JSON / format scaffolding
    "JSON", "string", "boolean", "integer", "float", "List", "Optional",
    # Section labels
    "REQUIRED", "OPTIONAL", "ALWAYS", "INCLUDE", "PLUS", "ONLY",
    "LANGUAGE", "RULES", "CRITICAL", "IMPORTANT",
}

STRIP_PATTERNS = [
    re.compile(r"\{\{[^}]*\}\}"),                        # {{escaped braces}}
    re.compile(r"\{[^}]*\}"),                            # {placeholders}
    re.compile(r"```[^`]*```", re.DOTALL),               # code blocks
    re.compile(r"`[^`]+`"),                              # inline code
    re.compile(r"https?://\S+"),                         # URLs
    re.compile(r"\[[A-Z][A-Z_]*\]"),                     # [TAG_PLACEHOLDERS]
    re.compile(r"<[A-Za-z_][A-Za-z0-9_]*>"),             # <var> markers
    re.compile(r"[\d.]+"),                               # numeric literals
]


def _strip_technical(text: str) -> str:
    """Remove technical tokens + format scaffolding so what's left is the
    natural-language portion that ought to be in the locale's script."""
    for pat in STRIP_PATTERNS:
        text = pat.sub(" ", text)
    for tok in TOKEN_WHITELIST:
        text = re.sub(rf"\b{re.escape(tok)}\b", " ", text)
    return text


def _walk_strings(obj: Any, path: str = "") -> List[Tuple[str, str]]:
    """Recursively yield (path, string) for every string leaf."""
    out: List[Tuple[str, str]] = []
    if isinstance(obj, str):
        out.append((path, obj))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            out.extend(_walk_strings(v, f"{path}.{k}" if path else k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.extend(_walk_strings(v, f"{path}[{i}]"))
    return out


def _load_yaml_strings(fp: Path) -> List[Tuple[str, str]]:
    return _walk_strings(yaml.safe_load(fp.read_text(encoding="utf-8")))


def _is_natural_language(text: str, min_chars: int = 80) -> bool:
    return len(text.strip()) >= min_chars


def _script_ratio(text: str, spec: LocaleSpec) -> Tuple[float, int, int]:
    assert spec.script_re is not None, "non-Latin spec required"
    stripped = _strip_technical(text)
    target = len(spec.script_re.findall(stripped))
    latin = len(LATIN_RE.findall(stripped))
    total = target + latin
    if total == 0:
        return 1.0, 0, 0
    return target / total, target, latin


def _english_stopword_density(text: str) -> Tuple[int, int]:
    """For Latin-script locales: count English stopwords vs total words."""
    stripped = _strip_technical(text)
    words = re.findall(r"\b[A-Za-zÀ-ɏ]{2,}\b", stripped)
    en_hits = ENGLISH_STOPWORDS.findall(stripped)
    return len(en_hits), len(words)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

# Threshold tuning notes:
#   SCRIPT_RATIO_MIN     — non-Latin: target script must be >= 30% of script chars
#                          (after stripping technical tokens). 30% leaves room
#                          for inline English nouns the LLM legitimately echoes.
#   STOPWORD_DENSITY_MAX — Latin: English stopwords must be < 35% of words.
#                          A real translation has a few English nouns
#                          (CIRIS, DMA names) but not "the/and/of/is/are/must"
#                          dominating.

SCRIPT_RATIO_MIN = 0.30
STOPWORD_DENSITY_MAX = 0.35


# Files that are intentionally polyglot — the prompt body interleaves many
# languages by design, so monolingual script-ratio and English-stopword
# density checks would always flag them. The polyglot character is the
# integrity feature; reading across multiple languages disrupts single-
# language attractor capture in the conscience LLM (verified end-to-end on
# the bounce harness — opt-veto v2.0 went from 0/10 catch on the live zh
# bug case to 10/10 abort once the body became polyglot).
#
# Add to this set ONLY when the file is universally polyglot (identical
# body across all 29 locales, with only the closing language-rules block
# varying per locale). The other tests in this module (canonical verbs,
# identifier tokens, label-placeholder, [EN] residuals) still run.
POLYGLOT_PROMPT_FILENAMES: frozenset[str] = frozenset({
    "optimization_veto_conscience.yml",  # v2.0+
})


# Canonical wire-protocol tokens. These MUST appear in every locale's prompt
# at least as often as in the base English source, because the LLM is supposed
# to echo them verbatim into JSON outputs (selected_action: "SPEAK" etc.).
#
# Two tiers:
#   STRICT — losing ANY occurrence is a wire-protocol risk (action verbs).
#            If the agent picks the wrong word ("発話" vs "SPEAK"), the
#            response_format parser rejects the message.
#   SOFT   — institutional names that mostly appear in prose. Some loss is
#            tolerable (1 occurrence per file) because the LLM doesn't have
#            to echo them; they're context.
ACTION_VERB_TOKENS = (
    "SPEAK", "PONDER", "DEFER", "TOOL", "REJECT", "OBSERVE",
    "MEMORIZE", "RECALL", "FORGET", "TASK_COMPLETE",
)
SOFT_IDENTITY_TOKENS = (
    "IRIS-E", "IRIS-C", "IRIS-O", "IRIS-H",
    "PDMA", "CSDMA", "DSDMA", "IDMA", "ASPDMA", "TSASPDMA", "DSASPDMA",
    "CIRIS",
)
SOFT_ALLOWED_LOSS = 1  # institutional names: lose ≤1 mention per file


def _count_token(text: str, token: str) -> int:
    return len(re.findall(rf"\b{re.escape(token)}\b", text))


# Catches lines like
#     `Context Summary: {context_summary}`
#     `Original Thought: {{original_thought_content}}`
#     `Domain: {{domain_name}}`
# anywhere in a YAML string value. The label is a Title-Case English phrase
# (1-4 words, ≤40 chars) followed by `: ` and a `{...}` or `{{...}}` placeholder
# on the same line. The placeholder presence is the key signal that this is a
# value-extraction template label that needs translation in localized files.
#
# Matches at start-of-line OR after a newline so we catch labels embedded
# inside multi-line YAML block scalars (the |- and | styles).
LABEL_PLACEHOLDER_RE = re.compile(
    r"(?:^|\n)\s*([A-Z][A-Za-z][A-Za-z\s]{0,38}?):\s+(?:\{\{[^{}]+\}\}|\{[^{}]+\})",
    re.MULTILINE,
)

# Labels that legitimately stay English in localized files (rare). Keep
# tight — adding to this list weakens the gap-detection. If a label is
# here, every locale will inherit the English form. Each entry should be
# justified — usually because it's a wire-protocol identifier the LLM
# echoes verbatim, not a human-facing label.
LABEL_PLACEHOLDER_ALLOWLIST: frozenset[str] = frozenset({
    # "User message:" — context label wired into Coherence + EpistemicHumility
    # user_prompt_templates (commit 814b84090) per the architectural decision
    # to keep English routing-scaffolding labels consistent across all 28
    # locales. Same precedent as the EOV polyglot fix (commit 0c6a962f1) which
    # uses "User's preferred locale:" as an English label in all locales.
    # Rationale (per polyglot/CLAUDE.md §6 + agent investigation 2026-05-03):
    # the conscience LLM judge reads English context labels fluently; the
    # English labels are routing scaffolding, not user-facing UI; avoids the
    # sub-agent-translation reliability problem (memory:
    # feedback_subagent_translation_unreliable).
    "User message",
})
# (Add entries with a comment explaining why each is exempt.)


def _extract_label_placeholder_phrases(text: str) -> set[str]:
    """Return the set of label phrases (without trailing colon) that appear
    in the form `Label: {placeholder}` anywhere in `text`."""
    return {m.group(1).strip() for m in LABEL_PLACEHOLDER_RE.finditer(text)}


def _base_file_for(localized_fp: Path) -> Optional[Path]:
    """Find the base English source for a localized YAML.
    Localized lives at .../prompts/localized/{lang}/{name}.yml — the en source
    is .../prompts/{name}.yml (no `localized/en/` subdir; the base IS the source)."""
    name = localized_fp.name
    parents = localized_fp.parents
    # parents[0]=lang, parents[1]=localized, parents[2]=prompts
    base = parents[2] / name
    return base if base.is_file() else None


def register_locale_tests(globals_dict: Dict[str, Any], locale: str) -> None:
    """Inject test_* functions into the calling module's globals.

    Why this odd shape (mutating globals) instead of a class or fixture: pytest
    discovers test_* functions at module-import time. We want one thin file per
    locale so a sub-agent can run only its slice with `pytest tests/.../test_<x>_*`.
    A factory + globals injection lets the thin file be a single line.
    """
    if locale not in LANGUAGE_SPECS:
        raise KeyError(f"unknown locale: {locale}; known: {sorted(LANGUAGE_SPECS)}")
    spec = LANGUAGE_SPECS[locale]

    DMA_DIR = REPO_ROOT / "ciris_engine" / "logic" / "dma" / "prompts" / "localized" / locale
    CONS_DIR = REPO_ROOT / "ciris_engine" / "logic" / "conscience" / "prompts" / "localized" / locale
    LOC_JSON = REPO_ROOT / "ciris_engine" / "data" / "localized" / f"{locale}.json"

    DMA_FILES = sorted(DMA_DIR.glob("*.yml")) if DMA_DIR.is_dir() else []
    CONS_FILES = sorted(CONS_DIR.glob("*.yml")) if CONS_DIR.is_dir() else []
    ALL_FILES = DMA_FILES + CONS_FILES

    def test_localized_dirs_exist() -> None:
        assert DMA_DIR.is_dir(), f"missing DMA {locale} locale dir: {DMA_DIR}"
        assert CONS_DIR.is_dir(), f"missing conscience {locale} locale dir: {CONS_DIR}"
        assert LOC_JSON.is_file(), f"missing localization JSON: {LOC_JSON}"

    def test_at_least_one_dma_and_conscience_file_present() -> None:
        assert len(DMA_FILES) >= 6, f"expected ≥6 DMA YAMLs in {DMA_DIR}, found {len(DMA_FILES)}"
        assert len(CONS_FILES) >= 1, f"expected ≥1 conscience YAML, found {len(CONS_FILES)}"

    if ALL_FILES:
        @pytest.mark.parametrize("fp", ALL_FILES, ids=lambda p: f"{p.parent.parent.name}/{p.name}")
        def test_no_en_placeholder_residuals_in_yml(fp: Path) -> None:
            for path, text in _load_yaml_strings(fp):
                assert not text.startswith("[EN]"), (
                    f"{fp.relative_to(REPO_ROOT)} key '{path}' still has an [EN] placeholder"
                )
    else:
        def _test_no_en_placeholder_no_files() -> None:
            pytest.fail(f"no YAML files found for locale {locale!r}; cannot check [EN] residuals")

        test_no_en_placeholder_residuals_in_yml = _test_no_en_placeholder_no_files  # type: ignore[assignment]

    if spec.is_latin and ALL_FILES:
        @pytest.mark.parametrize("fp", ALL_FILES, ids=lambda p: f"{p.parent.parent.name}/{p.name}")
        def test_natural_language_strings_are_in_target_language(fp: Path) -> None:
            """Latin-script locale: long strings dominated by English stopwords
            indicate English text leaked through. Allow some English (CIRIS,
            DMA, schema field names — already whitelisted), but not majority.

            POLYGLOT-PROMPT EXEMPTION: files in `POLYGLOT_PROMPT_FILENAMES`
            interleave many languages by design (the polyglot character
            disrupts single-language attractor capture in the LLM judge), so
            monolingual stopword-density checks would always fire."""
            if fp.name in POLYGLOT_PROMPT_FILENAMES:
                pytest.skip(
                    f"{fp.name} is intentionally polyglot — see POLYGLOT_PROMPT_FILENAMES"
                )
            violations = []
            for path, text in _load_yaml_strings(fp):
                if not _is_natural_language(text):
                    continue
                en_hits, words = _english_stopword_density(text)
                if words < 10:
                    continue
                density = en_hits / words
                if density >= STOPWORD_DENSITY_MAX:
                    preview = re.sub(r"\s+", " ", text.strip())[:140]
                    violations.append(
                        f"  {path}: en_stopword_density={density:.2f} "
                        f"({en_hits}/{words}) — {preview}..."
                    )
            assert not violations, (
                f"{fp.relative_to(REPO_ROOT)} has natural-language strings dominated "
                f"by English (should be in {spec.name}):\n" + "\n".join(violations)
            )
    elif not spec.is_latin and ALL_FILES:
        @pytest.mark.parametrize("fp", ALL_FILES, ids=lambda p: f"{p.parent.parent.name}/{p.name}")
        def test_natural_language_strings_are_in_target_script(fp: Path) -> None:
            """Non-Latin locale: each natural-language string must be ≥30%
            target-script characters (after stripping technical tokens) so
            English doesn't slip through.

            POLYGLOT-PROMPT EXEMPTION: files in `POLYGLOT_PROMPT_FILENAMES`
            interleave many languages by design (the polyglot character
            disrupts single-language attractor capture in the LLM judge), so
            monolingual script-ratio checks would always fire."""
            if fp.name in POLYGLOT_PROMPT_FILENAMES:
                pytest.skip(
                    f"{fp.name} is intentionally polyglot — see POLYGLOT_PROMPT_FILENAMES"
                )
            violations = []
            for path, text in _load_yaml_strings(fp):
                if not _is_natural_language(text):
                    continue
                ratio, target_count, latin_count = _script_ratio(text, spec)
                if ratio < SCRIPT_RATIO_MIN:
                    preview = re.sub(r"\s+", " ", text.strip())[:140]
                    violations.append(
                        f"  {path}: {spec.script.lower()}_ratio={ratio:.2f} "
                        f"({spec.script.lower()}={target_count}, latin={latin_count}) "
                        f"— {preview}..."
                    )
            assert not violations, (
                f"{fp.relative_to(REPO_ROOT)} has natural-language strings that aren't "
                f"in {spec.script}:\n" + "\n".join(violations)
            )
    else:
        # Skip-stub for the no-files branch so pytest still has SOMETHING to
        # collect besides the dir-exists check.
        def test_natural_language_strings_localized() -> None:
            pytest.fail(
                f"no YAML files found for locale {locale!r}; cannot check script content"
            )

    def test_retry_strings_present_and_localized() -> None:
        if not LOC_JSON.is_file():
            pytest.fail(f"missing localization JSON: {LOC_JSON}")
        data = json.loads(LOC_JSON.read_text(encoding="utf-8"))
        cons = data.get("conscience", {})
        retry_keys = [k for k in cons if k.startswith("retry_")]
        assert len(retry_keys) == 9, (
            f"expected 9 conscience.retry_* keys for {locale}, found {len(retry_keys)}"
        )
        violations = []
        for key in retry_keys:
            text = cons[key]
            assert isinstance(text, str), f"conscience.{key} is not a string: {type(text)}"
            assert not text.startswith("[EN]"), f"conscience.{key} still has [EN] placeholder"
            if spec.is_latin:
                if not _is_natural_language(text, min_chars=20):
                    continue
                en_hits, words = _english_stopword_density(text)
                if words < 4:
                    continue
                density = en_hits / words
                if density >= STOPWORD_DENSITY_MAX:
                    violations.append(
                        f"  conscience.{key}: en_stopword_density={density:.2f} "
                        f"({en_hits}/{words}) — {text[:140]}"
                    )
            else:
                if not _is_natural_language(text, min_chars=20):
                    if not (spec.script_re and spec.script_re.search(text)):
                        violations.append(
                            f"  conscience.{key}={text!r} — no {spec.script} characters"
                        )
                    continue
                ratio, target_count, latin_count = _script_ratio(text, spec)
                if ratio < SCRIPT_RATIO_MIN:
                    violations.append(
                        f"  conscience.{key}: {spec.script.lower()}_ratio={ratio:.2f} "
                        f"({target_count}/{latin_count}) — {text[:140]}"
                    )
        assert not violations, (
            f"Localized retry strings have language drift in {locale}:\n" + "\n".join(violations)
        )

    if ALL_FILES:
        @pytest.mark.parametrize("fp", ALL_FILES, ids=lambda p: f"{p.parent.parent.name}/{p.name}")
        def test_canonical_action_verbs_preserved(fp: Path) -> None:
            """Action verbs (SPEAK/PONDER/DEFER/TOOL/etc.) must appear in the
            localized prompt at least as often as in the base en source. The
            LLM has to echo these EXACT ASCII strings into JSON outputs; if
            an agent translated SPEAK → 说话 / SPRECHEN / etc. in places where
            it should have been preserved, the wire-protocol parser will
            reject the response."""
            base = _base_file_for(fp)
            if base is None:
                pytest.skip(f"no base file for {fp.name} (not in canonical prompt set)")
            base_text = base.read_text(encoding="utf-8")
            loc_text = fp.read_text(encoding="utf-8")
            violations = []
            for tok in ACTION_VERB_TOKENS:
                base_n = _count_token(base_text, tok)
                if base_n == 0:
                    continue
                loc_n = _count_token(loc_text, tok)
                if loc_n < base_n:
                    violations.append(
                        f"  '{tok}': base={base_n} locale={loc_n} "
                        f"(lost {base_n - loc_n} occurrence{'s' if base_n - loc_n != 1 else ''})"
                    )
            assert not violations, (
                f"{fp.relative_to(REPO_ROOT)} has lost canonical action verbs "
                f"that must appear verbatim in the prompt — the LLM has to echo "
                f"these into JSON `selected_action` outputs:\n" + "\n".join(violations)
            )

        @pytest.mark.parametrize("fp", ALL_FILES, ids=lambda p: f"{p.parent.parent.name}/{p.name}")
        def test_canonical_identifier_tokens_mostly_preserved(fp: Path) -> None:
            """Engine identifiers (IRIS-E/C/O/H, PDMA/CSDMA/DSDMA/IDMA/ASPDMA/
            TSASPDMA, CIRIS) appear mostly in prose context. They aren't
            wire-protocol critical, but losing more than one occurrence per
            file means the agent over-translated and the LLM may forget the
            canonical name. Allow up to {soft} occurrence(s) lost per token
            per file."""
            base = _base_file_for(fp)
            if base is None:
                pytest.skip(f"no base file for {fp.name}")
            base_text = base.read_text(encoding="utf-8")
            loc_text = fp.read_text(encoding="utf-8")
            violations = []
            for tok in SOFT_IDENTITY_TOKENS:
                base_n = _count_token(base_text, tok)
                if base_n == 0:
                    continue
                loc_n = _count_token(loc_text, tok)
                if loc_n + SOFT_ALLOWED_LOSS < base_n:
                    violations.append(
                        f"  '{tok}': base={base_n} locale={loc_n} "
                        f"(lost {base_n - loc_n}, allowed loss {SOFT_ALLOWED_LOSS})"
                    )
            assert not violations, (
                f"{fp.relative_to(REPO_ROOT)} has lost too many engine "
                f"identifiers — the LLM may not recognize them by their "
                f"canonical names:\n" + "\n".join(violations)
            )

    if ALL_FILES:
        @pytest.mark.parametrize("fp", ALL_FILES, ids=lambda p: f"{p.parent.parent.name}/{p.name}")
        def test_label_placeholder_lines_translated(fp: Path) -> None:
            """No English `Label: {placeholder}` line in the base prompt
            may survive untranslated into a localized file.

            Catches the pattern that bypasses the natural-language script
            check: short YAML fields (under the 80-char threshold) where a
            translator left the *label* in English while only translating
            longer body prose. Example failure mode this fired against:

                # ciris_engine/logic/dma/prompts/localized/am/csdma_common_sense.yml
                context_integration: |
                  Context Summary: {context_summary}      # ← English label
                  Original Thought: {original_thought_content}  # ← English label

                # base file (en) has the same labels — they must be
                # translated, not preserved.

            The placeholder presence is the key signal that this is a
            value-extraction template (vs e.g. a section heading the LLM
            should echo verbatim). Labels in the
            `LABEL_PLACEHOLDER_ALLOWLIST` are exempt — keep that list
            tight; every entry weakens the gap-detection."""
            base = _base_file_for(fp)
            if base is None:
                pytest.skip(f"no base file for {fp.name} (not in canonical prompt set)")
            base_text = base.read_text(encoding="utf-8")
            loc_text = fp.read_text(encoding="utf-8")

            base_labels = _extract_label_placeholder_phrases(base_text)
            if not base_labels:
                pytest.skip(f"base {base.name} has no label-placeholder lines")
            loc_labels = _extract_label_placeholder_phrases(loc_text)

            # English labels that appear unchanged in the localized file.
            leaks = (base_labels & loc_labels) - LABEL_PLACEHOLDER_ALLOWLIST
            if not leaks:
                return

            # Build a useful failure message that quotes the offending lines.
            offending_lines: List[str] = []
            for label in sorted(leaks):
                pat = re.compile(
                    rf"(?:^|\n)\s*{re.escape(label)}:\s+(?:\{{[^}}]+\}}|\{{\{{[^}}]+\}}\}})",
                    re.MULTILINE,
                )
                m = pat.search(loc_text)
                if m:
                    offending_lines.append(f"  '{label}:' — {m.group(0).strip()}")
                else:
                    offending_lines.append(f"  '{label}:' (could not re-locate)")

            assert not leaks, (
                f"{fp.relative_to(REPO_ROOT)} has untranslated English "
                f"label-placeholder lines from the base ({base.name}). "
                f"Each label must be translated to {spec.name} alongside "
                f"the placeholder it precedes:\n" + "\n".join(offending_lines)
            )

    def test_format_placeholders_preserved_in_retry_strings() -> None:
        if not LOC_JSON.is_file():
            pytest.fail(f"missing localization JSON: {LOC_JSON}")
        data = json.loads(LOC_JSON.read_text(encoding="utf-8"))
        cons = data.get("conscience", {})
        expected_placeholders = {
            "retry_intro": ["{action}", "{reason}"],
            "retry_observation_intro": ["{updated_observation}"],
        }
        for key, placeholders in expected_placeholders.items():
            text = cons.get(key, "")
            for ph in placeholders:
                assert ph in text, (
                    f"conscience.{key} is missing placeholder {ph!r}: {text[:150]}"
                )

    # Inject all test functions into the calling module's globals so pytest discovers them.
    globals_dict["test_localized_dirs_exist"] = test_localized_dirs_exist
    globals_dict["test_at_least_one_dma_and_conscience_file_present"] = (
        test_at_least_one_dma_and_conscience_file_present
    )
    globals_dict["test_no_en_placeholder_residuals_in_yml"] = test_no_en_placeholder_residuals_in_yml
    if spec.is_latin and ALL_FILES:
        globals_dict["test_natural_language_strings_are_in_target_language"] = (
            test_natural_language_strings_are_in_target_language
        )
    elif not spec.is_latin and ALL_FILES:
        globals_dict["test_natural_language_strings_are_in_target_script"] = (
            test_natural_language_strings_are_in_target_script
        )
    else:
        globals_dict["test_natural_language_strings_localized"] = (
            test_natural_language_strings_localized
        )
    globals_dict["test_retry_strings_present_and_localized"] = test_retry_strings_present_and_localized
    globals_dict["test_format_placeholders_preserved_in_retry_strings"] = (
        test_format_placeholders_preserved_in_retry_strings
    )
    if ALL_FILES:
        globals_dict["test_canonical_action_verbs_preserved"] = test_canonical_action_verbs_preserved
        globals_dict["test_canonical_identifier_tokens_mostly_preserved"] = (
            test_canonical_identifier_tokens_mostly_preserved
        )
        globals_dict["test_label_placeholder_lines_translated"] = (
            test_label_placeholder_lines_translated
        )
