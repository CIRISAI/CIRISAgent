"""Load context_policy.yaml into the typed policy table (FSD/PROMPT_CONTEXT_PROVENANCE.md §5).

The engine's copy lives at ``ciris_engine/data/context_policy.yaml``: ``ciris_engine/data`` is the shipped
non-code input directory (MANIFEST.in includes it recursively, and it is staged into the signed runtime tree), and
the file is named exactly as in ``formal/h3ere_ctxflow`` so ``gen_contract_policy.py`` run on it emits the
committed ``ContractPolicy.tla`` byte for byte (the generator writes the source path into its header). One source
for the guard and the TLA+ contract; tests fail if they drift.

Unknown names are errors: every value must parse into the closed enums of ``schemas/context/prompt_provenance``.
"""

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Tuple

import yaml

from ciris_engine.schemas.context.prompt_provenance import (
    ContextPolicy,
    KindSpec,
    Lifecycle,
    PolicyFacts,
    PolicyPredicate,
    PolicyRow,
    PromptStage,
    RuleProvenance,
    STUB_DISPOSITIONS,
    SegmentForm,
    SegmentKind,
    SegmentSource,
    StageRole,
    StubField,
    TrustLevel,
)

DEFAULT_POLICY_PATH = Path(__file__).resolve().parents[2] / "data" / "context_policy.yaml"

#: The part each stage plays (FSD §3). The judges are gen_contract_policy.JUDGES.
STAGE_ROLES: Dict[PromptStage, StageRole] = {
    PromptStage.ASPDMA: StageRole.DRAFTER,
    PromptStage.TSASPDMA: StageRole.SECOND_PASS,
    PromptStage.DSASPDMA: StageRole.SECOND_PASS,
    PromptStage.FSASPDMA: StageRole.SECOND_PASS,
    PromptStage.MSASPDMA: StageRole.SECOND_PASS,
    PromptStage.RSASPDMA: StageRole.SECOND_PASS,
    PromptStage.CSDMA: StageRole.EVALUATOR,
    PromptStage.DSDMA: StageRole.EVALUATOR,
    PromptStage.PDMA: StageRole.EVALUATOR,
    PromptStage.IDMA: StageRole.EVALUATOR,
    PromptStage.COHERENCE: StageRole.JUDGE,
    PromptStage.ENTROPY: StageRole.JUDGE,
    PromptStage.EPISTEMIC: StageRole.JUDGE,
    PromptStage.OPTVETO: StageRole.JUDGE,
}

#: Predicates under which a row's segment is REQUIRED when the predicate holds, not merely allowed. The TLA+
#: contract reads every holding predicate as "present"; at runtime ``always`` and ``advisory_rule`` rows are
#: allowance only (not every message has history or a display name; an own-turn preference is optional), while
#: the state-conditioned rows are the evidence the judges must not lack (FSD §5 ``require``, §14).
REQUIRING_PREDICATES = frozenset(
    {
        PolicyPredicate.TRUSTED_RULE_IN_FORCE,
        PolicyPredicate.SIGNED_GUIDANCE_IN_FORCE,
        PolicyPredicate.AMENDMENT_IN_FORCE,
        PolicyPredicate.ID_SCOPED,
        PolicyPredicate.RETRY,
    }
)

#: Kinds every call must carry wherever the policy allows them: the stage's own prompt.
ALWAYS_REQUIRED_KINDS = frozenset({SegmentKind.STAGE_INSTRUCTION})

#: Kinds whose state-conditioned rows ALLOW, never require. The evidence a stage must not lack when a trusted rule
#: is in force is the verified ``rule`` segment (FSD §5 ``require: {kind: rule, when: trusted_rule_in_force}``, §14):
#: the grant (``wa_guidance``) and the identity text (``amendment``) may accompany it, and one signed entry is never
#: required twice under two kinds.
ALLOWANCE_ONLY_KINDS = frozenset({SegmentKind.WA_GUIDANCE, SegmentKind.AMENDMENT})


def row_is_required(row: PolicyRow) -> bool:
    """Whether the row's segment must be present whenever its predicate holds."""
    if row.kind in ALWAYS_REQUIRED_KINDS:
        return True
    return row.predicate in REQUIRING_PREDICATES and row.kind not in ALLOWANCE_ONLY_KINDS


class ContextPolicyError(ValueError):
    """The policy file is malformed or uses a name outside the closed vocabulary."""


