"""Research-bound prompt overrides.

Implements ``FSD/RESEARCH_PROMPT_OVERRIDES.md``. Read that document before
changing anything here; it records *why* each rule exists, and most of the rules
exist because their absence produces research numbers that look clean and are
wrong.

Three things live here:

1. **The gate** (§2.3). Two env vars. ``CIRIS_RESEARCH_PROMPT_OVERRIDES`` says
   *what* (a manifest path); ``CIRIS_TESTING_MODE`` says *whether*. Absence of
   the first means the feature does not exist in this process — no registry is
   constructed, nothing is consulted. Presence of the first without the second
   is a hard refusal naming both remedies.

2. **The manifest** (§3). Keyed the way each real loader is already keyed — one
   namespace per loader, five namespaces, no invented sixth flat keyspace.

3. **Fail-loud validation** (§3.2). Every rule runs at manifest load, before the
   first LLM call, and collects into one error. A campaign that discovers a bad
   key on thought #400 has already burned 399 contaminated samples.

**What this does NOT cover, stated here and not only in the FSD**: a share of
*operative* instruction text — the words that steer verb choice — is still
compiled-in English Python literals with no loader to intercept: the
formatters and the inline helpers the ASPDMA template interpolates. (#974 is
routing that residue out in order: step 0 routed the DEFER policy to
``action_selection_pdma.action_params_defer_guidance``; step 1 routed the
ASPDMA user-message template to ``action_selection_pdma.context_integration``;
step 2 made ``dsdma_base.context_integration`` live for the DSDMA user
message; step 3 routed the CORE IDENTITY blocks to ``prompts.identity_block``
— all four ARE covered now.) There is deliberately no ``inline`` namespace,
because offering one would imply that surface is addressable. It is not. It is
instead *pinned*: :func:`compute_residue_digest` hashes the source of every
uncovered site and the manifest must declare the digest, so the residue cannot
drift mid-campaign without stopping the run.
"""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Set, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.logic.utils.env_flags import env_is_true

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Gate
# --------------------------------------------------------------------------

#: What: absolute path to the manifest. Absence = the feature does not exist.
ENV_MANIFEST = "CIRIS_RESEARCH_PROMPT_OVERRIDES"

#: Whether: the anchor. Reused, not invented — it is the repo's existing
#: research anchor and is known-absent in production images.
#:
#: NEVER invert these two. ``tests/conftest.py`` sets the anchor for the whole
#: unit-test suite; that is safe only because the anchor *alone* does nothing.
ENV_ANCHOR = "CIRIS_TESTING_MODE"


class ResearchOverrideRefused(RuntimeError):
    """The gate refused. Not a bug — a configuration statement."""


class ResearchOverrideError(RuntimeError):
    """The manifest is set and permitted, but cannot be applied faithfully.

    Always raised eagerly at load, never at first use, and never downgraded to
    a skip. Partial application is the failure mode this whole module exists to
    prevent.
    """


def _refusal_text(manifest_path: str) -> str:
    """The refusal (§2.4).

    Names *both* remedies deliberately. This failure has two valid resolutions
    and which one is correct depends on a fact the code cannot see: whether the
    operator believes they are in production or in the harness. A bare "refused"
    makes the operator guess, and the cheap guess — set the other variable until
    it starts — is the dangerous one.
    """
    return (
        f"research prompt overrides refused: {ENV_MANIFEST} is set "
        f"({manifest_path}) but {ENV_ANCHOR} is not 'true'. Research overrides "
        f"replace covenant and DMA prompt text and are a pre-registered-experiment "
        f"facility only — they never run in production.\n"
        f"Remedy, pick one:\n"
        f"  production run  -> unset {ENV_MANIFEST}\n"
        f"  experiment run  -> set {ENV_ANCHOR}=true"
    )


# --------------------------------------------------------------------------
# Repo geometry
# --------------------------------------------------------------------------

_ENGINE_ROOT = Path(__file__).resolve().parents[2]  # ciris_engine/
_DMA_PROMPTS_DIR = _ENGINE_ROOT / "logic" / "dma" / "prompts"
_CONSCIENCE_PROMPTS_DIR = _ENGINE_ROOT / "logic" / "conscience" / "prompts"
_POLYGLOT_DIR = _ENGINE_ROOT / "data" / "localized" / "polyglot"

#: PromptCollection fields that carry prompt *text*. Excludes metadata
#: (``component_name``/``description``/``version``), the accord-mode selector,
#: the capability flag, and the two free-form dicts.
_DMA_PROMPT_TEXT_FIELDS: FrozenSet[str] = frozenset(
    {
        "system_header",
        "system_guidance_header",
        "domain_principles",
        "evaluation_steps",
        "evaluation_criteria",
        "response_format",
        "response_guidance",
        "decision_format",
        "action_parameter_schemas",
        "csdma_ambiguity_guidance",
        "action_params_speak_csdma_guidance",
        "action_params_ponder_guidance",
        "action_params_observe_guidance",
        # The DEFER policy, routed out of the inline Python literal by #974
        # step 0 (§11). Keyed action_selection_pdma.action_params_defer_guidance.
        "action_params_defer_guidance",
        "reasoning_csdma_guidance",
        "final_ponder_advisory",
        "closing_reminder",
        "context_integration",
        # #993 — composed after the ASPDMA template render (no {slot} exists for
        # them in context_integration, and adding one would need all 29
        # localized copies edited).
        "tool_selection_guidance",
        "csdma_ambiguity_alignment_example",
        # #995 P1-6 — live YAML that was outside the key space, so R1 rejected
        # any manifest naming it as "does not reach any LLM prompt", which was
        # false. Both reach a model and neither is a declared PromptCollection
        # field; they are carried in `custom_prompts`, which `get_prompt()`
        # reads and `_apply_research_overrides` now writes.
        #
        # `taxonomy_text` is 3,273 B — the full rights/needs deferral taxonomy,
        # operative doctrine steering DEFER classification. Leaving it
        # uncoverable meant a deontic arm could not touch the text that decides
        # deferral.
        "taxonomy_text",
        "tool_correction_section",
    }
)

#: ConsciencePrompts fields that carry prompt text.
_CONSCIENCE_PROMPT_TEXT_FIELDS: FrozenSet[str] = frozenset(
    {"system_prompt", "user_prompt_template", "user_prompt_with_image_template"}
)

#: AgentTemplate fields that reach a prompt as prose.
_TEMPLATE_TEXT_FIELDS: FrozenSet[str] = frozenset({"description", "role_description", "domain"})

#: Corpus keys (§3.1, fixed enum).
#:
#: ``guide.comprehensive`` is deliberately ABSENT. The comprehensive guide is
#: concatenated into ``ACCORD_TEXT`` at ``constants.py`` import time, before any
#: override could exist, so it has no independent substitution point. It is
#: covered as part of ``accord.polyglot_full`` and cannot be swapped separately.
_ACCORD_CORPUS_KEYS: FrozenSet[str] = frozenset(
    {
        "accord.localized",  # get_localized_accord_text  -> ASPDMA/TSASPDMA/DSASPDMA
        "accord.polyglot_compressed",  # get_accord_text(compressed) -> PDMA/CSDMA/IDMA/DSDMA
        "accord.polyglot_full",  # get_accord_text(full) — includes the guide
    }
)


def _yml_stems(directory: Path) -> FrozenSet[str]:
    if not directory.is_dir():
        return frozenset()
    return frozenset(p.stem for p in directory.glob("*.yml"))


