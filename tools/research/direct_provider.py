"""Direct-provider harness — TORQUE's ``bare`` and ``values-ciris`` arms (#978).

FSD/RESEARCH_PROMPT_OVERRIDES.md §6.2, §10.3, §12, §14 step 11.

**Why this is not a CIRIS run.** No configuration of the H3ERE runtime yields a
bare prior: even fully blanked, a run still carries ASPDMA scaffolding, JSON
response-format coercion, the handler action enum, both bypass guardrails, and
the §6.1 residue. Approximating the baseline by turning CIRIS knobs produces a
fourth thing that is neither the baseline nor the pipeline, and labelling it the
baseline invalidates every comparison against it — which is why the override
loader REFUSES ``condition: "a"`` outright (2.9.9, R6). So the two
direct-provider arms come from here: a plain provider chat completion at
decoding parameters matched to the agent's, and nothing else.

Two arms:

``bare``
    No system content at all. Nothing but the arc's user turns.
``values-ciris``
    The arm injects a corpus's axiotic content as plain system content — the
    SAME SOURCE BYTES the h3ere arm holds. That is what makes the §12
    assertion-3 cross-harness half a real check: **source-hash injection, not
    composed-context equality** [M-3].

**The conversation is the independent unit** [M-7]. The battery threads ONE
``channel_id`` through its nine questions because "stage progression depends on
conversational context continuity" (``safety_battery.py`` ~:90-93). This runner
carries the full prior transcript forward on every turn. A stateless
per-question runner is a DIFFERENT INSTRUMENT and its numbers may not be placed
beside the h3ere arms [M-V2].

**DV honesty** [M-2]. There is no handler action enum on a plain provider call,
so ``action_tier`` (``selected_verb``, ``defer_rate``) does not exist for these
arms. Every row says so in words (``dv.action_tier == "undefined"``). It is
never emitted as a null, because a null in a defer column reads as "the model
chose not to defer" — a measurement claim this harness cannot make.
``text_tier`` (U-codes, refusal, resource_naming) is the comparable tier and it
is scored by the SAME battery scorer as every other arm
(``tools/safety/mh_battery_eval.py``).

Usage::

    # one arm, end to end
    python3 -m tools.research.direct_provider run \\
        --arm values-ciris --lang en \\
        --inject axiotic=corpus:accord.polyglot_compressed \\
        --model Qwen/Qwen3.6-35B-A3B \\
        --base-url https://api.deepinfra.com/v1/openai \\
        --key-file ~/.deepinfra_key \\
        --temperature 0.7 --top-p 1.0 --max-tokens 4096

    # score it through the battery scorer (same path as every other arm)
    python3 -m tools.safety.mh_battery_eval \\
        --results-jsonl qa_reports/safety_battery/<cell>/results.jsonl

    # the §12 gate's cross-harness half — compose-side block table
    python3 -m tools.research.direct_provider compose-dump \\
        --arm values-ciris --reference-dump /tmp/h3ere-ciris.jsonl \\
        --inject axiotic=corpus:accord.polyglot_compressed --out /tmp/dp.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.logic.utils import compose_dump as _compose_dump
from ciris_engine.schemas.dma.compose import (
    BlockClass,
    BlockDisposition,
    ComposedBlock,
    ComposeDumpMeta,
    RegimeArm,
)
from ciris_engine.schemas.types import JSONDict

# The battery is the instrument. Everything about the arc — which questions, in
# what order, in which locale, with the "User X said: '<...>'" wrapper stripped
# — is read from it, never re-specified here. That file is shared with the
# mental-health safety runs; this module imports it and does not touch it.
from tools.qa_runner.modules.safety_battery import (
    ISO_TO_LANG_DIR,
    REPORT_DIR,
    _capture_ci_provenance,
    _sha256_hex,
    _strip_question_wrapper,
    load_battery,
    slugify_model,
)

HARNESS = "direct-provider"

ARM_BARE = "bare"
ARM_VALUES_CIRIS = "values-ciris"
KNOWN_ARMS = (ARM_BARE, ARM_VALUES_CIRIS)

#: The DV representation for a tier that has no referent in this harness.
#: NOT ``None``, NOT ``""``, NOT ``0``. A null in a defer column reads as "did
#: not defer"; the honest statement is that the construct does not exist here.
DV_UNDEFINED = "undefined"
DV_DEFINED = "defined"

#: Reason strings for blocks with no direct-provider analogue (§10.3: declared
#: ``n/a`` per-arm in the dump — visible, never silently skipped).
NA_NO_ANALOGUE = "n/a:no-direct-provider-analogue"
NA_NOT_INJECTED = "n/a:not-injected-by-this-arm"

#: Classes §10.3 names as having no direct-provider analogue at all.
NO_ANALOGUE_CLASSES = frozenset({BlockClass.STRUCTURAL, BlockClass.PROCEDURAL})

_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class InjectedSource(BaseModel):
    """One corpus source this arm injects as plain system content.

    ``sha256`` is computed over the bytes THIS harness resolved and sent — not
    copied from the h3ere dump — so the cross-harness hold check catches a
    drifted corpus, a wrong ``CIRIS_ACCORD_MODE``, or a wrong locale.
    """

    model_config = ConfigDict(extra="forbid")

    block_class: BlockClass = Field(..., description="§10.2 class this source carries")
    source: str = Field(..., description="Dump `source` label, e.g. 'corpus:accord.polyglot_compressed'")
    sha256: str = Field(..., description="Hex SHA-256 over the resolved UTF-8 source bytes")
    bytes: int = Field(..., ge=0, description="UTF-8 byte length of the resolved source")


class DirectProviderDecoding(BaseModel):
    """Exactly what goes on the wire.

    §10.3 ``holds.decoding`` pins the decoding set with SET-EQUALITY semantics
    [M-6/M-N3] — pinned == transmitted, both directions — so this records the
    TRANSMITTED set. ``extra_body`` is a FUNCTION of ``base_url`` in the agent
    (``llm_service/service.py::_build_reasoning_off_extras``); this harness
    calls that very function rather than restating its table, so the two cannot
    drift apart.
    """

    model_config = ConfigDict(extra="forbid")

    model: str
    base_url: str
    temperature: float
    top_p: float
    max_tokens: int
    seed: Optional[int] = Field(
        default=None,
        description="CIRIS_LLM_SEED, OpenAI-compatible path only — same gate as service.py:1387",
    )
    extra_body: JSONDict = Field(default_factory=dict)

    def transmitted_keys(self) -> List[str]:
        """The parameter names actually sent — the set the manifest pins against."""
        keys = ["model", "messages", "temperature", "top_p", "max_tokens"]
        if self.seed is not None:
            keys.append("seed")
        if self.extra_body:
            keys.extend(f"extra_body.{k}" for k in sorted(self.extra_body))
        return sorted(keys)


class ChatTurn(BaseModel):
    """One message in the running transcript."""

    model_config = ConfigDict(extra="forbid")

    role: str
    content: str


class ArcTurn(BaseModel):
    """One question's result, plus the continuity evidence for that turn."""

    model_config = ConfigDict(extra="forbid")

    question_id: str
    question_version: int
    stage: str
    category: str
    question_text: str
    response_text: str
    duration_s: float
    success: bool
    error: Optional[str] = None
    turn_index: int = Field(..., ge=1, description="1-based position in the arc")
    prior_turns: int = Field(
        ...,
        ge=0,
        description="Messages already in the transcript when this turn's question was sent "
        "(system + every prior user/assistant pair) — the arc-continuity witness",
    )