def predicate_holds(predicate: PolicyPredicate, facts: PolicyFacts, retry: bool) -> bool:
    """Evaluate one policy predicate against the system's facts."""
    table = {
        PolicyPredicate.ALWAYS: True,
        PolicyPredicate.NEVER: False,
        PolicyPredicate.TRUSTED_RULE_IN_FORCE: facts.trusted_rule_in_force,
        PolicyPredicate.ID_SCOPED: facts.id_scoped,
        PolicyPredicate.SIGNED_GUIDANCE_IN_FORCE: facts.signed_guidance_in_force,
        PolicyPredicate.AMENDMENT_IN_FORCE: facts.amendment_in_force,
        PolicyPredicate.ADVISORY_RULE: facts.advisory_rule,
        PolicyPredicate.RETRY: retry,
    }
    return table[predicate]


def _required_flag(attrs: Mapping[str, object], name: str, kind: str) -> bool:
    value = attrs.get(name)
    if value is None:
        return False
    if value != "required":
        raise ContextPolicyError(f"{kind}.{name}: only 'required' is valid, got {value!r}")
    return True


def _parse_kind(kind_name: str, attrs: Mapping[str, object]) -> Tuple[SegmentKind, KindSpec]:
    known = {"trust", "lifecycle", "authn", "authz", "acct", "render", "residual", "source", "unused"}
    unknown = set(attrs) - known
    if unknown:
        raise ContextPolicyError(f"kind {kind_name!r}: unknown attributes {sorted(unknown)}")
    render = attrs.get("render")
    if render not in (None, "labelled"):
        raise ContextPolicyError(f"kind {kind_name!r}: unknown render {render!r}")
    trust = attrs.get("trust")
    source = attrs.get("source")
    return SegmentKind(kind_name), KindSpec(
        trust=TrustLevel(str(trust)) if trust is not None else None,
        lifecycle=Lifecycle(str(attrs.get("lifecycle"))),
        authn_required=_required_flag(attrs, "authn", kind_name),
        authz_required=_required_flag(attrs, "authz", kind_name),
        acct_required=_required_flag(attrs, "acct", kind_name),
        render_labelled=render == "labelled",
        residual=bool(attrs.get("residual", False)),
        source=SegmentSource(str(source)) if source is not None else None,
    )


def _parse_row(stage: str, key: str, cell: object, kinds: Mapping[SegmentKind, KindSpec]) -> PolicyRow:
    """One cell: a predicate, or ``{when: <predicate>, form: full|stub}`` (FSD §6a)."""
    kind_name, _, prov_name = key.partition(".")
    predicate: object = cell
    form_name: object = SegmentForm.FULL.value
    if isinstance(cell, dict):
        if set(cell) - {"when", "form"}:
            raise ContextPolicyError(f"{stage}.{key}: a cell is a predicate or {{when, form}}")
        predicate = cell.get("when", PolicyPredicate.ALWAYS.value)
        form_name = cell.get("form", SegmentForm.FULL.value)
    try:
        kind = SegmentKind(kind_name)
        provenance = RuleProvenance(prov_name) if prov_name else None
        pred = PolicyPredicate(str(predicate))
        form = SegmentForm(str(form_name))
    except ValueError as exc:
        raise ContextPolicyError(f"{stage}.{key}: {exc}") from exc
    if kind not in kinds:
        raise ContextPolicyError(f"{stage}.{key}: kind not declared")
    if (provenance is not None) != (kind == SegmentKind.RULE):
        raise ContextPolicyError(f"{stage}.{key}: a provenance is required on rule rows and only on them")
    return PolicyRow(kind=kind, provenance=provenance, predicate=pred, form=form)


