"""Class-set annotation instrument + the κ gate (#976, FSD §10.2.3).

A class-set version is citable only after **two independent annotators**
classify the full block inventory with **Cohen's κ ≥ 0.8 overall AND per-boundary
κ ≥ 0.8 on every class pair whose default disposition differs** — ``axiotic|deontic``
(gates ``safety_review``) and ``axiotic|structural`` (gates §11 step 0) foremost.
An aggregate κ over eleven classes with skewed marginals can pass while exactly
the decision-relevant boundaries fail [T-N2], which is why both are computed and
both must clear.

This file is the INSTRUMENT and the GATE. The annotation pass itself is human
work: two people who have not seen each other's answers, each classifying every
block, disagreements adjudicated and logged. One author annotating once — v1's
implicit procedure — is how every probe in review produced two defensible
answers, and ``kappa`` refuses two files that carry the same annotator id.

Usage::

    # 1. emit one blank sheet per annotator (optionally from a real dump)
    python3 -m tools.research.annotate_classes emit --annotator alice --out alice.csv
    python3 -m tools.research.annotate_classes emit --annotator bob   --out bob.csv \\
        --dump /tmp/dump-a.jsonl

    # 2. each annotator fills the `class` column, independently

    # 3. the gate
    python3 -m tools.research.annotate_classes kappa --a alice.csv --b bob.csv \\
        --class-set-version 2 [--adjudication-log adj.md]

Exit code 0 only when the class-set version is citable.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:  # running as a script, not -m
    sys.path.insert(0, str(REPO_ROOT))

from ciris_engine.logic.utils.regime_manifest import KAPPA_THRESHOLD, decision_relevant_boundaries  # noqa: E402
from ciris_engine.schemas.dma.compose import BlockClass  # noqa: E402
from ciris_engine.schemas.research.regime import KNOWN_CLASS_SET_VERSIONS  # noqa: E402

#: The two boundaries §10.2.3 names explicitly. They are not scored differently
#: — every boundary must clear — but they are reported first and named in the
#: verdict, because they are the two that gate a safety behaviour.
FOREMOST: Tuple[Tuple[BlockClass, BlockClass], ...] = (
    (BlockClass.AXIOTIC, BlockClass.DEONTIC),
    (BlockClass.AXIOTIC, BlockClass.STRUCTURAL),
)

_HEADER = ["block_id", "primary_class", "contaminant", "class", "notes"]


class AnnotationRefused(RuntimeError):
    """The annotation pass cannot be scored, so nothing is citable."""


# --------------------------------------------------------------------------
# Inventory
# --------------------------------------------------------------------------


def inventory_rows(dump: Optional[str] = None) -> List[Tuple[str, str, str]]:
    """``(block_id, current primary class, contaminant)`` for every block.

    From a real compose dump when one is given — that is the inventory the gate
    will actually run over — else from the #973 ``BLOCK_ANNOTATIONS`` table,
    which is the single-author best-effort annotation this pass replaces.
    """
    if dump:
        seen: Dict[str, Tuple[str, str]] = {}
        with open(dump, encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                if row.get("kind") == "compose_dump_meta":
                    continue
                block_id = str(row["block_id"])
                contaminant = ",".join(row.get("contaminant") or [])
                seen.setdefault(block_id, (str(row["class"]), contaminant))
        return [(block_id, cls, cont) for block_id, (cls, cont) in sorted(seen.items())]

    from ciris_engine.logic.utils.compose_dump import BLOCK_ANNOTATIONS

    return [
        (
            block_id,
            annotation.block_class.value,
            ",".join(c.value for c in (annotation.contaminant or ())),
        )
        for block_id, annotation in sorted(BLOCK_ANNOTATIONS.items())
    ]


def write_sheet(path: str, annotator: str, rows: Sequence[Tuple[str, str, str]]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(f"# annotator_id: {annotator}\n")
        handle.write(
            "# Fill the `class` column with ONE of: "
            + ", ".join(c.value for c in BlockClass)
            + "\n# `mixed` is a real answer when the block cannot be split. Do not\n"
            "# look at another annotator's sheet; that is the whole point.\n"
        )
        writer = csv.writer(handle)
        writer.writerow(_HEADER)
        for block_id, primary, contaminant in rows:
            writer.writerow([block_id, primary, contaminant, "", ""])


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Sheet:
    annotator: str
    path: str
    labels: Dict[str, BlockClass]


def read_sheet(path: str) -> Sheet:
    annotator = ""
    data_lines: List[str] = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("#"):
                if "annotator_id:" in line:
                    annotator = line.split("annotator_id:", 1)[1].strip()
                continue
            data_lines.append(line)
    if not annotator:
        raise AnnotationRefused(
            f"{path} carries no `# annotator_id:` header — an unattributed sheet cannot be shown to "
            f"be independent of the other one, and independence is the property κ is measuring."
        )

    labels: Dict[str, BlockClass] = {}
    unlabelled: List[str] = []
    for row in csv.DictReader(data_lines):
        block_id = (row.get("block_id") or "").strip()
        if not block_id:
            continue
        raw = (row.get("class") or "").strip().lower()
        if not raw:
            unlabelled.append(block_id)
            continue
        try:
            labels[block_id] = BlockClass(raw)
        except ValueError as exc:
            raise AnnotationRefused(
                f"{path}: block {block_id!r} is labelled {raw!r}, which is not one of "
                f"{[c.value for c in BlockClass]}"
            ) from exc
    if unlabelled:
        raise AnnotationRefused(
            f"{path}: {len(unlabelled)} block(s) left unlabelled ({unlabelled[:6]}...). The pass must be "
            f"TOTAL — a blank is not an abstention, it is an unscored block that the gate would then "
            f"treat as agreed."
        )
    return Sheet(annotator=annotator, path=path, labels=labels)


# --------------------------------------------------------------------------
# Cohen's kappa
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class KappaResult:
    label: str
    n: int
    kappa: Optional[float]
    reason: str = ""

    def passed(self) -> bool:
        return self.kappa is not None and self.kappa >= KAPPA_THRESHOLD


def cohens_kappa(pairs: Sequence[Tuple[BlockClass, BlockClass]], label: str) -> KappaResult:
    """Cohen's κ over paired labels.

    Degenerate case handled explicitly: when both annotators used exactly one
    label, agreement is perfect and expected agreement is also 1, so κ is 0/0.
    It is reported NOT ESTIMABLE, never 1.0 — a boundary neither annotator ever
    exercised carries no evidence that they would agree on it, and a gate that
    scores it 1.0 passes precisely the boundaries nobody tested.
    """
    n = len(pairs)
    if n == 0:
        return KappaResult(label=label, n=0, kappa=None, reason="no items")
    agree = sum(1 for left, right in pairs if left is right)
    p_o = agree / n
    labels: Set[BlockClass] = {c for pair in pairs for c in pair}
    p_e = 0.0
    for value in labels:
        p_left = sum(1 for left, _ in pairs if left is value) / n
        p_right = sum(1 for _, right in pairs if right is value) / n
        p_e += p_left * p_right
    if abs(1.0 - p_e) < 1e-12:
        return KappaResult(
            label=label,
            n=n,
            kappa=None,
            reason=f"degenerate: both annotators used only {sorted(c.value for c in labels)}",
        )
    return KappaResult(label=label, n=n, kappa=(p_o - p_e) / (1.0 - p_e))


def score(sheet_a: Sheet, sheet_b: Sheet) -> Tuple[KappaResult, List[KappaResult], List[str]]:
    """Overall κ, per-boundary κ, and the adjudication list."""
    if sheet_a.annotator == sheet_b.annotator:
        raise AnnotationRefused(
            f"both sheets carry annotator_id {sheet_a.annotator!r}. Two independent annotators are the "
            f"requirement (§10.2.3); one author annotating once is the v1 procedure this replaces."
        )
    only_a = sorted(set(sheet_a.labels) - set(sheet_b.labels))
    only_b = sorted(set(sheet_b.labels) - set(sheet_a.labels))
    if only_a or only_b:
        raise AnnotationRefused(
            f"the two sheets annotate different inventories — only in {sheet_a.annotator}: {only_a}; "
            f"only in {sheet_b.annotator}: {only_b}. κ over a partially-shared inventory is not κ."
        )

    block_ids = sorted(sheet_a.labels)
    pairs = [(sheet_a.labels[b], sheet_b.labels[b]) for b in block_ids]
    overall = cohens_kappa(pairs, "overall")

    boundaries: List[KappaResult] = []
    for left, right in decision_relevant_boundaries():
        subset = [p for p in pairs if p[0] in (left, right) and p[1] in (left, right)]
        name = f"{left.value}|{right.value}"
        marker = " *" if (left, right) in FOREMOST or (right, left) in FOREMOST else ""
        boundaries.append(cohens_kappa(subset, name + marker))

    adjudication = [
        f"{block_id}: {sheet_a.annotator}={sheet_a.labels[block_id].value} "
        f"{sheet_b.annotator}={sheet_b.labels[block_id].value}"
        for block_id in block_ids
        if sheet_a.labels[block_id] is not sheet_b.labels[block_id]
    ]
    return overall, boundaries, adjudication


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _report(overall: KappaResult, boundaries: Sequence[KappaResult], adjudication: Sequence[str]) -> int:
    def fmt(result: KappaResult) -> str:
        value = f"{result.kappa:.3f}" if result.kappa is not None else f"NOT ESTIMABLE ({result.reason})"
        verdict = "PASS" if result.passed() else "FAIL"
        return f"  {verdict}  k={value:<32} n={result.n:<4} {result.label}"

    print("κ (Cohen), class-set annotation pass — * = §10.2.3 foremost boundary")
    print(fmt(overall))
    print(f"per-boundary (every class pair whose default disposition differs; {len(boundaries)} pairs):")
    for result in boundaries:
        print(fmt(result))

    if adjudication:
        print(f"\ndisagreements to adjudicate and LOG ({len(adjudication)}):")
        for line in adjudication:
            print(f"  - {line}")

    failures = [r for r in [overall, *boundaries] if not r.passed()]
    if failures:
        print(
            f"\nNOT CITABLE — {len(failures)} of {len(boundaries) + 1} κ statistic(s) below "
            f"{KAPPA_THRESHOLD} or not estimable. A class-set version is citable only at κ ≥ "
            f"{KAPPA_THRESHOLD} OVERALL AND per-boundary (§10.2.3 [T-N2]); an aggregate κ over eleven "
            f"classes with skewed marginals can pass while exactly the decision-relevant boundaries fail."
        )
        return 1
    print(f"\nCITABLE — overall and all {len(boundaries)} boundaries clear κ ≥ {KAPPA_THRESHOLD}.")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m tools.research.annotate_classes", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    emit_p = sub.add_parser("emit", help="write a blank annotation sheet")
    emit_p.add_argument("--annotator", required=True, help="annotator id, sealed into the sheet header")
    emit_p.add_argument("--out", required=True)
    emit_p.add_argument("--dump", default=None, help="compose dump JSONL to take the inventory from")

    kappa_p = sub.add_parser("kappa", help="score two filled sheets and gate citability")
    kappa_p.add_argument("--a", required=True)
    kappa_p.add_argument("--b", required=True)
    kappa_p.add_argument("--class-set-version", type=int, default=None)
    kappa_p.add_argument("--adjudication-log", default=None, help="write the disagreement list here")

    args = parser.parse_args(argv)

    if args.command == "emit":
        rows = inventory_rows(args.dump)
        write_sheet(args.out, args.annotator, rows)
        print(f"wrote {len(rows)} blocks to {args.out} for annotator {args.annotator!r}")
        return 0

    if args.class_set_version is not None and args.class_set_version not in KNOWN_CLASS_SET_VERSIONS:
        print(
            f"REFUSED: class-set version {args.class_set_version} is not registered "
            f"(known: {sorted(KNOWN_CLASS_SET_VERSIONS)}) — scoring an unregistered version produces a "
            f"κ nobody can cite (§10.2.2).",
            file=sys.stderr,
        )
        return 2
    try:
        overall, boundaries, adjudication = score(read_sheet(args.a), read_sheet(args.b))
    except AnnotationRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    rc = _report(overall, boundaries, adjudication)
    if args.adjudication_log:
        Path(args.adjudication_log).write_text(
            "# Adjudication log (§10.2.3) — every line needs a resolution and a reason\n\n"
            + "\n".join(f"- [ ] {line}" for line in adjudication)
            + "\n",
            encoding="utf-8",
        )
    return rc


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