class ArcRun(BaseModel):
    """A whole arc: one conversation, which is the independent unit [M-7]."""

    model_config = ConfigDict(extra="forbid")

    arm: str
    locale: str
    domain: str
    turns: List[ArcTurn]
    injected: List[InjectedSource]
    decoding: DirectProviderDecoding
    system_bytes: int

    @property
    def arc_intact(self) -> bool:
        """False if any turn failed: a broken transcript is not a scorable arc."""
        return all(t.success for t in self.turns)


# ---------------------------------------------------------------------------
# Decoding — matched to the agent by construction, never restated
# ---------------------------------------------------------------------------


def build_extra_body(base_url: str, model: str) -> JSONDict:
    """The ``extra_body`` the agent would transmit for this (base_url, model).

    Calls the agent's own per-endpoint dispatch. The two agent-only branches
    are deliberately omitted and named here rather than silently dropped:

    * the CIRIS-proxy ``metadata`` block carries ``task_id``/``thought_id`` —
      pipeline identity that has no referent in a plain provider call;
    * OpenRouter's ``provider`` routing config IS kept, because it decides
      which physical backend serves the request and that is a decoding-relevant
      hold, not agent identity.
    """
    from ciris_engine.logic.services.runtime.llm_service.service import (  # noqa: PLC0415
        OpenAICompatibleClient,
        _build_openrouter_provider_config,
    )

    extra: JSONDict = dict(OpenAICompatibleClient._build_reasoning_off_extras(base_url, model))
    if "openrouter.ai" in (base_url or ""):
        provider_config = _build_openrouter_provider_config()
        if provider_config.order or provider_config.ignore:
            extra["provider"] = provider_config.model_dump(exclude_defaults=True)
    return extra


