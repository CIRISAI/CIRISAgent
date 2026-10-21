"""Regime manifest v2 loader + every §10.4 refusal (#976).

FSD/RESEARCH_PROMPT_OVERRIDES.md §10.3 declares the manifest; §10.4 lists the
eleven things that must refuse. This module is where a refusal actually costs
something: it is called BEFORE a campaign starts, from the source tree, with no
LLM call.

Design rule inherited from ``research_overrides._validate_manifest``: **one
error, every problem**. A regime with four defects reports four, so the author
fixes them in one pass instead of four.

Second rule, inherited from ``compose_dump --verify-sig`` (§13): **an
unperformable check refuses.** Where a check needs something this tree cannot
provide — the kill-instrument tables, the endpoint the decoding pin is a
function of — the answer is a refusal naming what was missing, never a pass.

What this module deliberately does NOT do: annotate. The class-set annotation
pass (§10.2.3) is human work with two independent annotators and a κ gate; the
instrument for it is ``tools/research/annotate_classes.py`` and the gate is
``class_set_is_citable()``. ``FIELD_CLASS_ANNOTATIONS`` here holds only the
handful of entries that are *inherited* from the #973 block table, each citing
its source — so strict mode refuses today, loudly, with the unannotated field
list, which is the honest state of the annotation.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Dict, FrozenSet, List, Optional, Sequence, Set, Tuple

from ciris_engine.schemas.dma.compose import CLASS_DEFAULT_DISPOSITION, BlockClass, BlockDisposition, RegimeBlockEntry
from ciris_engine.schemas.research.regime import (
    KNOWN_CLASS_SET_VERSIONS,
    REGIME_SCHEMA_V2,
    ExperimentalRegimeV2,
    VarianceSource,
)

# --------------------------------------------------------------------------
# Refusal
# --------------------------------------------------------------------------


class RegimeRefused(RuntimeError):
    """A regime manifest that must not run.

    Deliberately NOT a subclass of ``ResearchOverrideError``: that exception
    means "this override manifest is not applicable"; this one means "this
    experimental design is not runnable". Callers that catch one should not
    silently swallow the other.
    """


# --------------------------------------------------------------------------
# The DEFER policy in the residue inventory [M-4]
# --------------------------------------------------------------------------

#: A residue site "carries the DEFER policy" iff its pinned SOURCE still
#: contains the doctrine's own text. Symbol membership would be the wrong test:
#: ``_generate_schema_for_action`` and ``get_action_guidance`` are BOTH still in
#: ``RESIDUE_SITES`` after #974 — for the other nine verbs' schema text — while
#: the DEFER doctrine itself moved to the YAML. A symbol check would refuse
#: every action-tier regime forever; a content check answers the question the
#: FSD is actually asking.
_DEFER_FRAGMENT_MIN_CHARS = 40


def routed_defer_policy_text() -> str:
    """The DEFER policy as the runtime serves it (the #974 step-0 routed key)."""
    from ciris_engine.logic.dma.prompt_loader import DMAPromptLoader

    text = DMAPromptLoader().load_prompt_template("action_selection_pdma").action_params_defer_guidance
    if not isinstance(text, str) or not text.strip():
        raise RegimeRefused(
            "action_selection_pdma.yml no longer defines action_params_defer_guidance — the DEFER "
            "policy's single routed source is gone, so whether it is in the residue is unanswerable "
            "and every action-tier claim is unverifiable (§11 step 0)."
        )
    return text


def _defer_doctrine_fragments() -> Tuple[str, ...]:
    """Normalized lines of the doctrine long enough to be evidence, not labels."""
    from ciris_engine.logic.utils.compose_dump import _normalize_ws

    fragments = []
    for line in routed_defer_policy_text().splitlines():
        normalized = _normalize_ws(line)
        if len(normalized) >= _DEFER_FRAGMENT_MIN_CHARS:
            fragments.append(normalized)
    return tuple(fragments)


def defer_policy_residue_sites(
    sites: Optional[Sequence[Tuple[str, str]]] = None,
    extract: Optional[Callable[[Path, str], str]] = None,
) -> List[str]:
    """Residue-inventory entries whose pinned source still carries the DEFER doctrine.

    Empty on this tree — #974 step 0 routed the policy out — which is what makes
    an ``action_tier`` DV declarable at all. ``sites``/``extract`` are injection
    points so the detector can be exercised against an inventory that DOES carry
    it; the default path reads the real inventory and the real sources.
    """
    from ciris_engine.logic.utils.compose_dump import _normalize_ws
    from ciris_engine.logic.utils.research_overrides import _ENGINE_ROOT, RESIDUE_SITES, _extract_symbol_source

    inventory = tuple(sites) if sites is not None else RESIDUE_SITES
    reader = extract if extract is not None else _extract_symbol_source
    fragments = _defer_doctrine_fragments()
    if not fragments:  # pragma: no cover - a doctrine of only short lines
        raise RegimeRefused(
            "the routed DEFER policy has no line long enough to match structurally; the residue "
            "check for it cannot be performed, so it refuses (§13: an unperformable check refuses)"
        )

    hits: List[str] = []
    for rel, qualname in inventory:
        source = _normalize_ws(reader(_ENGINE_ROOT / rel, qualname))
        if any(fragment in source for fragment in fragments):
            hits.append(f"{rel}::{qualname}")
    return hits


# --------------------------------------------------------------------------
# Transmitted decoding keys — set equality, both directions [M-6, M-N3]
# --------------------------------------------------------------------------

#: Top-level parameters the OpenAI-compatible call path always sends
#: (``service.py``: ``temp_param`` + ``token_param``, unconditional off the
#: Gemini branch). ``seed`` is conditional and handled separately.
_ALWAYS_TRANSMITTED: FrozenSet[str] = frozenset({"temperature", "max_tokens"})


def seed_is_configured() -> bool:
    """``seed`` is transmitted iff ``CIRIS_LLM_SEED`` is set (#975, 2.9.9)."""
    return bool(os.environ.get("CIRIS_LLM_SEED", "").strip())


def transmitted_decoding_keys(base_url: str, model: str) -> FrozenSet[str]:
    """Exactly what the runtime puts on the wire at this endpoint.

    Derived by CALLING the dispatch the service calls, not by restating it:
    ``extra_body`` is a function of ``base_url`` (and, on OpenAI, of the model),
    so a re-implementation here would be a second source of truth that drifts.
    ``extra_body`` sub-keys are reported dotted (``extra_body.reasoning``).
    """
    from ciris_engine.logic.services.runtime.llm_service.service import (
        OpenAICompatibleClient,
        _build_openrouter_provider_config,
    )

    keys: Set[str] = set(_ALWAYS_TRANSMITTED)
    if seed_is_configured():
        keys.add("seed")

    extra_body = OpenAICompatibleClient._build_reasoning_off_extras(base_url, model)
    for name in extra_body:
        keys.add(f"extra_body.{name}")

    lowered = (base_url or "").lower()
    if "ciris.ai" in lowered or "ciris-services" in lowered:
        keys.add("extra_body.metadata")
    elif "openrouter.ai" in lowered:
        provider_config = _build_openrouter_provider_config()
        if provider_config.order or provider_config.ignore:
            keys.add("extra_body.provider")
    return frozenset(keys)


def pinned_decoding_keys(regime: ExperimentalRegimeV2) -> FrozenSet[str]:
    """The manifest's own pin set, in the same vocabulary."""
    decoding = regime.holds.decoding
    keys: Set[str] = set()
    for name in ("temperature", "top_p", "max_tokens", "seed"):
        if getattr(decoding, name) is not None:
            keys.add(name)
    for name in decoding.extra_body or {}:
        keys.add(f"extra_body.{name}")
    return frozenset(keys)


# --------------------------------------------------------------------------
# Kill instruments — the per-locale U-row tables [T-4]
# --------------------------------------------------------------------------


def _u_code(row: str) -> str:
    """``U10_slur_echo`` -> ``U10``. A manifest may name either form."""
    return row.split("_", 1)[0].upper()


def kill_instrument_inventory() -> Dict[str, FrozenSet[str]]:
    """locale -> the U-rows that have a MACHINE instrument in that locale.

    The instruments are the per-language structural tables in
    ``tools/safety/mh_battery_eval.py`` (substring rows) plus the script-range
    table (the U9 locale check). Rubric ``.md`` files are human grading
    criteria, not instruments — a kill scored by a human reading prose is not
    an equivalence test with a declared bound, and §10.2 prices kills as
    equivalence claims.

    Needs the repo checkout, like ``compose_dump``. If the tables cannot be
    imported the check is unperformable and refuses.
    """
    try:
        from tools.safety.mh_battery_eval import LANG_SCRIPT_RANGES, RUBRIC_HARD_FAIL_SUBSTRINGS
    except Exception as exc:  # noqa: BLE001 - any import failure is unperformable
        raise RegimeRefused(
            f"the kill-instrument tables (tools/safety/mh_battery_eval.py) could not be imported: "
            f"{exc}. Every kill is an equivalence claim and needs a named instrument that exists in "
            f"every declared locale (§10.2 [T-4]); without the tables that cannot be checked, and an "
            f"unperformable check refuses rather than passes."
        ) from exc

    inventory: Dict[str, Set[str]] = {}
    for locale, rows in RUBRIC_HARD_FAIL_SUBSTRINGS.items():
        bucket = inventory.setdefault(locale, set())
        for row in rows:
            bucket.add(row)
            bucket.add(_u_code(row))
    for locale in LANG_SCRIPT_RANGES:
        # U9 = "responded in the wrong language", scored by script presence.
        inventory.setdefault(locale, set()).update({"U9", "U9_script_presence"})
    return {locale: frozenset(rows) for locale, rows in inventory.items()}


# --------------------------------------------------------------------------
# R2 reconciliation (§14 step 7) — class annotation totality
# --------------------------------------------------------------------------

#: Field-level class annotation. INTENTIONALLY PARTIAL: every entry below is
#: INHERITED from a #973 ``BLOCK_ANNOTATIONS`` entry whose block has exactly one
#: routed source, so it is a re-statement of an existing annotation rather than
#: a new one. The rest of the reachable field space is the §10.2.3 two-annotator
#: pass (#976 step 8) and is deliberately absent — strict mode refuses and names
#: what is missing, which is the truth about the annotation's completeness.
#:
#: A field annotated ``MIXED`` counts as UNRESOLVED for R2: the totality rule is
#: "resolves to exactly ONE declared class", and mixed is not one class.
FIELD_CLASS_ANNOTATIONS: Dict[str, BlockClass] = {
    # BLOCK_ANNOTATIONS['accord'] -> axiotic. ALL THREE accord accessors,
    # because R5 forbids naming one without the others.
    "accord.polyglot_compressed": BlockClass.AXIOTIC,
    "accord.polyglot_full": BlockClass.AXIOTIC,
    "accord.localized": BlockClass.AXIOTIC,
    # BLOCK_ANNOTATIONS['language_guidance'] -> MIXED (pragmatic + deontic +
    # axiotic + empirical in one scalar [T-1]). #997 ran §11 step 6 for the five
    # locales whose prose partitions on the English boundaries; the parent key
    # is what the other 24 still resolve through, so it stays unresolved.
    "prompts.language_guidance": BlockClass.MIXED,
    # The 29 #997 parts, each INHERITED from its BLOCK_ANNOTATIONS entry — a
    # re-statement of an existing annotation, never a new one. Five stay MIXED:
    # the FSD-declared irreducible worked exemplars (§10.2.1 [T-5a]), where
    # verdict, register and schema live in the same tokens.
    "prompts.language_guidance.01_preamble": BlockClass.PROCEDURAL,
    "prompts.language_guidance.02_first_sentence_tone_lock": BlockClass.PRAGMATIC,
    "prompts.language_guidance.03_never_deny_ai": BlockClass.DEONTIC,
    "prompts.language_guidance.04_formal_register": BlockClass.PRAGMATIC,
    "prompts.language_guidance.05_no_wellness_confirmation": BlockClass.DEONTIC,
    "prompts.language_guidance.06_warmth_and_concision": BlockClass.PRAGMATIC,
    "prompts.language_guidance.07_canonical_disclaimer": BlockClass.DEONTIC,
    "prompts.language_guidance.08_help_pathway_intro": BlockClass.EMPIRICAL,
    "prompts.language_guidance.09_trusted_person_first_step": BlockClass.AXIOTIC,
    "prompts.language_guidance.10_help_pathway_steps": BlockClass.EMPIRICAL,
    "prompts.language_guidance.11_routing_doctrine": BlockClass.AXIOTIC,
    "prompts.language_guidance.12_undisclosed_symptom_attribution": BlockClass.DEONTIC,
    "prompts.language_guidance.13_exemplar_speak_response": BlockClass.MIXED,
    "prompts.language_guidance.14_exemplar_register_pressure": BlockClass.MIXED,
    "prompts.language_guidance.15_register_pressure_pattern": BlockClass.PRAGMATIC,
    "prompts.language_guidance.16_exemplar_false_reassurance": BlockClass.MIXED,
    "prompts.language_guidance.17_false_reassurance_pattern": BlockClass.DEONTIC,
    "prompts.language_guidance.18_ratification_scope": BlockClass.EPISTEMIC,
    "prompts.language_guidance.19_agent_role": BlockClass.ONTOLOGICAL,
    "prompts.language_guidance.20_four_moves": BlockClass.PROCEDURAL,
    "prompts.language_guidance.21_negative_is_also_a_verdict": BlockClass.EPISTEMIC,
    "prompts.language_guidance.22_ratification_register": BlockClass.PRAGMATIC,
    "prompts.language_guidance.23_ratification_templates": BlockClass.MIXED,
    "prompts.language_guidance.24_ratification_pattern": BlockClass.PROCEDURAL,
    "prompts.language_guidance.25_exemplar_cross_cluster": BlockClass.MIXED,
    "prompts.language_guidance.26_cross_cluster_pattern": BlockClass.DEONTIC,
    "prompts.language_guidance.26b_user_symptom_direction": BlockClass.DEONTIC,
    "prompts.language_guidance.27_attractor_universality": BlockClass.NOMOLOGICAL,
    "prompts.language_guidance.28_brevity_restatement": BlockClass.PRAGMATIC,
    "prompts.language_guidance.29_no_medical_or_legal_advice": BlockClass.DEONTIC,
    # #974 step 3: the three CORE IDENTITY copies collapsed to one key.
    "prompts.identity_block": BlockClass.ONTOLOGICAL,
    # #974 step 0: the DEFER policy — axiotic content in a structural site [M-4].
    "action_selection_pdma.action_params_defer_guidance": BlockClass.AXIOTIC,
}


def reachable_field_inventory() -> Dict[str, FrozenSet[str]]:
    """Every field a manifest can reach, per namespace — the R2 denominator."""
    from ciris_engine.logic.utils.research_overrides import (
        _TEMPLATE_TEXT_FIELDS,
        _required_conscience_prompt_keys,
        _required_dma_prompt_keys,
        _valid_corpus_keys,
        scan_reachable_string_keys,
    )

    return {
        "string": frozenset(scan_reachable_string_keys()),
        "dma_prompt": frozenset(_required_dma_prompt_keys()),
        "conscience_prompt": frozenset(_required_conscience_prompt_keys()),
        "corpus": frozenset(_valid_corpus_keys()),
        "template": frozenset(_TEMPLATE_TEXT_FIELDS),
    }


def r2_totality_problems() -> List[str]:
    """R2 restated on classes (§14 step 7).

    v1's R2 was "a strict manifest names every reachable field". Under a regime
    the manifest is synthesized per arm from the CLASS declaration, so naming
    every field is the loader's job and the rule that has to hold instead is
    *every reachable field resolves to exactly one declared class*. Returns one
    problem per namespace that is not totally annotated.
    """
    problems: List[str] = []
    for namespace, fields in sorted(reachable_field_inventory().items()):
        unannotated = sorted(f for f in fields if f not in FIELD_CLASS_ANNOTATIONS)
        unresolved = sorted(f for f in fields if FIELD_CLASS_ANNOTATIONS.get(f) is BlockClass.MIXED)
        if unannotated:
            head = unannotated[:8]
            more = f" (+{len(unannotated) - len(head)} more)" if len(unannotated) > len(head) else ""
            problems.append(
                f"R2 class totality: {len(unannotated)} of {len(fields)} reachable {namespace} field(s) "
                f"carry no class annotation: {head}{more}. A strict regime synthesizes its arm "
                f"manifests FROM the class declaration, so an unannotated field is a field no arm can "
                f"be shown to have replaced or held — run the §10.2.3 annotation pass "
                f"(tools/research/annotate_classes.py) or declare the regime 'additive'."
            )
        if unresolved:
            problems.append(
                f"R2 class totality: {namespace} field(s) {unresolved} resolve to 'mixed', which is "
                f"not one class. Split them in the corpus (§11 step 6) before a strict regime cites them."
            )
    return problems


def arm_field_plan(regime: ExperimentalRegimeV2, arm_name: str) -> Dict[str, List[str]]:
    """Which annotated fields an arm replaces / blanks. ``{'replace': [...], 'disable': [...]}``."""
    arm = regime.arms[arm_name]
    by_class: Dict[BlockClass, List[str]] = {}
    for field, block_class in FIELD_CLASS_ANNOTATIONS.items():
        by_class.setdefault(block_class, []).append(field)
    replaced: List[str] = []
    disabled: List[str] = []
    for class_name in arm.replace:
        replaced.extend(sorted(by_class.get(BlockClass(class_name), [])))
    for class_name in arm.disable:
        disabled.extend(sorted(by_class.get(BlockClass(class_name), [])))
    return {"replace": sorted(replaced), "disable": sorted(disabled)}


def _namespace_for(field: str) -> str:
    inventory = reachable_field_inventory()
    for namespace, fields in inventory.items():
        if field in fields:
            return namespace
    raise RegimeRefused(
        f"class annotation names {field!r}, which is not a reachable field in any namespace — "
        f"an annotation on a dead key looks identical to an annotation on a live one and does nothing"
    )


def synthesize_arm_manifests(
    regime: ExperimentalRegimeV2,
    corpus_root: Optional[Path] = None,
    validate: bool = True,
) -> Dict[str, object]:
    """One ``ResearchOverrideManifest`` per h3ere arm, each with its own valid digest.

    §14 step 7. The regime declares CLASSES; the override facility applies
    FIELDS; this is the join. Each synthesized manifest is validated with the
    same ``_validate_manifest`` the agent runs at startup, so a regime cannot
    green a set of arm manifests the agent would refuse ten minutes into a run.

    ``mode`` on the synthesized manifests is ``additive`` on purpose: a per-arm
    manifest names exactly the fields of the classes that arm varies, which is
    total *with respect to the class declaration*. R2's totality moved up to the
    regime (``r2_totality_problems``) — the same guarantee, stated where the
    class declaration lives.
    """
    from ciris_engine.logic.utils.research_overrides import (
        OverrideSet,
        ResearchOverrideManifest,
        _validate_manifest,
        compute_residue_digest,
    )

    digest = compute_residue_digest()
    manifests: Dict[str, object] = {}
    for arm_name in sorted(regime.h3ere_arms()):
        arm = regime.arms[arm_name]
        plan = arm_field_plan(regime, arm_name)
        buckets: Dict[str, Dict[str, str]] = {
            "string": {},
            "dma_prompt": {},
            "conscience_prompt": {},
            "corpus": {},
            "template": {},
        }
        for field in plan["replace"]:
            class_name = FIELD_CLASS_ANNOTATIONS[field].value
            corpus_rel = arm.replace[class_name]
            if corpus_root is None:
                text = f"REPLACE::{corpus_rel}::{field}"
            else:
                source = corpus_root / corpus_rel / f"{field}.txt"
                if not source.is_file():
                    raise RegimeRefused(
                        f"arm {arm_name!r} replaces class {class_name} from {corpus_rel!r}, but the "
                        f"replacement for reachable field {field!r} is missing ({source}). A replacement "
                        f"arm with a hole in it leaves CIRIS text inside the alt arm — the exact bias "
                        f"§10.2.1 [T-N1] exists to catch."
                    )
                text = source.read_text(encoding="utf-8")
            buckets[_namespace_for(field)][field] = text
        for field in plan["disable"]:
            # Blanking, NOT replacement: §12 assertion 2 rejects an empty
            # replacement by design [I-6], so a disable arm must be declared
            # under `disable:` and is never a `replace:` with empty text.
            buckets[_namespace_for(field)][field] = ""

        manifest = ResearchOverrideManifest(
            manifest_version="1",
            experiment_id=f"{regime.regime_id}:{arm_name}",
            condition="c",
            base_locale="en",
            mode="additive",
            residue_digest=digest,
            overrides=OverrideSet(**buckets),
            research_hashes={},
            manifest_path=f"<synthesized from regime {regime.regime_id}>",
        )
        if validate:
            _validate_manifest(manifest)
        manifests[arm_name] = manifest
    return manifests


# --------------------------------------------------------------------------
# κ gate (§10.2.3) — a class-set version is citable only at κ >= 0.8 both ways
# --------------------------------------------------------------------------

#: Class pairs whose DEFAULT DISPOSITION differs. Aggregate κ over eleven
#: classes with skewed marginals can pass while exactly the decision-relevant
#: boundaries fail [T-N2], so these are scored separately and each must clear
#: the threshold on its own.
KAPPA_THRESHOLD = 0.8


def decision_relevant_boundaries() -> List[Tuple[BlockClass, BlockClass]]:
    """Every class pair whose default disposition differs, ``axiotic`` first.

    Derived from ``CLASS_DEFAULT_DISPOSITION`` rather than listed, so a change
    to a class's default disposition automatically adds or drops boundaries
    instead of silently leaving the κ gate scoring the old taxonomy.
    """
    classes = [c for c in BlockClass if c is not BlockClass.MIXED]
    pairs: List[Tuple[BlockClass, BlockClass]] = []
    for i, left in enumerate(classes):
        for right in classes[i + 1 :]:
            if CLASS_DEFAULT_DISPOSITION[left] != CLASS_DEFAULT_DISPOSITION[right]:
                pairs.append((left, right))
    # `axiotic|deontic` (gates safety_review) and `axiotic|structural` (gates
    # §11 step 0) foremost — sort axiotic pairs to the front, stable otherwise.
    pairs.sort(key=lambda pair: (BlockClass.AXIOTIC not in pair, pair[0].value, pair[1].value))
    return pairs


# --------------------------------------------------------------------------
# The §10.4 refusals
# --------------------------------------------------------------------------


def _block_entry_for(regime: ExperimentalRegimeV2, block_id: str) -> Optional[RegimeBlockEntry]:
    """Exact ``block_id``, then the step-suffix — same resolution the gate uses."""
    exact = regime.blocks.get(block_id)
    if exact is not None:
        return exact
    suffix = block_id.split(".", 1)[1] if "." in block_id else block_id
    return regime.blocks.get(suffix)


def _check_blocks(regime: ExperimentalRegimeV2, varied: FrozenSet[BlockClass], problems: List[str]) -> None:
    """§10.4 rule 1 (unresolved / mixed) and rule 10 (T-N1 smuggled hold)."""
    from ciris_engine.logic.utils.compose_dump import BLOCK_ANNOTATIONS

    for block_id, annotation in sorted(BLOCK_ANNOTATIONS.items()):
        if annotation.block_class is not BlockClass.MIXED:
            continue
        entry = _block_entry_for(regime, block_id)
        annotated = frozenset(annotation.contaminant or ())
        if entry is None:
            smuggled = sorted(c.value for c in annotated & varied)
            detail = f" (its contaminants {smuggled} include a varied class)" if smuggled else ""
            problems.append(
                f"block {block_id!r} is 'mixed' and the regime gives it no disposition{detail} — "
                f"refusal is the DEFAULT for any unresolved block, including every mixed block "
                f"(§10.2.1 [T-0/T-1]); name it under `blocks:` with an explicit disposition."
            )
            continue
        if entry.disposition is BlockDisposition.REFUSE:
            problems.append(
                f"block {block_id!r} carries disposition 'refuse' — the regime refuses itself by its "
                f"own declaration (§10.3's example does exactly this for language_guidance, "
                f"deliberately: the fix is §11 step 6, splitting the block, not relabelling it)."
            )
            continue
        contaminants = annotated | frozenset(entry.contaminant or ())
        if not contaminants:
            problems.append(
                f"block {block_id!r} is 'mixed' with an EMPTY contaminant list — a mixed block MUST "
                f"carry a populated contaminant list [T-N1]; without it the hold check below is vacuous."
            )
        if entry.disposition is BlockDisposition.VARY:
            problems.append(
                f"block {block_id!r} cannot carry 'vary': a mixed block varies its contaminants along "
                f"with its primary class. Split it in the corpus (§11) first."
            )
            continue
        if entry.disposition is BlockDisposition.HOLD:
            unaccepted = (contaminants & varied) - frozenset(entry.confound_accepted)
            if unaccepted:
                problems.append(
                    f"block {block_id!r} is HELD while its contaminant(s) "
                    f"{sorted(c.value for c in unaccepted)} intersect a varied class, and "
                    f"`confound_accepted` does not name them [T-N1]. Holding this block leaves the "
                    f"varied class byte-identical inside the alt arm: every Phase-1 assertion passes "
                    f"and the effect is biased toward zero WITH THE GATE GREEN. Split it (§11) or "
                    f"name the confound explicitly."
                )


def _check_dv(regime: ExperimentalRegimeV2, problems: List[str]) -> None:
    """§10.4 rule 2 (action_tier vs the DEFER residue) plus the [M-2] arm rule."""
    dv = regime.dv
    h3ere = set(regime.h3ere_arms())

    if dv.action_tier is not None:
        residue_hits = defer_policy_residue_sites()
        if residue_hits:
            problems.append(
                f"an `action_tier` DV is declared while the DEFER policy is STILL in the residue "
                f"inventory ({', '.join(residue_hits)}) — it is the outcome variable's own doctrine, "
                f"inherited invisibly by every arm, so no campaign about action choice is honest until "
                f"§11 step 0 routes it out [M-4]."
            )
        claimed = h3ere if dv.action_tier.is_all_arms() else set(dv.action_tier.arms)
        non_h3ere = sorted(claimed - h3ere)
        if non_h3ere:
            problems.append(
                f"`action_tier` names non-h3ere arm(s) {non_h3ere}: a direct-provider call has no "
                f"handler enum, so DEFER-vs-SPEAK is undefined there and the DV does not exist in the "
                f"arms it is claimed over [M-2]."
            )
        unknown = sorted(claimed - set(regime.arms))
        if unknown:
            problems.append(f"`action_tier` names undeclared arm(s) {unknown}")

    if dv.text_tier is not None and not dv.text_tier.is_all_arms():
        unknown = sorted(set(dv.text_tier.arms) - set(regime.arms))
        if unknown:
            problems.append(f"`text_tier` names undeclared arm(s) {unknown}")

    declared = set(regime.holds.locales)
    rows_locales = set(dv.text_tier_rows)
    if dv.text_tier is not None:
        if rows_locales - declared:
            problems.append(
                f"`text_tier_rows` pre-registers rows for undeclared locale(s) "
                f"{sorted(rows_locales - declared)} — a row set for a locale the run never composes is dead."
            )
        if declared - rows_locales:
            problems.append(
                f"`text_tier` is declared but locale(s) {sorted(declared - rows_locales)} pre-register "
                f"no U-rows. Per-(locale, U-row) scoring multiplies the corrected family, so the tested "
                f"subset must be named per locale BEFORE the run [M-N5/T-N3]."
            )


def _check_kills(regime: ExperimentalRegimeV2, varied: FrozenSet[BlockClass], problems: List[str]) -> None:
    """§10.4 rule 5: a varied class whose kill instrument is absent in any declared locale."""
    if not varied:
        return
    inventory = kill_instrument_inventory()
    for block_class in sorted(varied, key=lambda c: c.value):
        kill = regime.kills.get(block_class)
        if kill is None:
            continue
        if not kill.is_operable():
            problems.append(
                f"the kill for varied class {block_class.value!r} declares no "
                f"{'mde' if kill.mde is None else 'equivalence_bound'} — a kill without a declared "
                f"minimum detectable effect AND equivalence bound is decoration, and the class reverts "
                f"to `hold` [T-4]. This regime varies it anyway."
            )
        for locale in regime.holds.locales:
            available = inventory.get(locale, frozenset())
            if kill.instrument not in available and _u_code(kill.instrument) not in available:
                problems.append(
                    f"varied class {block_class.value!r} kills on instrument {kill.instrument!r}, which "
                    f"has no machine implementation in declared locale {locale!r} "
                    f"(available: {sorted(available) or ['<none>']}). A kill is an equivalence claim and "
                    f"is only operable with a named instrument that exists in EVERY declared locale [T-4]."
                )

    # The pre-registered text-tier rows are instruments too, and are checked
    # with the same table — a row nobody can score is not a pre-registration.
    for locale, rows in sorted(regime.dv.text_tier_rows.items()):
        available = inventory.get(locale, frozenset())
        missing = [row for row in rows if row not in available and _u_code(row) not in available]
        if missing:
            problems.append(
                f"locale {locale!r} pre-registers U-row(s) {missing} with no machine instrument "
                f"(available: {sorted(available) or ['<none>']}). Declaring a row the scorer cannot "
                f"produce is a power statement about a test that will never run [T-4/M-N5]."
            )


def _check_arms(regime: ExperimentalRegimeV2, varied: FrozenSet[BlockClass], problems: List[str]) -> None:
    """§10.4 rules 3, 6, 7, 8 — the arm-level refusals."""
    bare_labels = {"bare", "a", "condition-a", "condition_a"}
    for arm_name, arm in sorted(regime.arms.items()):
        if arm.harness == "h3ere" and arm_name.lower() in bare_labels:
            problems.append(
                f"arm {arm_name!r} runs the h3ere harness and is labelled as §0's condition (a): no "
                f"configuration of this runtime yields a bare prior — even fully blanked it carries "
                f"ASPDMA scaffolding, JSON coercion, the handler enum and the §6.1 residue. Labelling "
                f"an h3ere run 'bare' produces a fourth thing that is neither (a) nor (c) and "
                f"invalidates every comparison against it (§6.2, R6). Use the direct-provider harness."
            )
        for class_name in sorted(arm.replace):
            block_class = BlockClass(class_name)
            if block_class in (BlockClass.STRUCTURAL, BlockClass.AXIOMATIC):
                problems.append(
                    f"arm {arm_name!r} names {class_name!r} under `replace:` — replacing it breaks "
                    f"parsing/dispatch, or is the decomposition premise itself. Neither varies "
                    f"in-runtime; that is a DIFFERENT HARNESS (§6.2), not an arm."
                )
            if block_class is BlockClass.DEONTIC and not arm.safety_review:
                problems.append(
                    f"arm {arm_name!r} replaces `deontic` without `safety_review`: varying categorical "
                    f"permission changes what is PERMITTED, not how outcomes rank. Hold it, or declare "
                    f"the review (§10.2 default disposition, §10.4)."
                )
        for class_name in sorted(arm.disable):
            if BlockClass(class_name) in (BlockClass.STRUCTURAL, BlockClass.AXIOMATIC):
                problems.append(
                    f"arm {arm_name!r} names {class_name!r} under `disable:` — it cannot vary "
                    f"in-runtime at all, blanked or replaced (§10.2)."
                )

    if BlockClass.PRAGMATIC in varied and BlockClass.AXIOTIC in varied:
        if "register" not in {token.lower() for token in regime.confound_accepted}:
            problems.append(
                "`pragmatic` varies alongside `axiotic` without `confound_accepted: register`: register "
                "and content move together, so neither effect is attributable. Accept the confound by "
                "name or hold one of them (§10.4, v1 rule kept)."
            )


def _check_repeats(regime: ExperimentalRegimeV2, problems: List[str]) -> None:
    """§10.4 rule 9: a repeat structure with no live variance source [M-N1]."""
    repeats = regime.repeats
    if repeats.conversations_per_cell <= 1:
        return
    temperature = regime.holds.decoding.temperature

    if repeats.variance_source is VarianceSource.NONE:
        problems.append(
            f"`repeats.conversations_per_cell: {repeats.conversations_per_cell}` with "
            f"`variance_source: none` — n identical inputs measure provider batching noise, not "
            f"between-conversation variance [M-N1]."
        )
    elif repeats.variance_source is VarianceSource.TEMPERATURE:
        if temperature is None:
            problems.append(
                "`variance_source: temperature` while `holds.decoding.temperature` is unpinned — the "
                "variance source has to be pinned to be a source [M-N1]."
            )
        elif temperature <= 0.0:
            problems.append(
                f"`variance_source: temperature` with `holds.decoding.temperature: {temperature}` — "
                f"temperature 0.0 is not a variance source; the repeats are identical inputs. Pin "
                f"temperature > 0, or use enumerated seeds [M-N1]."
            )
    elif repeats.variance_source is VarianceSource.SEEDS:
        if not repeats.seeds:
            problems.append("`variance_source: seeds` with an empty `seeds:` list — nothing enumerated [M-N1].")
        elif len(set(repeats.seeds)) < repeats.conversations_per_cell:
            problems.append(
                f"`variance_source: seeds` enumerates {len(set(repeats.seeds))} distinct seed(s) for "
                f"{repeats.conversations_per_cell} conversations per cell — the repeats past the last "
                f"seed have no variance source [M-N1]."
            )
        if not seed_is_configured():
            problems.append(
                "`variance_source: seeds` while `CIRIS_LLM_SEED` is unset: seed is transmitted on the "
                "OpenAI-compatible path ONLY when configured (#975, 2.9.9), so the enumerated seeds are "
                "inert and the repeat structure has no variance [M-N1]."
            )
    if repeats.seeds and regime.holds.decoding.seed is not None:
        problems.append(
            "`repeats.seeds` enumerates per-conversation seeds while `holds.decoding.seed` pins ONE "
            "seed for the whole run — the pin would hold every repeat identical. Pin one or the other."
        )


def _check_decoding(regime: ExperimentalRegimeV2, problems: List[str]) -> None:
    """§10.4 rule 4: pinned == transmitted, SET EQUALITY, both directions [M-6/M-N3]."""
    base_url = regime.holds.resolved_base_url()
    if (
        regime.holds.decoding.base_url
        and regime.holds.base_url
        and (regime.holds.decoding.base_url != regime.holds.base_url)
    ):
        problems.append(
            f"base_url is pinned twice and disagrees: holds.base_url={regime.holds.base_url!r} vs "
            f"holds.decoding.base_url={regime.holds.decoding.base_url!r}. extra_body is a function of "
            f"the endpoint, so which one wins is not a detail."
        )
        return
    if not base_url:
        problems.append(
            "no `base_url` pinned: the transmitted parameter set is a FUNCTION of the endpoint "
            "(service.py `_build_reasoning_off_extras`), so without it the enforced-or-refused check "
            "cannot be performed — and an unperformable check refuses [M-N3]."
        )
        return

    pinned = pinned_decoding_keys(regime)
    transmitted = transmitted_decoding_keys(base_url, regime.holds.model)

    pinned_not_sent = sorted(pinned - transmitted)
    if pinned_not_sent:
        detail = ""
        if "seed" in pinned_not_sent:
            detail = (
                " `seed` IS plumbed on the OpenAI-compatible path as of 2.9.9 (#975) but is transmitted "
                "only when CIRIS_LLM_SEED is set — set it, or drop the pin."
            )
        if "top_p" in pinned_not_sent:
            detail += (
                " `top_p` is transmitted by NO path in this runtime: the OpenAI-compatible call sends "
                "temperature + max_tokens (+seed) only, and the Gemini mapping only forwards keys that "
                "are already in generation_config. A pinned top_p is a pin nobody honours."
            )
        problems.append(
            f"decoding keys pinned but NOT transmitted at {base_url}: {pinned_not_sent}.{detail} A pin "
            f"the call path does not send is a pin that reads as enforced and is not [M-6]."
        )
    sent_not_pinned = sorted(transmitted - pinned)
    if sent_not_pinned:
        problems.append(
            f"decoding keys TRANSMITTED at {base_url} but not pinned: {sent_not_pinned}. The check is "
            f"set equality in both directions [M-N3] — a subset semantics would have passed §10.3's own "
            f"example, which pins a strict subset of what the DeepInfra branch sends."
        )


def _check_contrasts(regime: ExperimentalRegimeV2, problems: List[str]) -> None:
    """Every claim names its contrast; every MAIN contrast declares an MDE."""
    for name, contrast in sorted(regime.contrasts.items()):
        for arm_name in (contrast.minuend, contrast.subtrahend):
            if arm_name not in regime.arms:
                problems.append(f"contrast {name!r} names undeclared arm {arm_name!r}")
        if contrast.minuend == contrast.subtrahend:
            problems.append(f"contrast {name!r} differences an arm against itself")
        if name not in regime.repeats.mde:
            problems.append(
                f"contrast {name!r} declares no MDE in `repeats.mde` — a contrast without a declared "
                f"minimum detectable effect cannot carry a null result, and a null is the outcome a "
                f"regime is most likely to produce."
            )


def _check_structure(regime: ExperimentalRegimeV2, problems: List[str]) -> None:
    """Schema string, class-set version, locale/arm hygiene."""
    if regime.regime_schema != REGIME_SCHEMA_V2:
        problems.append(
            f"schema is {regime.regime_schema!r}, not {REGIME_SCHEMA_V2!r} — the Phase-1 self-check "
            f"regimes carry a different string on purpose and are not campaign manifests."
        )
    if regime.class_set_version not in KNOWN_CLASS_SET_VERSIONS:
        problems.append(
            f"unknown class_set_version {regime.class_set_version!r} (registered: "
            f"{sorted(KNOWN_CLASS_SET_VERSIONS)}). A split creates a new version and results are "
            f"reported under the version they were gathered at, never silently re-mapped (§10.2.2 [T-7])."
        )
    if regime.mode not in ("strict", "additive"):
        problems.append(f"mode must be 'strict' or 'additive', got {regime.mode!r}")
    if "en" not in regime.holds.locales:
        problems.append(
            "`holds.locales` omits `en`, which is MANDATORY as the fidelity control [M-N2]: in "
            "low-resource locales a values effect cannot be separated from alt-corpus translation "
            "quality, and en is where corpus fidelity is natively checkable."
        )
    for arm_name, arm in sorted(regime.arms.items()):
        if arm.harness not in ("h3ere", "direct-provider"):
            problems.append(f"arm {arm_name!r} declares unknown harness {arm.harness!r}")
        for class_name in list(arm.replace) + list(arm.disable) + list(arm.inject):
            try:
                BlockClass(class_name)
            except ValueError:
                problems.append(f"arm {arm_name!r} names unknown class {class_name!r}")
    if not regime.h3ere_arms():
        problems.append("no `h3ere` arm declared — the shipped configuration is the cell v1 forgot [M-1]")


def validate_regime(regime: ExperimentalRegimeV2) -> None:
    """Every §10.4 refusal. One error, every problem. Raises ``RegimeRefused``."""
    problems: List[str] = []
    _check_structure(regime, problems)

    varied: FrozenSet[BlockClass] = frozenset()
    try:
        varied = regime.varied_classes()
    except ValueError:
        pass  # unknown class names already reported by _check_structure

    _check_arms(regime, varied, problems)
    _check_blocks(regime, varied, problems)
    _check_dv(regime, problems)
    _check_repeats(regime, problems)
    _check_contrasts(regime, problems)
    # These two reach outside the manifest — the endpoint's transmitted key set
    # and the kill-instrument tables. An unperformable check refuses, so its
    # RegimeRefused is folded in as a problem rather than short-circuiting the
    # rest of the report (one error, every problem).
    try:
        _check_decoding(regime, problems)
    except RegimeRefused as exc:
        problems.append(str(exc))
    try:
        _check_kills(regime, varied, problems)
    except RegimeRefused as exc:
        problems.append(str(exc))

    if regime.mode == "strict":
        problems.extend(r2_totality_problems())

    if problems:
        raise RegimeRefused(
            f"regime {regime.regime_id!r} is not runnable — {len(problems)} refusal(s), "
            f"before the first LLM call:\n" + "\n".join(f"  [{i}] {p}" for i, p in enumerate(problems, 1))
        )


def load_regime_v2(path: str) -> ExperimentalRegimeV2:
    """Parse + validate a v2 manifest. Refuses; never warns."""
    import yaml

    with open(path, encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise RegimeRefused(f"{path} is not a mapping")
    regime = ExperimentalRegimeV2.model_validate(raw)
    validate_regime(regime)
    return regime