@lru_cache(maxsize=1)
def _polyglot_corpus_keys() -> FrozenSet[str]:
    """``polyglot.<name>`` for every block a base DMA template actually cites.

    Blocks that exist on disk but are cited by nothing do not reach a prompt and
    therefore are not overridable — naming one would be a no-op, which is R1's
    whole point.
    """
    import re

    cited: Set[str] = set()
    pattern = re.compile(r"\{\{POLYGLOT_([A-Z0-9_]+)\}\}")
    for yml in sorted(_DMA_PROMPTS_DIR.glob("*.yml")):
        for name in pattern.findall(yml.read_text(encoding="utf-8")):
            cited.add(f"polyglot.{name.lower()}")
    return frozenset(cited)


# --------------------------------------------------------------------------
# Reachable ``get_string`` key space — scanned from source, never hardcoded
# --------------------------------------------------------------------------

#: Call names that resolve a localization key from their arguments.
_LOCALIZATION_CALLERS: FrozenSet[str] = frozenset(
    {"get_string", "_local", "_framing", "localizer", "get_language_guidance"}
)

#: Prefixes that indicate a key reaching an LLM prompt (as opposed to client UI).
_PROMPT_KEY_PREFIXES: Tuple[str, ...] = ("prompts.", "conscience.")

#: The key space as it stood when this module was written. The loader does NOT
#: consult this — it rescans source every time, so it cannot go stale. This
#: exists purely so the drift guard has something to compare against: if the
#: real surface moves, CI says so instead of the override silently ceasing to
#: cover a field.
DECLARED_STRING_KEY_SPACE: FrozenSet[str] = frozenset(
    {
        "conscience.forced_ponder_rationale",
        "conscience.override_rationale",
        "conscience.ponder_alternative_approach",
        "conscience.ponder_attempted",
        "conscience.ponder_bypass_failed",
        "conscience.ponder_conscience_failed",
        "conscience.ponder_forced_retry",
        "conscience.repeated_speak_guidance",
        "conscience.retry_alternatives_header",
        "conscience.retry_general_outro",
        "conscience.retry_header",
        "conscience.retry_intro",
        "conscience.retry_must_be_different",
        "conscience.retry_observation_intro",
        "conscience.retry_observation_outro",
        "conscience.retry_uncertainties_label",
        "conscience.retry_why_label",
        "prompts.dma.bounce_advisory_aspdma",
        "prompts.dma.bounce_header",
        "prompts.dma.bounce_instruction",
        "prompts.dma.bounce_original_marker",
        "prompts.dma.bounce_trigger_line",
        "prompts.identity_block",
        "prompts.language_guidance",
        "prompts.prohibitions.AUTONOMOUS_DECEPTION",
        "prompts.prohibitions.BIOMETRIC_INFERENCE",
        "prompts.prohibitions.CONTENT_MODERATION",
        "prompts.prohibitions.CYBER_OFFENSIVE",
        "prompts.prohibitions.DECEPTION_FRAUD",
        "prompts.prohibitions.DISCRIMINATION",
        "prompts.prohibitions.ELECTION_INTERFERENCE",
        "prompts.prohibitions.FINANCIAL",
        "prompts.prohibitions.HAZARDOUS_MATERIALS",
        "prompts.prohibitions.HOME_SECURITY",
        "prompts.prohibitions.IDENTITY_VERIFICATION",
        "prompts.prohibitions.INFRASTRUCTURE_CONTROL",
        "prompts.prohibitions.LEGAL",
        "prompts.prohibitions.MANIPULATION_COERCION",
        "prompts.prohibitions.MEDICAL",
        "prompts.prohibitions.RESEARCH",
        "prompts.prohibitions.SPIRITUAL_DIRECTION",
        "prompts.prohibitions.SURVEILLANCE_MASS",
        "prompts.prohibitions.WEAPONS_HARMFUL",
        "prompts.prohibitions._header",
        "prompts.prohibitions._tier_module",
        "prompts.prohibitions._tier_never",
    }
)


def _joined_str_prefix(node: ast.JoinedStr) -> Optional[str]:
    """Return the literal prefix of an f-string, if it starts with one."""
    if not node.values:
        return None
    head = node.values[0]
    if isinstance(head, ast.Constant) and isinstance(head.value, str):
        return head.value
    return None


def _scan_module_for_keys(path: Path) -> Set[str]:
    keys: Set[str] = set()
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):  # pragma: no cover - defensive
        return keys

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
        if name not in _LOCALIZATION_CALLERS:
            continue
        args: List[ast.expr] = list(node.args) + [kw.value for kw in node.keywords if kw.arg == "key"]
        for arg in args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                if arg.value.startswith(_PROMPT_KEY_PREFIXES):
                    keys.add(arg.value)
            elif isinstance(arg, ast.JoinedStr):
                prefix = _joined_str_prefix(arg)
                if prefix == "prompts.prohibitions.":
                    # The one dynamic prefix in the codebase
                    # (localization.py: _local(f"prompts.prohibitions.{category}")).
                    # Expanded from the single source of truth so it can never
                    # drift from the WiseBus gate.
                    from ciris_engine.logic.buses.prohibitions import PROHIBITED_CAPABILITIES

                    keys.update(f"{prefix}{c}" for c in PROHIBITED_CAPABILITIES)
    return keys


@lru_cache(maxsize=1)
def scan_reachable_string_keys() -> FrozenSet[str]:
    """The live ``get_string`` key space that actually reaches an LLM prompt.

    Rescanned from source rather than hardcoded, so a manifest can never name
    one of the 123 dead ``prompts.*`` keys and have it silently discarded.
    Cached per process; only ever called when a manifest is active.
    """
    keys: Set[str] = set()
    for path in _ENGINE_ROOT.rglob("*.py"):
        keys |= _scan_module_for_keys(path)
    return frozenset(keys)


# --------------------------------------------------------------------------
#: dma_prompt keys whose composed value the override layer does NOT decide.
#:
#: The #989 container mismatch is FIXED and is not what this tuple is for any
#: more. That history still matters, because it is what the tuple exists to
#: catch: ``BaseDMA._load_prompts`` read prompt YAML with ``yaml.safe_load``
#: and kept a plain dict, while ``_apply_research_overrides`` ``setattr``'d
#: onto a ``PromptCollection`` — a CONTAINER mismatch, not a policy decision.
#: Thirteen fields (ten in ``action_selection_pdma``, the action-selection tier
#: where an axiotic experiment's dependent variable is decided) were never
#: overridden while the loader logged successful replacements for their
#: siblings: a campaign could swap a value, read a success line, and run the
#: original. ``apply_research_overrides_to_mapping`` (prompt_loader.py) now
#: serves the mapping path with the same manifest and the same fail-loud
#: posture, so those keys are live.
#:
#: The OTHER shape of the same lie is the layer applying a value that the
#: runtime then declines to compose. #990 found one — ``action_selection_pdma.
#: action_parameter_schemas``, whose composed value is GENERATED from the live
#: action enum by ``_get_dynamic_action_schemas``, making the YAML field (and
#: therefore any override of it) a fallback nothing normally reads. It was NOT
#: parked here. Every field that enters a composed prompt is overridable, so the
#: override is now applied at the COMPOSITION boundary
#: (``ActionSelectionContextBuilder._composed_action_parameter_schemas``), after
#: generation, where a manifest value actually wins. The whole facility is gated
#: behind research mode; a replacement that no longer matches the action enum
#: can make a response unparseable, and that is a legitimate research condition,
#: made legible at the call site rather than prevented.
#:
#: So: still empty, and it should stay that way. If some future field genuinely
#: cannot be reached, name it here — R1 will refuse it by name and R2 totality
#: will drop it automatically — but prefer making it reachable. Re-measure with
#:     python3 -m tools.research.probe_gate_coverage --namespace dma_prompt
OVERRIDE_IMMUNE_DMA_PROMPT_KEYS: Tuple[str, ...] = ()