def read_seed_env() -> Optional[int]:
    """``CIRIS_LLM_SEED``, same contract as ``service.py:1387``.

    Opt-in on purpose, and an unparseable value refuses rather than being
    silently dropped — under a pinned manifest a dropped determinism pin is
    worse than a crash.
    """
    raw = os.environ.get("CIRIS_LLM_SEED", "")
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        raise SystemExit(
            f"CIRIS_LLM_SEED must be an integer, got {raw!r} — "
            f"refusing to run with an unparseable determinism pin"
        )


# ---------------------------------------------------------------------------
# Source resolution — the same accessors the h3ere composition routes through
# ---------------------------------------------------------------------------


def resolve_source_bytes(source: str, locale: str) -> str:
    """Resolve a dump ``source`` label to the corpus text it names.

    Deliberately goes through the SAME accessors the h3ere composition routes
    through (``get_accord_text`` / ``get_localized_accord_text``, both of which
    honour ``CIRIS_ACCORD_MODE`` and the §5.2 in-memory research corpus
    substitution). Resolving independently is the whole point: if this returned
    the hash recorded in the reference dump, assertion 3 would be tautological.
    """
    if source == "corpus:accord.polyglot_compressed":
        from ciris_engine.logic.utils.constants import get_accord_text  # noqa: PLC0415

        return get_accord_text("compressed")
    if source == "corpus:accord.polyglot_full":
        from ciris_engine.logic.utils.constants import get_accord_text  # noqa: PLC0415

        return get_accord_text("force_full")
    if source == "corpus:accord.localized":
        from ciris_engine.logic.utils.constants import get_localized_accord_text  # noqa: PLC0415

        return get_localized_accord_text(locale)
    if source.startswith("file:"):
        return Path(source[len("file:") :]).expanduser().read_text(encoding="utf-8")
    raise SystemExit(
        f"unknown inject source {source!r}. Known: corpus:accord.polyglot_compressed, "
        f"corpus:accord.polyglot_full, corpus:accord.localized, file:<path>. "
        f"The label must be one an h3ere compose dump records in its `source` column, "
        f"or the cross-harness hold check has nothing to compare against."
    )


def resolve_injections(inject: Dict[str, str], locale: str) -> Tuple[List[InjectedSource], str]:
    """Resolve ``{class: source_label}`` into (records, concatenated system text).

    Sources are emitted in declaration order and joined with a blank line —
    the same join the agent's ``_coalesce_consecutive_roles`` performs when a
    strict provider forces multiple system messages into one.
    """
    records: List[InjectedSource] = []
    chunks: List[str] = []
    for raw_class, source in inject.items():
        try:
            block_class = BlockClass(raw_class)
        except ValueError:
            raise SystemExit(
                f"--inject: {raw_class!r} is not a §10.2 class. Known: "
                f"{', '.join(c.value for c in BlockClass)}"
            )
        text = resolve_source_bytes(source, locale)
        if not text:
            raise SystemExit(
                f"--inject {raw_class}={source}: resolved to EMPTY. An arm that injects nothing is "
                f"`bare`, not `{ARM_VALUES_CIRIS}` — §12 assertion 2 rejects empty replacements by "
                f"design, and mislabelling this arm invalidates the contrast it feeds."
            )
        encoded = text.encode("utf-8")
        records.append(
            InjectedSource(
                block_class=block_class,
                source=source,
                sha256=hashlib.sha256(encoded).hexdigest(),
                bytes=len(encoded),
            )
        )
        chunks.append(text)
    return records, "\n\n".join(chunks)


# ---------------------------------------------------------------------------
# The arc
# ---------------------------------------------------------------------------


async def complete_turn(
    client: AsyncOpenAI,
    decoding: DirectProviderDecoding,
    messages: Sequence[ChatTurn],
) -> str:
    """One plain chat completion.

    No ``response_format``, no instructor, no tool schema: JSON response
    coercion is §6.2 pipeline scaffolding, and a harness that carries it is not
    a bare prior.
    """
    seed_param: Dict[str, int] = {} if decoding.seed is None else {"seed": decoding.seed}
    extra_param: Dict[str, JSONDict] = {} if not decoding.extra_body else {"extra_body": decoding.extra_body}
    response = await client.chat.completions.create(
        model=decoding.model,
        messages=[turn.model_dump() for turn in messages],
        temperature=decoding.temperature,
        top_p=decoding.top_p,
        max_tokens=decoding.max_tokens,
        **seed_param,
        **extra_param,
    )
    choices = response.choices
    if not choices:
        return ""
    return choices[0].message.content or ""


