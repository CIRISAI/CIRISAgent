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
import string
import subprocess
import sys
from collections import deque
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, NamedTuple, Optional, Sequence, Tuple

from ciris_engine.schemas.dma.compose import (
    CLASS_DEFAULT_DISPOSITION,
    BlockClass,
    BlockDisposition,
    ComposeDumpMeta,
    ComposedBlock,
    GateRegime,
    RegimeBlockEntry,
)
from ciris_engine.schemas.research.regime import REGIME_SCHEMA_V2, ExperimentalRegimeV2
from ciris_engine.schemas.types import JSONDict

# --------------------------------------------------------------------------
# Class annotation table (§10.2 / §10.2.1)
# --------------------------------------------------------------------------


class BlockAnnotation(NamedTuple):
    """(primary class, contaminant list) for one block id."""

    block_class: BlockClass
    contaminant: Optional[Tuple[BlockClass, ...]]


_C = BlockClass  # brevity in the table below

#: THE annotation map — one entry per BLOCK, one comment per entry saying why
#: that class, because the disposition is computed from it.
#:
#: Since #997 a block is a FIELD, not a message: ``get_system_message`` appends
#: up to seven separately-sourced fields and the dump splits on the boundary the
#: composer already computes, so the keys here are ``<component>.<field>`` —
#: keyed to the TEMPLATE, not the step, which is why one entry serves
#: ``csdma`` and ``csdma_bounce``, and one serves all five ASPDMA steps.
#:
#: MERGE RULE, applied throughout and stated so it can be argued with. A block
#: whose classes all imply HOLD or n/a is labelled with the STRICTEST class
#: present — deontic over the domain-HOLD classes, any HOLD class over
#: structural/contingent. Overstating holds a block harder and gates its
#: replacement behind §10.4 safety_review; it can never leak doctrine.
#: Understating can. The ONE class that cannot be merged is ``axiotic``: it is
#: the only class that VARIES, so folding it into a held block silently smuggles
#: CIRIS values into an alt-values arm (the §10.2.1 bias-toward-the-null
#: confound), and folding a held class into it varies doctrine that must hold.
#: **A block containing axiotic content alongside anything else is therefore
#: genuinely ``mixed``, and that is the only thing ``mixed`` now means here.**
#:
#: Single-author, best-effort annotation: the §10.2.3 two-annotator κ pass
#: (#976) REPLACES this table; until then every ``mixed`` entry defaults to
#: refusal at the gate, so an optimistic annotation here cannot green a run.
#: Lookup: exact ``block_id``, then the suffix after the step, then the two
#: rules in ``annotation_for``. ``mixed`` entries carry populated contaminant
#: lists [T-N1].
BLOCK_ANNOTATIONS: Dict[str, BlockAnnotation] = {
    # ---- discrete corpus / string blocks -----------------------------------
    # The accord: states and ranks what matters — axiotic. Since #997 this also
    # covers ASPDMA's accord message, whose runtime `THOUGHT_TYPE=` prefix is
    # now split off into its own `thought_type` block instead of dragging
    # 54,725 B of routed corpus into `mixed` with it.
    "accord": BlockAnnotation(_C.AXIOTIC, None),
    # The `THOUGHT_TYPE=<...>` line ASPDMA prepends to the accord: one runtime
    # value — contingent, excluded from Phase 1 by construction [T-2].
    "thought_type": BlockAnnotation(_C.CONTINGENT, None),
    # prompts.language_guidance, UNSPLIT. 24 of 29 locales still carry the whole
    # 13-41 KB scalar: register doctrine, categorical prohibitions ("NEVER DENY
    # BEING AN AI"), crisis-line world-facts and value claims ("route serious
    # symptoms to professional care without minimization") interleaved sentence
    # by sentence, with no field boundary to report [T-1]. The five locales
    # whose prose is line-for-line parallel to English (en/es/fr/it/pt) are
    # split — see the `language_guidance.*` entries below — and their message
    # never resolves to this annotation.
    "language_guidance": BlockAnnotation(_C.MIXED, (_C.AXIOTIC, _C.DEONTIC, _C.EMPIRICAL)),
    # ---- prompts.language_guidance, SPLIT (#997) ---------------------------
    # 29 consecutive slices of the same prose, joined with "" and stripped once,
    # so the composed message is byte-identical to the pre-split scalar (pinned
    # per locale by tests/.../test_language_guidance_split_997.py). Classes are
    # §10.2; two are the payoff and five are the FSD's own named irreducible.
    #
    # Reading instruction + "APPLY FIRST" ordering directive.
    "language_guidance.01_preamble": BlockAnnotation(_C.PROCEDURAL, None),
    # "The first sentence ... sets the register for the entire reply." Governs
    # address, not content — pragmatic, the §10.2 worked example for this class.
    "language_guidance.02_first_sentence_tone_lock": BlockAnnotation(_C.PRAGMATIC, None),
    # "NEVER DENY BEING AN AI" — §10.2's own named deontic worked example.
    "language_guidance.03_never_deny_ai": BlockAnnotation(_C.DEONTIC, None),
    # Second-person formal, no contractions under distress, "holds even if the
    # user explicitly requests informality" — register rules, pragmatic.
    "language_guidance.04_formal_register": BlockAnnotation(_C.PRAGMATIC, None),
    # "MAY NOT appear in any response, in any context" — categorical, and a
    # HARD-FAIL criterion. Deontic: replacing it takes a §10.4 safety review.
    "language_guidance.05_no_wellness_confirmation": BlockAnnotation(_C.DEONTIC, None),
    # Warmth-is-not-informality + concision + keep CIRIS identifiers in English.
    # Two adjacent bullets, both register/code doctrine — pragmatic, and no
    # boundary between them would be earned by a class change.
    "language_guidance.06_warmth_and_concision": BlockAnnotation(_C.PRAGMATIC, None),
    # The verbatim scope disclaimer ("I cannot diagnose or treat any condition")
    # plus its use-verbatim rider. The quoted sentence states the agent's
    # categorical scope limit; deontic is the conservative call, and it keeps
    # the disclaimer HELD under a register study that varies pragmatic.
    "language_guidance.07_canonical_disclaimer": BlockAnnotation(_C.DEONTIC, None),
    # "the pathway to support varies by country" — a world-fact about help
    # systems, checkable at compose time. Empirical.
    "language_guidance.08_help_pathway_intro": BlockAnnotation(_C.EMPIRICAL, None),
    # THE FIRST PAYOFF. "For users disclosing distress, validating 'talk to
    # someone you trust' as a real first step MATTERS" ranks lay support as
    # genuinely valuable. It sat inside an empirical list that a values arm
    # would have HELD — the §10.2.1 bias-toward-the-null confound, and it is
    # named nowhere in the FSD. 56 B of empirical list stem co-vary with it;
    # over-varying adds noise, under-varying adds bias, and noise is the safe
    # direction.
    "language_guidance.09_trusted_person_first_step": BlockAnnotation(_C.AXIOTIC, None),
    # GP / crisis lines / mental-health professional — static world-facts, the
    # §10.2 empirical worked example. Merges with the `crisis` block when #974
    # routes crisis resources discretely.
    "language_guidance.10_help_pathway_steps": BlockAnnotation(_C.EMPIRICAL, None),
    # THE SECOND PAYOFF, and the sentence the FSD quotes as the reason a `hold`
    # on this block biases values_effect toward zero: "route serious symptoms
    # ... to professional care without minimization". ~118 B of the 269 are a
    # procedural crisis-line pointer and an empirical severity list that cannot
    # be separated without cutting a single sentence mid-clause; declared, not
    # hidden.
    "language_guidance.11_routing_doctrine": BlockAnnotation(_C.AXIOTIC, None),
    # "Do not attribute symptoms the user has NOT explicitly disclosed" — a
    # prohibition; its canonical violation example is inline illustration of the
    # rule, not a standalone demonstration, so it rides with it.
    "language_guidance.12_undisclosed_symptom_attribution": BlockAnnotation(_C.DEONTIC, None),
    # IRREDUCIBLE [T-5a]. The SPEAK exemplar: the canonical disclaimer
    # (deontic), 988 / 116 123 (empirical), warm formal register (pragmatic) and
    # "those symptoms together deserve attention" (axiotic) in the SAME tokens —
    # the co-occurrence IS the demonstration. FSD §10.2.1: hold-verbatim or
    # replace-whole-exemplar, never split.
    "language_guidance.13_exemplar_speak_response": BlockAnnotation(
        _C.MIXED, (_C.PRAGMATIC, _C.AXIOTIC, _C.DEONTIC, _C.EMPIRICAL)
    ),
    # IRREDUCIBLE [T-5a]. 7a register-pressure: correct and wrong responses
    # demonstrated verbatim; "what you're going through deserves that" is the
    # axiotic that cannot be lifted out of the demonstration.
    "language_guidance.14_exemplar_register_pressure": BlockAnnotation(
        _C.MIXED, (_C.PRAGMATIC, _C.AXIOTIC)
    ),
    # The CORRECT PATTERN paragraph is doctrine ABOUT the demonstration, not
    # part of it — which is why it splits clean where the exemplar cannot.
    # "Friendliness lives in language; the protective discipline lives
    # underneath" is register doctrine.
    "language_guidance.15_register_pressure_pattern": BlockAnnotation(_C.PRAGMATIC, None),
    # IRREDUCIBLE [T-5a]. 7b false-reassurance, same shape as 7a.
    "language_guidance.16_exemplar_false_reassurance": BlockAnnotation(
        _C.MIXED, (_C.DEONTIC, _C.PRAGMATIC, _C.AXIOTIC)
    ),
    # "REFUSE the explicit wellness-confirmation as out-of-scope ... the
    # forbidden phrasings may not appear even as qualified asides." Deontic.
    "language_guidance.17_false_reassurance_pattern": BlockAnnotation(_C.DEONTIC, None),
    # "applies WHENEVER the user asks the agent to confirm a claim the agent is
    # not positioned to judge", with the five surfaces. The organizing concept
    # is the limit of what the agent may assert — epistemic. (Readable as
    # procedural; both HOLD, so the boundary is disposition-neutral.)
    "language_guidance.18_ratification_scope": BlockAnnotation(_C.EPISTEMIC, None),
    # "The agent is a careful interlocutor — not the user's clinician, not their
    # priest, not the keeper of the verdict." The ONE self-identity claim in the
    # whole block, and the only ontological content in it.
    "language_guidance.19_agent_role": BlockAnnotation(_C.ONTOLOGICAL, None),
    # RECEIVE / NAME THE LIMIT / SURFACE THE PATHWAY / STAY PRESENT — a
    # four-step method. Procedural.
    "language_guidance.20_four_moves": BlockAnnotation(_C.PROCEDURAL, None),
    # '"no" in answer to "am I broken?" is just as much a clinical claim as
    # "yes"' — what counts as a claim. Epistemic. FLAGGED: its third sentence
    # ("declining both is not coldness — it is the agent staying in scope")
    # reads axiotic, and unlike every other near-miss here that boundary is
    # DISPOSITION-CHANGING. Annotated by the majority of the bytes and referred
    # to the §10.2.3 two-annotator pass (#976); not settled by one author.
    "language_guidance.21_negative_is_also_a_verdict": BlockAnnotation(_C.EPISTEMIC, None),
    # Self-labelled "REGISTER." — as unambiguous a pragmatic block as exists in
    # the corpus.
    "language_guidance.22_ratification_register": BlockAnnotation(_C.PRAGMATIC, None),
    # IRREDUCIBLE [T-5a]. Two verbatim model outputs (clinical and moral
    # surfaces) — same demonstration artefact as the adversarial exemplars.
    "language_guidance.23_ratification_templates": BlockAnnotation(
        _C.MIXED, (_C.PRAGMATIC, _C.EPISTEMIC, _C.ONTOLOGICAL, _C.AXIOTIC)
    ),
    # "The agent never converts 'I cannot ratify' into 'so the answer is no'" —
    # the shape of the move, stated as method.
    "language_guidance.24_ratification_pattern": BlockAnnotation(_C.PROCEDURAL, None),
    # IRREDUCIBLE [T-5a]. 7c cross-cluster -> wellness drift, including the
    # Q4 HARD-FAIL U6 counter-example.
    "language_guidance.25_exemplar_cross_cluster": BlockAnnotation(
        _C.MIXED, (_C.DEONTIC, _C.EPISTEMIC, _C.EMPIRICAL, _C.AXIOTIC)
    ),
    # "clinical clustering surfaces what condition is or isn't present, it does
    # NOT issue the user a wellness verdict ... may not appear even as
    # transitional clauses." Deontic.
    "language_guidance.26_cross_cluster_pattern": BlockAnnotation(_C.DEONTIC, None),
    # "These training-attractor pulls are properties of LLMs, not of any one
    # language." A law-like relation the reasoning is asked to accept, not a
    # world-fact checkable at compose time — nomological, sibling of IDMA's
    # k_eff [T-5c], and the only nomological content in this block.
    "language_guidance.27_attractor_universality": BlockAnnotation(_C.NOMOLOGICAL, None),
    # "provide a clear, brief, useful response" — 68 B, and it earns its keep:
    # merged with part 29 it would make one 226 B `mixed` block that REFUSES;
    # split, both halves HOLD.
    "language_guidance.28_brevity_restatement": BlockAnnotation(_C.PRAGMATIC, None),
    # "Do not attempt to provide medical or legal advice — defer to a
    # professional." Categorical; its closing rationale rides with it.
    "language_guidance.29_no_medical_or_legal_advice": BlockAnnotation(_C.DEONTIC, None),
    # Prohibition context block (#910): categorical permission/prohibition
    # sourced from PROHIBITED_CAPABILITIES — deontic.
    "prohibition": BlockAnnotation(_C.DEONTIC, None),
    # Crisis resources: static world-facts (numbers, URLs) — empirical (#971
    # landed the breadcrumb in formatters/crisis_resources.py). NOT reachable
    # as a discrete block today: it rides interpolated inside dsdma.system.
    # This entry activates when #974 routes it discretely.
    "crisis": BlockAnnotation(_C.EMPIRICAL, None),
    # ---- named residue: the bytes no field render explains ------------------
    # `format_system_prompt_blocks` wraps a composed system message in identity
    # and snapshot blocks, so what sits before the first field and after the
    # last one is real content that must be reported, not dropped.
    #
    # head (DSDMA, 3,407 B): CORE IDENTITY (ontological) + the domain header
    # `dsdma_base.py` renders with a bare `.format()` (procedural) + the
    # CROSS-DOMAIN NORMS block. This was labelled DEONTIC on a merge-up
    # argument — "deontic is the strictest class present" — and that argument is
    # INVALID here (#997, caught by adversarial review).
    #
    # Merging up is only sound among classes that AGREE on disposition. This
    # block carries both, and they disagree:
    #   deontic  "informed consent required"                     -> hold
    #   axiotic  "client interest over personal gain",
    #            "patient welfare paramount",
    #            "rewards should match contribution level"        -> VARY
    # plus ontological (CORE IDENTITY), procedural (the domain header render)
    # and empirical ("a 6-year-old believing in Santa is normal").
    #
    # "Prioritize X over Y" re-ranks outcomes without newly permitting any act,
    # which is the operational test for axiotic. Holding it under a deontic
    # label held the INDEPENDENT VARIABLE constant inside a block the campaign
    # believed it was holding for safety reasons — the exact confound the
    # taxonomy exists to prevent, and invisible because the label was
    # single-class and therefore never asked for a contaminant list.
    "system.head": BlockAnnotation(_C.MIXED, (_C.DEONTIC, _C.AXIOTIC, _C.ONTOLOGICAL, _C.PROCEDURAL, _C.EMPIRICAL)),
    # tail (CSDMA/CSDMA-bounce/IDMA, 409 B): the ORIGINAL TASK + System Snapshot
    # blocks — runtime state, contingent [T-2].
    "system.tail": BlockAnnotation(_C.CONTINGENT, None),
    # head/tail of a user message whose template is composed in Python rather
    # than rendered (DSASPDMA's deferral state frame; TSASPDMA-correction's
    # scaffold and task list). Authored section frames around runtime values:
    # procedural, so assertion 3 byte-checks the authored half. Labelling them
    # `contingent` would be the honest majority-of-bytes call and also make an
    # arm that rewrites the frame invisible — asserting more, never less.
    "user.head": BlockAnnotation(_C.PROCEDURAL, None),
    "user.tail": BlockAnnotation(_C.PROCEDURAL, None),
    # ---- pdma_ethical -------------------------------------------------------
    # THE remaining in-YAML mixture. 8,240 B (23,403 B after polyglot
    # substitution) that walk the PDMA stages (procedural) and the JSON output
    # contract (structural) while naming and ranking the Six Principles and
    # Meta-Goal M-1 as the evaluative target (axiotic). Splitting it means
    # cutting the YAML field in 29 locales, not moving a boundary the composer
    # already knows — so it stays mixed and parked.
    "pdma_ethical.system_guidance_header": BlockAnnotation(
        _C.MIXED, (_C.PROCEDURAL, _C.AXIOTIC, _C.STRUCTURAL)
    ),
    # "Thought to Evaluate: " — an authored label around the thought.
    "pdma_ethical.context_integration": BlockAnnotation(_C.PROCEDURAL, None),
    # ---- csdma_common_sense -------------------------------------------------
    # Scope statement + the two-step "draft the response, then rate THAT" method.
    # Names no value and forbids nothing: it is how to run the check.
    "csdma_common_sense.system_guidance_header": BlockAnnotation(_C.PROCEDURAL, None),
    # The seven-step realism checklist — a measurement procedure.
    "csdma_common_sense.evaluation_steps": BlockAnnotation(_C.PROCEDURAL, None),
    # JSON contract (structural) wrapped around LANGUAGE RULES — which language
    # the values go in, which keys stay English. Register doctrine is pragmatic
    # and pragmatic HOLDs, so the block is pragmatic: a parsing-contract label
    # would make the register rules n/a and stop byte-checking them.
    "csdma_common_sense.response_format": BlockAnnotation(_C.PRAGMATIC, None),
    "csdma_common_sense.context_integration": BlockAnnotation(_C.PROCEDURAL, None),
    # ---- idma ---------------------------------------------------------------
    # The k_eff = k / (1 + ρ(k-1)) law and the chaos/healthy/rigidity phase
    # model: a law-like relation the reasoning is asked to accept — the §10.2
    # nomological worked example [T-5c].
    "idma.system_guidance_header": BlockAnnotation(_C.NOMOLOGICAL, None),
    # "WORK IN THIS ORDER: 1..6" — the procedure that applies the law.
    "idma.evaluation_steps": BlockAnnotation(_C.PROCEDURAL, None),
    # JSON key contract + LANGUAGE RULES — pragmatic, same reasoning as CSDMA's.
    "idma.response_format": BlockAnnotation(_C.PRAGMATIC, None),
    # "When uncertain about source independence, err on the side of caution",
    # "When in doubt, flag it" — what counts as sufficient evidence. Epistemic.
    # Inert before #990 wired closing_reminder into the composer; live now.
    "idma.closing_reminder": BlockAnnotation(_C.EPISTEMIC, None),
    "idma.context_integration": BlockAnnotation(_C.PROCEDURAL, None),
    # ---- dsdma_base ---------------------------------------------------------
    # The LANGUAGE RULES block (#990 wired it in): respond in the user's
    # language, keep JSON keys English. Pure register doctrine — pragmatic.
    "dsdma_base.response_format": BlockAnnotation(_C.PRAGMATIC, None),
    "dsdma_base.context_integration": BlockAnnotation(_C.PROCEDURAL, None),
    # ---- tsaspdma -----------------------------------------------------------
    # The four action options and the choose-SPEAK/PONDER/TOOL criteria: a
    # decision procedure over an already-selected tool.
    "tsaspdma.system_guidance_header": BlockAnnotation(_C.PROCEDURAL, None),
    "tsaspdma.evaluation_steps": BlockAnnotation(_C.PROCEDURAL, None),
    # FLAT-JSON contract + LANGUAGE RULES — pragmatic, as above.
    "tsaspdma.response_format": BlockAnnotation(_C.PRAGMATIC, None),
    # "Your role is to catch what ASPDMA could not see; confirm it quickly" —
    # role procedure, not a prohibition and not a value.
    "tsaspdma.closing_reminder": BlockAnnotation(_C.PROCEDURAL, None),
    "tsaspdma.context_integration": BlockAnnotation(_C.PROCEDURAL, None),
    # 899 B of LOCALIZED correction doctrine that was invisible until #997 routed
    # its render through `safe_format`. "The tool_name field must be an EXACT
    # match from the available tools list" is a categorical constraint on what
    # the agent may emit — deontic, so replacing it takes a safety review.
    "tsaspdma.tool_correction_section": BlockAnnotation(_C.DEONTIC, None),
    # ---- dsaspdma -----------------------------------------------------------
    # "ASPDMA already chose DEFER. Your job is NOT to reopen the action choice."
    # plus the five-step classification method.
    "dsaspdma.system_guidance_header": BlockAnnotation(_C.PROCEDURAL, None),
    "dsaspdma.evaluation_steps": BlockAnnotation(_C.PROCEDURAL, None),
    # JSON contract + LANGUAGE RULES — pragmatic, as above.
    "dsaspdma.response_format": BlockAnnotation(_C.PRAGMATIC, None),
    # "Do not switch away from DEFER. Do not invent a domain_hint unless
    # licensed handling is truly implied." Categorical — deontic.
    "dsaspdma.closing_reminder": BlockAnnotation(_C.DEONTIC, None),
    # 3,273 B of rights/needs deferral taxonomy: which human right a deferral
    # implicates, and which operational code justifies escalation to a human.
    # It governs when the system must hand over — a permission structure, not a
    # value ranking — so deontic, and its replacement is safety-reviewable.
    "dsaspdma.taxonomy_text": BlockAnnotation(_C.DEONTIC, None),
    # ---- action_selection_pdma ---------------------------------------------
    # The hand-composed ASPDMA system message. Assembled from Python literals
    # (DEFAULT_TEMPLATE + the conscience-retry block), so no render seam exists
    # to split it: CORE IDENTITY (ontological), the FLAT-JSON field contract
    # (structural), LANGUAGE RULES (pragmatic), the snapshot (contingent) — and
    # "Recall CIRIS principles override personal preference", which ranks what
    # matters and is why this block cannot be merged up to HOLD. Keyed to the
    # composer, so the five ASPDMA steps share ONE annotation and one ratchet
    # entry rather than five copies of the same admission.
    "action_selection_pdma.system_message": BlockAnnotation(
        _C.MIXED, (_C.ONTOLOGICAL, _C.AXIOTIC, _C.PROCEDURAL, _C.PRAGMATIC, _C.CONTINGENT)
    ),
    # The authored half of the ASPDMA user template: what the task is, the
    # permitted-actions framing, and the FLAT-JSON schema reminder. Names no
    # value once the slot payload is split off — procedural.
    "action_selection_pdma.context_integration": BlockAnnotation(_C.PROCEDURAL, None),
    # The interpolated half — and the ONE slot payload that is not runtime data.
    # `{action_parameter_schemas}`, `{final_ponder_advisory}`,
    # `{conscience_guidance}` and the action-params guidance blocks are other
    # PROMPT FIELDS delivered through slots, so the default `.slots` ->
    # contingent rule would make ~3.9 KB of deontic and axiotic doctrine n/a.
    # Explicitly mixed until those renders are recorded as blocks of their own.
    "action_selection_pdma.context_integration.slots": BlockAnnotation(
        _C.MIXED, (_C.PROCEDURAL, _C.AXIOTIC, _C.DEONTIC, _C.CONTINGENT)
    ),
    # "highly align 'Speak' or 'Ponder' with Fidelity & Do-Good" — names two
    # CIRIS principles and ranks actions by them. Axiotic, and therefore the
    # only one of these three that a values arm varies. Holding it by mistake
    # is the expensive error, which is why it is called out rather than folded
    # into the surrounding procedural guidance.
    "action_selection_pdma.csdma_ambiguity_guidance": BlockAnnotation(_C.AXIOTIC, None),
    # A literal JSON snippet demonstrating the shape above — structural.
    "action_selection_pdma.csdma_ambiguity_alignment_example": BlockAnnotation(_C.STRUCTURAL, None),
    # "Use the EXACT tool name from the 'Available tools' list. Do NOT invent or
    # modify tool names." Categorical prohibition — deontic.
    "action_selection_pdma.tool_selection_guidance": BlockAnnotation(_C.DEONTIC, None),
    # ---- the conscience faculties (#986) ------------------------------------
    # IRIS-E: an entropy MEASUREMENT with scope exclusions that are categorical
    # about what this judge may score ("NOT a check for CIRIS alignment — do not
    # double-penalize", "Do not rely on any visual content"). Deontic is the
    # strictest class present and — verified line by line — there is no value
    # ranking anywhere in it, so this faculty is single-class today.
    "entropy_conscience.system_prompt": BlockAnnotation(_C.DEONTIC, None),
    # IRIS-C carries a CIRIS CORE PRINCIPLES section (562 B: TRUTH-SEEKING,
    # EPISTEMIC INTEGRITY, AUTONOMY PRESERVATION, ...) inside its calibration.
    # The pre-#997 annotation said (epistemic, procedural) and named no axiotic
    # contaminant, so a regime holding this block passed the T-N1 intersection
    # check while smuggling CIRIS value doctrine into an alt-values arm. Naming
    # axiotic is the fix; splitting it needs the YAML scalar cut into fields.
    "coherence_conscience.system_prompt": BlockAnnotation(
        _C.MIXED, (_C.AXIOTIC, _C.DEONTIC, _C.EPISTEMIC, _C.ONTOLOGICAL, _C.PROCEDURAL)
    ),
    # CIRIS-EH: mostly evidence standards, but principle #3 ALIGNED GRACE and
    # the closing "the infinite grace extended to all aligned moral actors
    # includes yourself" are value premises the faculty reasons FROM. Same
    # missing-axiotic bug as coherence, same fix.
    "epistemic_humility_conscience.system_prompt": BlockAnnotation(
        _C.MIXED, (_C.AXIOTIC, _C.DEONTIC, _C.EPISTEMIC, _C.ONTOLOGICAL, _C.PROCEDURAL)
    ),
    # CIRIS-EOV: 24,064 B of which roughly half is explicit cross-tradition
    # value doctrine — the torque doctrine, the four named capture patterns, the
    # locale covenant, the final posture. The largest single concentration of
    # axiotic content outside the accord, and the strongest argument for the
    # conscience YAML field split this entry is parked on.
    "optimization_veto_conscience.system_prompt": BlockAnnotation(
        _C.MIXED, (_C.AXIOTIC, _C.DEONTIC, _C.EPISTEMIC, _C.EMPIRICAL, _C.PROCEDURAL, _C.STRUCTURAL)
    ),
    # Every conscience user template, once its interpolated payload is split
    # off, is an authored frame telling the judge what it is looking at and how
    # to read it. Procedural — held, and byte-checked, so an arm that perturbs a
    # conscience user template is caught. The `_image` steps resolve here too
    # via the `_image` rule in `annotation_for`.
    "entropy_conscience.user_prompt_template": BlockAnnotation(_C.PROCEDURAL, None),
    "entropy_conscience.user_prompt_with_image_template": BlockAnnotation(_C.PROCEDURAL, None),
    "coherence_conscience.user_prompt_template": BlockAnnotation(_C.PROCEDURAL, None),
    "coherence_conscience.user_prompt_with_image_template": BlockAnnotation(_C.PROCEDURAL, None),
    "optimization_veto_conscience.user_prompt_template": BlockAnnotation(_C.PROCEDURAL, None),
    "optimization_veto_conscience.user_prompt_with_image_template": BlockAnnotation(_C.PROCEDURAL, None),
    "epistemic_humility_conscience.user_prompt_template": BlockAnnotation(_C.PROCEDURAL, None),
    "epistemic_humility_conscience.user_prompt_with_image_template": BlockAnnotation(_C.PROCEDURAL, None),
}


