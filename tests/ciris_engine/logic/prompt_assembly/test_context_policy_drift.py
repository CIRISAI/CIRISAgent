"""The engine's policy and the formal model share one source (FSD/PROMPT_CONTEXT_PROVENANCE.md §5, §11).

- the engine's enums are exactly gen_contract_policy.py's closed vocabulary;
- the engine's predicate evaluation holds in exactly the scenarios PRED_SCEN says;
- the engine's judges are the generator's JUDGES, and every stage the model consumes is an engine stage;
- gen_contract_policy.py run on the ENGINE's context_policy.yaml emits the committed ContractPolicy.tla
  byte for byte, and the engine's yaml is the formal directory's yaml.
"""

import importlib.util
import pathlib
import shutil
import subprocess
import sys

import pytest

from ciris_engine.logic.prompt_assembly.policy import DEFAULT_POLICY_PATH, STAGE_ROLES, load_context_policy, predicate_holds
from ciris_engine.schemas.context.prompt_provenance import (
    Lifecycle,
    PolicyFacts,
    PolicyPredicate,
    PromptStage,
    RuleProvenance,
    SegmentForm,
    SegmentKind,
    StageRole,
    StubField,
    TrustLevel,
)

REPO = pathlib.Path(__file__).resolve().parents[4]
FORMAL = REPO / "formal" / "h3ere_ctxflow"


@pytest.fixture(scope="module")
def gen():
    spec = importlib.util.spec_from_file_location("gen_contract_policy", FORMAL / "gen_contract_policy.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: The model's scenarios S1..S6 (formal/h3ere_ctxflow/README.md) as the facts the system would establish.
SCENARIO_FACTS = {
    "S1": PolicyFacts(),
    "S2": PolicyFacts(advisory_rule=True),  # a user states a rule in their own message
    "S3": PolicyFacts(advisory_rule=True),  # the WA states a rule in chat (advisory until signed)
    "S4": PolicyFacts(signed_guidance_in_force=True),
    "S5": PolicyFacts(amendment_in_force=True),
    "S6": PolicyFacts(amendment_in_force=True, id_scoped=True),
}


def test_vocabulary_matches_the_generator(gen):
    assert {k.value for k in SegmentKind} == gen.KINDS
    assert {p.value for p in RuleProvenance} == gen.PROVENANCES
    assert {t.value for t in TrustLevel} == gen.TRUST
    assert {lc.value for lc in Lifecycle} == gen.LIFECYCLE
    assert {p.value for p in PolicyPredicate} == gen.PREDICATES
    assert {f.value for f in StubField} == gen.STUB_FIELDS
    assert {f.value for f in SegmentForm} == gen.FORMS


def test_predicates_hold_in_exactly_the_generators_scenarios(gen):
    assert set(gen.PRED_SCEN) == {p.value for p in PolicyPredicate}
    for pred in PolicyPredicate:
        holds = {s for s, facts in SCENARIO_FACTS.items() if predicate_holds(pred, facts, retry=False)}
        assert holds == gen.PRED_SCEN[pred.value], pred


def test_stages_match_the_model(gen):
    judges = {s.value for s, role in STAGE_ROLES.items() if role == StageRole.JUDGE}
    assert judges == set(gen.JUDGES)
    assert set(gen.MODEL_STAGES) <= {s.value for s in PromptStage}
    assert set(STAGE_ROLES) == set(PromptStage)
    policy = load_context_policy()
    assert set(gen.MODEL_STAGES) <= {s.value for s in policy.stages}


def test_engine_policy_is_the_formal_policy():
    """One file: the formal copy is a symlink to the engine's, so they cannot drift."""
    formal = FORMAL / "context_policy.yaml"
    assert formal.is_symlink()
    assert formal.resolve() == DEFAULT_POLICY_PATH.resolve()
    assert DEFAULT_POLICY_PATH.read_bytes() == formal.read_bytes()


def test_generator_on_the_engine_policy_emits_the_committed_contract(tmp_path):
    work = tmp_path / "w"
    work.mkdir()
    # The generator writes its source path into the header: run it on the engine's file under that name.
    shutil.copyfile(DEFAULT_POLICY_PATH, work / "context_policy.yaml")
    out = tmp_path / "ContractPolicy.tla"
    subprocess.run(
        [sys.executable, str(FORMAL / "gen_contract_policy.py"), "context_policy.yaml", str(out)],
        cwd=work,
        check=True,
        capture_output=True,
    )
    assert out.read_bytes() == (FORMAL / "ContractPolicy.tla").read_bytes()


def test_the_engine_loader_reads_every_row(gen):
    """Every row of the yaml is in the typed table, in file order (the rendering order)."""
    import yaml

    raw = yaml.safe_load(DEFAULT_POLICY_PATH.read_bytes())
    policy = load_context_policy()
    for stage_name, rows in raw["stages"].items():
        typed = policy.stages[PromptStage(stage_name)]
        assert [r.key for r in typed] == list(rows)
        cells = [c if isinstance(c, dict) else {"when": c, "form": "full"} for c in rows.values()]
        assert [r.predicate.value for r in typed] == [c["when"] for c in cells]
        assert [r.form.value for r in typed] == [c.get("form", "full") for c in cells]
    assert [s.value for s in policy.ablated_stages] == raw["ablated_stages"]
    assert [f.value for f in policy.stub_fields] == raw["stub_fields"]
