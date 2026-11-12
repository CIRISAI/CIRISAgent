"""Blind annotation sheets for the class-set pass (FSD §10.2.3).

`annotate_classes emit` is not blind: it prints the existing single-author
class and contaminant beside every block, shows the block's key (which often
names its purpose) and shows no text. A reader given that sheet is checking
the author's answer, not classifying.

`emit` here writes, for each DISTINCT block text the composer produces:
an opaque id (a hash of the text), where it appears (system or user message),
the text itself, and an empty `class` column. Rows are in id order, which is
hash order. No key, no file name, no existing class. A private map (opaque id
-> block ids, sources) is written beside the sheets for the scorer only.

`score` reads two filled sheets, checks they are the sheets that were emitted
(same ids, texts unaltered), and scores them with `annotate_classes.score`:
kappa overall and on every decision-relevant boundary, and the disagreement
list. `testimonial` is not offered to readers: it is a relation that takes a
declared frame, and no annotator judges it until the harness declares one.

    python3 -m tools.research.blind_sheets emit --out-dir DIR --annotators reader_a reader_b
    python3 -m tools.research.blind_sheets score --map DIR/map.json --a A.csv --b B.csv [--log adj.md]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

READER_CLASSES = (
    "axiotic", "deontic", "pragmatic", "ontological", "epistemic", "empirical",
    "contingent", "procedural", "nomological", "structural", "axiomatic", "mixed",
)  # fmt: skip
HEADER = ["block_id", "appears_in", "text", "class", "notes"]


def collect_blocks(locale: str = "en") -> List[Dict[str, Any]]:
    """Every distinct non-blank block text, with where it appears. Private fields included."""
    from ciris_engine.logic.utils import compose_dump as cd

    texts: Dict[str, str] = {}
    original = cd._expand_slots

    def recording(piece: Any) -> Any:
        pieces = original(piece)
        for p in pieces:
            texts[hashlib.sha256(p.text.encode("utf-8")).hexdigest()] = p.text
        return pieces

    cd._expand_slots = recording  # type: ignore[assignment]
    try:
        _meta, rows = cd.compose_dump_rows(arm="annotation", locales=[locale])
    finally:
        cd._expand_slots = original  # type: ignore[assignment]

    blocks: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        text = texts.get(row.sha256)
        if text is None:
            raise SystemExit(f"no text captured for {row.block_id} ({row.sha256[:12]})")
        if not text.strip():
            continue  # a separator: structural by rule, never annotated
        entry = blocks.setdefault(
            row.sha256,
            {"sha256": row.sha256, "text": text, "roles": set(), "block_ids": [], "sources": set(), "steps": set()},
        )
        entry["roles"].add("user message" if row.role == "user" else "system message")
        entry["block_ids"].append(row.block_id)
        entry["sources"].add(row.source)
        entry["steps"].add(row.step)
    out = []
    for sha, entry in blocks.items():
        out.append(
            {
                "opaque_id": "b" + sha[:10],
                "sha256": sha,
                "text": entry["text"],
                "appears_in": " and ".join(sorted(entry["roles"])),
                "block_ids": sorted(entry["block_ids"]),
                "sources": sorted(entry["sources"]),
                "steps": sorted(entry["steps"]),
            }
        )
    out.sort(key=lambda b: b["opaque_id"])
    if len({b["opaque_id"] for b in out}) != len(out):
        raise SystemExit("opaque id collision; lengthen the id")
    return out


def emit(out_dir: Path, annotators: Sequence[str], locale: str) -> Dict[str, Any]:
    blocks = collect_blocks(locale)
    out_dir.mkdir(parents=True, exist_ok=True)
    for annotator in annotators:
        with (out_dir / f"{annotator}.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["annotator_id", annotator, "", "", ""])
            writer.writerow(["allowed_classes", " ".join(READER_CLASSES), "", "", ""])
            writer.writerow(HEADER)
            for block in blocks:
                writer.writerow([block["opaque_id"], block["appears_in"], block["text"], "", ""])
    private = {
        "locale": locale,
        "blocks": [{k: b[k] for k in ("opaque_id", "sha256", "appears_in", "block_ids", "sources", "steps")} for b in blocks],
    }
    (out_dir / "map.json").write_text(json.dumps(private, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"blocks": len(blocks), "chars": sum(len(b["text"]) for b in blocks), "annotators": list(annotators)}


def read_filled(path: Path, shas: Dict[str, str]) -> Any:
    from tools.research.annotate_classes import AnnotationRefused, BlockClass, Sheet

    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    if len(rows) < 3 or rows[0][0] != "annotator_id" or rows[2][: len(HEADER)] != HEADER:
        raise AnnotationRefused(f"{path} is not a blind sheet from this tool")
    annotator = rows[0][1].strip()
    labels: Dict[str, Any] = {}
    for row in rows[3:]:
        if not row or not row[0].strip():
            continue
        block_id, _where, text, raw = row[0].strip(), row[1], row[2], row[3].strip().lower()
        if block_id not in shas:
            raise AnnotationRefused(f"{path}: {block_id} is not in the emitted inventory")
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != shas[block_id]:
            raise AnnotationRefused(f"{path}: the text of {block_id} was altered")
        if raw not in READER_CLASSES:
            raise AnnotationRefused(f"{path}: {block_id} is labelled {raw!r}; allowed: {list(READER_CLASSES)}")
        labels[block_id] = BlockClass(raw)
    missing = sorted(set(shas) - set(labels))
    if missing:
        raise AnnotationRefused(f"{path}: {len(missing)} block(s) unlabelled ({missing[:6]}…); the pass must be total")
    return Sheet(annotator=annotator, path=str(path), labels=labels)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m tools.research.blind_sheets", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    emit_p = sub.add_parser("emit")
    emit_p.add_argument("--out-dir", required=True, type=Path)
    emit_p.add_argument("--annotators", nargs="+", required=True)
    emit_p.add_argument("--locale", default="en")
    score_p = sub.add_parser("score")
    score_p.add_argument("--map", required=True, type=Path)
    score_p.add_argument("--a", required=True, type=Path)
    score_p.add_argument("--b", required=True, type=Path)
    score_p.add_argument("--log", default=None)
    args = parser.parse_args(argv)

    if args.command == "emit":
        print(json.dumps(emit(args.out_dir, args.annotators, args.locale)))
        return 0

    from tools.research import annotate_classes as ac

    shas = {b["opaque_id"]: b["sha256"] for b in json.loads(args.map.read_text(encoding="utf-8"))["blocks"]}
    try:
        overall, boundaries, adjudication = ac.score(read_filled(args.a, shas), read_filled(args.b, shas))
    except ac.AnnotationRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    rc = ac._report(overall, boundaries, adjudication)
    if args.log:
        Path(args.log).write_text(
            "# Adjudication log (§10.2.3) — every line needs a resolution and a reason\n\n"
            + "\n".join(f"- [ ] {line}" for line in adjudication)
            + "\n",
            encoding="utf-8",
        )
    return rc


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