async def run_arc(
    *,
    arm: str,
    battery: JSONDict,
    locale: str,
    client: AsyncOpenAI,
    decoding: DirectProviderDecoding,
    injected: Sequence[InjectedSource],
    system_text: str,
    limit: int = 0,
    on_turn: Optional[Callable[[ArcTurn], None]] = None,
) -> ArcRun:
    """Run the battery's arc as ONE conversation.

    Turn N is sent with the full transcript of turns 1..N-1 attached. This is
    the whole reason the harness exists in this shape: the battery threads one
    ``channel_id`` through the arc because stage progression depends on
    conversational context continuity, so a stateless per-question runner
    measures something else [M-V2].
    """
    questions = list(battery["questions"])  # type: ignore[call-overload]
    if limit > 0:
        questions = questions[:limit]

    transcript: List[ChatTurn] = []
    if system_text:
        transcript.append(ChatTurn(role="system", content=system_text))

    turns: List[ArcTurn] = []
    for index, question in enumerate(questions, 1):
        translations = question.get("translations", {})
        raw_text = translations.get(locale) or translations.get("en", "")
        question_text = _strip_question_wrapper(raw_text) if raw_text else ""
        if not question_text:
            turns.append(
                ArcTurn(
                    question_id=str(question["question_id"]),
                    question_version=int(question["question_version"]),
                    stage=str(question.get("stage", "")),
                    category=str(question.get("category", "")),
                    question_text="",
                    response_text="",
                    duration_s=0.0,
                    success=False,
                    error=f"no translation available for cell language {locale!r} or fallback 'en'",
                    turn_index=index,
                    prior_turns=len(transcript),
                )
            )
            continue

        prior_turns = len(transcript)
        transcript.append(ChatTurn(role="user", content=question_text))
        start = time.time()
        try:
            # list(...) — the request is captured as it was SENT; handing the
            # live list to the client would let later appends rewrite history.
            response_text = await complete_turn(client, decoding, list(transcript))
            duration = time.time() - start
            error: Optional[str] = None if response_text else "empty response body"
        except Exception as exc:  # noqa: BLE001 — one failed turn is recorded, not raised
            duration = time.time() - start
            response_text = ""
            error = f"{type(exc).__name__}: {exc}"

        if response_text:
            transcript.append(ChatTurn(role="assistant", content=response_text))
        else:
            # No fabricated assistant turn. The arc is now broken and
            # ArcRun.arc_intact says so; a broken transcript is not scorable.
            transcript.pop()

        turn = ArcTurn(
            question_id=str(question["question_id"]),
            question_version=int(question["question_version"]),
            stage=str(question.get("stage", "")),
            category=str(question.get("category", "")),
            question_text=question_text,
            response_text=response_text,
            duration_s=duration,
            success=bool(response_text),
            error=error,
            turn_index=index,
            prior_turns=prior_turns,
        )
        turns.append(turn)
        if on_turn is not None:
            on_turn(turn)

    return ArcRun(
        arm=arm,
        locale=locale,
        domain=str(battery["cell"]["domain"]),  # type: ignore[index]
        turns=turns,
        injected=list(injected),
        decoding=decoding,
        system_bytes=len(system_text.encode("utf-8")),
    )


# ---------------------------------------------------------------------------
# Capture — the battery's schema, byte-for-byte on the shared keys
# ---------------------------------------------------------------------------


def _dv_block() -> JSONDict:
    """The tiered DV, stated per row (§10.3 ``dv``)."""
    return {
        "action_tier": DV_UNDEFINED,
        "action_tier_reason": (
            "direct-provider harness: no handler action enum exists, so selected_verb and "
            "defer_rate have no referent. Emitted as the string 'undefined', never as null — "
            "a null in a defer column reads as 'did not defer', which is a measurement claim "
            "this harness cannot make (FSD §10.3 dv)."
        ),
        "text_tier": DV_DEFINED,
    }


def result_row(run: ArcRun, turn: ArcTurn, battery: JSONDict, run_id: str, as_user: str) -> JSONDict:
    """One ``ciris.ai/safety_battery_result/v1`` row.

    The shared keys are exactly ``SafetyBatteryTests._result_to_jsonl_row``'s,
    in the same order, so one scorer reads every arm. The direct-provider-only
    keys are additive.

    ``as_display_name`` is NULL on purpose: the battery's h3ere path creates a
    locale user so the agent reads ``user_preferred_name`` from the profile.
    That is dynamic context (§6.5), not template text — a bare provider call
    cannot receive it without adding system content, at which point the arm is
    no longer bare. Recording the locale display name here would claim the
    model saw a name it never saw.
    """
    return {
        "schema": "ciris.ai/safety_battery_result/v1",
        "run_id": run_id,
        "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "battery_id": battery["battery_id"],
        "battery_version": battery["battery_version"],
        "cell": battery["cell"],
        "question_id": turn.question_id,
        "question_version": turn.question_version,
        "stage": turn.stage,
        "category": turn.category,
        "as_user": as_user,
        "as_display_name": None,
        "question_text": turn.question_text,
        "agent_response": turn.response_text,
        "agent_task_id": None,
        "duration_s": round(turn.duration_s, 3),
        "success": turn.success,
        "error": turn.error,
        # ---- direct-provider additions (additive; the battery ignores them) --
        "harness": HARNESS,
        "arm": run.arm,
        "turn_index": turn.turn_index,
        "prior_turns": turn.prior_turns,
        "dv": _dv_block(),
    }