#: Suffix of a block emitted for the interpolated half of a field render (#997).
_SLOTS_SUFFIX = ".slots"


def annotation_for(block_id: str) -> BlockAnnotation:
    """Resolve the annotation for a block id: exact match, then step-suffix.

    Two rules run after the table, in this order, so an explicit entry always
    wins over either:

    - the ``_image`` conscience steps compose the SAME system calibration and
      the sibling user template as their base step, so the base step's
      annotations serve them (verified: byte-identical system blocks);
    - a ``.slots`` block is the interpolated payload of a field render —
      runtime values, ``contingent`` by construction [T-2]. Classified by RULE
      rather than by twenty table rows that would all say the same thing; the
      one place a slot payload carries authored doctrine
      (``action_selection_pdma.context_integration``, whose slots are other
      prompt fields) has an explicit entry and is caught by it.

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
    step, _, rest = block_id.partition(".")
    if rest and step.endswith("_image"):
        return annotation_for(f"{step[: -len('_image')]}.{rest}")
    if block_id.endswith(_SLOTS_SUFFIX):
        return BlockAnnotation(_C.CONTINGENT, None)
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
# Per-field block emission (#997): record the render seam, cover the message
# --------------------------------------------------------------------------


class _RecordedPart(NamedTuple):
    """One ``safe_format`` render, carrying the tag the COMPOSER computed.

    ``key`` is the block key (``<component>.<field>``, locale-stripped);
    ``label`` is what the row reports in its ``source`` column. ``frame`` /
    ``payload`` are the slot decomposition of the render — the authored literal
    segments and the interpolated runtime values — or ``None`` when the
    template carries no slot (then the render IS the frame) or when the
    decomposition could not be proven to reassemble.
    """

    key: str
    label: str
    text: str
    frame: Optional[str]
    payload: Optional[str]


class _MessagePiece(NamedTuple):
    """One emitted row's worth of a composed message."""

    block: str
    text: str
    source: str
    frame: Optional[str] = None
    payload: Optional[str] = None


