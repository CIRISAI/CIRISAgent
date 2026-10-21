"""
Every `interactive_config` in the tree is a program in one small language.

This is its compiler's front end: every key is one the schema declares, every
axis has one spelling, every reference points at something that exists and
comes earlier. A manifest that fails here would have rendered on the client
as a step with no fields, a condition nothing evaluates, or a `required` that
disagrees with an `optional` -- all of which shipped before this file existed
(CIRISClient#39).

The rules are checked against the DATA, not against a regex over the text, so
a new manifest gets the same treatment as the migrated ones.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, Dict, Iterator, List, Set

import pytest

from ciris_engine.schemas.runtime.manifest import (
    ConfigurationFieldDefinition,
    ConfigurationStep,
    InteractiveConfiguration,
)

REPO = Path(__file__).resolve().parents[2]
MANIFESTS = sorted(REPO.glob("ciris_adapters/*/manifest.json"))

# Retired spellings. Each was a second way to say something the schema already
# said; the migration collapsed them and this keeps them out.
RETIRED_STEP_KEYS = {"optional", "field", "field_name"}
RETIRED_FIELD_KEYS = {"field_id"}

# Documentation keys the language permits anywhere. Nothing reads them.
DOC_KEYS = {"_comment"}

STEP_KEYS = set(ConfigurationStep.model_fields) | DOC_KEYS
FIELD_KEYS = set(ConfigurationFieldDefinition.model_fields) | DOC_KEYS
IC_KEYS = set(InteractiveConfiguration.model_fields) | DOC_KEYS | {
    # Top-level documentation blocks one manifest carries; harmless, unread.
    "_step_types_reference",
    "_field_types_reference",
    # Where the configurable class lives, for loaders that need it.
    "configurable_class",
}

# What each step type writes into collected_config besides its declared
# fields. Mirrors AdapterConfigurationService; a condition may name these.
IMPLICIT_WRITES = {
    "discovery": {"base_url"},
    "oauth": {"oauth_tokens", "base_url"},
    "device_auth": {"oauth_tokens"},
}

CONDITION_OPERATORS = {"equals", "not_equals", "values"}


def _load_migrator():
    spec = importlib.util.spec_from_file_location(
        "migrate_interactive_config", REPO / "tools" / "dev" / "migrate_interactive_config.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _configs() -> Iterator[tuple[Path, Dict[str, Any]]]:
    for path in MANIFESTS:
        data = json.loads(path.read_text(encoding="utf-8"))
        ic = data.get("interactive_config")
        if ic:
            yield path, ic


CONFIGS = list(_configs())
IDS = [p.parent.name for p, _ in CONFIGS]


def test_the_language_is_in_use() -> None:
    # If this ever drops to zero the rest of the file is vacuous.
    assert len(CONFIGS) >= 20, [p.parent.name for p, _ in CONFIGS]


@pytest.mark.parametrize(("path", "ic"), CONFIGS, ids=IDS)
def test_validates_as_interactive_configuration(path: Path, ic: Dict[str, Any]) -> None:
    InteractiveConfiguration.model_validate(ic)


@pytest.mark.parametrize(("path", "ic"), CONFIGS, ids=IDS)
def test_every_key_is_declared(path: Path, ic: Dict[str, Any]) -> None:
    """extra="allow" means an undeclared key validates silently. Not here."""
    problems: List[str] = []
    for k in ic:
        if k not in IC_KEYS:
            problems.append(f"interactive_config.{k}")
    for step in ic["steps"]:
        for k in step:
            if k in RETIRED_STEP_KEYS:
                problems.append(f"{step['step_id']}.{k} is RETIRED -- run tools/dev/migrate_interactive_config.py")
            elif k not in STEP_KEYS:
                problems.append(f"{step['step_id']}.{k} is not a ConfigurationStep key")
        for field in step.get("fields") or []:
            fid = f"{step['step_id']}.fields[{field.get('name', '?')}]"
            for k in field:
                if k in RETIRED_FIELD_KEYS:
                    problems.append(f"{fid}.{k} is RETIRED")
                elif k not in FIELD_KEYS:
                    problems.append(f"{fid}.{k} is not a ConfigurationFieldDefinition key")
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize(("path", "ic"), CONFIGS, ids=IDS)
def test_step_ids_are_unique_and_fields_are_named(path: Path, ic: Dict[str, Any]) -> None:
    seen: Set[str] = set()
    for step in ic["steps"]:
        assert step["step_id"] not in seen, f"duplicate step_id {step['step_id']!r}"
        seen.add(step["step_id"])
        for field in step.get("fields") or []:
            assert field.get("name"), f"{step['step_id']}: a field with no name writes nothing"


@pytest.mark.parametrize(("path", "ic"), CONFIGS, ids=IDS)
def test_references_point_backwards_at_things_that_exist(path: Path, ic: Dict[str, Any]) -> None:
    """A step may depend on, or condition on, only what an EARLIER step produced.

    `depends_on` names step_ids. `condition.field` names a key in
    collected_config, which is: a field declared on any earlier step (select
    steps write their declared field), or what a discovery/oauth step writes.
    A forward or dangling reference is a step that can never be reached.
    """
    earlier_ids: Set[str] = set()
    written: Set[str] = set()
    problems: List[str] = []
    for step in ic["steps"]:
        sid = step["step_id"]
        for dep in step.get("depends_on") or []:
            if dep not in earlier_ids:
                problems.append(f"{sid}.depends_on names {dep!r}, which is not an earlier step")
        cond = step.get("condition")
        if cond:
            ops = CONDITION_OPERATORS & set(cond)
            if len(ops) != 1:
                problems.append(f"{sid}.condition needs exactly one of {sorted(CONDITION_OPERATORS)}, has {sorted(ops)}")
            field = cond.get("field")
            if field not in written:
                problems.append(
                    f"{sid}.condition reads {field!r}, which no earlier step writes "
                    f"(written so far: {sorted(written)}) -- the step could never be shown"
                )
        earlier_ids.add(sid)
        written |= {f["name"] for f in step.get("fields") or [] if f.get("name")}
        written |= IMPLICIT_WRITES.get(step["step_type"], set())
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize(("path", "ic"), CONFIGS, ids=IDS)
def test_select_steps_declare_what_they_write(path: Path, ic: Dict[str, Any]) -> None:
    """A select step with no declared field writes only its step_id.

    That is allowed, but then nothing downstream may `condition` on a
    friendlier name -- covered above. This documents which selects are
    step_id-only so a new `condition` on one of them fails loudly there.
    """
    for step in ic["steps"]:
        if step["step_type"] == "select":
            fields = step.get("fields") or []
            assert len(fields) <= 1, f"{step['step_id']}: a select writes ONE value; it declares {len(fields)} fields"


def test_migration_is_a_fixed_point() -> None:
    """Running the migrator over the tree changes nothing. `--check` for CI."""
    mig = _load_migrator()
    for path, _ in CONFIGS:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        assert mig.migrate_manifest(data) == data, f"{path.parent.name}: migration is not applied"
        assert mig.patch_text(text) == text, f"{path.parent.name}: text patch would change the file"


def test_schema_has_one_key_per_axis() -> None:
    """The three drifts, as schema facts, so they cannot come back."""
    step = set(ConfigurationStep.model_fields)
    field = set(ConfigurationFieldDefinition.model_fields)
    assert "required" in step and "optional" not in step
    assert "fields" in step and "field" not in step and "field_name" not in step
    assert "name" in field and "field_id" not in field
    assert ConfigurationFieldDefinition.model_fields["name"].is_required()
    # depends_on is a list of step ids, nothing else
    assert "List" in str(ConfigurationStep.model_fields["depends_on"].annotation)
    assert "Dict" not in str(ConfigurationStep.model_fields["depends_on"].annotation)


# ---- CIRISAgent#1158 review (Codex P1): the retired spelling is READ, never written ----


def test_an_out_of_tree_manifest_with_field_id_still_loads(caplog: pytest.LogCaptureFixture) -> None:
    """The in-tree lint above rejects `field_id`; ingestion must not, or an
    adapter authored before #1154 vanishes from discover_services() with one
    error line. It is read as `name` and the author is told."""
    from ciris_engine.schemas.runtime.manifest import ConfigurationFieldDefinition

    with caplog.at_level("WARNING"):
        f = ConfigurationFieldDefinition.model_validate({"field_id": "api_key", "type": "string"})
    assert f.name == "api_key"
    assert "field_id" not in (f.model_extra or {}), "the retired key must not survive as an extra"
    assert "retired key `field_id`" in caplog.text and "migrate_interactive_config" in caplog.text
    both = ConfigurationFieldDefinition.model_validate({"name": "a", "field_id": "b"})
    assert both.name == "a", "when both are present the canonical key wins"
    with pytest.raises(Exception):
        ConfigurationFieldDefinition.model_validate({"type": "string"})  # neither: still a nameless field


def test_a_legacy_optional_step_keeps_its_requiredness(caplog: pytest.LogCaptureFixture) -> None:
    """`optional: false` from a pre-#1154 manifest meant mandatory; with `required`
    the one key, it must not silently become skippable (review on #1158)."""
    from ciris_engine.schemas.runtime.manifest import ConfigurationStep

    base = {"step_id": "s1", "step_type": "select", "title": "t", "description": "d"}
    with caplog.at_level("WARNING"):
        mandatory = ConfigurationStep.model_validate({**base, "optional": False})
    assert mandatory.required is True
    assert "optional" not in (mandatory.model_extra or {})
    assert "retired key `optional`" in caplog.text
    skippable = ConfigurationStep.model_validate({**base, "optional": True})
    assert skippable.required is False
    both = ConfigurationStep.model_validate({**base, "optional": True, "required": True})
    assert both.required is True, "the canonical key wins when both are present"