def _check_stubs_and_firewall(
    stages: Mapping[PromptStage, List[PolicyRow]],
    ablated: List[PromptStage],
    kinds: Mapping[SegmentKind, KindSpec],
    provenance: Mapping[RuleProvenance, TrustLevel],
    stub_fields: List[StubField],
) -> None:
    """The compiler's §6a checks, at load: the engine refuses a policy the model would refuse."""

    def trust_of(row: PolicyRow) -> Optional[TrustLevel]:
        return provenance[row.provenance] if row.provenance is not None else kinds[row.kind].trust

    for stage, rows in stages.items():
        for row in rows:
            if row.form != SegmentForm.STUB:
                continue
            if stage not in ablated:
                raise ContextPolicyError(f"{stage.value}.{row.key}: stub form is for ablated stages only")
            if trust_of(row) != TrustLevel.UNTRUSTED:
                raise ContextPolicyError(f"{stage.value}.{row.key}: only untrusted segments are stubbed")
            if not stub_fields:
                raise ContextPolicyError("stub form used but no stub_fields declared")
            if row.kind.value not in STUB_DISPOSITIONS:
                raise ContextPolicyError(f"{stage.value}.{row.key}: no disposition vocabulary for kind {row.kind.value}")
    for stage in ablated:
        for row in stages[stage]:
            if row.predicate == PolicyPredicate.NEVER:
                continue
            untrusted = trust_of(row) == TrustLevel.UNTRUSTED
            if untrusted and row.form != SegmentForm.STUB and not kinds[row.kind].residual:
                raise ContextPolicyError(f"firewall: ablated stage {stage.value} allows untrusted {row.key} in full")


def parse_context_policy(raw: bytes) -> ContextPolicy:
    """Parse policy bytes into the typed table; raises ContextPolicyError on anything outside the vocabulary."""
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ContextPolicyError("policy root must be a mapping")
    try:
        kinds = dict(_parse_kind(str(k), v or {}) for k, v in data["kinds"].items())
        provenance = {RuleProvenance(str(k)): TrustLevel(str(v)) for k, v in data["rule_provenance"].items()}
        stages: Dict[PromptStage, List[PolicyRow]] = {}
        for stage_name, rows in data["stages"].items():
            stage = PromptStage(str(stage_name))
            # YAML anchors alias ONE dict across stages: copy before reading, so no stage's cells are another's.
            cells = dict(rows)
            stages[stage] = [_parse_row(stage.value, str(key), cell, kinds) for key, cell in cells.items()]
        ablated = [PromptStage(str(s)) for s in data["ablated_stages"]]
        stub_fields = [StubField(str(f)) for f in data.get("stub_fields") or []]
        version = int(data["version"])
    except (KeyError, TypeError, AttributeError) as exc:
        raise ContextPolicyError(f"policy is missing or misshapes a section: {exc!r}") from exc
    except ValueError as exc:
        if isinstance(exc, ContextPolicyError):
            raise
        raise ContextPolicyError(str(exc)) from exc
    if SegmentKind.RULE in kinds and kinds[SegmentKind.RULE].trust is not None:
        raise ContextPolicyError("rule trust comes from its provenance, not the kind")
    for kind, spec in kinds.items():
        if kind != SegmentKind.RULE and spec.trust is None:
            raise ContextPolicyError(f"kind {kind.value!r} declares no trust")
    for stage in ablated:
        if stage not in stages:
            raise ContextPolicyError(f"ablated stage {stage.value!r} has no rows")
    if len(set(stub_fields)) != len(stub_fields):
        raise ContextPolicyError("stub_fields lists a field twice")
    _check_stubs_and_firewall(stages, ablated, kinds, provenance, stub_fields)
    return ContextPolicy(
        version=version,
        ablated_stages=ablated,
        kinds=kinds,
        rule_provenance=provenance,
        stages=stages,
        stub_fields=stub_fields,
        source_sha256=hashlib.sha256(raw).hexdigest(),
    )


def load_context_policy(path: Optional[Path] = None) -> ContextPolicy:
    """Load a policy file (the engine's own when ``path`` is None)."""
    if path is None:
        return _default_policy()
    return parse_context_policy(Path(path).read_bytes())


@lru_cache(maxsize=1)
def _default_policy() -> ContextPolicy:
    return parse_context_policy(DEFAULT_POLICY_PATH.read_bytes())


def declared_trust(policy: ContextPolicy, kind: SegmentKind, provenance: Optional[RuleProvenance]) -> TrustLevel:
    """The policy's trust for a kind (for a rule, its provenance's)."""
    if provenance is not None:
        return policy.rule_provenance[provenance]
    trust = policy.kinds[kind].trust
    if trust is None:  # parse_context_policy refuses this for every kind but rule
        raise ContextPolicyError(f"kind {kind.value!r} has no trust")
    return trust


__all__ = [
    "ALLOWANCE_ONLY_KINDS",
    "ALWAYS_REQUIRED_KINDS",
    "ContextPolicyError",
    "DEFAULT_POLICY_PATH",
    "REQUIRING_PREDICATES",
    "STAGE_ROLES",
    "declared_trust",
    "load_context_policy",
    "parse_context_policy",
    "predicate_holds",
    "row_is_required",
]
