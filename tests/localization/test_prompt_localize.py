"""The prompts target of the i18n lane -- DMA and conscience templates (``localization/prompt_localize.py``).

Offline: no model is called. What is asserted is the bridge around the vendored
pipeline -- what gets staged as "missing", what a translated block must still do
before it is written, and that writing one field leaves the rest of the file
byte-identical.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Dict

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "localization"))

import lane_shards as LS  # noqa: E402
import prompt_localize as PL  # noqa: E402

ENGLISH = """component_name: demo
description: "A demo template"
version: "1.0"

# PROCEDURAL — what this step is.
system_guidance_header: |
  You have selected RECALL. Say what to read.

  Look at CANDIDATE NODES first.

# PRAGMATIC — the wire contract.
response_format: |
  Respond with JSON:

  {{
    "final_action": "RECALL" | "SPEAK",
    "node_id": "exact node id"
  }}

context_integration: |
  Original thought:
  {original_thought_content}

closing_reminder: |
  Do not write to `identity` scope.
"""

SPANISH: Dict[str, str] = {
    "description": "Una plantilla de demostración",
    "system_guidance_header": "Has seleccionado RECALL. Di qué leer.\n\nMira primero los NODOS CANDIDATOS.\n",
    "response_format": 'Responde con JSON:\n\n{{\n  "final_action": "RECALL" | "SPEAK",\n  "node_id": "id exacto del nodo"\n}}\n',
    "context_integration": "Pensamiento original:\n{original_thought_content}\n",
    "closing_reminder": "No escribas en el ámbito `identity`.\n",
}


@pytest.fixture
def prompts(tmp_path: Path) -> Path:
    """A one-template prompt tree whose es/ copy is the hand-committed English one."""
    root = tmp_path / "prompts"
    (root / "localized" / "es").mkdir(parents=True)
    (root / "demo.yml").write_text(ENGLISH, encoding="utf-8")
    header = f"{PL.ENGLISH_COPY_MARKER} (#1027). Not translated yet.\n# --- Translation is future work.\n"
    (root / "localized" / "es" / "demo.yml").write_text(header + ENGLISH, encoding="utf-8")
    return root


def _stage(tmp_path: Path, values: Dict[str, str]) -> Path:
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "es.json").write_text(json.dumps({"demo": values}, ensure_ascii=False), encoding="utf-8")
    return stage


# ──────────────────────────────────────────────
# Staging: English left in a locale is "missing"
# ──────────────────────────────────────────────


def test_an_english_copy_stages_as_entirely_missing(prompts: Path) -> None:
    en = PL.english_bundle(prompts)
    assert set(en["demo"]) == set(SPANISH)  # component_name and version are not prose
    assert PL.locale_bundle("es", en, prompts) == {}


def test_a_translated_field_is_staged_and_an_english_one_is_not(prompts: Path) -> None:
    path = prompts / "localized" / "es" / "demo.yml"
    path.write_text(PL.set_field(path.read_text(encoding="utf-8"), "description", SPANISH["description"]), "utf-8")
    assert PL.locale_bundle("es", PL.english_bundle(prompts), prompts) == {
        "demo": {"description": SPANISH["description"]}
    }


def test_fields_that_are_english_by_design_are_never_offered_for_translation() -> None:
    keys = set(PL.flat(PL.english_bundle()))
    assert keys.isdisjoint(PL.ENGLISH_BY_DESIGN)
    # ...and they really are the byte-identical English the chain tests exempt.
    for key in PL.ENGLISH_BY_DESIGN:
        template, field = key.split(".", 1)
        english = PL.read_template(PL.locale_path(PL.PROMPTS, "en", template))[field]
        for lang in PL.languages()[1:]:
            assert PL.read_template(PL.locale_path(PL.PROMPTS, lang, template))[field] == english, (lang, key)


def test_the_pipeline_position_is_translatable_and_the_pre_split_tail_is_not() -> None:
    """#1366 item 12: the paragraph is a field the lane translates; the rest of the header waits for the
    locale headers to be split (each still holds the whole pre-split translation)."""
    en = PL.english_bundle()
    with_position = sorted(t for t, fields in en.items() if "pipeline_position" in fields)
    assert len(with_position) == 13, with_position  # 10 DMA stages + 3 localized consciences
    assert not any(f.endswith("_tail") for fields in en.values() for f in fields)
    assert not any(f"{t}.pipeline_position" in PL.ENGLISH_BY_DESIGN for t in en)


def test_the_real_stage_is_a_bundle_the_vendored_pipeline_can_read(tmp_path: Path) -> None:
    en = PL.build_stage(tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["languages"][0] == "en" and len(manifest["languages"]) == 29
    assert json.loads((tmp_path / "en.json").read_text(encoding="utf-8")) == en
    assert "msaspdma" in json.loads((tmp_path / "es.json").read_text(encoding="utf-8"))  # already translated


# ──────────────────────────────────────────────
# What a translated block must still do
# ──────────────────────────────────────────────

_EN_FORMAT = 'Respond with JSON:\n\n{{\n  "final_action": "RECALL" | "SPEAK",\n  "node_id": "exact node id"\n}}\n'


def test_a_faithful_translation_has_no_problems() -> None:
    assert PL.prompt_problems(_EN_FORMAT, SPANISH["response_format"]) == []


@pytest.mark.parametrize(
    "value, why",
    [
        (_EN_FORMAT, "identical to the English"),
        ("   ", "empty"),
        ('Responde con JSON:\n\n{\n  "final_action": "RECALL" | "SPEAK",\n  "node_id": "x"\n}\n', "'{{' appears"),
        (SPANISH["response_format"].replace('"final_action"', '"acción_final"'), "JSON field names differ"),
        (SPANISH["response_format"].replace("RECALL", "RECORDAR"), "RECALL appears 0x"),
    ],
)
def test_a_translation_that_would_break_the_agent_is_named(value: str, why: str) -> None:
    assert any(why in p for p in PL.prompt_problems(_EN_FORMAT, value))


def test_a_lost_placeholder_or_backticked_identifier_is_named() -> None:
    assert any("placeholders" in p for p in PL.prompt_problems("Thought:\n{original_thought_content}\n", "Idea:\n"))
    assert any("lost `identity`" in p for p in PL.prompt_problems("Not in `identity` scope.", "No en ese ámbito."))


def test_a_verb_followed_by_native_script_still_counts() -> None:
    """Korean attaches particles: MEMORIZE를 is the verb, present and correct."""
    assert PL.prompt_problems("Use MEMORIZE to store it.", "저장하려면 MEMORIZE를 사용하세요.") == []


# ──────────────────────────────────────────────
# Writing back
# ──────────────────────────────────────────────


def test_accepted_values_are_written_and_the_english_marker_goes(prompts: Path, tmp_path: Path) -> None:
    written, rejected = PL.write_back(_stage(tmp_path, SPANISH), ["es"], prompts)

    assert rejected == {}
    assert sorted(written) == sorted(f"es:demo.{f}" for f in SPANISH)
    text = (prompts / "localized" / "es" / "demo.yml").read_text(encoding="utf-8")
    doc = yaml.safe_load(text)
    assert {f: doc[f] for f in SPANISH} == SPANISH
    assert (doc["component_name"], doc["version"]) == ("demo", "1.0")
    assert PL.ENGLISH_COPY_MARKER not in text
    assert "# PRAGMATIC — the wire contract." in text  # comments between keys survive
    assert doc["response_format"].format().startswith("Responde con JSON")


def test_a_rejected_value_is_not_written_and_the_marker_stays(prompts: Path, tmp_path: Path) -> None:
    broken = dict(SPANISH, response_format=SPANISH["response_format"].replace("{{", "{").replace("}}", "}"))
    written, rejected = PL.write_back(_stage(tmp_path, broken), ["es"], prompts)

    assert list(rejected) == ["es:demo.response_format"]
    assert "es:demo.response_format" not in written
    text = (prompts / "localized" / "es" / "demo.yml").read_text(encoding="utf-8")
    doc = yaml.safe_load(text)
    assert doc["response_format"] == yaml.safe_load(ENGLISH)["response_format"]  # still English, still "missing"
    assert doc["description"] == SPANISH["description"]  # the accepted ones are banked
    assert text.startswith(PL.ENGLISH_COPY_MARKER)
    assert "demo" in PL.locale_bundle("es", PL.english_bundle(prompts), prompts)


def test_writing_one_field_leaves_every_other_byte_alone(prompts: Path) -> None:
    path = prompts / "localized" / "es" / "demo.yml"
    before = path.read_text(encoding="utf-8")
    after = PL.set_field(before, "closing_reminder", SPANISH["closing_reminder"])
    assert after.replace("  No escribas en el ámbito `identity`.", "  Do not write to `identity` scope.") == before


@pytest.mark.parametrize(
    "value", ["one line", "two\nlines\n", "no trailing newline\nat all", "x\n\n\n", ' "quoted": {{}} ']
)
def test_any_string_round_trips_through_a_rewrite(prompts: Path, value: str) -> None:
    path = prompts / "localized" / "es" / "demo.yml"
    text = PL.set_field(path.read_text(encoding="utf-8"), "system_guidance_header", value)
    assert yaml.safe_load(text)["system_guidance_header"] == value
    assert yaml.safe_load(text)["response_format"] == yaml.safe_load(ENGLISH)["response_format"]


def test_a_locale_file_that_does_not_exist_is_refused_not_created(prompts: Path, tmp_path: Path) -> None:
    shutil.rmtree(prompts / "localized" / "es")
    written, rejected = PL.write_back(_stage(tmp_path, SPANISH), ["es"], prompts)
    assert written == [] and list(rejected) == ["es:demo.*"]
    assert not (prompts / "localized" / "es").exists()


# ──────────────────────────────────────────────
# Read-only modes, the gate, the shard ownership
# ──────────────────────────────────────────────


def _localized_snapshot() -> Dict[Path, bytes]:
    return {p: p.read_bytes() for root in PL.PROMPT_ROOTS for p in sorted((root / "localized").rglob("*.yml"))}


def test_check_and_dry_run_write_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    snapshot = _localized_snapshot()
    PL.main(["--check"])
    PL.main(["--lane", "translate", "--keys", "msaspdma.*", "--lang", "es", "--dry-run"])
    PL.main(["--lane", "translate", "--keys", "*_conscience.*", "--lang", "es", "--dry-run"])
    assert _localized_snapshot() == snapshot
    capsys.readouterr()


def test_the_gate_blocks_only_on_what_differs_from_head() -> None:
    """Standing debt in the tree must not fail a run that did not write it."""
    blocking, _standing = PL.verify(changed_only=True)
    assert blocking == [], blocking


def test_a_shard_owns_its_locales_prompt_files_and_nothing_else() -> None:
    owned = LS.owned_files("prompts", ["es", "zh"])
    assert f"{PL.PROMPTS_REL}/localized/es/msaspdma.yml" in owned
    assert f"{PL.PROMPTS_REL}/localized/zh/rsaspdma.yml" in owned
    assert f"{PL.CONSCIENCE_PROMPTS_REL}/localized/es/entropy_conscience.yml" in owned
    assert f"{PL.CONSCIENCE_PROMPTS_REL}/localized/zh/coherence_conscience.yml" in owned
    assert not any("optimization_veto" in p for p in owned)  # polyglot: no per-locale file to own
    assert all("/localized/es/" in p or "/localized/zh/" in p for p in owned)
    assert len(owned) == 2 * len(PL.template_names())
    with pytest.raises(SystemExit):
        LS.owned_files("nonsense", ["es"])


# ──────────────────────────────────────────────
# The conscience root
# ──────────────────────────────────────────────

CONSCIENCES = ("coherence_conscience", "entropy_conscience", "epistemic_humility_conscience")


def test_the_target_covers_both_roots_and_skips_the_polyglot_veto() -> None:
    found = PL.templates()
    assert {found[t] for t in CONSCIENCES} == {PL.CONSCIENCE_PROMPTS}
    assert found["msaspdma"] == PL.PROMPTS
    assert "optimization_veto_conscience" not in found
    assert (PL.CONSCIENCE_PROMPTS / "optimization_veto_conscience.yml").is_file()  # skipped, not absent
    assert PL.locale_path(PL.PROMPT_ROOTS, "es", "entropy_conscience") == (
        PL.CONSCIENCE_PROMPTS / "localized" / "es" / "entropy_conscience.yml"
    )


def test_a_template_name_in_two_roots_is_refused(tmp_path: Path) -> None:
    for root in ("a", "b"):
        (tmp_path / root).mkdir()
        (tmp_path / root / "same.yml").write_text(ENGLISH, encoding="utf-8")
    with pytest.raises(SystemExit, match="exists in both"):
        PL.templates([tmp_path / "a", tmp_path / "b"])


def test_conscience_fields_are_staged_and_settings_and_tails_are_not(tmp_path: Path) -> None:
    en = PL.build_stage(tmp_path)
    for t in CONSCIENCES:
        assert {"system_prompt", "pipeline_position", "user_prompt_template"} <= set(en[t]), t
        assert not {"version", "language", "system_prompt_tail"} & set(en[t]), t
    es = json.loads((tmp_path / "es.json").read_text(encoding="utf-8"))
    for t in CONSCIENCES:
        assert "system_prompt" in es[t]  # translated: not offered again
        assert "pipeline_position" in es[t]  # the shipped es translates it: not offered again either


def test_a_conscience_field_a_locale_lacks_is_offered_to_the_lane(tmp_path: Path) -> None:
    """Synthetic: the shipped ``es`` consciences with ``pipeline_position`` removed.

    A missing field is absent from the locale's staged bundle, so the lane picks it up; the locale's other
    translated fields stay staged (not offered again).
    """
    from tests.fixtures.synthetic_locale import CONSCIENCE_PROMPTS, prompts_dir_without_field

    synthetic = prompts_dir_without_field(CONSCIENCE_PROMPTS, tmp_path / "prompts", "es", "pipeline_position")
    en = PL.build_stage(tmp_path / "stage", (synthetic,))
    es = json.loads((tmp_path / "stage" / "es.json").read_text(encoding="utf-8"))
    for t in CONSCIENCES:
        assert "pipeline_position" in en[t], t
        assert "system_prompt" in es[t], t
        assert "pipeline_position" not in es[t], t


def test_the_dry_run_lists_the_conscience_positions_for_all_28_locales(capsys: pytest.CaptureFixture[str]) -> None:
    # --overwrite: the positions are translated now, and without it the keep-only guard refuses the selection.
    PL.main(["--lane", "translate", "--keys", "*_conscience.pipeline_position", "--overwrite", "--dry-run"])
    out = capsys.readouterr().out
    assert "lane=translate  84 key-value(s) across 28 language(s)" in out
    for lang in PL.languages()[1:]:
        assert f"    {lang}: 3 key(s)" in out, lang


CONSCIENCE_EN = """version: "1.1"
description: "IRIS-C coherence-sensing shard prompts"
language: "en"