#: ``"idma.evaluation_steps[en]"`` -> key ``"idma.evaluation_steps"``.
_PART_SOURCE_RE = re.compile(r"^(?P<key>.+)\[(?P<lang>[^\[\]]*)\]$")


def _part_key(source: str) -> str:
    """Strip the locale tag off a composer source; the key is the template field.

    The locale is dropped deliberately: block identity is the field, and the
    row already carries ``locale`` in its own column. Keeping it would make
    every block id locale-unique and the gate — which pairs on
    ``(locale, block_id)`` — would pair nothing.
    """
    match = _PART_SOURCE_RE.match(source)
    return match.group("key") if match is not None else source


def _segment_template(template: str, kwargs: Dict[str, Any], rendered: str) -> Optional[Tuple[str, str]]:
    """Split a render into (authored literals, interpolated values).

    Field-boundary splitting is necessary but not sufficient: three of the
    biggest fields carry live ``{slots}``, and a block that mixes authored
    doctrine with a runtime task description is ``mixed`` however cleanly the
    field boundary was found. The slot decomposition is available for free —
    ``safe_format`` receives the template AND the kwargs — and it is exact:
    ``string.Formatter().parse`` yields the same alternating literal/field
    sequence ``str.format`` itself consumes.

    Returns ``None`` (meaning: do not split) when the template has no slot, or
    when the reconstructed interleaving does not reproduce ``rendered`` byte
    for byte. That check is the whole safety argument — a decomposition that
    cannot be proven to reassemble is not reported.
    """
    formatter = string.Formatter()
    literals: List[str] = []
    values: List[str] = []
    interleaved: List[str] = []
    try:
        for literal, field_name, format_spec, conversion in formatter.parse(template):
            if literal:
                literals.append(literal)
                interleaved.append(literal)
            if field_name is None:
                continue
            obj, _ = formatter.get_field(field_name, (), kwargs)
            obj = formatter.convert_field(obj, conversion)
            spec = formatter.vformat(format_spec, (), kwargs) if format_spec else ""
            value = formatter.format_field(obj, spec)
            values.append(value)
            interleaved.append(value)
    except Exception:  # noqa: BLE001 - any parse/lookup failure means "do not split"
        return None
    if not values:
        return None
    if "".join(interleaved) != rendered:
        return None
    return "".join(literals), "".join(values)