# The uncovered inline residue (§6.1)
# --------------------------------------------------------------------------

#: Every operative-instruction site that this facility does NOT cover, named as
#: ``(module-relative-path, qualname)``. ``"*"`` means the whole module.
#:
#: Sites are anchored on *symbols*, not line numbers, so unrelated edits
#: elsewhere in a file do not trip the digest but a change to the doctrine
#: itself does.
#:
#: This inventory is a FLOOR, not a measurement (FSD §1.4.1). It was assembled
#: by reading the DMA, conscience and formatter modules; it does not reliably
#: find prose assembled by conditional f-string interpolation, nor literals in
#: adapter code, nor ``ToolInfo.description`` text whose volume depends on which
#: adapters are loaded. Do not represent the digest as covering more than this.
RESIDUE_SITES: Tuple[Tuple[str, str], ...] = (
    # #995 P1-4 — the TSASPDMA correction-mode scaffold. A 523 B inline
    # f-string, not localized, that never passes through
    # prompt_loader.get_user_message. The equivalent literal in
    # ActionSelectionContextBuilder was routed out by #974 step 1; this one was
    # missed, so `tsaspdma_correction.user` was reachable by NO override key —
    # overriding all 101 keys moves 34 of 35 blocks and leaves this one
    # byte-identical.
    #
    # Being outside the manifest is a coverage gap. Being outside the digest
    # too meant it could drift mid-campaign without stopping the run, which is
    # precisely what residue_digest exists to prevent. Pinned here; the
    # manifest-reachability fix (adding tool_correction_section to
    # _DMA_PROMPT_TEXT_FIELDS) is separate and does not close this hole.
    (
        "logic/dma/tsaspdma.py",
        "TSASPDMAEvaluator._create_correction_mode_messages",
    ),
    # The ASPDMA user message TEMPLATE routed out in #974 step 1 — it is now
    # prompts/action_selection_pdma.yml `context_integration`, covered by the
    # dma_prompt namespace, so `build_main_user_content` left this inventory.
    # What stays pinned is the inline prose the template still interpolates:
    # the ponder-round framing, the startup directive, the reject-thought
    # note, and the original-task/schema helpers below.
    (
        "logic/dma/action_selection/context_builder.py",
        "ActionSelectionContextBuilder._build_ponder_context",
    ),
    (
        "logic/dma/action_selection/context_builder.py",
        "ActionSelectionContextBuilder._build_startup_guidance",
    ),
    (
        "logic/dma/action_selection/context_builder.py",
        "ActionSelectionContextBuilder._get_reject_thought_guidance",
    ),
    (
        "logic/dma/action_selection/context_builder.py",
        "ActionSelectionContextBuilder._build_original_task_context",
    ),
    (
        "logic/dma/action_selection/context_builder.py",
        "ActionSelectionContextBuilder._get_dynamic_action_schemas",
    ),
    # Action-schema and guidance scaffolding. The DEFER policy itself routed
    # OUT of these symbols in #974 step 0 (it now lives in
    # prompts/action_selection_pdma.yml, covered by the dma_prompt namespace);
    # what remains inline is the per-action schema text for the OTHER verbs
    # (SPEAK/PONDER/MEMORIZE/RECALL/FORGET/REJECT/TOOL/OBSERVE/TASK_COMPLETE)
    # and the non-DEFER guidance_map entries — still uncovered, still pinned.
    (
        "logic/dma/action_selection/action_instruction_generator.py",
        "ActionInstructionGenerator.generate_action_instructions",
    ),
    (
        "logic/dma/action_selection/action_instruction_generator.py",
        "ActionInstructionGenerator._generate_schema_for_action",
    ),
    (
        "logic/dma/action_selection/action_instruction_generator.py",
        "ActionInstructionGenerator.get_action_guidance",
    ),
    (
        "logic/dma/action_selection/action_instruction_generator.py",
        "ActionInstructionGenerator._format_memory_action_schema",
    ),
    (
        "logic/dma/action_selection/action_instruction_generator.py",
        "ActionInstructionGenerator._generate_tool_schema",
    ),
    # DSDMA gathering + composition scaffolding. The DSDMA user message routed
    # out in #974 step 2 (dsdma_base.yml context_integration is live) and the
    # CORE IDENTITY blocks routed out in step 3 (prompts.identity_block, one
    # source for all three former copies). evaluate_thought stays pinned for
    # its remaining prompt-reaching literals (the platform-context framing);
    # compose_messages for its error-path fallback doctrine ("You are a
    # domain-specific evaluator ...") and the identity-prepend logic.
    ("logic/dma/dsdma_base.py", "BaseDSDMA.evaluate_thought"),
    ("logic/dma/dsdma_base.py", "BaseDSDMA.compose_messages"),
    # Conscience override reasons, which flow back into the retry prompt. The
    # operative one — the repeated-SPEAK guidance that instructs the agent to
    # emit specific words — routed out in #974 step 5
    # (conscience.repeated_speak_guidance); the module stays pinned for its
    # remaining inline reason strings.
    ("logic/conscience/action_sequence_conscience.py", "*"),
    # Formatters: zero localization imports across all six, every one emits
    # hardcoded English into a prompt. (Said "five" while listing six since the
    # inventory was written — #995. The count matters: `baseline_note` reports
    # "six formatters" to anyone reading a manifest, and two numbers for the
    # same uncovered surface is exactly the kind of drift the digest exists to
    # make impossible.)
    ("logic/formatters/system_snapshot.py", "*"),
    ("logic/formatters/identity.py", "*"),
    ("logic/formatters/user_profiles.py", "*"),
    ("logic/formatters/crisis_resources.py", "*"),
    ("logic/formatters/prompt_blocks.py", "*"),
    ("logic/formatters/escalation.py", "*"),
    # Retry remediation dict [I-7]: re-injects the English action-verb whitelist
    # into retry prompts BELOW the bus-layer capture hook, locale-correlated
    # (non-English cells trigger more retries). Static and arm-invariant, which
    # makes it residue: pinned here so it cannot drift mid-campaign, and so the
    # §12 structural residue scan can match it in composed output.
    ("logic/services/runtime/llm_service/service.py", "LLM_ERROR_REMEDIATIONS"),
)


def _extract_symbol_source(path: Path, qualname: str) -> str:
    source = path.read_text(encoding="utf-8")
    if qualname == "*":
        return source
    tree = ast.parse(source)

    def find(node: ast.AST, prefix: str) -> Optional[ast.AST]:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                qual = f"{prefix}{child.name}"
                if qual == qualname:
                    return child
                if qualname.startswith(qual + "."):
                    found = find(child, qual + ".")
                    if found is not None:
                        return found
            # Module/class-level ASSIGNMENTS are residue too (#975 / [I-7]):
            # LLM_ERROR_REMEDIATIONS is a bare dict assignment that re-injects
            # English action-verb doctrine into retry prompts. The extractor
            # previously resolved only def/class, so a constant could never be
            # pinned — which is how that dict stayed out of the inventory.
            elif isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Name) and f"{prefix}{target.id}" == qualname:
                        return child
            elif isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                if f"{prefix}{child.target.id}" == qualname:
                    return child
        return None

    node = find(tree, "")
    if node is None:
        raise ResearchOverrideError(
            f"residue inventory names a symbol that no longer exists: "
            f"{path.relative_to(_ENGINE_ROOT)}::{qualname}. The uncovered inline "
            f"surface moved; update RESIDUE_SITES and re-pin residue_digest."
        )
    segment = ast.get_source_segment(source, node)
    if segment is None:  # pragma: no cover - defensive
        raise ResearchOverrideError(f"could not extract source for {path}::{qualname}")
    return segment