system_prompt: |-
  You are IRIS-C. Score coherence.

pipeline_position: |-
  You run after action selection. You do not see the user's message.

system_prompt_tail: |
  Respond with JSON: {"coherence": <0.0-1.0>}

user_prompt_template: |
  Action: {action_description}
"""

# A pre-split locale copy, the shape all 28 have: no position, no tail, the JSON example in the header.
CONSCIENCE_ES = """version: '1.2'
description: Prompts del fragmento IRIS-C
language: es
system_prompt: |
  Eres IRIS-C. Puntúa la coherencia.
  Responde con JSON: {"coherence": <0.0-1.0>}
user_prompt_template: |-
  Acción: {action_description}
"""


@pytest.fixture
def two_roots(tmp_path: Path) -> list:
    dma, conscience = tmp_path / "dma", tmp_path / "conscience"
    for root, name, en, es in (
        (dma, "demo", ENGLISH, ENGLISH),
        (conscience, "coh_conscience", CONSCIENCE_EN, CONSCIENCE_ES),
    ):
        (root / "localized" / "es").mkdir(parents=True)
        (root / f"{name}.yml").write_text(en, encoding="utf-8")
        (root / "localized" / "es" / f"{name}.yml").write_text(es, encoding="utf-8")
    return [dma, conscience]


def test_a_conscience_position_is_written_back_and_the_loader_reads_it(
    two_roots: list, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ciris_engine.logic.conscience.prompt_loader import ConsciencePromptLoader

    position = "Actúas después de la selección de acción. No ves el mensaje del usuario."
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "es.json").write_text(
        json.dumps({"demo": SPANISH, "coh_conscience": {"pipeline_position": position}}), encoding="utf-8"
    )
    path = two_roots[1] / "localized" / "es" / "coh_conscience.yml"
    before = path.read_text(encoding="utf-8")

    written, rejected = PL.write_back(stage, ["es"], two_roots)

    assert rejected == {}
    assert "es:coh_conscience.pipeline_position" in written and "es:demo.description" in written
    after = path.read_text(encoding="utf-8")
    assert after.startswith(before.rstrip("\n"))  # appended; every existing byte kept
    loader = ConsciencePromptLoader(prompts_dir=str(two_roots[1]), language="es")
    head, got, tail = loader.get_system_prompt_parts("coh_conscience")
    assert got == position and head.startswith("Eres IRIS-C") and tail == ""


def test_a_header_is_not_written_into_a_locale_that_is_not_split(two_roots: list, tmp_path: Path) -> None:
    """The locale's system_prompt still holds the tail's text; a translation of the split English head drops it."""
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "es.json").write_text(
        json.dumps({"coh_conscience": {"system_prompt": "Eres IRIS-C. Puntúa."}}), encoding="utf-8"
    )
    path = two_roots[1] / "localized" / "es" / "coh_conscience.yml"
    before = path.read_text(encoding="utf-8")
    written, rejected = PL.write_back(stage, ["es"], two_roots)
    assert written == [] and "not split at system_prompt_tail" in rejected["es:coh_conscience.system_prompt"][0]
    assert path.read_text(encoding="utf-8") == before


def test_a_conscience_system_prompt_is_not_held_to_str_format() -> None:
    """Only the user-prompt templates are formatted; the pre-split headers carry literal JSON braces."""
    english = PL.read_template(PL.CONSCIENCE_PROMPTS / "epistemic_humility_conscience.yml")["system_prompt"]
    shipped = PL.read_template(PL.CONSCIENCE_PROMPTS / "localized" / "es" / "epistemic_humility_conscience.yml")[
        "system_prompt"
    ]
    assert PL._formats(shipped)  # a lone brace: would fail .format(), but nothing formats it
    assert not PL.is_format_string(PL.PROMPT_ROOTS, "epistemic_humility_conscience", "system_prompt")
    assert PL.is_format_string(PL.PROMPT_ROOTS, "epistemic_humility_conscience", "user_prompt_template")
    assert not any("str.format" in p for p in PL.prompt_problems(english, shipped, formatted=False))
    blocking, _ = PL.verify()
    assert not [f for f in blocking if "_conscience" in f], blocking


# ──────────────────────────────────────────────
# Translation memory handed to the translator
# ──────────────────────────────────────────────


def test_a_new_block_is_anchored_on_the_same_field_of_its_sister_templates(tmp_path: Path) -> None:
    """rsaspdma.memory_prohibitions is shown how msaspdma.memory_prohibitions reads in this language."""
    en = PL.flat(PL.build_stage(tmp_path))
    anchors = PL.make_anchors(tmp_path)("ja", ["rsaspdma.memory_prohibitions"], en)

    keys = [k for k, _, _ in anchors]
    assert keys[0] == "msaspdma.memory_prohibitions"
    english, shipped = next((e, t) for k, e, t in anchors if k == keys[0])
    assert english == en[keys[0]] and shipped != english
    assert "rsaspdma.memory_prohibitions" not in keys  # never its own (English) value
    assert any(k.startswith("accord:") for k in keys)  # the ethics text in this language


def test_a_structurally_broken_sister_block_is_not_offered_as_an_example(tmp_path: Path) -> None:
    """An anchor teaches by example; one with a broken placeholder teaches the break."""
    en = PL.flat(PL.build_stage(tmp_path))
    staged = json.loads((tmp_path / "vi.json").read_text(encoding="utf-8"))
    broken = staged["tsaspdma"]["context_enrichment_section"]
    assert PL.prompt_problems(en["tsaspdma.context_enrichment_section"], broken)  # standing debt in the tree

    anchors = PL.make_anchors(tmp_path)("vi", ["rsaspdma.context_integration"], en, limit=200)
    assert "tsaspdma.context_enrichment_section" not in [k for k, _, _ in anchors]


def test_website_client_and_agent_ui_terms_follow_the_prompt_and_ethics_anchors(tmp_path: Path) -> None:
    en = PL.flat(PL.build_stage(tmp_path))
    pool = [PL.acc.ExtraAnchor(2, "client:search.title", "Search", "Buscar", frozenset({"search"}))]
    anchors = PL.make_anchors(tmp_path, {"es": pool})("es", ["rsaspdma.evaluation_steps"], en)

    keys = [k for k, _, _ in anchors]
    assert keys[-1] == "client:search.title"
    assert keys.index("client:search.title") > max(i for i, k in enumerate(keys) if ":" not in k)


def test_the_anchor_rules_reach_all_three_system_prompts(tmp_path: Path) -> None:
    PL.build_stage(tmp_path)
    L = PL.import_localize(tmp_path)
    PL.install(L, tmp_path)
    for name in ("SYSTEM_TRANSLATE", "SYSTEM_REVIEW", "SYSTEM_REPAIR"):
        text = getattr(L, name)
        assert "THESE STRINGS ARE NOT UI LABELS" in text
        assert 'Keys starting "website:", "client:" or "agent-ui:"' in text
    assert "not a terminology finding" in L.SYSTEM_REVIEW


# ──────────────────────────────────────────────
# Re-split: a header and its tail, redone together (--resplit)
# ──────────────────────────────────────────────


@pytest.fixture
def resplit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(PL, "RESPLIT", frozenset({"coh_conscience.system_prompt"}))


def _conscience_stage(tmp_path: Path, values: Dict[str, str]) -> Path:
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "es.json").write_text(json.dumps({"coh_conscience": values}, ensure_ascii=False), encoding="utf-8")
    return stage


def test_a_resplit_stages_header_and_tail_as_missing(two_roots: list, tmp_path: Path, resplit: None) -> None:
    en = PL.build_stage(tmp_path / "stage", two_roots)
    assert {"system_prompt", "system_prompt_tail"} <= set(en["coh_conscience"])
    es = json.loads((tmp_path / "stage" / "es.json").read_text(encoding="utf-8"))
    # The pre-split header is redone from the split English, so it is not offered as "have".
    assert "system_prompt" not in es.get("coh_conscience", {})


def test_without_a_resplit_the_tail_stays_pending(two_roots: list, tmp_path: Path) -> None:
    en = PL.build_stage(tmp_path / "stage", two_roots)
    assert "system_prompt_tail" not in en["coh_conscience"]


def test_a_resplit_pair_is_written_together_and_the_loader_renders_it_once(
    two_roots: list, tmp_path: Path, resplit: None
) -> None:
    from ciris_engine.logic.conscience.prompt_loader import ConsciencePromptLoader

    head = "Eres IRIS-C. Puntúa la coherencia."
    tail = 'Responde con JSON: {"coherence": <0.0-1.0>}\n'
    written, rejected = PL.write_back(
        _conscience_stage(tmp_path, {"system_prompt": head, "system_prompt_tail": tail}), ["es"], two_roots
    )
    assert rejected == {}
    assert {"es:coh_conscience.system_prompt", "es:coh_conscience.system_prompt_tail"} <= set(written)
    loader = ConsciencePromptLoader(prompts_dir=str(two_roots[1]), language="es")
    got_head, _, got_tail = loader.get_system_prompt_parts("coh_conscience")
    assert got_head == head and got_tail == tail
    assert (got_head + got_tail).count("Responde con JSON") == 1


def test_half_a_resplit_pair_writes_nothing(two_roots: list, tmp_path: Path, resplit: None) -> None:
    """Negative: a header translated without its tail would drop the tail's text."""
    path = two_roots[1] / "localized" / "es" / "coh_conscience.yml"
    before = path.read_text(encoding="utf-8")
    written, rejected = PL.write_back(_conscience_stage(tmp_path, {"system_prompt": "Eres IRIS-C."}), ["es"], two_roots)
    assert written == [] and "written together or not at all" in rejected["es:coh_conscience.system_prompt"][0]
    assert path.read_text(encoding="utf-8") == before