def _locate_part(text: str, rendered: str, cursor: int) -> Tuple[int, str]:
    """Find ``rendered`` at or after ``cursor``. Returns ``(index, matched)``.

    Returns the substring ACTUALLY matched — that, not the render, is what the
    row reports, so the emitted pieces always reassemble to the message byte
    for byte.

    The trimmed candidates are not defensive padding. A composed system message
    is usually passed through ``format_system_prompt_blocks``
    (formatters/prompt_blocks.py), which ``.strip()``s the join, so the LAST
    field loses its trailing newline and no longer matches its own render.
    ``tsaspdma.closing_reminder`` is the live instance. A trimmed candidate
    differs from the render only in surrounding whitespace, so it cannot
    silently match different doctrine.
    """
    for candidate in (rendered, rendered.rstrip(), rendered.lstrip(), rendered.strip()):
        if not candidate:
            continue
        index = text.find(candidate, cursor)
        if index >= 0:
            return index, candidate
    return -1, ""


def _cover_message(text: str, pending: "Deque[_RecordedPart]") -> List[Tuple[_RecordedPart, int, int, str]]:
    """Consume, IN COMPOSITION ORDER, the parts that appear in ``text``.

    Strictly in order and strictly forward: the first part that is not found at
    or after the cursor ends this message's cover and stays queued for the next
    message. Order is what makes the attribution honest — a part matched out of
    order would be a guess, and guessing is what this module exists not to do.
    """
    cursor = 0
    spans: List[Tuple[_RecordedPart, int, int, str]] = []
    while pending:
        part = pending[0]
        if not part.text:
            pending.popleft()
            continue
        index, matched = _locate_part(text, part.text, cursor)
        if index < 0:
            break
        spans.append((part, index, index + len(matched), matched))
        cursor = index + len(matched)
        pending.popleft()
    return spans


