"""compose --dump + ablation gate Phase 1 (#973, FSD/RESEARCH_PROMPT_OVERRIDES.md §12).

Converts ablation completeness from an author's claim into a machine check:

- ``dump``  composes every DMA step per locale through the #972
  ``compose_messages()`` seams, driven by the #972 golden fixtures (the named
  compose fixture [I-2] — no LLM, no persistence, dynamic slots pinned to
  stable fixture constants), and emits one JSONL row per discrete block.
- ``gate``  runs the FSD §12 Phase-1 assertions over two dumps, block-keyed,
  with the honest descope (FSD §14 step 3): the dump covers the routed +
  already-block-structured surface; unrouted text reports ``mixed``; gate
  assertions 2/3 iterate only blocks whose class is not ``mixed``; every
  ``mixed`` block inside a varied class refuses, by name; ``contingent`` is
  excluded by construction [T-2].

Process shape [I-V3]: the prompt caches are process-global singletons
(``_loader_cache`` prompt_loader.py, the override ``_loaded`` singleton
research_overrides.py), so arms are composed **subprocess-per-arm** (the
``--arms-config`` driver shells out to this module once per arm) with
in-process locale iteration.

Usage::

    python3 -m ciris_engine.logic.utils.compose_dump dump --arm h3ere-ciris \
        --locales en,am --out /tmp/a.jsonl [--manifest overrides.json] [--sign]
    python3 -m ciris_engine.logic.utils.compose_dump dump --arms-config arms.yaml --out-dir /tmp/dumps
    python3 -m ciris_engine.logic.utils.compose_dump gate --dump-a a.jsonl --dump-b b.jsonl \
        --regime regime.yaml [--verify-sig]

Signed dumps (#977, ciris-server 0.5.154): ``--sign`` signs the emitted JSONL
via ``ciris_server.sign_object`` with label = the arm name — sealed inside the
signed manifest, so a dump cannot be relabelled into a different arm. ``gate
--verify-sig`` accepts only a TRUE ``verify_object`` (an unperformable check
refuses) and requires the sealed label to equal each dump's recorded arm.
Both sides need the live node runtime in-process (engine + edge + federation
delivery) — the 0.5.154 contract for detached-object signing.

The dump needs the repo checkout: the compose fixture lives in
``tests/ciris_engine/logic/dma/compose_golden.py`` (load-bearing for #972's
golden-bytes proof; reused here rather than re-invented). The ``gate``
subcommand reads only dump files + the regime manifest and works anywhere.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List, NamedTuple, Optional, Sequence, Tuple

from ciris_engine.schemas.dma.compose import (
    CLASS_DEFAULT_DISPOSITION,
    BlockClass,
    BlockDisposition,
    ComposeDumpMeta,
    ComposedBlock,
    GateRegime,
    RegimeBlockEntry,
)
from ciris_engine.schemas.types import JSONDict

# --------------------------------------------------------------------------
# Class annotation table (§10.2 / §10.2.1)
# --------------------------------------------------------------------------


class BlockAnnotation(NamedTuple):
    """(primary class, contaminant list) for one block id."""

    block_class: BlockClass
    contaminant: Optional[Tuple[BlockClass, ...]]


_C = BlockClass  # brevity in the table below

#: THE annotation map — one module-level table, one comment per entry.
#: Single-author, best-effort annotation: the §10.2.3 two-annotator κ pass
#: (#976) REPLACES this table; until then every ``mixed`` entry defaults to
#: refusal at the gate, so an optimistic annotation here cannot green a run.
#: Lookup: exact ``block_id`` first, then the suffix after the step
#: (``annotation_for``). ``mixed`` entries carry populated contaminant lists
#: [T-N1].
BLOCK_ANNOTATIONS: Dict[str, BlockAnnotation] = {
    # Discrete accord system block (polyglot for round-1 DMAs, localized for
    # the action-selection family): states and ranks what matters — axiotic.
    "accord": BlockAnnotation(_C.AXIOTIC, None),
    # ASPDMA's accord block carries a runtime `THOUGHT_TYPE=<...>` slot
    # prepended to the routed localized accord in the SAME message — one
    # block, mixed, per the honesty rule; the slot itself is contingent.
    "aspdma.accord": BlockAnnotation(_C.MIXED, (_C.AXIOTIC, _C.CONTINGENT)),
    # prompts.language_guidance (13,524 B at en): pragmatic + deontic +
    # axiotic + empirical in one scalar, unsplittable short of rewriting it
    # [T-1]. Primary is pragmatic register doctrine; contaminants per §10.2.1.
    "language_guidance": BlockAnnotation(_C.MIXED, (_C.AXIOTIC, _C.DEONTIC, _C.EMPIRICAL)),
    # Prohibition context block (#910): categorical permission/prohibition
    # sourced from PROHIBITED_CAPABILITIES — deontic.
    "prohibition": BlockAnnotation(_C.DEONTIC, None),
    # Crisis resources: static world-facts (numbers, URLs) — empirical (#971
    # landed the breadcrumb in formatters/crisis_resources.py). NOT reachable
    # as a discrete block today: it rides interpolated inside dsdma.system
    # (mixed). This entry activates when #974 routes it discretely.
    "crisis": BlockAnnotation(_C.EMPIRICAL, None),
    # PDMA composed system message: PDMA stage framework (procedural) naming
    # principles (axiotic) + task/snapshot interpolation (contingent).
    "pdma.system": BlockAnnotation(_C.MIXED, (_C.PROCEDURAL, _C.AXIOTIC, _C.CONTINGENT)),
    # PDMA user message: thought text (contingent) in a template frame.
    "pdma.user": BlockAnnotation(_C.MIXED, (_C.CONTINGENT, _C.PROCEDURAL)),
    # CSDMA system: common-sense evaluation guidance (procedural, epistemic
    # plausibility doctrine) + snapshot/task interpolation (contingent).
    "csdma.system": BlockAnnotation(_C.MIXED, (_C.PROCEDURAL, _C.EPISTEMIC, _C.CONTINGENT)),
    # CSDMA user message: context summary + thought (contingent) in a frame.
    "csdma.user": BlockAnnotation(_C.MIXED, (_C.CONTINGENT, _C.PROCEDURAL)),
    # IDMA system: the k_eff formula and chaos/healthy/rigidity frame — the
    # §10.2 nomological worked example [T-5c] — plus snapshot (contingent).
    "idma.system": BlockAnnotation(_C.MIXED, (_C.NOMOLOGICAL, _C.PROCEDURAL, _C.CONTINGENT)),
    # IDMA user message: thought + prior-DMA results (contingent) in a frame.
    "idma.user": BlockAnnotation(_C.MIXED, (_C.CONTINGENT, _C.PROCEDURAL)),
    # DSDMA system: CORE IDENTITY (ontological) + crisis resources block
    # (empirical, interpolated — see 'crisis' above) + domain instructions
    # (procedural) + snapshot (contingent).
    "dsdma.system": BlockAnnotation(_C.MIXED, (_C.ONTOLOGICAL, _C.EMPIRICAL, _C.PROCEDURAL, _C.CONTINGENT)),
    # DSDMA user message: task context + thought (contingent) in a frame.
    # ROUTED since #974 step 2 (dsdma_base.context_integration went live) —
    # keyed source, class honestly stays mixed (contingent slots in the render).
    "dsdma.user": BlockAnnotation(_C.MIXED, (_C.CONTINGENT, _C.PROCEDURAL)),
    # ASPDMA system: identity block (ontological) + selection framing.
    "aspdma.system": BlockAnnotation(_C.MIXED, (_C.ONTOLOGICAL, _C.PROCEDURAL, _C.CONTINGENT)),
    # ASPDMA user message: the ~90-line action doctrine — axiotic content in
    # a structural site [M-4] — plus deontic "Requires wise authority
    # approval" lines and task context (contingent). ROUTED since #974: the
    # DEFER policy (step 0, action_params_defer_guidance) and the whole
    # user-message template (step 1, context_integration) are keyed and
    # overridable, so the SOURCE reports the dma_prompt render seam — but the
    # render interpolates contingent task/snapshot/DMA-summary slots and
    # inline helper prose, so the CLASS honestly stays mixed (§10.2.1).
    "aspdma.user": BlockAnnotation(_C.MIXED, (_C.PROCEDURAL, _C.AXIOTIC, _C.DEONTIC, _C.CONTINGENT)),
    # DSASPDMA system: dma_prompt-routed guidance keys joined inline into one
    # message (procedural stage directives).
    "dsaspdma.system": BlockAnnotation(_C.MIXED, (_C.PROCEDURAL, _C.CONTINGENT)),
    # DSASPDMA user: deferral taxonomy prompt + original thought/reason.
    "dsaspdma.user": BlockAnnotation(_C.MIXED, (_C.CONTINGENT, _C.PROCEDURAL, _C.AXIOTIC)),
    # TSASPDMA system: tool-review framing (procedural).
    "tsaspdma.system": BlockAnnotation(_C.MIXED, (_C.PROCEDURAL, _C.CONTINGENT)),
    # TSASPDMA user: tool documentation (empirical world-facts) + reasoning.
    "tsaspdma.user": BlockAnnotation(_C.MIXED, (_C.CONTINGENT, _C.EMPIRICAL, _C.PROCEDURAL)),
    # TSASPDMA correction system: same framing as tsaspdma.system.
    "tsaspdma_correction.system": BlockAnnotation(_C.MIXED, (_C.PROCEDURAL, _C.CONTINGENT)),
    # TSASPDMA correction user: correction doctrine + FLAT-JSON coercion
    # (structural parsing contract) + available-tools listing (contingent).
    "tsaspdma_correction.user": BlockAnnotation(_C.MIXED, (_C.CONTINGENT, _C.PROCEDURAL, _C.STRUCTURAL)),
    # ---- #986: the conscience-override RETRY compositions ------------------
    # Same construction as the first-pass ASPDMA accord block (runtime
    # THOUGHT_TYPE= slot + routed localized accord in one message), so it
    # carries the same annotation. Named explicitly rather than left to the
    # `accord` suffix fallback, which would hand it a bare AXIOTIC and quietly
    # disagree with `aspdma.accord` about the identical bytes.
    "aspdma_retry.accord": BlockAnnotation(_C.MIXED, (_C.AXIOTIC, _C.CONTINGENT)),
    "aspdma_retry_observation.accord": BlockAnnotation(_C.MIXED, (_C.AXIOTIC, _C.CONTINGENT)),
    "aspdma_ponder_notes.accord": BlockAnnotation(_C.MIXED, (_C.AXIOTIC, _C.CONTINGENT)),
    # The follow-up thought after a conscience-forced PONDER: an ordinary ASPDMA
    # composition whose user message additionally carries the conscience-authored
    # ponder notes (contingent payload, axiotic in what it asks the agent to
    # reconsider).
    "aspdma_ponder_notes.system": BlockAnnotation(_C.MIXED, (_C.ONTOLOGICAL, _C.PROCEDURAL, _C.CONTINGENT)),
    "aspdma_ponder_notes.user": BlockAnnotation(_C.MIXED, (_C.CONTINGENT, _C.PROCEDURAL, _C.AXIOTIC)),
    # ---- #986: the DMA-bounce compositions --------------------------------
    # CSDMA re-run on a bounced thought: identical block structure to `csdma`,
    # with the localized bounce preamble riding inside the user message.
    "aspdma_bounce_advisory.accord": BlockAnnotation(_C.MIXED, (_C.AXIOTIC, _C.CONTINGENT)),
    "aspdma_bounce_advisory.system": BlockAnnotation(_C.MIXED, (_C.ONTOLOGICAL, _C.PROCEDURAL, _C.CONTINGENT)),
    # The advisory tells ASPDMA a DMA could not clear threshold — an epistemic
    # claim about the evidence, in the ordinary contingent user frame.
    "aspdma_bounce_advisory.user": BlockAnnotation(
        _C.MIXED, (_C.CONTINGENT, _C.PROCEDURAL, _C.EPISTEMIC, _C.AXIOTIC)
    ),
    "csdma_bounce.system": BlockAnnotation(_C.MIXED, (_C.PROCEDURAL, _C.EPISTEMIC, _C.CONTINGENT)),
    # The bounce preamble is procedural retry doctrine ("try again, differently")
    # wrapped around the contingent thought text and the technical trigger line.
    "csdma_bounce.user": BlockAnnotation(_C.MIXED, (_C.CONTINGENT, _C.PROCEDURAL, _C.EPISTEMIC)),
    # Retry system message: the template-derived CORE IDENTITY block
    # (ontological) in the ordinary ASPDMA selection framing.
    "aspdma_retry.system": BlockAnnotation(_C.MIXED, (_C.ONTOLOGICAL, _C.PROCEDURAL, _C.CONTINGENT)),
    "aspdma_retry_observation.system": BlockAnnotation(_C.MIXED, (_C.ONTOLOGICAL, _C.PROCEDURAL, _C.CONTINGENT)),
    # Retry user message: the first-pass ASPDMA user message PLUS the conscience
    # retry envelope in the {conscience_guidance} slot. The envelope is deontic
    # ("your next attempt MUST be materially different", "DEFER to Wise
    # Authority"), axiotic (the shard justifications name what was at stake) and
    # contingent (the failed action, the shard evidence).
    "aspdma_retry.user": BlockAnnotation(
        _C.MIXED, (_C.CONTINGENT, _C.PROCEDURAL, _C.DEONTIC, _C.AXIOTIC)
    ),
    "aspdma_retry_observation.user": BlockAnnotation(
        _C.MIXED, (_C.CONTINGENT, _C.PROCEDURAL, _C.DEONTIC, _C.AXIOTIC)
    ),
    # ---- #986: the conscience faculties -----------------------------------
    # IRIS-E: semantic-entropy calibration for the LLM judge — how to measure
    # (procedural) and what counts as knowing (epistemic).
    "entropy_conscience.system": BlockAnnotation(_C.MIXED, (_C.EPISTEMIC, _C.PROCEDURAL)),
    # IRIS-C: coherence calibration — same shape.
    "coherence_conscience.system": BlockAnnotation(_C.MIXED, (_C.EPISTEMIC, _C.PROCEDURAL)),
    # CIRIS-EOV: the Order-Maximisation side-constraint. Names protected
    # dimensions (axiotic) and forbids trading them at any ratio (deontic).
    "optimization_veto_conscience.system": BlockAnnotation(
        _C.MIXED, (_C.AXIOTIC, _C.DEONTIC, _C.PROCEDURAL)
    ),
    # CIRIS-EH: humility calibration — uncertainty doctrine.
    "epistemic_humility_conscience.system": BlockAnnotation(_C.MIXED, (_C.EPISTEMIC, _C.PROCEDURAL)),
    # Every conscience user message is its routed template with the evaluated
    # action/user text interpolated: a contingent payload in a procedural frame.
    "entropy_conscience.user": BlockAnnotation(_C.MIXED, (_C.CONTINGENT, _C.PROCEDURAL)),
    "coherence_conscience.user": BlockAnnotation(_C.MIXED, (_C.CONTINGENT, _C.PROCEDURAL)),
    "optimization_veto_conscience.user": BlockAnnotation(_C.MIXED, (_C.CONTINGENT, _C.PROCEDURAL)),
    "epistemic_humility_conscience.user": BlockAnnotation(_C.MIXED, (_C.CONTINGENT, _C.PROCEDURAL)),
    # The image-context variants compose the SAME system calibration and the
    # sibling user template, so they carry the same classes.
    "entropy_conscience_image.system": BlockAnnotation(_C.MIXED, (_C.EPISTEMIC, _C.PROCEDURAL)),
    "coherence_conscience_image.system": BlockAnnotation(_C.MIXED, (_C.EPISTEMIC, _C.PROCEDURAL)),
    "optimization_veto_conscience_image.system": BlockAnnotation(
        _C.MIXED, (_C.AXIOTIC, _C.DEONTIC, _C.PROCEDURAL)
    ),
    "epistemic_humility_conscience_image.system": BlockAnnotation(_C.MIXED, (_C.EPISTEMIC, _C.PROCEDURAL)),
    "entropy_conscience_image.user": BlockAnnotation(_C.MIXED, (_C.CONTINGENT, _C.PROCEDURAL)),
    "coherence_conscience_image.user": BlockAnnotation(_C.MIXED, (_C.CONTINGENT, _C.PROCEDURAL)),
    "optimization_veto_conscience_image.user": BlockAnnotation(_C.MIXED, (_C.CONTINGENT, _C.PROCEDURAL)),
    "epistemic_humility_conscience_image.user": BlockAnnotation(_C.MIXED, (_C.CONTINGENT, _C.PROCEDURAL)),
}


def annotation_for(block_id: str) -> BlockAnnotation:
    """Resolve the annotation for a block id: exact match, then step-suffix.

    An unannotated block (composition grew a message this table has never
    seen) is honestly ``mixed`` — which the gate refuses without an explicit
    per-block disposition, so a new block can never slip through green.
    """
    exact = BLOCK_ANNOTATIONS.get(block_id)
    if exact is not None:
        return exact
    suffix = block_id.split(".", 1)[1] if "." in block_id else block_id
    by_suffix = BLOCK_ANNOTATIONS.get(suffix)
    if by_suffix is not None:
        return by_suffix
    return BlockAnnotation(_C.MIXED, (_C.CONTINGENT, _C.PROCEDURAL))


# --------------------------------------------------------------------------
# Residue scan v2 (assertion 4) — structural, not lexical [M-4]
# --------------------------------------------------------------------------

#: Fragments shorter than this (whitespace-normalized) are not scanned:
#: below it the string constants in RESIDUE_SITES are labels ("RECALL:") and
#: separators, which match everywhere and mean nothing.
_FRAGMENT_MIN_CHARS = 40

#: The cheap token adjunct (M-1) — retained, never the mechanism.
#: (token, case_sensitive). Principle names scan case-insensitively.
_TOKEN_ADJUNCT: Tuple[Tuple[str, bool], ...] = (
    ("CIRIS", True),
    ("M-1", True),
    ("beneficence", False),
    ("non-maleficence", False),
    ("autonomy", False),
    ("justice", False),
    ("fidelity", False),
    ("transparency", False),
    ("integrity", False),
)

_WS_RE = re.compile(r"\s+")


def _normalize_ws(text: str) -> str:
    """Whitespace-normalize for fragment matching (never for hashing)."""
    return _WS_RE.sub(" ", text).strip()


def _parse_symbol_source(segment: str) -> ast.AST:
    """Parse an extracted symbol source segment, tolerating method indentation."""
    try:
        return ast.parse(segment)
    except (IndentationError, SyntaxError):
        import textwrap

        return ast.parse("if True:\n" + textwrap.indent(segment, "    "))


def residue_fragments() -> Tuple[Tuple[str, str], ...]:
    """Normalized string-literal fragments of every ``RESIDUE_SITES`` entry.

    Reuses the residue inventory's own symbol extractor so the scan can never
    cover a different surface than ``compute_residue_digest()`` pins. Returns
    ``(fragment_id, normalized_text)`` pairs, deduplicated on text (the DEFER
    policy exists in two copies — one fragment id serves both, deliberately:
    presence in composed output is what the scan measures, not which copy).

    This is a FLOOR, like the inventory itself: literals assembled by
    runtime interpolation do not reduce to a matchable constant.
    """
    from ciris_engine.logic.utils.research_overrides import (
        _ENGINE_ROOT,
        _extract_symbol_source,
        RESIDUE_SITES,
    )

    fragments: List[Tuple[str, str]] = []
    seen: Dict[str, str] = {}
    for rel, qualname in RESIDUE_SITES:
        segment = _extract_symbol_source(_ENGINE_ROOT / rel, qualname)
        tree = _parse_symbol_source(segment)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                normalized = _normalize_ws(node.value)
                if len(normalized) < _FRAGMENT_MIN_CHARS:
                    continue
                if normalized in seen:
                    continue
                digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
                fragment_id = f"{rel}::{qualname}#{digest}"
                seen[normalized] = fragment_id
                fragments.append((fragment_id, normalized))
    return tuple(fragments)


def _scan_residue(normalized_block: str, fragments: Sequence[Tuple[str, str]]) -> List[str]:
    return [fragment_id for fragment_id, text in fragments if text in normalized_block]


def _scan_tokens(text: str) -> List[str]:
    lowered = text.lower()
    hits: List[str] = []
    for token, case_sensitive in _TOKEN_ADJUNCT:
        if (token in text) if case_sensitive else (token.lower() in lowered):
            hits.append(token)
    return hits


# --------------------------------------------------------------------------
# Routed-block identification: recording pass-throughs
# --------------------------------------------------------------------------


class _RoutedRecorder:
    """Pass-through wrappers around the four prompt-content loaders.

    Instead of guessing block identity from message positions, the dump
    patches the loaders (same patch set the #972 golden harness uses) with
    wrappers that return the REAL content and remember it. A composed message
    byte-equal to a recorded loader output IS that routed block; everything
    else is inline. Honest by construction.
    """

    def __init__(self) -> None:
        # Bind the real callables BEFORE any patching replaces the names.
        from ciris_engine.logic.conscience import core as _conscience_core
        from ciris_engine.logic.conscience.prompt_loader import ConsciencePromptLoader
        from ciris_engine.logic.dma.prompt_loader import DMAPromptLoader
        from ciris_engine.logic.utils import constants as _constants
        from ciris_engine.logic.utils import localization as _localization

        self._real_accord: Callable[..., str] = _constants.get_accord_text
        self._real_localized: Callable[..., str] = _constants.get_localized_accord_text
        self._real_language_guidance: Callable[[str], str] = _localization.get_language_guidance
        self._real_prohibition: Callable[[str], str] = _localization.get_prohibition_guidance
        self._real_user_message: Callable[..., str] = DMAPromptLoader.get_user_message
        self._real_conscience_system: Callable[..., str] = ConsciencePromptLoader.get_system_prompt
        self._real_conscience_user: Callable[..., str] = ConsciencePromptLoader.get_user_prompt
        #: The accord as the CONSCIENCES see it (#986). They import the module
        #: constant ``ACCORD_TEXT`` directly rather than calling
        #: ``get_accord_text()``, so this text reaches an LLM having bypassed
        #: both ACCORD_MODE and ``override_corpus`` — it is the accord, and it
        #: is NOT routed. Recorded separately (never into ``routed``) so a
        #: genuinely routed registration always wins the label.
        self.conscience_accord: str = str(getattr(_conscience_core, "ACCORD_TEXT", ""))
        #: exact content -> (block name, routed source label)
        self.routed: Dict[str, Tuple[str, str]] = {}

    def _register(self, value: str, name: str, source: str) -> str:
        if value:
            self.routed.setdefault(value, (name, source))
        return value

    def accord(self, mode: str = "default") -> str:
        from ciris_engine.logic.utils.constants import ACCORD_MODE

        effective = ACCORD_MODE if mode in ("default", "full") else mode
        variant = "polyglot_full" if effective in ("full", "force_full") else "polyglot_compressed"
        return self._register(self._real_accord(mode), "accord", f"corpus:accord.{variant}")

    def localized_accord(self, lang: Optional[str] = None) -> str:
        return self._register(self._real_localized(lang), "accord", "corpus:accord.localized")

    def language_guidance(self, lang_code: str) -> str:
        return self._register(
            self._real_language_guidance(lang_code), "language_guidance", "string:prompts.language_guidance"
        )

    def prohibition_guidance(self, lang_code: str) -> str:
        return self._register(
            self._real_prohibition(lang_code), "prohibition", "string:prompts.prohibitions"
        )

    def user_message(self, loader: object, template_data: object, **kwargs: object) -> str:
        """Recording pass-through around ``DMAPromptLoader.get_user_message`` (#974).

        Every DMA whose user message is wholly the render of its routed
        ``context_integration`` template composes a message byte-equal to this
        return value — that block is then honestly sourced
        ``dma_prompt:<template>.context_integration``. A DMA that only
        interpolates a fragment of the render (DSASPDMA), appends to it, or
        strips it into different bytes never matches and stays ``inline``.
        """
        value = self._real_user_message(loader, template_data, **kwargs)
        component = str(getattr(template_data, "component_name", "unknown"))
        return self._register(value, "user", f"dma_prompt:{component}.context_integration")

    def conscience_system_prompt(self, loader: object, conscience_type: str) -> str:
        """Recording pass-through around ``ConsciencePromptLoader.get_system_prompt`` (#986)."""
        return self._register(
            self._real_conscience_system(loader, conscience_type),
            "system",
            f"conscience_prompt:{conscience_type}.system_prompt",
        )

    def conscience_user_prompt(
        self, loader: object, conscience_type: str, image_context: Optional[str] = None, **kwargs: str
    ) -> str:
        """Recording pass-through around ``ConsciencePromptLoader.get_user_prompt`` (#986).

        The loader picks between two overridable templates on ``image_context``,
        so the recorded source names whichever one actually rendered — a dump
        that said ``user_prompt_template`` for an image-context render would
        credit coverage to a key that did not compose.
        """
        value = self._real_conscience_user(loader, conscience_type, image_context=image_context, **kwargs)
        field = "user_prompt_with_image_template" if image_context else "user_prompt_template"
        return self._register(value, "user", f"conscience_prompt:{conscience_type}.{field}")


def _content_text(message: JSONDict) -> str:
    """Flatten a message's content (plain or multimodal list) to text."""
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text", "")))
        return "".join(parts)
    return str(content)


def _identify_block(text: str, role: str, recorder: _RoutedRecorder, unmatched_count: int) -> Tuple[str, str]:
    """Return (block name, source label) for one composed message.

    Routed blocks match a recorded loader output byte-for-byte. The ASPDMA
    accord block (runtime ``THOUGHT_TYPE=`` slot + routed accord in one
    message) is named ``accord`` but sourced ``inline`` — one block, mixed,
    never finer granularity than the code has. Everything else is the seam's
    inline system/user message.
    """
    routed = recorder.routed.get(text)
    if routed is not None:
        return routed
    if text.startswith("THOUGHT_TYPE=") and "\n\n" in text:
        rest = text.split("\n\n", 1)[1]
        rest_routed = recorder.routed.get(rest)
        if rest_routed is not None and rest_routed[0] == "accord":
            return ("accord", "inline")
    # The conscience accord (#986). Checked AFTER the routed lookup so a routed
    # registration always wins: if ACCORD_MODE ever makes get_accord_text()
    # return these same bytes, the block is reported by its real routed source
    # rather than being demoted to inline.
    if text and text == recorder.conscience_accord:
        return ("accord", "inline")
    base = "user" if role == "user" else "system"
    name = base if unmatched_count == 0 else f"{base}.{unmatched_count + 1}"
    return (name, "inline")


# --------------------------------------------------------------------------
# The dump
# --------------------------------------------------------------------------


def _fixture_module() -> object:
    """Load the #972 compose fixture (repo checkout required)."""
    try:
        from tests.ciris_engine.logic.dma import compose_golden
    except ImportError as exc:  # pragma: no cover - repo layout guard
        raise SystemExit(
            "compose_dump dump requires the repo checkout: the compose fixture is "
            "tests/ciris_engine/logic/dma/compose_golden.py (the #972 golden harness). "
            f"Import failed: {exc}"
        )
    return compose_golden


def _rows_for_messages(
    messages: List[JSONDict],
    *,
    step: str,
    locale: str,
    arm: str,
    recorder: _RoutedRecorder,
    fragments: Sequence[Tuple[str, str]],
) -> List[ComposedBlock]:
    rows: List[ComposedBlock] = []
    unmatched: Dict[str, int] = {"system": 0, "user": 0}
    for seq, message in enumerate(messages):
        role = str(message.get("role", ""))
        text = _content_text(message)
        base = "user" if role == "user" else "system"
        name, source = _identify_block(text, role, recorder, unmatched[base])
        if source == "inline" and (name.startswith("system") or name.startswith("user")):
            unmatched[base] += 1
        block_id = f"{step}.{name}"
        annotation = annotation_for(block_id)
        rows.append(
            ComposedBlock(
                block_id=block_id,
                step=step,
                locale=locale,
                arm=arm,
                seq=seq,
                role=role,
                block_class=annotation.block_class,
                disposition=CLASS_DEFAULT_DISPOSITION[annotation.block_class],
                source=source,
                sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                bytes=len(text.encode("utf-8")),
                contaminant=list(annotation.contaminant) if annotation.contaminant is not None else None,
                residue_hits=_scan_residue(_normalize_ws(text), fragments),
                token_hits=_scan_tokens(text),
            )
        )
    return rows


def compose_dump_rows(
    *,
    arm: str,
    locales: Sequence[str],
    steps: Optional[Sequence[str]] = None,
    manifest: Optional[str] = None,
) -> Tuple[ComposeDumpMeta, List[ComposedBlock]]:
    """Compose every step per locale and return (meta, sorted rows).

    A failed composition is NAMED, not dropped (assertion 1's dump half):
    the raising step/locale is wrapped into the error message and the dump
    aborts non-zero.
    """
    import asyncio

    if manifest is not None:
        # Must precede the first composition: the override registry loads once
        # per process (research_overrides._loaded). Two-key gate as everywhere.
        os.environ["CIRIS_RESEARCH_PROMPT_OVERRIDES"] = manifest
        os.environ["CIRIS_TESTING_MODE"] = "true"

    golden = _fixture_module()
    step_names: Tuple[str, ...] = tuple(steps) if steps else tuple(golden.STEP_NAMES)  # type: ignore[attr-defined]
    fragments = residue_fragments()
    recorder = _RoutedRecorder()
    rows: List[ComposedBlock] = []

    def _user_message_seam(loader: object, template_data: object, **kwargs: object) -> str:
        """Plain function so patching DMAPromptLoader.get_user_message keeps
        descriptor binding (a bound method as a class attribute would swallow
        the loader instance)."""
        return recorder.user_message(loader, template_data, **kwargs)

    def _conscience_system_seam(loader: object, conscience_type: str) -> str:
        """Plain function, same descriptor-binding reason as above."""
        return recorder.conscience_system_prompt(loader, conscience_type)

    def _conscience_user_seam(
        loader: object, conscience_type: str, image_context: Optional[str] = None, **kwargs: str
    ) -> str:
        """Plain function, same descriptor-binding reason as above."""
        return recorder.conscience_user_prompt(loader, conscience_type, image_context=image_context, **kwargs)

    for locale in locales:
        env = golden.prompt_content_environment(  # type: ignore[attr-defined]
            language=locale,
            accord=recorder.accord,
            localized_accord=recorder.localized_accord,
            language_guidance=recorder.language_guidance,
            prohibition_guidance=recorder.prohibition_guidance,
            user_message=_user_message_seam,
            conscience_system_prompt=_conscience_system_seam,
            conscience_user_prompt=_conscience_user_seam,
        )
        with env:
            for step in step_names:
                try:
                    messages: List[JSONDict] = asyncio.run(golden.capture_step(step))  # type: ignore[attr-defined]
                except Exception as exc:
                    raise SystemExit(
                        f"composition FAILED for step={step} locale={locale} arm={arm}: {exc!r} "
                        f"(assertion 1: a failed composition is named, not dropped)"
                    ) from exc
                rows.extend(
                    _rows_for_messages(
                        messages, step=step, locale=locale, arm=arm, recorder=recorder, fragments=fragments
                    )
                )

    from ciris_engine.logic.utils.research_overrides import compute_residue_digest

    meta = ComposeDumpMeta(
        conscience_guidance_mode=_conscience_mode_for_dump(),
        arm=arm,
        manifest=manifest,
        locales=list(locales),
        steps=list(step_names),
        residue_digest=compute_residue_digest(),
        fragment_count=len(fragments),
    )
    rows.sort(key=lambda r: (r.locale, r.step, r.seq))
    return meta, rows



def _conscience_mode_for_dump() -> str:
    """#986: the dump is an audit artifact; it pins the #983 mode it composed under."""
    from ciris_engine.logic.utils.conscience_mode import conscience_guidance_mode

    return conscience_guidance_mode()

def write_dump(meta: ComposeDumpMeta, rows: Sequence[ComposedBlock], out: Optional[str]) -> None:
    lines = [meta.model_dump_json()]
    lines.extend(row.model_dump_json(by_alias=True) for row in rows)
    payload = "\n".join(lines) + "\n"
    if out is None:
        sys.stdout.write(payload)
    else:
        Path(out).write_text(payload, encoding="utf-8")


def load_dump(path: str) -> Tuple[ComposeDumpMeta, List[ComposedBlock]]:
    lines = [line for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        raise SystemExit(f"{path}: empty dump")
    meta = ComposeDumpMeta.model_validate_json(lines[0])
    rows = [ComposedBlock.model_validate_json(line) for line in lines[1:]]
    return meta, rows


# --------------------------------------------------------------------------
# Detached dump signatures (#977 / FSD §13) — ciris_server 0.5.154 sign_object
# --------------------------------------------------------------------------


def _sig_path_for(dump_path: str) -> str:
    """The detached-signature path convention: ``<dump>.sig.json`` beside it."""
    return dump_path + ".sig.json"


def sign_dump(out_path: str, arm: str) -> str:
    """Sign the emitted dump with the node's key — ``ciris_server.sign_object``.

    ``label`` = the arm name, and it rides INSIDE the signed manifest, so a
    dump cannot be relabelled into a different arm after the fact — for a
    campaign with hidden and visible arms that is the property that matters
    most, and it is why the label goes here rather than into a filename. The
    signature claims only provenance: this node's key saw exactly these bytes.

    This is the #977 replacement for the FSD §13 ``local_sign_hybrid``
    descope: same "locally signed, not CEG-signed" honesty, but the manifest
    (byte hash + label + signer + timestamp) and the hybrid signature come
    from the substrate's single purpose-built verb instead of being assembled
    here. NOTE ``sign_object`` requires the LIVE node runtime (in-process
    Engine + edge + federation delivery, 0.5.154 contract); outside one the
    substrate refuses and the dump run FAILS LOUDLY rather than silently
    emitting output that was asked to be signed and is not.

    Writes ``<out>.sig.json`` next to the dump; returns the signature path.
    """
    try:
        import ciris_server  # type: ignore[import-not-found, import-untyped, unused-ignore]
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"--sign requires ciris_server: {exc}")
    sign = getattr(ciris_server, "sign_object", None)
    if sign is None:
        raise SystemExit("--sign requires ciris_server.sign_object (ciris-server >= 0.5.154)")
    try:
        signature_json = sign(out_path, label=arm)
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            f"--sign FAILED for {out_path}: {exc} "
            f"(sign_object signs with the live node's key — it needs the in-process "
            f"Engine + edge + federation delivery running; a bare CLI process has none)"
        )
    sig_path = _sig_path_for(out_path)
    Path(sig_path).write_text(str(signature_json), encoding="utf-8")
    return sig_path


def verify_dump_signature(dump_path: str, expected_arm: str) -> Optional[str]:
    """Verify a dump's detached signature. None = verified; str = the failure.

    Accepts ONLY ``ciris_server.verify_object(...) is True``. False is an
    honest mismatch (the dump changed, or the signature is bad). An exception
    means the check could not be PERFORMED — refused here too, because a
    verifier that cannot tell "forged" from "I could not look" admits both.

    The sealed label must equal the arm the dump's meta row claims: the label
    lives inside the signed manifest, so a valid signature with a different
    label is a dump signed FOR another arm being presented as this one — the
    exact relabelling the label-in-envelope design exists to refuse.
    """
    sig_file = Path(_sig_path_for(dump_path))
    if not sig_file.exists():
        return f"{sig_file}: missing detached signature (produce the dump with --sign)"
    sig_json = sig_file.read_text(encoding="utf-8")

    try:
        import ciris_server  # type: ignore[import-not-found, import-untyped, unused-ignore]
    except Exception as exc:  # noqa: BLE001
        return f"ciris_server not importable — verification could not be performed: {exc}"
    verify = getattr(ciris_server, "verify_object", None)
    if verify is None:
        return "ciris_server.verify_object unavailable (need >= 0.5.154) — verification could not be performed"

    try:
        verified = verify(dump_path, sig_json)
    except Exception as exc:  # noqa: BLE001
        return f"verification could not be PERFORMED ({exc}) — refused; 'could not look' is not 'verified'"
    if verified is not True:
        return (
            "signature does not verify: the dump bytes changed since signing, the signature "
            "document was tampered with (including its sealed label), or the signer's key is "
            "not registered in this node's federation directory"
        )

    label: Optional[str] = None
    try:
        manifest = json.loads(sig_json).get("manifest")
        if isinstance(manifest, dict):
            raw_label = manifest.get("label")
            label = raw_label if isinstance(raw_label, str) else None
    except (TypeError, ValueError):
        label = None
    if label != expected_arm:
        return (
            f"sealed label {label!r} != dump arm {expected_arm!r} — a dump signed under one arm "
            f"is being presented as another"
        )
    return None


# --------------------------------------------------------------------------
# Gate Phase 1 (FSD §12) — six assertions, block-keyed
# --------------------------------------------------------------------------


def _regime_entry_for(regime: GateRegime, block_id: str) -> Optional[RegimeBlockEntry]:
    """Per-block regime entry: exact block_id, then step-suffix (see GateRegime)."""
    exact = regime.blocks.get(block_id)
    if exact is not None:
        return exact
    suffix = block_id.split(".", 1)[1] if "." in block_id else block_id
    return regime.blocks.get(suffix)


def load_regime(path: str) -> GateRegime:
    import yaml

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return GateRegime.model_validate(raw)


def run_gate(dump_a_path: str, dump_b_path: str, regime_path: str, verify_sig: bool = False) -> int:
    """FSD §12 Phase-1 assertions over two dumps. Returns process exit code."""
    from ciris_engine.logic.utils.research_overrides import compute_residue_digest

    meta_a, rows_a = load_dump(dump_a_path)
    meta_b, rows_b = load_dump(dump_b_path)
    regime = load_regime(regime_path)
    varied = regime.varied_classes()

    failures: List[str] = []
    na_blocks: List[str] = []
    contingent_excluded = 0

    # ---- --verify-sig: detached signatures must verify TRUE (#977) ------
    if verify_sig:
        for label, path, meta in (("dump-a", dump_a_path, meta_a), ("dump-b", dump_b_path, meta_b)):
            problem = verify_dump_signature(path, meta.arm)
            if problem is not None:
                failures.append(f"[sig] {label}: {problem}")

    def block_key(row: ComposedBlock) -> Tuple[str, str]:
        return (row.locale, row.block_id)

    index_a = {block_key(r): r for r in rows_a}
    index_b = {block_key(r): r for r in rows_b}

    # ---- assertion 5: residue_digest matches the pin --------------------
    live_digest = compute_residue_digest()
    pinned = regime.pins.residue_digest
    if pinned == "live":
        # Self-check-only sentinel: pin resolves to THIS tree's digest. A
        # campaign regime pins the concrete value; "live" exists so the CI
        # self-check does not need a per-commit regime file.
        pinned = live_digest
    for label, digest in (("regime pin", pinned), ("dump-a", meta_a.residue_digest), ("dump-b", meta_b.residue_digest)):
        if digest != live_digest:
            failures.append(
                f"[5] residue_digest mismatch: {label} carries {digest}, source tree is {live_digest} "
                f"— the uncovered inline doctrine moved (or the dump was produced from a different tree)"
            )

    # Residue-scan instrument consistency (assertion 4's floor): both dumps
    # must have scanned the same fragment inventory as this tree yields.
    live_fragment_count = len(residue_fragments())
    for label, count in (("dump-a", meta_a.fragment_count), ("dump-b", meta_b.fragment_count)):
        if count != live_fragment_count:
            failures.append(
                f"[4] residue scan inventory drift: {label} scanned {count} fragments, "
                f"this tree yields {live_fragment_count} — the scan the dump ran is not the scan being trusted"
            )

    # ---- assertion 1: every arm x locale composes -----------------------
    for label, meta, rows in (("dump-a", meta_a, rows_a), ("dump-b", meta_b, rows_b)):
        present = {(r.locale, r.step) for r in rows}
        for locale in meta.locales:
            for step in meta.steps:
                if (locale, step) not in present:
                    failures.append(f"[1] {label}: step={step} locale={locale} has no composed blocks")
    if set(index_a) != set(index_b):
        only_a = sorted("{}:{}".format(*k) for k in set(index_a) - set(index_b))
        only_b = sorted("{}:{}".format(*k) for k in set(index_b) - set(index_a))
        # Reported under 1 (block-space mismatch); per-class consequences are
        # re-checked under 2/3 for the blocks that DO pair up.
        if only_a:
            failures.append(f"[1] blocks only in dump-a: {', '.join(only_a)}")
        if only_b:
            failures.append(f"[1] blocks only in dump-b: {', '.join(only_b)}")

    # ---- assertions 2/3/4/6 + mixed refusals, block-keyed ---------------
    for key in sorted(set(index_a) & set(index_b)):
        row_a = index_a[key]
        row_b = index_b[key]
        name = f"{row_a.locale}:{row_a.block_id}"

        if row_a.block_class != row_b.block_class:
            failures.append(
                f"[6] {name}: class disagrees between dumps "
                f"({row_a.block_class.value} vs {row_b.block_class.value}) — annotation drift"
            )
            continue

        block_class = row_a.block_class

        # contingent: excluded from Phase 1 by construction [T-2].
        if block_class is BlockClass.CONTINGENT:
            contingent_excluded += 1
            continue

        # structural/axiomatic discrete blocks cannot vary: n/a, listed.
        if block_class in (BlockClass.STRUCTURAL, BlockClass.AXIOMATIC):
            na_blocks.append(name)
            continue

        if block_class is BlockClass.MIXED:
            entry = _regime_entry_for(regime, row_a.block_id)
            contaminants = frozenset(row_a.contaminant or [])
            if entry is None:
                if contaminants & varied:
                    failures.append(
                        f"[6] REFUSE {name}: mixed block with contaminant "
                        f"{sorted(c.value for c in contaminants & varied)} inside a varied class and no "
                        f"per-block disposition in the regime (§10.2.1 — the run does not start)"
                    )
                else:
                    failures.append(
                        f"[6] REFUSE {name}: mixed block with no per-block disposition in the regime "
                        f"(§10.2.1 default is refuse)"
                    )
                continue
            if entry.disposition is BlockDisposition.REFUSE:
                failures.append(f"[6] REFUSE {name}: regime dispositions this mixed block 'refuse'")
                continue
            if entry.disposition is BlockDisposition.VARY:
                failures.append(
                    f"[6] REFUSE {name}: a mixed block cannot carry 'vary' in Phase 1 — split it in the "
                    f"corpus first (§11), then its routed fragments vary cleanly"
                )
                continue
            if entry.disposition is BlockDisposition.NOT_APPLICABLE:
                na_blocks.append(name)
                continue
            # hold: T-N1 — contaminant intersecting a varied class refuses
            # unless confound_accepted names that exact contaminant.
            unaccepted = (contaminants & varied) - frozenset(entry.confound_accepted)
            if unaccepted:
                failures.append(
                    f"[6] REFUSE {name}: held mixed block smuggles varied class(es) "
                    f"{sorted(c.value for c in unaccepted)} (contaminant intersects a varied class without "
                    f"confound_accepted [T-N1])"
                )
                continue
            # Descope (FSD §14 step 3): assertions 2/3 iterate only routed
            # (non-mixed) classes — a held mixed block is not byte-checked
            # here; #974 routing shrinks this surface.
            continue

        # Routed classes: assertion 2 (varied) / assertion 3 (held).
        if block_class in varied:
            if row_a.bytes == 0 or row_b.bytes == 0:
                failures.append(
                    f"[2] {name}: varied {block_class.value} block has an EMPTY side (replacement must be non-empty)"
                )
            elif row_a.sha256 == row_b.sha256:
                failures.append(
                    f"[2] {name}: {block_class.value} is varied by the regime but the block is byte-identical "
                    f"across arms (sha256 {row_a.sha256[:12]}…) — the ablation did not reach it"
                )
        else:
            if row_a.sha256 != row_b.sha256:
                failures.append(
                    f"[3] {name}: held {block_class.value} block differs across arms "
                    f"(sha256 {row_a.sha256[:12]}… vs {row_b.sha256[:12]}…)"
                )

        # ---- assertion 4: residue + token hits must be arm-invariant ----
        if row_a.residue_hits != row_b.residue_hits:
            failures.append(
                f"[4] {name}: residue fragment hits diverge between arms "
                f"({len(row_a.residue_hits)} vs {len(row_b.residue_hits)}) — shared inline doctrine is not shared"
            )
        if row_a.token_hits != row_b.token_hits:
            failures.append(f"[4] {name}: token adjunct hits diverge ({row_a.token_hits} vs {row_b.token_hits})")

    # ---- report ---------------------------------------------------------
    total_pairs = len(set(index_a) & set(index_b))
    residue_total = sum(len(r.residue_hits) for r in rows_a)
    print(f"gate: regime={regime.regime_id} varied={sorted(c.value for c in varied) or ['<none>']}")
    print(f"gate: {total_pairs} block pairs; contingent excluded by construction: {contingent_excluded}")
    print(f"gate: n/a blocks: {', '.join(sorted(na_blocks)) if na_blocks else 'none'}")
    print(f"gate: residue fragment hits in dump-a: {residue_total} (inventory: {live_fragment_count} fragments)")
    if failures:
        for failure in failures:
            print(f"FAIL {failure}")
        print(f"GATE: FAIL — {len(failures)} failing check(s), every failing block named above")
        return 1
    print("GATE: PASS — all Phase-1 assertions hold")
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _run_arms_config(config_path: str, locales: str, out_dir: str, steps: Optional[str]) -> int:
    """Driver: one subprocess per arm (the caches are process-global [I-V3])."""
    import yaml

    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    arms: Dict[str, Optional[str]] = {}
    for name, spec in (raw.get("arms") or {}).items():
        arms[str(name)] = spec.get("manifest") if isinstance(spec, dict) else None
    if not arms:
        raise SystemExit(f"{config_path}: no arms declared")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, manifest in arms.items():
        cmd = [
            sys.executable,
            "-m",
            "ciris_engine.logic.utils.compose_dump",
            "dump",
            "--arm",
            name,
            "--locales",
            locales,
            "--out",
            str(out / f"{name}.jsonl"),
        ]
        if manifest:
            cmd += ["--manifest", manifest]
        if steps:
            cmd += ["--steps", steps]
        result = subprocess.run(cmd, check=False)
        if result.returncode != 0:
            print(f"arm '{name}' dump FAILED (rc={result.returncode})", file=sys.stderr)
            return result.returncode
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m ciris_engine.logic.utils.compose_dump",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    dump_p = sub.add_parser("dump", help="compose every step per locale, emit JSONL block rows")
    dump_p.add_argument("--arm", default="h3ere-ciris", help="regime arm name recorded in every row")
    dump_p.add_argument("--locales", default="en", help="comma-separated locales")
    dump_p.add_argument("--steps", default=None, help="comma-separated steps (default: all)")
    dump_p.add_argument("--manifest", default=None, help="research override manifest to compose under")
    dump_p.add_argument("--out", default=None, help="output JSONL path (default: stdout)")
    dump_p.add_argument(
        "--sign",
        action="store_true",
        help="sign the emitted JSONL with the node's key (ciris_server.sign_object, >=0.5.154); "
        "label = the arm name, sealed inside the signed manifest so the dump cannot be relabelled. "
        "Writes <out>.sig.json. Requires --out and a live node runtime in-process.",
    )
    dump_p.add_argument("--arms-config", default=None, help="YAML {arms: {name: {manifest: path}}}; subprocess per arm")
    dump_p.add_argument("--out-dir", default=None, help="output directory for --arms-config")

    gate_p = sub.add_parser("gate", help="run the FSD §12 Phase-1 assertions over two dumps")
    gate_p.add_argument("--dump-a", required=True)
    gate_p.add_argument("--dump-b", required=True)
    gate_p.add_argument("--regime", required=True, help="regime manifest YAML (Phase-1 subset of §10.3)")
    gate_p.add_argument(
        "--verify-sig",
        action="store_true",
        help="require a verifying <dump>.sig.json beside each dump whose sealed label equals the "
        "dump's arm; only ciris_server.verify_object(...) is True passes — an unperformable "
        "check refuses, it does not pass",
    )

    args = parser.parse_args(argv)

    if args.command == "dump":
        if args.arms_config:
            return _run_arms_config(args.arms_config, args.locales, args.out_dir or ".", args.steps)
        if args.sign and args.out is None:
            raise SystemExit("--sign requires --out: a signature covers a file's exact bytes, and stdout is not a file")
        locales = [loc.strip() for loc in args.locales.split(",") if loc.strip()]
        steps = [s.strip() for s in args.steps.split(",") if s.strip()] if args.steps else None
        meta, rows = compose_dump_rows(arm=args.arm, locales=locales, steps=steps, manifest=args.manifest)
        write_dump(meta, rows, args.out)
        if args.sign:
            sig_path = sign_dump(args.out, args.arm)
            print(f"signed: {sig_path} (label={args.arm!r} sealed in the manifest)", file=sys.stderr)
        return 0
    return run_gate(args.dump_a, args.dump_b, args.regime, verify_sig=args.verify_sig)


if __name__ == "__main__":
    sys.exit(main())