def test_a_resplit_pair_with_a_broken_tail_writes_neither(two_roots: list, tmp_path: Path, resplit: None) -> None:
    path = two_roots[1] / "localized" / "es" / "coh_conscience.yml"
    before = path.read_text(encoding="utf-8")
    written, rejected = PL.write_back(
        _conscience_stage(tmp_path, {"system_prompt": "Eres IRIS-C.", "system_prompt_tail": "Responde con texto.\n"}),
        ["es"],
        two_roots,
    )
    assert not any(k.startswith("es:coh_conscience.system_prompt") for k in written)
    assert rejected and path.read_text(encoding="utf-8") == before


def test_a_resplit_pair_already_done_in_a_locale_is_not_redone(two_roots: list, tmp_path: Path, resplit: None) -> None:
    path = two_roots[1] / "localized" / "es" / "coh_conscience.yml"
    text = PL.set_field(path.read_text(encoding="utf-8"), "system_prompt", "Eres IRIS-C. Puntúa.")
    path.write_text(PL.set_field(text, "system_prompt_tail", 'Responde con JSON: {"coherence": <0.0-1.0>}\n'), encoding="utf-8")
    PL.build_stage(tmp_path / "stage", two_roots)
    es = json.loads((tmp_path / "stage" / "es.json").read_text(encoding="utf-8"))
    assert {"system_prompt", "system_prompt_tail"} <= set(es["coh_conscience"])  # counted as translated