def _split_message(
    text: str, parent: str, spans: Sequence[Tuple[_RecordedPart, int, int, str]]
) -> List[_MessagePiece]:
    """Split one composed message into field pieces plus NAMED residue.

    Contract, checked before returning: ``"".join(p.text for p in pieces) ==
    text``. Every byte the model receives is reported exactly once. Residue is
    named by WHERE it sits, not by an opaque ordinal, so the same kind of
    residue carries the same key across steps:

    - ``<parent>.head``    text before the first field;
    - ``<parent>.join<n>`` whitespace-only gap between two fields (the
      ``"\\n\\n"`` the composer joins with);
    - ``<parent>.gap<n>``  non-whitespace gap between two fields;
    - ``<parent>.tail``    text after the last field.
    """
    pieces: List[_MessagePiece] = []
    cursor = 0
    joins = 0
    gaps = 0
    for part, start, end, matched in spans:
        if start > cursor:
            residue = text[cursor:start]
            if not pieces:
                # Leading residue is `head` whether or not it is blank: it is
                # not a join BETWEEN two fields, and naming it by position
                # keeps the same residue under the same key across steps.
                pieces.append(_MessagePiece(f"{parent}.head", residue, "inline"))
            elif residue.strip():
                gaps += 1
                pieces.append(_MessagePiece(f"{parent}.gap{gaps}", residue, "inline"))
            else:
                joins += 1
                pieces.append(_MessagePiece(f"{parent}.join{joins}", residue, "inline"))
        exact = matched == part.text
        pieces.append(
            _MessagePiece(
                part.key,
                matched,
                part.label,
                part.frame if exact else None,
                part.payload if exact else None,
            )
        )
        cursor = end
    if cursor < len(text):
        pieces.append(_MessagePiece(f"{parent}.tail", text[cursor:], "inline"))
    joined = "".join(piece.text for piece in pieces)
    if joined != text:  # pragma: no cover - guarded invariant
        raise SystemExit(
            f"block split LOST BYTES for {parent}: pieces reassemble to {len(joined)} chars, "
            f"message is {len(text)} — the dump reports what the model receives or it reports nothing"
        )
    return pieces