def compute_residue_digest() -> str:
    """SHA256 over the source of every uncovered inline site.

    The residue stays uncovered but becomes *pinned*: it cannot drift mid-campaign
    without stopping the run. Same idea as ``ACCORD_EXPECTED_HASHES``, applied to
    a surface with no file to hash.
    """
    hasher = hashlib.sha256()
    for rel, qualname in RESIDUE_SITES:
        path = _ENGINE_ROOT / rel
        if not path.exists():
            raise ResearchOverrideError(
                f"residue inventory names a module that no longer exists: {rel}. "
                f"Update RESIDUE_SITES and re-pin residue_digest."
            )
        hasher.update(f"\x00{rel}::{qualname}\x00".encode("utf-8"))
        hasher.update(_extract_symbol_source(path, qualname).encode("utf-8"))
    return f"sha256:{hasher.hexdigest()}"


# --------------------------------------------------------------------------
# Manifest schema
# --------------------------------------------------------------------------


class OverrideSet(BaseModel):
    """The five namespaces (§3.1).

    There is deliberately no ``inline`` namespace. ``extra="forbid"`` so a
    manifest that invents one fails instead of being quietly ignored.
    """

    model_config = ConfigDict(extra="forbid")

    #: ``string`` keys are LOCALIZED — the same key resolves to different text in
    #: each locale. A value may therefore be either:
    #:
    #: * ``str``   — this exact text in EVERY locale. A deliberate choice, not a
    #:   default: it puts one language's text into every language's prompt.
    #: * ``dict``  — ``{locale: text}``, the faithful form for a localized key.
    #:   A locale absent from the mapping REFUSES at resolution rather than
    #:   falling back to English (that fallback is the R4 laundering this
    #:   facility exists to prevent).
    #:
    #: Before this was a union, every value was a scalar snapshotted at ``en``,
    #: so a baseline manifest silently served English guidance, English
    #: prohibitions and English retry scaffolding in all 29 locales.
    string: Dict[str, Union[str, Dict[str, str]]] = Field(default_factory=dict)
    dma_prompt: Dict[str, str] = Field(default_factory=dict)
    conscience_prompt: Dict[str, str] = Field(default_factory=dict)
    corpus: Dict[str, str] = Field(default_factory=dict)
    template: Dict[str, str] = Field(default_factory=dict)


class ResearchOverrideManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest_version: str = Field(..., description="Must be '1'")
    experiment_id: str = Field(..., min_length=1)
    condition: str = Field(..., description="Pre-registration condition label: a, b or c")
    base_locale: str = Field(default="en")
    mode: str = Field(..., description="'strict' (totality required) or 'additive' (pilots)")
    residue_digest: str = Field(..., description="sha256:… over the uncovered inline surface")
    overrides: OverrideSet = Field(default_factory=OverrideSet)
    research_hashes: Dict[str, str] = Field(default_factory=dict)

    #: Not from the file — recorded at load so the trace can carry provenance.
    manifest_path: str = Field(default="")

    def trace_fields(self) -> Dict[str, str]:
        """Provenance for the trace. ``mode`` is here because R2 is only a
        guarantee if the analysis side can assert on it (§7.10)."""
        return {
            "research_experiment_id": self.experiment_id,
            "research_condition": self.condition,
            "research_mode": self.mode,
            "research_manifest": self.manifest_path,
            "research_residue_digest": self.residue_digest,
        }


# --------------------------------------------------------------------------
# Validation (§3.2)
# --------------------------------------------------------------------------


def _base_locale_bundle(locale: str) -> Dict[str, Any]:
    from ciris_engine.logic.utils.localization import _get_language_data

    data: Dict[str, Any] = _get_language_data(locale)
    return data


def _bundle_has(bundle: Dict[str, Any], key: str) -> bool:
    from ciris_engine.logic.utils.localization import _resolve_key

    return _resolve_key(bundle, key) is not None


def _yaml_present_fields(path: Path, allowed: FrozenSet[str]) -> Set[str]:
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return set()
    return {k for k, v in data.items() if k in allowed and isinstance(v, str) and v.strip()}


def _schema_present_dma_prompt_keys() -> Set[str]:
    """Every ``<template>.<field>`` a base YAML defines — INCLUDING the ones the
    override layer cannot apply.

    Distinct from :func:`_required_dma_prompt_keys` on purpose. R2 totality asks
    "what must a strict manifest name?" and must exclude the #989-immune keys,
    because demanding a key the loader refuses makes strictness unsatisfiable.
    The coverage probe asks "what exists to be measured?" and must INCLUDE them
    — measuring which keys are dark is the whole point, and a probe that skipped
    them could never notice #989 being fixed.
    """
    present: Set[str] = set()
    for yml in sorted(_DMA_PROMPTS_DIR.glob("*.yml")):
        for field in _yaml_present_fields(yml, _DMA_PROMPT_TEXT_FIELDS):
            present.add(f"{yml.stem}.{field}")
    return present


def _required_dma_prompt_keys() -> Set[str]:
    """Every ``<template>.<field>`` a base YAML defines AND the layer can apply.

    R2 strict demands totality — name every reachable field — and #989 forbids
    naming the thirteen the override layer cannot reach. Read as "present in
    the schema", those two rules make a total manifest impossible to write.

    "Reachable" therefore means **reachable by the override layer**, which is
    the only reading under which R2's promise is true: a strict manifest that
    named all 36 would be asserting control over 13 fields it does not have.
    Excluding them keeps strictness honest instead of aspirational — and the
    exclusion is measured (``OVERRIDE_IMMUNE_DMA_PROMPT_KEYS``), so when #989
    option 1 lands and the keys become applicable, they re-enter the totality
    requirement automatically rather than by anyone remembering to.
    """
    required: Set[str] = set()
    for yml in sorted(_DMA_PROMPTS_DIR.glob("*.yml")):
        for field in _yaml_present_fields(yml, _DMA_PROMPT_TEXT_FIELDS):
            key = f"{yml.stem}.{field}"
            if key in OVERRIDE_IMMUNE_DMA_PROMPT_KEYS:
                continue
            required.add(key)
    return required


def _required_conscience_prompt_keys() -> Set[str]:
    required: Set[str] = set()
    for yml in sorted(_CONSCIENCE_PROMPTS_DIR.glob("*.yml")):
        for field in _yaml_present_fields(yml, _CONSCIENCE_PROMPT_TEXT_FIELDS):
            required.add(f"{yml.stem}.{field}")
    return required


def _valid_corpus_keys() -> FrozenSet[str]:
    return _ACCORD_CORPUS_KEYS | _polyglot_corpus_keys()