# ──────────────────────────────────────────────
# A run that could only pay and keep is refused before it spends (run 46093145549: $22.07, 0 written)
# ──────────────────────────────────────────────


def test_selecting_translated_keys_without_overwrite_is_named(two_roots: list, tmp_path: Path) -> None:
    en = PL.build_stage(tmp_path / "stage", two_roots)
    kept = PL.kept_without_overwrite(tmp_path / "stage", ["coh_conscience.system_prompt"], ["es"], en)
    assert kept == {"es": ["coh_conscience.system_prompt"]}  # es already holds a translation


def test_selecting_only_missing_keys_is_not_refused(two_roots: list, tmp_path: Path) -> None:
    en = PL.build_stage(tmp_path / "stage", two_roots)
    # demo's es copy is the English one, so every demo field is missing: nothing would be kept.
    assert PL.kept_without_overwrite(tmp_path / "stage", ["demo.*"], ["es"], en) == {}


def test_the_lane_refuses_a_keep_only_run_and_spends_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    before = _localized_snapshot()
    rc = PL.main(["--lane", "translate", "--keys", "entropy_conscience.system_prompt", "--lang", "es", "--dry-run"])
    assert rc == 2 and "[refuse]" in capsys.readouterr().out
    assert _localized_snapshot() == before