def summary_doc(run: ArcRun, battery: JSONDict, run_id: str, as_user: str, results_jsonl: Path) -> JSONDict:
    """``ciris.ai/safety_battery_summary/v1`` + the harness/decoding record."""
    n_success = sum(1 for t in run.turns if t.success)
    try:
        rel_jsonl = str(results_jsonl.relative_to(Path.cwd()))
    except ValueError:
        rel_jsonl = str(results_jsonl)
    return {
        "schema": "ciris.ai/safety_battery_summary/v1",
        "run_id": run_id,
        "battery_id": battery["battery_id"],
        "battery_version": battery["battery_version"],
        "cell": battery["cell"],
        "template_id": "n/a:direct-provider",
        "model": run.decoding.model,
        "as_user": as_user,
        "as_display_name": None,
        "n_questions": len(run.turns),
        "n_responses_captured": n_success,
        "n_errors": len(run.turns) - n_success,
        "total_duration_s": round(sum(t.duration_s for t in run.turns), 2),
        "results_jsonl": rel_jsonl,
        # ---- direct-provider additions --------------------------------------
        "harness": HARNESS,
        "arm": run.arm,
        "repeat_unit": "conversation",
        "arc_intact": run.arc_intact,
        "system_bytes": run.system_bytes,
        "dv": _dv_block(),
        "decoding": run.decoding.model_dump(),
        "transmitted_keys": run.decoding.transmitted_keys(),
        "injected_sources": [src.model_dump(mode="json") for src in run.injected],
    }


def manifest_doc(run: ArcRun, battery: JSONDict, run_id: str, results_dir: Path, started_at: str) -> JSONDict:
    """``ciris.ai/safety_battery_manifest_signed/v1`` + the harness record.

    ``agent_audit_anchors`` is EMPTY and stays empty: there is no agent, so
    there is no TPM-backed audit chain to anchor to. That absence is the point
    of the arm; papering over it with synthetic ids would fake provenance.
    """
    results_jsonl = results_dir / "results.jsonl"
    summary_path = results_dir / "summary.json"
    return {
        "schema": "ciris.ai/safety_battery_manifest_signed/v1",
        "run_id": run_id,
        "captured_at_start": started_at,
        "captured_at_end": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cell": battery["cell"],
        "battery_id": battery["battery_id"],
        "battery_version": battery["battery_version"],
        "rubric_sha256": battery.get("rubric_sha256"),
        "agent_id": None,
        "agent_name": None,
        "agent_version": None,
        "template_id": "n/a:direct-provider",
        "model": run.decoding.model,
        "model_slug": slugify_model(run.decoding.model),
        "live_base_url": run.decoding.base_url,
        "live_provider": "openai",
        "bundle": {
            "results_jsonl_sha256": _sha256_hex(results_jsonl) if results_jsonl.exists() else None,
            "summary_json_sha256": _sha256_hex(summary_path) if summary_path.exists() else None,
        },
        "agent_audit_anchors": [],
        "ci_provenance": _capture_ci_provenance(),
        # ---- direct-provider additions --------------------------------------
        "harness": HARNESS,
        "arm": run.arm,
        "arc_intact": run.arc_intact,
        "dv": _dv_block(),
        "decoding": run.decoding.model_dump(),
        "transmitted_keys": run.decoding.transmitted_keys(),
        "injected_sources": [src.model_dump(mode="json") for src in run.injected],
    }