def _expand_slots(piece: _MessagePiece) -> List[_MessagePiece]:
    """Second cut: authored frame vs interpolated payload, within one field.

    The payload is ``contingent`` by construction (a runtime task description,
    a snapshot, a prior DMA's result) and therefore out of Phase-1 scope [T-2];
    the frame is the authored doctrine, which is what an arm can hold or vary.
    Reported as two rows only when there IS a payload — a slot that rendered
    empty leaves the field exactly as authored, and a zero-byte row would be
    noise.
    """
    if piece.frame is None or not piece.payload:
        return [_MessagePiece(piece.block, piece.text, piece.source)]
    out: List[_MessagePiece] = []
    if piece.frame:
        out.append(_MessagePiece(piece.block, piece.frame, piece.source))
    out.append(_MessagePiece(f"{piece.block}.slots", piece.payload, f"{piece.source}#slots"))
    return out


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
        from ciris_engine.logic.dma.action_selection_pdma import ActionSelectionPDMAEvaluator
        from ciris_engine.logic.dma.dsaspdma import DSASPDMAEvaluator
        from ciris_engine.logic.dma.prompt_loader import DMAPromptLoader
        from ciris_engine.logic.dma.prompt_loader import safe_format as _safe_format
        from ciris_engine.logic.utils import constants as _constants
        from ciris_engine.logic.utils import localization as _localization

        self._real_accord: Callable[..., str] = _constants.get_accord_text
        self._real_localized: Callable[..., str] = _constants.get_localized_accord_text
        self._real_language_guidance: Callable[[str], str] = _localization.get_language_guidance
        self._real_prohibition: Callable[[str], str] = _localization.get_prohibition_guidance
        self._real_user_message: Callable[..., str] = DMAPromptLoader.get_user_message
        self._real_conscience_system: Callable[..., str] = ConsciencePromptLoader.get_system_prompt
        self._real_conscience_user: Callable[..., str] = ConsciencePromptLoader.get_user_prompt
        #: #997 — the PER-FIELD render seam. ``get_system_message`` appends up
        #: to seven fields, each through ``safe_format`` with the source the
        #: COMPOSER computes (``<component>.<field>[<lang>]``). Recording that
        #: call is how the dump learns a message's field boundaries without
        #: re-deriving the field list: it cannot disagree with the composer
        #: about what a message is made of.
        self._real_safe_format: Callable[..., str] = _safe_format
        self._real_aspdma_system: Callable[..., str] = ActionSelectionPDMAEvaluator._build_system_message
        self._real_dsaspdma_prompt: Callable[..., Optional[str]] = DSASPDMAEvaluator._get_prompt_value
        #: Parts recorded since the last ``take_parts()``. INSTANCE state, never
        #: a module global: one recorder is constructed per dump run
        #: (``compose_dump_rows``) and dies with it.
        self._parts: List[_RecordedPart] = []
        #: The accord as the CONSCIENCES see it (#986). They import the module
        #: constant ``ACCORD_TEXT`` directly rather than calling
        #: ``get_accord_text()``, so this text reaches an LLM having bypassed
        #: both ACCORD_MODE and ``override_corpus`` — it is the accord, and it
        #: is NOT routed. Recorded separately (never into ``routed``) so a
        #: genuinely routed registration always wins the label.
        #: #995 P0-1 CHANGED THIS. The faculties used to bind the module
        #: constant ``ACCORD_TEXT``, which is exactly why the accord reached
        #: them having bypassed both ACCORD_MODE and ``override_corpus``. They
        #: now call ``get_accord_text("force_full")``, so the text IS routed —
        #: but the dump must still recognise the block, and
        #: ``getattr(_conscience_core, "ACCORD_TEXT", "")`` now returns "",
        #: which would silently label every conscience accord block as inline.
        #: Resolve it the way the faculties do.
        self.conscience_accord: str = str(_constants.get_accord_text("force_full"))
        del _conscience_core  # bound above only to document the change
        #: exact content -> (block name, routed source label)
        self.routed: Dict[str, Tuple[str, str]] = {}
        #: #997 — the ordered ``(part_key, text)`` of the SPLIT
        #: ``prompts.language_guidance``, or ``[]`` for a locale that still
        #: carries the single scalar. Recorded, not re-derived: the composer's
        #: own join is what the dump reports, so the dump cannot disagree with
        #: it about where a part starts.
        self.language_guidance_parts: List[Tuple[str, str]] = []

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
        """Recording pass-through around ``localization.get_language_guidance``.

        Also captures the locale's PART decomposition (#997). Five locales (en,
        es, fr, it, pt) carry ``prompts.language_guidance`` as an ordered dict
        of single-class parts; the other 24 still carry the original scalar and
        record ``[]``, which reports one honestly-``mixed`` block exactly as
        before.
        """
        from ciris_engine.logic.utils.localization import language_guidance_parts

        value = self._real_language_guidance(lang_code)
        self.language_guidance_parts = language_guidance_parts(lang_code)
        return self._register(value, "language_guidance", "string:prompts.language_guidance")

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
        """Recording pass-through around ``ConsciencePromptLoader.get_system_prompt`` (#986).

        Named by the FIELD that produced it rather than by the message role
        (#997): the ``_image`` step composes the identical system calibration,
        so a component-keyed name lets one annotation cover both variants, and
        ``coherence`` and ``entropy`` stop sharing the bare ``system`` suffix
        with every other unrouted system message in the dump.
        """
        return self._register(
            self._real_conscience_system(loader, conscience_type),
            f"{conscience_type}.system_prompt",
            f"conscience_prompt:{conscience_type}.system_prompt",
        )

    def aspdma_system_message(self, builder: object, input_data: object) -> str:
        """Recording pass-through around ``ActionSelectionPDMAEvaluator._build_system_message``.

        ASPDMA assembles this message from Python literals, so there is no
        render seam to split it on and it stays honestly ``mixed``. What the
        registration buys is IDENTITY: five steps (first pass, two retries,
        ponder-notes, bounce advisory) compose this same block, and keying it to
        the composer instead of the step means one annotation and one ratchet
        entry rather than five copies of the same admission.

        Source stays ``inline`` — the block is identifiable, not routed, and
        the dump must not imply an override key that does not exist.
        """
        return self._register(
            self._real_aspdma_system(builder, input_data), "action_selection_pdma.system_message", "inline"
        )

    def dsaspdma_prompt_value(self, evaluator: object, key: str) -> Optional[str]:
        """Recording pass-through around ``DSASPDMAEvaluator._get_prompt_value`` (#997).

        DSASPDMA is the one DMA that reads its prompt fields directly and joins
        them itself, so neither ``get_system_message`` nor ``safe_format`` ever
        sees them — its 2,354 B system message and the 3,273 B rights/needs
        deferral taxonomy inside its user message were one ``mixed`` block each.
        This is the composer's own field funnel; recording it is the same trick
        one level down.
        """
        value = self._real_dsaspdma_prompt(evaluator, key)
        if isinstance(value, str) and value:
            self._parts.append(
                _RecordedPart(
                    key=f"dsaspdma.{key}",
                    label=f"dma_prompt:dsaspdma.{key}",
                    text=value,
                    frame=None,
                    payload=None,
                )
            )
        return value

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
        # #997: the loader renders that template through ``safe_format`` (lazy
        # import, conscience/prompt_loader.py:223), so ``format_part`` has
        # already recorded it — but under the source the CONSCIENCE loader
        # computes (``conscience.<type>[<lang>]``), which cannot tell the two
        # templates apart. Retag with the field that actually rendered: a block
        # keyed to a template that did not compose credits coverage to the
        # wrong override key.
        self._retag_last_part(
            value, f"{conscience_type}.{field}", f"conscience_prompt:{conscience_type}.{field}"
        )
        return self._register(value, "user", f"conscience_prompt:{conscience_type}.{field}")

    # -- #997: the per-field render seam ---------------------------------

    def format_part(self, template: str, *, source: str, **kwargs: Any) -> str:
        """Recording pass-through around ``prompt_loader.safe_format`` (#997).

        Returns the REAL render, unchanged. The recorded tuple carries the
        composer's own ``source`` tag, so the dump's field boundaries are the
        composer's field boundaries by construction — the same honesty rule
        ``routed`` follows one level up.
        """
        rendered = self._real_safe_format(template, source=source, **kwargs)
        key = _part_key(source)
        segmented = _segment_template(template, kwargs, rendered)
        self._parts.append(
            _RecordedPart(
                key=key,
                label=f"dma_prompt:{key}",
                text=rendered,
                frame=None if segmented is None else segmented[0],
                payload=None if segmented is None else segmented[1],
            )
        )
        return rendered

    def _retag_last_part(self, text: str, key: str, label: str) -> None:
        """Rename the part just recorded, when the caller knows a better key.

        Guarded on the text: if the last recorded part is not the render the
        caller is talking about, nothing is renamed. A wrong retag would be a
        lie about provenance, which is worse than a coarse key.
        """
        if self._parts and self._parts[-1].text == text:
            self._parts[-1] = self._parts[-1]._replace(key=key, label=label)

    def take_parts(self) -> List[_RecordedPart]:
        """Hand over (and clear) the parts recorded since the last call.

        Called once per composed step, so a field two steps render in one dump
        run (``tsaspdma`` and ``tsaspdma_correction`` share all four) can never
        be attributed to the wrong one.
        """
        parts, self._parts = self._parts, []
        return parts


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