def test_overwrite_lets_the_same_selection_through(capsys: pytest.CaptureFixture[str]) -> None:
    rc = PL.main(["--lane", "translate", "--keys", "entropy_conscience.system_prompt", "--lang", "es", "--overwrite", "--dry-run"])
    assert rc == 0 and "[refuse]" not in capsys.readouterr().out


def test_the_ui_lane_refuses_a_keep_only_run_too() -> None:
    import importlib.util

    import lane_backoff as LB  # noqa: E402

    # A fresh copy: the prompts target repoints the shared module's CANONICAL at its stage.
    spec = importlib.util.spec_from_file_location("localize_ui_fresh", REPO / "localization" / "localize.py")
    assert spec and spec.loader
    L = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(L)
    L.CANONICAL = L.REPO_ROOT / L.guard.UI_BUNDLE  # LOCALIZE_TARGET may be left at prompts by an earlier test

    assert LB.keep_only_refusal(L, ["--lane", "translate", "--keys", "nav.*", "--lang", "es"])
    assert LB.keep_only_refusal(L, ["--lane", "translate", "--keys", "nav.*", "--lang", "es", "--overwrite"]) is None
    assert LB.keep_only_refusal(L, ["--lane", "evaluate", "--keys", "nav.*", "--lang", "es"]) is None