def _check_epistemic_schema_can_represent_absence() -> Optional[str]:
    """Condition (b) prerequisite (FSD §4.2(iii), §8.1).

    With the faculties disabled both epistemic aggregates are ``None``, and
    ``conscience_execution.py`` substitutes ``entropy=0.1, coherence=0.9`` into
    the same fields that carry *measured* values in condition (c). Downstream
    the two are indistinguishable, so a c−b analysis on epistemic scalars
    compares measurements against two constants and reports a large, clean,
    entirely artefactual effect.

    Returns a refusal reason if the schema still cannot represent "not
    measured", else None. This is a read-only check: fixing the defect is a
    truthfulness fix to the conscience layer, tracked separately.
    """
    try:
        from ciris_engine.schemas.conscience.core import EpistemicData
    except Exception as exc:  # pragma: no cover - defensive
        return f"could not import EpistemicData to verify condition-(b) safety: {exc}"

    for field_name in ("entropy_level", "coherence_level"):
        field = EpistemicData.model_fields.get(field_name)
        if field is None:
            return f"EpistemicData has no field {field_name!r}; condition-(b) safety cannot be verified"
        annotation = field.annotation
        allows_none = annotation is not None and type(None) in getattr(annotation, "__args__", ())
        if not allows_none:
            return (
                f"EpistemicData.{field_name} is non-nullable, so a trace cannot represent "
                f"'not measured'. With the epistemic faculties disabled, "
                f"conscience_execution.py substitutes constants (entropy=0.1, coherence=0.9) "
                f"into the same fields that carry measured values in condition (c) — the two "
                f"are indistinguishable downstream and a c-b comparison on epistemic scalars "
                f"would report a large, clean, entirely artefactual effect. "
                f"See FSD/RESEARCH_PROMPT_OVERRIDES.md §4.2(i)/(iii) and §8.1: the "
                f"truthfulness fixes must land before a condition-(b) campaign runs."
            )
    return None


def _validate_manifest(manifest: ResearchOverrideManifest) -> None:
    """R1–R5 plus the condition-(b) guard. One error, every problem."""
    problems: List[str] = []
    ov = manifest.overrides

    if manifest.manifest_version != "1":
        problems.append(f"manifest_version must be '1', got {manifest.manifest_version!r}")
    if manifest.mode not in ("strict", "additive"):
        problems.append(f"mode must be 'strict' or 'additive', got {manifest.mode!r}")
    if manifest.condition == "a":
        # R6 (FSD §6.2 / §10.4, finding M-8): no configuration of this runtime
        # yields a bare prior. Even fully blanked, a run still carries ASPDMA
        # scaffolding, JSON response coercion, the handler action enum and the
        # §6.1 residue. Labelling an h3ere run (a) produces a fourth thing that
        # is neither (a) nor (b) and invalidates every comparison against it —
        # condition (a) must come from a separate direct-to-provider harness.
        problems.append(
            "condition 'a' refused: an h3ere run cannot be a bare-prior baseline "
            "(FSD/RESEARCH_PROMPT_OVERRIDES.md §6.2). Use the direct-to-provider "
            "harness for condition (a); this runtime only accepts 'b' or 'c'."
        )
    elif manifest.condition not in ("b", "c"):
        problems.append(f"condition must be 'b' or 'c', got {manifest.condition!r}")

    # --- R1: every key must resolve -------------------------------------
    reachable_strings = scan_reachable_string_keys()
    bundle = _base_locale_bundle(manifest.base_locale)
    for key in sorted(ov.string):
        if key not in reachable_strings:
            problems.append(
                f"string override {key!r} does not reach any LLM prompt "
                f"(no get_string call site resolves it). Setting a dead key looks "
                f"identical to setting a live one and does nothing."
            )
        elif not _bundle_has(bundle, key):
            problems.append(
                f"string override {key!r} is reachable but absent from the "
                f"{manifest.base_locale} bundle — the un-overridden arm serves the raw "
                f"key string as prompt content. Fix the bundle before running."
            )

    valid_dma = _required_dma_prompt_keys()
    dma_templates = _yml_stems(_DMA_PROMPTS_DIR)
    for key in sorted(ov.dma_prompt):
        template, _, field = key.partition(".")
        if not field:
            problems.append(f"dma_prompt key {key!r} must be '<template>.<field>'")
        elif template not in dma_templates:
            problems.append(f"dma_prompt key {key!r}: no template {template!r} in {_DMA_PROMPTS_DIR.name}/")
        elif field not in _DMA_PROMPT_TEXT_FIELDS:
            problems.append(f"dma_prompt key {key!r}: {field!r} is not a PromptCollection text field")
        elif key not in valid_dma:
            problems.append(
                f"dma_prompt key {key!r}: the base template does not define {field!r}, "
                f"so the field never reaches a prompt and the override would be discarded."
            )

    valid_consc = _required_conscience_prompt_keys()
    consc_names = _yml_stems(_CONSCIENCE_PROMPTS_DIR)
    for key in sorted(ov.conscience_prompt):
        name, _, field = key.partition(".")
        if not field:
            problems.append(f"conscience_prompt key {key!r} must be '<conscience>.<field>'")
        elif name not in consc_names:
            problems.append(f"conscience_prompt key {key!r}: no conscience {name!r}")
        elif field not in _CONSCIENCE_PROMPT_TEXT_FIELDS:
            problems.append(f"conscience_prompt key {key!r}: {field!r} is not a ConsciencePrompts text field")
        elif key not in valid_consc:
            problems.append(f"conscience_prompt key {key!r}: the base file does not define {field!r}")

    corpus_keys = _valid_corpus_keys()
    for key in sorted(ov.corpus):
        if key not in corpus_keys:
            problems.append(f"corpus key {key!r} is not one of {sorted(corpus_keys)}")

    from ciris_engine.schemas.config.agent import AgentTemplate

    for key in sorted(ov.template):
        if key not in _TEMPLATE_TEXT_FIELDS:
            problems.append(f"template key {key!r} is not an overridable AgentTemplate prose field")
        elif key not in AgentTemplate.model_fields:
            problems.append(f"template key {key!r} no longer exists on AgentTemplate")

    # --- R5: no partial covenant ----------------------------------------
    # Checked before R2 so its (more specific) message wins on a strict run.
    named_accord = _ACCORD_CORPUS_KEYS & set(ov.corpus)
    if named_accord and named_accord != _ACCORD_CORPUS_KEYS:
        problems.append(
            f"R5 partial covenant: corpus names {sorted(named_accord)} but not "
            f"{sorted(_ACCORD_CORPUS_KEYS - named_accord)}. The two accord accessors feed "
            f"different DMAs — the localized one feeds ASPDMA/TSASPDMA/DSASPDMA, the DMAs "
            f"that actually pick the verb. Replacing one and not the other leaves the real "
            f"covenant where it counts most, and biases the result toward understating its "
            f"effect. All accord.* keys together, or none."
        )

    # --- R2: strict demands totality ------------------------------------
    if manifest.mode == "strict":
        for label, required, present in (
            ("string", set(reachable_strings), set(ov.string)),
            ("dma_prompt", valid_dma, set(ov.dma_prompt)),
            ("conscience_prompt", valid_consc, set(ov.conscience_prompt)),
            ("corpus", set(corpus_keys), set(ov.corpus)),
            ("template", set(_TEMPLATE_TEXT_FIELDS), set(ov.template)),
        ):
            missing = sorted(required - present)
            if missing:
                problems.append(
                    f"R2 strict mode: {label} namespace omits {len(missing)} reachable "
                    f"field(s): {missing}. Partial replacement leaves CIRIS text in a "
                    f"supposedly non-CIRIS arm. Name them, or use mode 'additive' "
                    f"(which is recorded in the trace)."
                )

    # --- residue digest (§6.1) ------------------------------------------
    actual_residue = compute_residue_digest()
    if manifest.residue_digest != actual_residue:
        problems.append(
            f"residue digest mismatch: manifest pins {manifest.residue_digest}, "
            f"source is {actual_residue}. The uncovered inline action doctrine "
            f"(ASPDMA user message, action-schema scaffolding, DSDMA user message, "
            f"identity blocks, formatters) changed. Every arm shares that text; a "
            f"mid-campaign change to it is a confound. Re-pin deliberately, do not paper over."
        )

    # --- condition (b) prerequisite -------------------------------------
    if manifest.condition == "b":
        reason = _check_epistemic_schema_can_represent_absence()
        if reason:
            problems.append(f"condition 'b' refused: {reason}")

    if problems:
        raise ResearchOverrideError(
            "research prompt override manifest is not applicable — "
            f"{len(problems)} problem(s) found at load, before the first LLM call:\n"
            + "\n".join(f"  [{i}] {p}" for i, p in enumerate(problems, 1))
        )


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------