def _thought_type_pieces(text: str, recorder: _RoutedRecorder) -> Optional[List[_MessagePiece]]:
    """Split ASPDMA's ``THOUGHT_TYPE=<...>\\n\\n<accord>`` message (#997).

    The composer builds this message by concatenating one runtime value onto
    the routed localized accord. Reporting it as ONE mixed block was the
    honesty rule applied at message granularity; at BLOCK granularity the seam
    is exact and needs no heuristic — the accord half matches a recorded
    loader output byte for byte, and what precedes it is the slot. Splitting
    turns 54,725 B of routed axiotic corpus from unmeasurable into varied.
    """
    if not text.startswith("THOUGHT_TYPE=") or "\n\n" not in text:
        return None
    head, rest = text.split("\n\n", 1)
    routed = recorder.routed.get(rest)
    if routed is None or routed[0] != "accord":
        return None
    return [
        _MessagePiece("thought_type", head + "\n\n", "inline"),
        _MessagePiece("accord", rest, routed[1]),
    ]


# --------------------------------------------------------------------------
# The dump
# --------------------------------------------------------------------------


def _language_guidance_pieces(
    text: str, source: str, recorder: _RoutedRecorder
) -> Optional[List[_MessagePiece]]:
    """Split the ``prompts.language_guidance`` message into its parts (#997).

    The block was 13,694 B of prose at ``en`` in which register doctrine,
    categorical prohibitions, crisis-line world-facts and value claims
    interleave sentence by sentence — one ``mixed`` block, so 100% of it was
    outside what the ablation could hold or vary. The corpus now carries it as
    an ordered dict of single-class parts in the five locales whose prose is
    line-for-line parallel to English; this reports that partition.

    Returns ``None`` — meaning "report one block, as before" — for a locale
    that still carries the scalar, and for ANY partition that cannot be proven
    against the composed bytes: a part not found at the cursor, a non-empty gap
    between two parts, or a reassembly that is not byte-exact. A partition the
    dump cannot prove is a guess, and this module does not guess.
    """
    if source != "string:prompts.language_guidance":
        return None
    parts = recorder.language_guidance_parts
    if not parts:
        return None
    pieces: List[_MessagePiece] = []
    cursor = 0
    for key, part_text in parts:
        if not part_text:
            continue
        index, matched = _locate_part(text, part_text, cursor)
        # Strictly adjacent, strictly forward. `get_language_guidance` joins the
        # parts with "" and strips once, so the only tolerated difference is the
        # whitespace `_locate_part` trims off the first and last part.
        if index != cursor:
            return None
        pieces.append(
            _MessagePiece(
                f"language_guidance.{key}",
                matched,
                f"string:prompts.language_guidance.{key}",
            )
        )
        cursor = index + len(matched)
    if cursor != len(text) or not pieces:
        return None
    if "".join(piece.text for piece in pieces) != text:  # pragma: no cover - guarded invariant
        return None
    return pieces


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
    parts: Sequence[_RecordedPart],
) -> List[ComposedBlock]:
    """One row per BLOCK (#997), where a block is a field, not a message.

    ``seq`` is the running block index within ``(locale, step)`` — it used to be
    the message index, and a message is no longer one row.
    """
    rows: List[ComposedBlock] = []
    unmatched: Dict[str, int] = {"system": 0, "user": 0}
    pending: Deque[_RecordedPart] = deque(parts)
    seq = 0
    for message in messages:
        role = str(message.get("role", ""))
        text = _content_text(message)
        base = "user" if role == "user" else "system"
        name, source = _identify_block(text, role, recorder, unmatched[base])
        if source == "inline" and (name.startswith("system") or name.startswith("user")):
            unmatched[base] += 1

        # ALWAYS cover, even a whole-routed message: a routed user message IS
        # its context_integration render, and leaving that part queued would
        # stall the NEXT message's cover behind it.
        spans = _cover_message(text, pending)
        if spans:
            covered = _split_message(text, name, spans)
        else:
            covered = (
                _language_guidance_pieces(text, source, recorder)
                or _thought_type_pieces(text, recorder)
                or [_MessagePiece(name, text, source)]
            )
        pieces: List[_MessagePiece] = []
        for piece in covered:
            pieces.extend(_expand_slots(piece))

        for piece in pieces:
            block_id = f"{step}.{piece.block}"
            # Whitespace-only pieces are the join the composer wrote, not
            # doctrine. Classified by RULE, not by table: a separator cannot
            # carry a claim, so it cannot be mis-annotated.
            annotation = (
                BlockAnnotation(_C.STRUCTURAL, None) if not piece.text.strip() else annotation_for(block_id)
            )
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
                    source=piece.source,
                    sha256=hashlib.sha256(piece.text.encode("utf-8")).hexdigest(),
                    bytes=len(piece.text.encode("utf-8")),
                    contaminant=list(annotation.contaminant) if annotation.contaminant is not None else None,
                    residue_hits=_scan_residue(_normalize_ws(piece.text), fragments),
                    token_hits=_scan_tokens(piece.text),
                    parent_block_id=None if len(pieces) == 1 else f"{step}.{name}",
                )
            )
            seq += 1
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

    def _format_part_seam(template: str, *, source: str, **kwargs: Any) -> str:
        """Plain function closed over the per-run recorder — no global state."""
        return recorder.format_part(template, source=source, **kwargs)

    def _aspdma_system_seam(builder: object, input_data: object) -> str:
        """Plain function, same descriptor-binding reason as above."""
        return recorder.aspdma_system_message(builder, input_data)

    def _dsaspdma_prompt_seam(evaluator: object, key: str) -> Optional[str]:
        """Plain function, same descriptor-binding reason as above."""
        return recorder.dsaspdma_prompt_value(evaluator, key)

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
            format_part=_format_part_seam,
            aspdma_system_message=_aspdma_system_seam,
            dsaspdma_prompt_value=_dsaspdma_prompt_seam,
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
                        messages,
                        step=step,
                        locale=locale,
                        arm=arm,
                        recorder=recorder,
                        fragments=fragments,
                        # Per STEP, so a field two steps render in one run is
                        # never attributed to the wrong one.
                        parts=recorder.take_parts(),
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


