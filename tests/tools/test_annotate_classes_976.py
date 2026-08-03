"""#976 — the κ instrument and its gate (FSD §10.2.3).

The annotation PASS is human work. What is tested here is the INSTRUMENT: that
it emits a total sheet, that it computes Cohen's κ correctly, that a boundary
nobody exercised reads as NOT ESTIMABLE rather than perfect, and above all that
**an aggregate κ can pass while a decision-relevant boundary fails** [T-N2] —
the failure mode the per-boundary requirement exists for.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict

import pytest

from ciris_engine.schemas.dma.compose import BlockClass
from tools.research.annotate_classes import (
    AnnotationRefused,
    cohens_kappa,
    inventory_rows,
    main,
    read_sheet,
    score,
    write_sheet,
)

_SCORED_CLASSES = [c for c in BlockClass if c is not BlockClass.MIXED]


def _write(path: Path, annotator: str, labels: Dict[str, str]) -> Path:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(f"# annotator_id: {annotator}\n")
        writer = csv.writer(handle)
        writer.writerow(["block_id", "primary_class", "contaminant", "class", "notes"])
        for block_id, label in labels.items():
            writer.writerow([block_id, "mixed", "", label, ""])
    return path


def _balanced(flip_axiotic_to_deontic: int = 0) -> Dict[str, str]:
    """Two items per class so every boundary has data on both sides."""
    labels: Dict[str, str] = {}
    for block_class in _SCORED_CLASSES:
        for index in range(4):
            labels[f"{block_class.value}.{index}"] = block_class.value
    for index in range(flip_axiotic_to_deontic):
        labels[f"axiotic.{index}"] = "deontic"
    return labels


# ---------------------------------------------------------------------------
# emit
# ---------------------------------------------------------------------------


def test_emit_writes_a_total_sheet_with_a_sealed_annotator_id(tmp_path: Path) -> None:
    rows = inventory_rows()
    out = tmp_path / "alice.csv"
    write_sheet(str(out), "alice", rows)
    text = out.read_text(encoding="utf-8")
    assert text.startswith("# annotator_id: alice\n")
    assert "language_guidance" in text
    with pytest.raises(AnnotationRefused, match="unlabelled"):
        read_sheet(str(out))  # a blank sheet is not an abstention


def test_emit_can_take_the_inventory_from_a_real_compose_dump(tmp_path: Path) -> None:
    dump = tmp_path / "dump.jsonl"
    dump.write_text(
        '{"kind": "compose_dump_meta", "arm": "a"}\n'
        '{"block_id": "pdma.system", "class": "mixed", "contaminant": ["procedural"]}\n'
        '{"block_id": "pdma.system", "class": "mixed", "contaminant": ["procedural"]}\n'
        '{"block_id": "pdma.accord", "class": "axiotic", "contaminant": null}\n',
        encoding="utf-8",
    )
    rows = inventory_rows(str(dump))
    assert [r[0] for r in rows] == ["pdma.accord", "pdma.system"]  # deduped, sorted
    assert rows[1][2] == "procedural"


# ---------------------------------------------------------------------------
# kappa arithmetic
# ---------------------------------------------------------------------------


def test_perfect_agreement_over_two_labels_is_one() -> None:
    pairs = [(BlockClass.AXIOTIC, BlockClass.AXIOTIC), (BlockClass.DEONTIC, BlockClass.DEONTIC)]
    assert cohens_kappa(pairs, "t").kappa == pytest.approx(1.0)


def test_a_boundary_nobody_exercised_is_not_estimable_never_one() -> None:
    """A gate that scores an untested boundary 1.0 passes precisely the
    boundaries nobody tested."""
    pairs = [(BlockClass.AXIOTIC, BlockClass.AXIOTIC)] * 5
    result = cohens_kappa(pairs, "axiotic|deontic")
    assert result.kappa is None
    assert "degenerate" in result.reason
    assert not result.passed()


def test_empty_boundary_is_not_estimable() -> None:
    result = cohens_kappa([], "axiotic|structural")
    assert result.kappa is None and not result.passed()


def test_chance_level_agreement_scores_near_zero() -> None:
    pairs = [
        (BlockClass.AXIOTIC, BlockClass.DEONTIC),
        (BlockClass.DEONTIC, BlockClass.AXIOTIC),
        (BlockClass.AXIOTIC, BlockClass.DEONTIC),
        (BlockClass.DEONTIC, BlockClass.AXIOTIC),
    ]
    kappa = cohens_kappa(pairs, "t").kappa
    assert kappa is not None and kappa < 0.0


# ---------------------------------------------------------------------------
# the gate
# ---------------------------------------------------------------------------


def test_a_clean_two_annotator_pass_is_citable(tmp_path: Path) -> None:
    a = read_sheet(str(_write(tmp_path / "a.csv", "alice", _balanced())))
    b = read_sheet(str(_write(tmp_path / "b.csv", "bob", _balanced())))
    overall, boundaries, adjudication = score(a, b)
    assert overall.passed() and adjudication == []
    assert boundaries and all(result.passed() for result in boundaries)


def test_aggregate_kappa_can_pass_while_the_axiotic_deontic_boundary_fails(tmp_path: Path) -> None:
    """[T-N2], the whole reason §10.2.3 requires per-boundary κ: an aggregate κ
    over eleven classes with skewed marginals passes while exactly the boundary
    that gates ``safety_review`` fails."""
    a = read_sheet(str(_write(tmp_path / "a.csv", "alice", _balanced())))
    b = read_sheet(str(_write(tmp_path / "b.csv", "bob", _balanced(flip_axiotic_to_deontic=3))))
    overall, boundaries, adjudication = score(a, b)

    assert overall.passed(), "fixture no longer demonstrates T-N2: the aggregate must still pass"
    by_name = {result.label.replace(" *", ""): result for result in boundaries}
    assert not by_name["axiotic|deontic"].passed()
    assert len(adjudication) == 3
    assert all("alice=axiotic bob=deontic" in line for line in adjudication)


def test_two_sheets_from_the_same_annotator_refuse(tmp_path: Path) -> None:
    """One author annotating once is the v1 procedure this replaces."""
    a = read_sheet(str(_write(tmp_path / "a.csv", "alice", _balanced())))
    b = read_sheet(str(_write(tmp_path / "b.csv", "alice", _balanced())))
    with pytest.raises(AnnotationRefused, match="Two independent annotators"):
        score(a, b)


def test_sheets_over_different_inventories_refuse(tmp_path: Path) -> None:
    labels = _balanced()
    partial = dict(list(labels.items())[:-2])
    a = read_sheet(str(_write(tmp_path / "a.csv", "alice", labels)))
    b = read_sheet(str(_write(tmp_path / "b.csv", "bob", partial)))
    with pytest.raises(AnnotationRefused, match="different inventories"):
        score(a, b)


def test_sheet_without_an_annotator_header_refuses(tmp_path: Path) -> None:
    path = tmp_path / "anon.csv"
    path.write_text("block_id,primary_class,contaminant,class,notes\nx,mixed,,axiotic,\n", encoding="utf-8")
    with pytest.raises(AnnotationRefused, match="no `# annotator_id:` header"):
        read_sheet(str(path))


def test_unknown_class_label_refuses(tmp_path: Path) -> None:
    path = _write(tmp_path / "a.csv", "alice", {"x": "deontological"})
    with pytest.raises(AnnotationRefused, match="not one of"):
        read_sheet(str(path))


# ---------------------------------------------------------------------------
# CLI exit codes — the gate has to be usable as a gate
# ---------------------------------------------------------------------------


def test_cli_exits_zero_only_when_citable(tmp_path: Path) -> None:
    _write(tmp_path / "a.csv", "alice", _balanced())
    _write(tmp_path / "b.csv", "bob", _balanced())
    argv = ["kappa", "--a", str(tmp_path / "a.csv"), "--b", str(tmp_path / "b.csv"), "--class-set-version", "2"]
    assert main(argv) == 0

    _write(tmp_path / "c.csv", "carol", _balanced(flip_axiotic_to_deontic=3))
    argv[4] = str(tmp_path / "c.csv")
    assert main(argv) == 1


def test_cli_refuses_an_unregistered_class_set_version(tmp_path: Path) -> None:
    _write(tmp_path / "a.csv", "alice", _balanced())
    _write(tmp_path / "b.csv", "bob", _balanced())
    argv = ["kappa", "--a", str(tmp_path / "a.csv"), "--b", str(tmp_path / "b.csv"), "--class-set-version", "99"]
    assert main(argv) == 2


def test_cli_writes_the_adjudication_log(tmp_path: Path) -> None:
    _write(tmp_path / "a.csv", "alice", _balanced())
    _write(tmp_path / "b.csv", "bob", _balanced(flip_axiotic_to_deontic=3))
    log = tmp_path / "adj.md"
    main(
        [
            "kappa",
            "--a",
            str(tmp_path / "a.csv"),
            "--b",
            str(tmp_path / "b.csv"),
            "--adjudication-log",
            str(log),
        ]
    )
    text = log.read_text(encoding="utf-8")
    assert text.count("- [ ] ") == 3
    assert "alice=axiotic bob=deontic" in text