def write_capture(run: ArcRun, battery: JSONDict, run_id: str, results_dir: Path, started_at: str) -> Path:
    """Write ``results.jsonl`` + ``summary.json`` + ``manifest_signed.json``."""
    results_dir.mkdir(parents=True, exist_ok=True)
    results_jsonl = results_dir / "results.jsonl"
    as_user = f"direct_provider_{run.locale}"
    with open(results_jsonl, "w", encoding="utf-8") as handle:
        for turn in run.turns:
            handle.write(json.dumps(result_row(run, turn, battery, run_id, as_user), ensure_ascii=False))
            handle.write("\n")
    with open(results_dir / "summary.json", "w", encoding="utf-8") as handle:
        json.dump(summary_doc(run, battery, run_id, as_user, results_jsonl), handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    with open(results_dir / "manifest_signed.json", "w", encoding="utf-8") as handle:
        json.dump(manifest_doc(run, battery, run_id, results_dir, started_at), handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return results_jsonl


# ---------------------------------------------------------------------------
# Compose-side stub for the §12 gate
# ---------------------------------------------------------------------------


def compose_stub_rows(
    *,
    arm: str,
    reference_rows: Sequence[ComposedBlock],
    inject: Dict[str, str],
) -> List[ComposedBlock]:
    """Project an h3ere block table into this arm's direct-provider table.

    The BLOCK SPACE is the h3ere composition's — a direct-provider call has no
    DMA steps of its own, so borrowing the reference's ``(locale, block_id)``
    keys is what lets the gate pair rows at all. The HASHES are this harness's:
    every carried row re-resolves its source from the corpus, so a divergence
    is a real finding and not a copy.

    Per row:

    * ``block_class`` in ``NO_ANALOGUE_CLASSES`` (structural / procedural) →
      ``n/a``: §10.3 names these as having no direct-provider analogue.
    * class not in this arm's ``inject`` map, or routed from a DIFFERENT source
      than the arm injects → ``n/a:not-injected-by-this-arm``. ``mixed`` blocks
      land here too: they are pipeline-composed scaffolding, and this harness
      composes none.
    * otherwise → the block is HELD across the harness boundary and carries the
      sha256 of the bytes this arm injects [M-3].

    Every row is emitted. ``n/a`` is declared per-arm and visible; nothing is
    silently skipped.
    """
    fragments = _compose_dump.residue_fragments()
    resolved: Dict[Tuple[str, str], str] = {}

    rows: List[ComposedBlock] = []
    for reference in reference_rows:
        wanted_source = inject.get(reference.block_class.value)
        carried = (
            reference.block_class not in NO_ANALOGUE_CLASSES
            and wanted_source is not None
            and wanted_source == reference.source
        )
        if carried and wanted_source is not None:
            key = (wanted_source, reference.locale)
            if key not in resolved:
                resolved[key] = resolve_source_bytes(wanted_source, reference.locale)
            text = resolved[key]
            encoded = text.encode("utf-8")
            rows.append(
                reference.model_copy(
                    update={
                        "arm": arm,
                        "disposition": BlockDisposition.HOLD,
                        "source": wanted_source,
                        "sha256": hashlib.sha256(encoded).hexdigest(),
                        "bytes": len(encoded),
                        "residue_hits": _compose_dump._scan_residue(_compose_dump._normalize_ws(text), fragments),
                        "token_hits": _compose_dump._scan_tokens(text),
                    }
                )
            )
            continue

        reason = NA_NO_ANALOGUE if reference.block_class in NO_ANALOGUE_CLASSES else NA_NOT_INJECTED
        rows.append(
            reference.model_copy(
                update={
                    "arm": arm,
                    "disposition": BlockDisposition.NOT_APPLICABLE,
                    "source": reason,
                    "sha256": _EMPTY_SHA256,
                    "bytes": 0,
                    "residue_hits": [],
                    "token_hits": [],
                }
            )
        )
    return rows


def compose_stub_meta(arm: str, reference_meta: ComposeDumpMeta) -> ComposeDumpMeta:
    """Meta for a direct-provider dump.

    ``residue_digest`` and ``fragment_count`` are recomputed against the live
    tree — not copied — because assertion 5 asks "was this dump produced
    against the tree being trusted?", and the answer is yes for both harnesses
    or the pairing is meaningless. ``conscience_guidance_mode`` is
    ``n/a:direct-provider``: there is no conscience layer here, and #986 asks
    that arm assignment be auditable from artifacts rather than from operator
    intention — so the absence is recorded rather than defaulted to ``full``.
    """
    return ComposeDumpMeta(
        arm=arm,
        manifest=None,
        locales=list(reference_meta.locales),
        steps=list(reference_meta.steps),
        residue_digest=_live_residue_digest(),
        fragment_count=len(_compose_dump.residue_fragments()),
        conscience_guidance_mode="n/a:direct-provider",
    )


def _live_residue_digest() -> str:
    from ciris_engine.logic.utils.research_overrides import compute_residue_digest  # noqa: PLC0415

    return compute_residue_digest()


# ---------------------------------------------------------------------------
# Arm resolution
# ---------------------------------------------------------------------------


def parse_inject_flags(values: Sequence[str]) -> Dict[str, str]:
    inject: Dict[str, str] = {}
    for raw in values:
        if "=" not in raw:
            raise SystemExit(f"--inject expects <class>=<source-label>, got {raw!r}")
        block_class, source = raw.split("=", 1)
        inject[block_class.strip()] = source.strip()
    return inject


def arm_from_regime(regime_path: str, arm: str) -> RegimeArm:
    """Read one arm out of a §10.3 regime manifest.

    Refuses an ``h3ere`` arm outright: presenting a pipeline arm as ``bare`` is
    a §10.4 refusal, and this harness is the reason that refusal is affordable.
    """
    import yaml  # noqa: PLC0415

    with open(regime_path, encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    arms = raw.get("arms") or {}
    if arm not in arms:
        raise SystemExit(f"{regime_path}: no arm {arm!r} (declared: {', '.join(sorted(arms)) or '<none>'})")
    spec = RegimeArm.model_validate(arms[arm])
    if spec.harness != HARNESS:
        raise SystemExit(
            f"{regime_path}: arm {arm!r} declares harness {spec.harness!r}. This runner is the "
            f"{HARNESS!r} harness only — an h3ere arm presented as a direct-provider arm is a "
            f"§10.4 refusal (there is no configuration of H3ERE that yields a bare prior, §6.2)."
        )
    return spec


def resolve_arm_inject(arm: str, inject: Dict[str, str]) -> Dict[str, str]:
    """Validate the arm/inject pairing. The arm name is a claim about content."""
    if arm == ARM_BARE and inject:
        raise SystemExit(
            f"arm {ARM_BARE!r} injects nothing by definition — it is the no-values baseline. "
            f"Got --inject {sorted(inject)}. Use --arm {ARM_VALUES_CIRIS} (or a regime arm name) "
            f"for an arm that carries values."
        )
    if arm == ARM_VALUES_CIRIS and not inject:
        raise SystemExit(
            f"arm {ARM_VALUES_CIRIS!r} with nothing to inject is {ARM_BARE!r} wearing another "
            f"name — pass --inject <class>=<source-label> (e.g. "
            f"axiotic=corpus:accord.polyglot_compressed) or declare inject: in --regime."
        )
    return inject


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _read_key(key: Optional[str], key_file: Optional[str]) -> str:
    if key:
        return key
    if key_file:
        return Path(key_file).expanduser().read_text(encoding="utf-8").strip()
    env_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if env_key:
        return env_key
    raise SystemExit("no API key: pass --key, --key-file, or set OPENAI_API_KEY")


def _cmd_run(args: argparse.Namespace) -> int:
    if args.lang not in ISO_TO_LANG_DIR:
        raise SystemExit(f"unknown language code {args.lang!r}; expected one of: {sorted(ISO_TO_LANG_DIR)}")

    inject = parse_inject_flags(args.inject or [])
    if args.regime:
        spec = arm_from_regime(args.regime, args.arm)
        inject = dict(spec.inject) or inject
    inject = resolve_arm_inject(args.arm, inject)

    battery: JSONDict = load_battery(args.lang, args.domain)
    injected, system_text = resolve_injections(inject, args.lang)

    decoding = DirectProviderDecoding(
        model=args.model,
        base_url=args.base_url,
        temperature=args.temperature,
        top_p=args.top_p,
        max_tokens=args.max_tokens,
        seed=read_seed_env(),
        extra_body=build_extra_body(args.base_url, args.model),
    )

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    results_dir = (
        Path(args.out).expanduser()
        if args.out
        else REPORT_DIR / f"{args.lang}_{args.domain}_{args.arm}_{run_id}"
    )

    client = AsyncOpenAI(
        api_key=_read_key(args.key, args.key_file),
        base_url=args.base_url,
        timeout=args.timeout,
    )

    n_questions = len(list(battery["questions"]))  # type: ignore[call-overload]
    n_arc = min(args.limit, n_questions) if args.limit > 0 else n_questions

    def _report(turn: ArcTurn) -> None:
        mark = "ok " if turn.success else "ERR"
        detail = f"{len(turn.response_text)} chars" if turn.success else (turn.error or "unknown error")
        print(
            f"[{mark}] ({turn.turn_index}/{n_arc}) {turn.question_id} "
            f"· prior_turns={turn.prior_turns} · {turn.duration_s:.1f}s · {detail}",
            flush=True,
        )

    print(
        f"direct-provider · arm={args.arm} · lang={args.lang} · model={args.model}\n"
        f"  base_url={args.base_url}\n"
        f"  transmitted={decoding.transmitted_keys()}\n"
        f"  injected={[(s.block_class.value, s.source, s.bytes) for s in injected] or '<none>'}\n"
        f"  action_tier={DV_UNDEFINED} (no handler action enum in this harness)",
        flush=True,
    )

    run = asyncio.run(
        run_arc(
            arm=args.arm,
            battery=battery,
            locale=args.lang,
            client=client,
            decoding=decoding,
            injected=injected,
            system_text=system_text,
            limit=args.limit,
            on_turn=_report,
        )
    )

    results_jsonl = write_capture(run, battery, run_id, results_dir, started_at)
    print(f"\ncapture: {results_dir}/  (results.jsonl, summary.json, manifest_signed.json)")
    print(f"arc_intact={run.arc_intact}  repeats.unit=conversation")
    print(f"score: python3 -m tools.safety.mh_battery_eval --results-jsonl {results_jsonl}")
    if args.sign:
        sig_path = _compose_dump.sign_dump(str(results_jsonl), args.arm)
        print(f"signed: {sig_path} (label={args.arm!r} sealed in the manifest)")
    return 0 if run.arc_intact else 1


def _cmd_compose_dump(args: argparse.Namespace) -> int:
    inject = parse_inject_flags(args.inject or [])
    if args.regime:
        spec = arm_from_regime(args.regime, args.arm)
        inject = dict(spec.inject) or inject
    inject = resolve_arm_inject(args.arm, inject)

    reference_meta, reference_rows = _compose_dump.load_dump(args.reference_dump)
    meta = compose_stub_meta(args.arm, reference_meta)
    rows = compose_stub_rows(arm=args.arm, reference_rows=reference_rows, inject=inject)
    _compose_dump.write_dump(meta, rows, args.out)

    n_held = sum(1 for r in rows if r.disposition is BlockDisposition.HOLD)
    n_na = len(rows) - n_held
    print(
        f"direct-provider compose stub: arm={args.arm} · {n_held} held (source-hash) · {n_na} n/a "
        f"(declared per-arm, never skipped)",
        file=sys.stderr,
    )
    if args.sign:
        if args.out is None:
            raise SystemExit("--sign requires --out: a signature covers a file's exact bytes, and stdout is not a file")
        sig_path = _compose_dump.sign_dump(args.out, args.arm)
        print(f"signed: {sig_path} (label={args.arm!r} sealed in the manifest)", file=sys.stderr)
    return 0


def _add_arm_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--arm", default=ARM_BARE, help=f"arm name (built-in: {', '.join(KNOWN_ARMS)})")
    parser.add_argument("--regime", default=None, help="§10.3 regime manifest YAML to read the arm's inject: from")
    parser.add_argument(
        "--inject",
        action="append",
        default=None,
        metavar="CLASS=SOURCE",
        help="inject a corpus source as plain system content, e.g. "
        "axiotic=corpus:accord.polyglot_compressed (repeatable)",
    )
    parser.add_argument(
        "--sign",
        action="store_true",
        help="sign the emitted artifact via ciris_server.sign_object (>=0.5.154), label = arm name "
        "sealed in-envelope. OPT-IN: sign_object needs the live folded-node runtime in-process, "
        "which a bare provider harness does not have — see the module docstring.",
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m tools.research.direct_provider",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="run the battery arc as one conversation against a provider")
    _add_arm_args(run_p)
    run_p.add_argument("--lang", default="en", help="ISO 639-1 cell language")
    run_p.add_argument("--domain", default="mental_health")
    run_p.add_argument("--model", required=True, help="CASE-SENSITIVE provider model id")
    run_p.add_argument("--base-url", required=True, help="OpenAI-compatible endpoint (pins extra_body [M-N3])")
    run_p.add_argument("--key", default=None)
    run_p.add_argument("--key-file", default=None)
    run_p.add_argument("--temperature", type=float, required=True, help="pinned by holds.decoding")
    run_p.add_argument("--top-p", type=float, default=1.0)
    run_p.add_argument("--max-tokens", type=int, default=4096)
    run_p.add_argument("--timeout", type=float, default=1800.0)
    run_p.add_argument("--limit", type=int, default=0, help="first N questions (cycle-time mode — NOT a scored arc)")
    run_p.add_argument("--out", default=None, help="capture dir (default: qa_reports/safety_battery/<cell>_<arm>_<ts>)")

    dump_p = sub.add_parser("compose-dump", help="emit this arm's ComposedBlock table for the §12 gate")
    _add_arm_args(dump_p)
    dump_p.add_argument("--reference-dump", required=True, help="an h3ere compose_dump JSONL — defines the block space")
    dump_p.add_argument("--out", default=None, help="output JSONL path (default: stdout)")

    args = parser.parse_args(argv)
    if args.command == "run":
        return _cmd_run(args)
    return _cmd_compose_dump(args)


if __name__ == "__main__":
    sys.exit(main())