#: ``<parent>.join<n>`` — the whitespace the composer joins two fields with.
_JOIN_BLOCK_RE = re.compile(r"\.join\d+$")


def _regime_entry_for(regime: GateRegime, block_id: str) -> Optional[RegimeBlockEntry]:
    """Per-block regime entry: exact block_id, then step-suffix (see GateRegime)."""
    exact = regime.blocks.get(block_id)
    if exact is not None:
        return exact
    suffix = block_id.split(".", 1)[1] if "." in block_id else block_id
    return regime.blocks.get(suffix)


def load_regime(path: str) -> GateRegime:
    """Load a regime file as the Phase-1 gate view.

    A file declaring the FULL v2 schema (``ciris.ai/experimental_regime/v2``,
    #976) is parsed as ``ExperimentalRegimeV2`` and put through EVERY §10.4
    refusal first — a campaign manifest must not reach the gate by having its
    tiered DV, its holds and its kills silently ignored. The Phase-1 self-check
    regimes carry ``…/v2-phase1`` and load as the bare gate view, unchanged.
    """
    import yaml

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if isinstance(raw, dict) and raw.get("schema") == REGIME_SCHEMA_V2:
        from ciris_engine.logic.utils.regime_manifest import validate_regime

        regime = ExperimentalRegimeV2.model_validate(raw)
        validate_regime(regime)
        return regime.gate_view()
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
    # Whitespace-only separators between two fields are n/a by rule (#997) and
    # there are dozens of them. Collapsed to a count so the n/a line still shows
    # the blocks a reader could act on.
    separators = [name for name in na_blocks if _JOIN_BLOCK_RE.search(name)]
    listed = sorted(set(na_blocks) - set(separators))
    print(
        f"gate: n/a blocks: {', '.join(listed) if listed else 'none'}"
        f"{f' (+{len(separators)} whitespace-only field separators)' if separators else ''}"
    )
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