_active: Optional[ResearchOverrideManifest] = None
_loaded = False


def reset_research_overrides() -> None:
    """Drop cached gate state. Tests only."""
    global _active, _loaded
    _active = None
    _loaded = False
    scan_reachable_string_keys.cache_clear()
    _polyglot_corpus_keys.cache_clear()


def get_active_overrides() -> Optional[ResearchOverrideManifest]:
    """The active manifest, or None.

    None means the path is *unreachable*, not merely unused: with the manifest
    env var absent no registry is constructed and no override state exists in
    the process.
    """
    global _active, _loaded
    if _loaded:
        return _active

    manifest_path = os.getenv(ENV_MANIFEST, "").strip()
    if not manifest_path:
        _active = None
        _loaded = True
        return None

    if not env_is_true(ENV_ANCHOR):
        raise ResearchOverrideRefused(_refusal_text(manifest_path))

    path = Path(manifest_path)
    if not path.is_file():
        raise ResearchOverrideError(f"{ENV_MANIFEST} points at {manifest_path}, which is not a readable file")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ResearchOverrideError(f"{manifest_path} is not valid JSON: {exc}") from exc

    manifest = ResearchOverrideManifest(**raw, manifest_path=str(path))
    _validate_manifest(manifest)

    _active = manifest
    _loaded = True
    logger.warning(
        "[RESEARCH-OVERRIDES] ACTIVE — experiment=%s condition=%s mode=%s manifest=%s. "
        "%s. This process is NOT running stock CIRIS prompts.",
        manifest.experiment_id,
        manifest.condition,
        manifest.mode,
        path,
        describe_coverage(manifest),
    )
    return manifest


# --------------------------------------------------------------------------
# Interception accessors — called from the real loaders
# --------------------------------------------------------------------------


def override_string(key: str, lang_code: Optional[str] = None) -> Optional[str]:
    """Resolve a ``string`` override for ``key`` in ``lang_code``.

    A scalar value applies to every locale. A mapping is resolved against
    ``lang_code``; a locale the mapping does not cover REFUSES rather than
    falling back to English, because silently serving English into a non-English
    prompt is exactly the laundering R4 forbids — and it is what this facility
    did for every localized key before the value type became a union.

    ``lang_code=None`` is accepted only for scalar values, so callers that
    genuinely have no locale in hand still work.
    """
    m = get_active_overrides()
    if m is None:
        return None
    value = m.overrides.string.get(key)
    if value is None or isinstance(value, str):
        return value

    if lang_code is None:
        raise RuntimeError(
            f"research overrides active: key {key!r} is overridden per-locale, but the "
            f"caller resolved it without a locale. A per-locale override cannot be "
            f"applied to an unknown locale — pass lang_code, or make the override a "
            f"single string if one text really is intended for every locale."
        )
    try:
        return value[lang_code]
    except KeyError:
        raise RuntimeError(
            f"research overrides active: key {key!r} is overridden per-locale but carries "
            f"no entry for locale {lang_code!r} (has: {', '.join(sorted(value)) or 'none'}). "
            f"Falling back to English would put English text in a {lang_code!r} prompt — the "
            f"laundering R4 forbids. Add {lang_code!r} to the mapping, or use a single "
            f"string if that text is intended for every locale."
        ) from None


def override_dma_prompt(template_name: str, field: str) -> Optional[str]:
    m = get_active_overrides()
    return m.overrides.dma_prompt.get(f"{template_name}.{field}") if m else None


def override_conscience_prompt(conscience_type: str, field: str) -> Optional[str]:
    m = get_active_overrides()
    return m.overrides.conscience_prompt.get(f"{conscience_type}.{field}") if m else None


def override_corpus(key: str) -> Optional[str]:
    m = get_active_overrides()
    return m.overrides.corpus.get(key) if m else None


def override_template_field(field: str) -> Optional[str]:
    m = get_active_overrides()
    return m.overrides.template.get(field) if m else None


def overrides_are_active() -> bool:
    return get_active_overrides() is not None


# --------------------------------------------------------------------------
# Precedence (§3.3) — AgentTemplate already carries UNGATED prompt overrides
# --------------------------------------------------------------------------

#: Which base DMA template each ``AgentTemplate.*_overrides`` block shadows, and
#: which PromptCollection fields it beats. ``pdma.py:_build_system_message_text``
#: returns the template's ``system_prompt`` and never calls the prompt loader at
#: all, so a leftover template override silently beats a manifest entry.
_TEMPLATE_OVERRIDE_SHADOWS: Dict[str, Tuple[str, Dict[str, Tuple[str, ...]]]] = {
    "pdma_overrides": (
        "pdma_ethical",
        {
            "system_prompt": (
                "system_guidance_header",
                "domain_principles",
                "evaluation_steps",
                "evaluation_criteria",
                "response_format",
                "response_guidance",
            ),
            "user_prompt_template": ("context_integration",),
        },
    ),
    "csdma_overrides": (
        "csdma_common_sense",
        {
            "system_prompt": (
                "system_guidance_header",
                "domain_principles",
                "evaluation_steps",
                "evaluation_criteria",
                "response_format",
                "response_guidance",
            ),
            "user_prompt_template": ("context_integration",),
        },
    ),
    "action_selection_pdma_overrides": (
        "action_selection_pdma",
        {
            "system_prompt": (
                "system_guidance_header",
                "domain_principles",
                "evaluation_steps",
                "evaluation_criteria",
                "response_format",
                "response_guidance",
            ),
            "user_prompt_template": ("context_integration",),
        },
    ),
}


def assert_no_template_conflict(template: Any) -> None:
    """Refuse if an AgentTemplate override and the manifest target the same field.

    Do not silently pick a winner. A field left set from an earlier run would
    otherwise beat the manifest with no signal at all.
    """
    manifest = get_active_overrides()
    if manifest is None:
        return

    conflicts: List[str] = []
    for attr, (base_template, field_map) in _TEMPLATE_OVERRIDE_SHADOWS.items():
        block = getattr(template, attr, None)
        if block is None:
            continue
        for block_field, shadowed in field_map.items():
            if not getattr(block, block_field, None):
                continue
            for shadowed_field in shadowed:
                key = f"{base_template}.{shadowed_field}"
                if key in manifest.overrides.dma_prompt:
                    conflicts.append(
                        f"AgentTemplate.{attr}.{block_field} (ungated, consulted BEFORE the "
                        f"prompt loader) shadows manifest dma_prompt key {key!r}"
                    )

    # The `template` namespace is NOT checked here: those fields have exactly one
    # writer (the loaded YAML) and the manifest overlays them in
    # apply_template_overrides. There is no second ungated path to conflict with.
    if conflicts:
        raise ResearchOverrideError(
            "research override precedence conflict — refusing rather than picking a winner:\n"
            + "\n".join(f"  - {c}" for c in conflicts)
            + "\n Clear the AgentTemplate *_overrides block, or drop the manifest key."
        )


