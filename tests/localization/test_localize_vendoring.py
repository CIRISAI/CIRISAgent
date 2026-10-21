"""The vendoring record for the CIRISClient localization pipeline.

A gate is trusted only once it has been shown to FAIL on an injected defect, so
every positive check here has a negative twin.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Dict

import pytest

REPO = Path(__file__).resolve().parents[2]


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_localize_vendoring", REPO / "tools/dev/check_localize_vendoring.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


V = _load()


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """A copy of exactly what the record declares, at the same paths."""
    record: Dict[str, Any] = json.loads((REPO / V.RECORD).read_text(encoding="utf-8"))
    for rel in [V.RECORD.as_posix(), *(e["path"] for e in record["files"])]:
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / rel, dst)
    return tmp_path


def test_the_real_tree_matches_its_record() -> None:
    assert V.check(REPO) == []


def test_record_names_the_upstream_commit_and_every_vendored_file() -> None:
    record = V.load_record(REPO)
    assert record["upstream"]["repo"] == "CIRISAI/CIRISClient"
    assert len(record["upstream"]["commit"]) == 40
    verbatim = {e["path"] for e in record["files"] if e["kind"] == "verbatim"}
    for must in ("localization/localize.py", "localization/glossary.py", "localization/TRANSLATION_GUIDE.md",
                 "localization/upstream/check_localization_sync.py", "localization/glossaries/yo_glossary.md"):  # fmt: skip
        assert must in verbatim
    assert sum(1 for p in verbatim if p.startswith("localization/glossaries/")) == 29


def test_copy_is_clean(tree: Path) -> None:
    assert V.check(tree) == []


def test_a_modified_vendored_file_fails(tree: Path) -> None:
    target = tree / "localization/localize.py"
    target.write_bytes(target.read_bytes().replace(b"MAX_ANCHOR_CHARS = 240", b"MAX_ANCHOR_CHARS = 2400"))
    problems = V.check(tree)
    assert any("localization/localize.py" in p and "differs from upstream" in p for p in problems), problems
    assert V.main(["--root", str(tree)]) == 1


def test_a_one_byte_glossary_edit_fails(tree: Path) -> None:
    target = tree / "localization/glossaries/am_glossary.md"
    target.write_bytes(target.read_bytes() + b" ")
    assert any("am_glossary.md" in p for p in V.check(tree))


def test_an_undeclared_file_in_a_vendored_directory_fails(tree: Path) -> None:
    (tree / "localization/glossaries/xx_glossary.md").write_text("| English | xx |\n", encoding="utf-8")
    assert any("undeclared" in p and "xx_glossary.md" in p for p in V.check(tree))


def test_a_missing_vendored_file_fails(tree: Path) -> None:
    (tree / "localization/glossary.py").unlink()
    assert any("glossary.py" in p and "missing" in p for p in V.check(tree))


def test_a_declared_patch_passes_and_an_undeclared_change_to_it_fails(tree: Path) -> None:
    record = json.loads((tree / V.RECORD).read_text(encoding="utf-8"))
    entry = next(e for e in record["files"] if e["path"] == "localization/localize.py")
    target = tree / entry["path"]
    target.write_bytes(target.read_bytes() + b"# local patch\n")
    (tree / "localization/patches").mkdir()
    (tree / "localization/patches/localize.patch").write_text("+# local patch\n", encoding="utf-8")
    entry.update(kind="patched", patch="localization/patches/localize.patch", sha256=V.sha256(target.read_bytes()))
    (tree / V.RECORD).write_text(json.dumps(record), encoding="utf-8")
    assert V.check(tree) == []
    target.write_bytes(target.read_bytes() + b"# and another\n")
    assert any("recorded patched state" in p for p in V.check(tree))


def test_derived_files_are_provenance_not_drift(tree: Path) -> None:
    lane = tree / ".github/workflows/i18n-lane.yml"
    lane.write_text(lane.read_text(encoding="utf-8") + "# ours to edit\n", encoding="utf-8")
    assert V.check(tree) == []
