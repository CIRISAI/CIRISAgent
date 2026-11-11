"""The DMA-prompt target of the i18n lane (``localization/prompt_localize.py``).

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


def test_check_and_dry_run_write_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    snapshot = {p: p.read_bytes() for p in sorted((PL.PROMPTS / "localized").rglob("*.yml"))}
    PL.main(["--check"])
    PL.main(["--lane", "translate", "--keys", "msaspdma.*", "--lang", "es", "--dry-run"])
    assert {p: p.read_bytes() for p in sorted((PL.PROMPTS / "localized").rglob("*.yml"))} == snapshot
    capsys.readouterr()


def test_the_gate_blocks_only_on_what_differs_from_head() -> None:
    """Standing debt in the tree must not fail a run that did not write it."""
    blocking, _standing = PL.verify(changed_only=True)
    assert blocking == [], blocking


def test_a_shard_owns_its_locales_prompt_files_and_nothing_else() -> None:
    owned = LS.owned_files("prompts", ["es", "zh"])
    assert f"{PL.PROMPTS_REL}/localized/es/msaspdma.yml" in owned
    assert f"{PL.PROMPTS_REL}/localized/zh/rsaspdma.yml" in owned
    assert all("/localized/es/" in p or "/localized/zh/" in p for p in owned)
    assert len(owned) == 2 * len(PL.template_names())
    with pytest.raises(SystemExit):
        LS.owned_files("nonsense", ["es"])


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
    pool = [PL.acc.ExtraAnchor(2, "client:memory.title", "Memory", "Memoria", frozenset({"memory"}))]
    anchors = PL.make_anchors(tmp_path, {"es": pool})("es", ["rsaspdma.evaluation_steps"], en)

    keys = [k for k, _, _ in anchors]
    assert keys[-1] == "client:memory.title"
    assert keys.index("client:memory.title") > max(i for i, k in enumerate(keys) if ":" not in k)


def test_the_anchor_rules_reach_all_three_system_prompts(tmp_path: Path) -> None:
    PL.build_stage(tmp_path)
    L = PL.import_localize(tmp_path)
    PL.install(L, tmp_path)
    for name in ("SYSTEM_TRANSLATE", "SYSTEM_REVIEW", "SYSTEM_REPAIR"):
        text = getattr(L, name)
        assert "THESE STRINGS ARE NOT UI LABELS" in text
        assert 'Keys starting "website:", "client:" or "agent-ui:"' in text
    assert "not a terminology finding" in L.SYSTEM_REVIEW