def apply_template_overrides(template: Any) -> Any:
    """Overlay the ``template`` namespace onto a loaded AgentTemplate."""
    manifest = get_active_overrides()
    if manifest is None:
        return template
    assert_no_template_conflict(template)
    for field, value in manifest.overrides.template.items():
        setattr(template, field, value)
    if manifest.overrides.template:
        logger.warning(
            "[RESEARCH-OVERRIDES] AgentTemplate prose replaced: %s",
            sorted(manifest.overrides.template),
        )
    return template


# --------------------------------------------------------------------------
# Coverage reporting — the honest part
# --------------------------------------------------------------------------


def describe_coverage(manifest: Optional[ResearchOverrideManifest] = None) -> str:
    """One line naming what is covered and what is provably not.

    Emitted at load so the uncovered surface appears in the run's own logs, not
    only in a design document nobody re-reads at analysis time.
    """
    m = manifest or get_active_overrides()
    if m is None:
        return "research overrides inactive"
    ov = m.overrides
    counts = (
        f"covered: string={len(ov.string)}/{len(scan_reachable_string_keys())} "
        f"dma_prompt={len(ov.dma_prompt)}/{len(_required_dma_prompt_keys())} "
        f"conscience_prompt={len(ov.conscience_prompt)}/{len(_required_conscience_prompt_keys())} "
        f"corpus={len(ov.corpus)}/{len(_valid_corpus_keys())} "
        f"template={len(ov.template)}/{len(_TEMPLATE_TEXT_FIELDS)}"
    )
    return (
        f"{counts}. NOT COVERED (inline English, present in EVERY arm, pinned at "
        f"{m.residue_digest}): the inline helpers interpolated into the ASPDMA "
        f"user message, the non-DEFER action schema/guidance scaffolding, the "
        f"six formatters, and the conscience override reasons. (#974 routed the "
        f"DEFER policy — step 0 — the ASPDMA user-message template — step 1 — "
        f"the DSDMA user message — step 2 — and the CORE IDENTITY blocks — "
        f"step 3 — out of this residue; all four ARE covered.) Any paper using "
        f"this facility must report that the non-CIRIS arm was reasoning under "
        f"CIRIS's action doctrine, in English"
    )


def strict_manifest_skeleton(experiment_id: str = "CHANGE-ME", condition: str = "c") -> Dict[str, Any]:
    """A totality-complete strict manifest with every value left as a marker.

    A strict manifest names ~97 keys across five namespaces. Hand-writing one
    invites exactly the omission R2 exists to catch, and R2's error message is a
    worse authoring tool than a skeleton. Every value is a visible
    ``REPLACE::<key>`` marker so an unedited entry shows up in the prompt rather
    than passing for content.
    """
    return {
        "manifest_version": "1",
        "experiment_id": experiment_id,
        "condition": condition,
        "base_locale": "en",
        "mode": "strict",
        "residue_digest": compute_residue_digest(),
        "overrides": {
            "string": {k: f"REPLACE::{k}" for k in sorted(scan_reachable_string_keys())},
            "dma_prompt": {k: f"REPLACE::{k}" for k in sorted(_required_dma_prompt_keys())},
            "conscience_prompt": {k: f"REPLACE::{k}" for k in sorted(_required_conscience_prompt_keys())},
            "corpus": {k: f"REPLACE::{k}" for k in sorted(_valid_corpus_keys())},
            "template": {k: f"REPLACE::{k}" for k in sorted(_TEMPLATE_TEXT_FIELDS)},
        },
        "research_hashes": {},
    }


def baseline_manifest(locales: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """A strict manifest pre-filled with the CURRENT live values.

    ``locales`` selects which locales the localized ``string`` keys are captured
    for; it defaults to every locale in the bundle, so a locale added later is
    picked up with no change here. Narrow it when an experiment runs a known
    subset — a full capture of every localized key across every locale is large,
    and a manifest carrying locales the run never composes is noise.

    A ``string`` key is emitted as a ``{locale: text}`` mapping when its text
    actually differs across the captured locales, and as a plain string when it
    does not. That is what makes the round-trip guarantee below true: capturing
    a localized key at ``en`` alone and pinning that one value used to serve
    English guidance, English prohibitions and English retry scaffolding in all
    29 locales, while reporting a clean run.

    `strict_manifest_skeleton()` emits `REPLACE::<key>` placeholders for all 97
    keys. That is right for a wholesale variant — a non-CIRIS arm is a complete
    replacement — but it is a footgun for a SURGICAL change: submitting it as-is
    replaces the entire covenant with placeholder text, when the operator only
    meant to alter one prompt.

    Strict mode is total-or-refuse on purpose: a run that applies half its
    overrides and reports clean is exactly the failure this facility exists to
    prevent. So a targeted experiment still has to supply all 97 keys — it just
    needs the other 96 to be what they already are.

    Emit this, change the one line you mean to change, and every other key
    round-trips to its current value.
    """
    from ciris_engine.logic.conscience.prompt_loader import ConsciencePromptLoader
    from ciris_engine.logic.dma.prompt_loader import DMAPromptLoader
    from ciris_engine.logic.utils.localization import get_available_languages, get_string

    skeleton = strict_manifest_skeleton()
    out: Dict[str, Any] = dict(skeleton)
    out["experiment_id"] = "CHANGE-ME"
    filled: Dict[str, Dict[str, Any]] = {ns: {} for ns in skeleton["overrides"]}

    captured = list(locales) if locales else get_available_languages()
    if not captured:
        raise RuntimeError(
            "no locales available to capture — refusing to emit a baseline that would "
            "silently cover no locale at all"
        )
    base = str(out.get("base_locale") or "en")
    if base not in captured:
        # The base locale anchors the scalar case; without it a key that does not
        # vary would still be captured from an arbitrary locale.
        captured = [base, *captured]

    for key in skeleton["overrides"].get("string", {}):
        try:
            per_locale = {lang: get_string(lang, key) for lang in captured}
        except Exception:  # noqa: BLE001 — an unresolvable key keeps its marker
            filled["string"][key] = skeleton["overrides"]["string"][key]
            continue
        # Collapse to a scalar only when the key genuinely does not vary, so the
        # manifest stays small without ever standing one locale in for another.
        distinct = set(per_locale.values())
        filled["string"][key] = per_locale[base] if len(distinct) == 1 else per_locale

    cl = ConsciencePromptLoader()
    for key, marker in skeleton["overrides"].get("conscience_prompt", {}).items():
        name, _, field = key.rpartition(".")
        try:
            filled["conscience_prompt"][key] = getattr(cl.load_prompts(name), field)
        except Exception:  # noqa: BLE001
            filled["conscience_prompt"][key] = marker

    dl = DMAPromptLoader()
    for key, marker in skeleton["overrides"].get("dma_prompt", {}).items():
        name, _, field = key.rpartition(".")
        try:
            tmpl = dl.load_prompt_template(name)
            val = tmpl.get(field) if isinstance(tmpl, dict) else getattr(tmpl, field, None)
            filled["dma_prompt"][key] = str(val) if val is not None else marker
        except Exception:  # noqa: BLE001
            filled["dma_prompt"][key] = marker

    # corpus / template values are large or structural; leave their markers so
    # an operator has to opt into replacing them deliberately.
    for ns in ("corpus", "template"):
        filled[ns] = dict(skeleton["overrides"].get(ns, {}))

    out["overrides"] = filled
    # The note goes to the CALLER, never into the manifest: `extra="forbid"`
    # rejects unknown keys, so emitting `_baseline_note` inline made
    # `baseline > m.json && validate m.json` fail on a key this function itself
    # added. See baseline_unresolved().
    return out


def baseline_unresolved(manifest: Dict[str, Any]) -> List[str]:
    """Keys in a baseline manifest still carrying their ``REPLACE::`` marker.

    These are the value-bearing keys `baseline` deliberately refuses to pre-fill:
    leaving them unset makes an unfilled arm fail loudly instead of silently
    re-running the CIRIS values under an experimental label.
    """
    return sorted(
        f"{ns}.{key}"
        for ns, block in manifest.get("overrides", {}).items()
        for key, value in block.items()
        if isinstance(value, str) and value.startswith("REPLACE::")
    )


def validate_manifest_file(path: str) -> Tuple[bool, str]:
    """Validate a manifest EXACTLY as the agent will, and return (ok, report).

    Why this exists as a callable rather than only as agent-startup behaviour:
    the agent's refusal is correct and must stay, but it arrives ~10 minutes
    into a run, after dependency install, preflight and boot. The same verdict
    is available in seconds from the manifest and the source tree alone, so
    every caller that is about to spend those ten minutes should ask first
    (#962).

    This is a MIRROR of the startup gate, never a replacement and never a
    softening: it calls the same loader, so a manifest that passes here passes
    there for the same reasons, and one that fails here would have failed there.
    Nothing about a failure is downgraded to a warning — the caller is expected
    to stop.

    The report names the remedy, which the raw exception does not. Two failures
    are unfixable from the error text alone:

    * ``residue_digest`` — the researcher cannot derive the value; it is a hash
      over this tree's uncovered inline surface. So the report prints the
      RUNNING digest, as a pasteable JSON line, for this exact commit.
    * R2 totality — a strict manifest names ~97 keys, and "omits 44 fields"
      is a worse authoring tool than a generated skeleton. So the report points
      at ``skeleton`` / ``baseline``.
    """
    manifest_path = Path(path)
    if not manifest_path.is_file():
        return False, f"{path} is not a readable file"

    # The anchor is a RUNTIME gate on whether this process may swap the
    # covenant out. Validating a file swaps nothing, so the validator sets both
    # keys on itself: refusing to check a manifest because the checker is not
    # authorised to apply one would only teach researchers to skip the check.
    #
    # Both keys and the registry are restored on the way out. This runs in a
    # subprocess in CI, where that would not matter — but it is also importable,
    # and an in-process caller left holding an active manifest would have every
    # later get_string() raise on a key the manifest does not name. A checker
    # that changes the thing it checked is its own bug class.
    saved = {k: os.environ.get(k) for k in (ENV_MANIFEST, ENV_ANCHOR)}
    os.environ[ENV_MANIFEST] = str(manifest_path)
    os.environ[ENV_ANCHOR] = "true"
    reset_research_overrides()
    try:
        manifest = get_active_overrides()
    except Exception as exc:  # noqa: BLE001 - pydantic and our own errors both land here
        detail = str(exc)
        lines = [f"manifest REJECTED: {manifest_path}", "", detail, ""]
        if "residue_digest" in detail:
            lines += [
                "residue_digest pins the inline English action doctrine that overrides do",
                "NOT cover — it is present in every arm, so a mid-campaign change to it is",
                "a confound. It cannot be guessed; it is computed from THIS source tree.",
                "The value for this exact commit is:",
                "",
                f'    "residue_digest": "{compute_residue_digest()}",',
                "",
                "Paste that into the manifest. If it disagrees with a digest you pinned",
                "earlier, the doctrine moved: re-pin deliberately, do not paper over.",
            ]
        if "R2 strict mode" in detail:
            lines += [
                "A strict manifest must name every reachable key — partial replacement",
                "leaves CIRIS text in a supposedly non-CIRIS arm. Do not hand-write it:",
                "",
                "    python3 -m ciris_engine.logic.utils.research_overrides skeleton   # REPLACE:: markers",
                "    python3 -m ciris_engine.logic.utils.research_overrides baseline   # current live values",
                "",
                "Use 'additive' mode for a pilot — it is recorded in the trace, so an",
                "additive run cannot later be read as a total replacement.",
            ]
        return False, "\n".join(lines)
    finally:
        for key, previous in saved.items():
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous
        reset_research_overrides()

    if manifest is None:  # pragma: no cover - unreachable: env var is set above
        return False, f"{manifest_path} produced no manifest"
    return True, (
        f"manifest OK: {manifest_path}\n"
        f"  experiment: {manifest.experiment_id}\n"
        f"  condition : {manifest.condition}\n"
        f"  mode      : {manifest.mode}\n"
        f"  residue   : {manifest.residue_digest}\n"
        f"  {describe_coverage(manifest)}"
    )


if __name__ == "__main__":  # pragma: no cover - operator convenience
    import sys

    command = sys.argv[1] if len(sys.argv) > 1 else "digest"
    if command == "digest":
        print(compute_residue_digest())
    elif command == "validate":
        if len(sys.argv) < 3:
            print("usage: ... research_overrides validate <manifest.json>", file=sys.stderr)
            sys.exit(2)
        ok, report = validate_manifest_file(sys.argv[2])
        print(report, file=sys.stdout if ok else sys.stderr)
        sys.exit(0 if ok else 1)
    elif command == "skeleton":
        print(json.dumps(strict_manifest_skeleton(), indent=2, ensure_ascii=False))
    elif command == "baseline":
        # Optional locale narrowing: `baseline en,es,am`. Default captures every
        # locale in the bundle, so a locale added later needs no change here.
        _locales = [s for s in sys.argv[2].split(",") if s.strip()] if len(sys.argv) > 2 else None
        _manifest = baseline_manifest(_locales)
        print(json.dumps(_manifest, indent=2, ensure_ascii=False))
        _unresolved = baseline_unresolved(_manifest)
        if _unresolved:
            print(
                f"{len(_unresolved)} key(s) still carry REPLACE:: markers and MUST be filled or "
                f"the run is not measuring what it claims. Change only the keys your experiment "
                f"alters.\n  " + "\n  ".join(_unresolved),
                file=sys.stderr,
            )
    elif command == "keyspace":
        for namespace, keys in (
            ("string", scan_reachable_string_keys()),
            ("dma_prompt", _required_dma_prompt_keys()),
            ("conscience_prompt", _required_conscience_prompt_keys()),
            ("corpus", _valid_corpus_keys()),
            ("template", _TEMPLATE_TEXT_FIELDS),
        ):
            for key in sorted(keys):
                print(f"{namespace}\t{key}")
    else:
        print(
            f"usage: python3 -m {__name__.rsplit('.', 1)[0]}.research_overrides "
            f"[digest|skeleton|baseline|keyspace|validate <manifest.json>]"
        )
        sys.exit(2)
