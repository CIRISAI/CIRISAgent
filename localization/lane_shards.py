#!/usr/bin/env python3
"""Shard the i18n lane across locales, and collect the shards into one commit.

AGENT-OWNED (not vendored; see ``localization/VENDORED.md``). The vendored
``localize.py`` loops over languages one at a time with blocking calls, so a
28-locale run is 28 sequential pipelines. ``.github/workflows/i18n-lane.yml``
runs N shards of that same pipeline instead, each over a disjoint subset of the
locales, and one ``collect`` job that is the only writer. This module is the
bookkeeping both sides share, so the shard and the collector cannot disagree on
who owns what:

``matrix``  the deterministic assignment, as a GitHub Actions matrix.
``pack``    (shard) copy ONLY this shard's own locale files, its report, its
            log and its exit status into an upload directory.
``collect`` (collector) recompute the assignment, refuse any shard whose
            artifact holds a file outside its own locales, copy the rest into the
            checkout, merge the MQM reports and sum the spend.

Ownership is a closed list of paths per locale (``owned_files``): for
``TARGET=ui`` the agent bundle ``ciris_engine/data/localized/<lang>.json``; for
``TARGET=accord`` the staged segment bundle ``localization/accord/<stage>/<lang>.json``
and the reassembled ``ciris_engine/data/localized/<stem>_<version>_<lang>.txt``.
A shard's checkout also rewrites other locales' files (the stage seeds all 28),
which is exactly why only owned paths travel.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import accord_localize as acc  # noqa: E402

LOCALIZED = REPO_ROOT / "ciris_engine" / "data" / "localized"
DEFAULT_SHARDS = 7
ARTIFACT_PREFIX = "i18n-shard-"
SHARD_META = "shard.json"
SHARD_REPORT = "i18n-report.json"
SHARD_LOG = "lane.log"
FILES_DIR = "files"

_SPEND_LINE = re.compile(
    r"^  (?P<model>\S+): (?P<inp>[\d,]+) in \((?P<cached>[\d,]+) cache-read\) / "
    r"(?P<out>[\d,]+) out ~ \$(?P<usd>[\d.]+)"
)
_SPEND_TOTAL = re.compile(r"^  total ~ \$(?P<usd>[\d.]+)\s*$")


# ─────────────────────────────────────────────────────────────────────────────
# Assignment
# ─────────────────────────────────────────────────────────────────────────────


def lane_languages(localized: Path = LOCALIZED) -> List[str]:
    """The target locales, in manifest order (what ``agent_languages`` reads)."""
    return [lang for lang in acc.agent_languages(localized) if lang != "en"]


def parse_shards(value: str) -> int:
    try:
        n = int(str(value).strip() or DEFAULT_SHARDS)
    except ValueError:
        raise SystemExit(f"[refuse] shards must be a whole number, got {value!r}")
    if not 1 <= n <= 28:
        raise SystemExit(f"[refuse] shards must be between 1 and 28, got {n}")
    return n


def assign(langs: Sequence[str], shards: int, *, known: Optional[Sequence[str]] = None) -> List[List[str]]:
    """Round-robin ``langs`` (default: every target locale) over ``shards``.

    Deterministic: the same inputs always give the same layout, which is what
    lets the collector recompute ownership instead of trusting an artifact.
    Round-robin over manifest order spreads the slow low-resource locales.
    Shards that would be empty are dropped, so the matrix is never wider than
    the work.
    """
    every = list(known) if known is not None else lane_languages()
    wanted: List[str] = []
    for lang in langs or every:
        if lang not in wanted:
            wanted.append(lang)
    unknown = sorted(set(wanted) - set(every))
    if unknown:
        raise SystemExit(f"[refuse] not languages this lane ships: {', '.join(unknown)}")
    if shards < 1:
        raise SystemExit("[refuse] shards must be at least 1")
    out: List[List[str]] = [[] for _ in range(shards)]
    for i, lang in enumerate(wanted):
        out[i % shards].append(lang)
    return [s for s in out if s]


def matrix(layout: List[List[str]]) -> Dict[str, List[Dict[str, str]]]:
    return {"include": [{"shard": str(i), "langs": " ".join(s)} for i, s in enumerate(layout)]}


# ─────────────────────────────────────────────────────────────────────────────
# Ownership
# ─────────────────────────────────────────────────────────────────────────────


def owned_files(target: str, langs: Sequence[str], *, version: str = "", stem: str = "accord") -> List[str]:
    """Repo-relative paths a shard over ``langs`` may write. A closed list."""
    out: List[str] = []
    for lang in langs:
        if not re.fullmatch(r"[a-z]{2,3}", lang) or lang == "en":
            raise SystemExit(f"[refuse] {lang!r} is not a target locale code")
        if target == "ui":
            out.append(f"ciris_engine/data/localized/{lang}.json")
        elif target == "accord":
            stage = acc.default_stage_dir(version, stem).relative_to(REPO_ROOT).as_posix()
            out.append(f"{stage}/{lang}.json")
            out.append(acc.accord_path(LOCALIZED, version, lang, stem).relative_to(REPO_ROOT).as_posix())
        else:
            raise SystemExit(f"[refuse] TARGET must be accord or ui, got {target!r}")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Spend and reports
# ─────────────────────────────────────────────────────────────────────────────


def parse_spend(log_text: str) -> Dict[str, Any]:
    """Sum every ``Spend.report`` block in a lane log (accord prints one per unit)."""
    models: Dict[str, Dict[str, float]] = {}
    total = 0.0
    for line in log_text.splitlines():
        m = _SPEND_LINE.match(line)
        if m:
            row = models.setdefault(m["model"], {"input_tokens": 0, "cache_read": 0, "output_tokens": 0, "usd": 0.0})
            row["input_tokens"] += int(m["inp"].replace(",", ""))
            row["cache_read"] += int(m["cached"].replace(",", ""))
            row["output_tokens"] += int(m["out"].replace(",", ""))
            row["usd"] = round(row["usd"] + float(m["usd"]), 6)
            continue
        t = _SPEND_TOTAL.match(line)
        if t:
            total += float(t["usd"])
    return {"total_usd": round(total, 6), "models": models}


def add_spend(into: Dict[str, Any], part: Dict[str, Any]) -> None:
    into["total_usd"] = round(into.get("total_usd", 0.0) + part.get("total_usd", 0.0), 6)
    models = into.setdefault("models", {})
    for model, row in part.get("models", {}).items():
        acc_row = models.setdefault(model, {"input_tokens": 0, "cache_read": 0, "output_tokens": 0, "usd": 0.0})
        for k in ("input_tokens", "cache_read", "output_tokens"):
            acc_row[k] += row.get(k, 0)
        acc_row["usd"] = round(acc_row["usd"] + row.get("usd", 0.0), 6)


def merge_report(into: Dict[str, Any], part: Dict[str, Any], target: str, langs: Sequence[str]) -> List[str]:
    """Fold one shard's report into ``into``. Returns problems (foreign locales).

    ``ui``: ``{lang: {...}}``. ``accord``: ``{unit: {lang: {...}}}`` (one
    localize.py report per unit, merged by accord_localize.py).
    """
    problems: List[str] = []
    owned = set(langs)

    def fold(dst: Dict[str, Any], src: Dict[str, Any], where: str) -> None:
        for lang, entry in src.items():
            if lang not in owned:
                problems.append(f"report{where} has locale {lang!r}, which this shard does not own")
                continue
            dst[lang] = entry

    if target == "accord":
        for unit, per_lang in part.items():
            if not isinstance(per_lang, dict):
                problems.append(f"report unit {unit!r} is not an object")
                continue
            fold(into.setdefault(unit, {}), per_lang, f"[{unit}]")
    else:
        fold(into, part, "")
    return problems


# ─────────────────────────────────────────────────────────────────────────────
# Shard side
# ─────────────────────────────────────────────────────────────────────────────


def parse_rc(value: str) -> int:
    """The lane's exit status; empty (the step died before recording it) is a failure."""
    try:
        return int(str(value).strip())
    except ValueError:
        return -1


def pack(
    *,
    target: str,
    version: str,
    stem: str,
    shard: str,
    langs: Sequence[str],
    rc: int,
    out: Path,
    root: Path = REPO_ROOT,
    report: Optional[Path] = None,
    log: Optional[Path] = None,
) -> Dict[str, Any]:
    """Copy this shard's own locale files (only) plus its report/log into ``out``."""
    if out.exists():
        shutil.rmtree(out)
    (out / FILES_DIR).mkdir(parents=True)
    copied: List[str] = []
    for rel in owned_files(target, langs, version=version, stem=stem):
        src = root / rel
        if src.is_file() and not src.is_symlink():
            dst = out / FILES_DIR / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            copied.append(rel)
    if report is not None and report.is_file():
        shutil.copyfile(report, out / SHARD_REPORT)
    if log is not None and log.is_file():
        shutil.copyfile(log, out / SHARD_LOG)
    meta = {"shard": str(shard), "langs": list(langs), "rc": rc, "files": copied}
    (out / SHARD_META).write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return meta


# ─────────────────────────────────────────────────────────────────────────────
# Collector side
# ─────────────────────────────────────────────────────────────────────────────


def _artifact_files(base: Path) -> Tuple[List[str], List[str]]:
    """Every file under ``base`` as a posix relative path, and anything refused outright."""
    files: List[str] = []
    bad: List[str] = []
    if not base.is_dir():
        return files, bad
    for path in sorted(base.rglob("*")):
        rel = path.relative_to(base).as_posix()
        if path.is_symlink():
            bad.append(f"{rel} is a symlink")
        elif path.is_file():
            files.append(rel)
    return files, bad


def collect(
    *,
    target: str,
    version: str,
    stem: str,
    layout: List[List[str]],
    source: Path,
    root: Path = REPO_ROOT,
    log: Any = print,
) -> Tuple[Dict[str, Any], List[str]]:
    """Copy each shard's own files into ``root``; return (merged report, failures).

    A shard is REFUSED whole -- none of its files are copied -- when its
    artifact holds any file outside its own locales, names a different locale
    set than the assignment, or has a symlink. The other shards still land: the
    lane banks what passed, as the single-job lane always has.
    """
    failures: List[str] = []
    report: Dict[str, Any] = {}
    spend: Dict[str, Any] = {"total_usd": 0.0, "models": {}}
    shards_out: List[Dict[str, Any]] = []
    expected = {str(i): langs for i, langs in enumerate(layout)}

    present = sorted(p.name for p in source.iterdir()) if source.is_dir() else []
    for name in present:
        if not name.startswith(ARTIFACT_PREFIX) or name[len(ARTIFACT_PREFIX) :] not in expected:
            failures.append(f"{name}: not an artifact of this run's {len(layout)} shard(s) -- ignored")

    for shard, langs in expected.items():
        row: Dict[str, Any] = {"shard": shard, "langs": langs, "status": "missing", "rc": None, "files": []}
        shards_out.append(row)
        base = source / f"{ARTIFACT_PREFIX}{shard}"
        meta_path = base / SHARD_META
        if not meta_path.is_file():
            failures.append(f"shard {shard} ({' '.join(langs)}): no artifact -- it did not finish")
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except ValueError as exc:
            failures.append(f"shard {shard}: unreadable {SHARD_META} ({exc})")
            row["status"] = "refused"
            continue
        row["rc"] = meta.get("rc")

        why: List[str] = []
        if str(meta.get("shard")) != shard or list(meta.get("langs") or []) != list(langs):
            why.append(f"artifact says shard {meta.get('shard')!r} / {meta.get('langs')!r}, assignment is {langs!r}")
        owned = set(owned_files(target, langs, version=version, stem=stem))
        files, bad = _artifact_files(base / FILES_DIR)
        why.extend(bad)
        why.extend(f"{rel} is not one of this shard's locale files" for rel in files if rel not in owned)
        extra, bad_top = _artifact_files(base)
        why.extend(bad_top)
        allowed_top = {SHARD_META, SHARD_REPORT, SHARD_LOG}
        why.extend(
            f"{rel} is not a file a shard uploads"
            for rel in extra
            if not rel.startswith(FILES_DIR + "/") and rel not in allowed_top
        )

        part_report: Dict[str, Any] = {}
        if (base / SHARD_REPORT).is_file():
            try:
                part_report = json.loads((base / SHARD_REPORT).read_text(encoding="utf-8"))
            except ValueError as exc:
                why.append(f"unreadable {SHARD_REPORT} ({exc})")
        staged: Dict[str, Any] = {}
        why.extend(merge_report(staged, part_report, target, langs))

        if why:
            row["status"] = "refused"
            for w in why:
                failures.append(f"shard {shard} REFUSED: {w}")
            continue

        for rel in files:
            dst = root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(base / FILES_DIR / rel, dst)
        row["files"] = files
        merge_report(report, staged, target, langs)
        if (base / SHARD_LOG).is_file():
            part_spend = parse_spend((base / SHARD_LOG).read_text(encoding="utf-8", errors="replace"))
            row["spend_usd"] = part_spend["total_usd"]
            add_spend(spend, part_spend)
        rc = meta.get("rc")
        if rc == 0:
            row["status"] = "ok"
        else:
            row["status"] = "failed"
            failures.append(
                f"shard {shard} ({' '.join(langs)}): lane exited {rc} -- its accepted values are banked, "
                f"rejected ones withheld (fail-closed)"
            )
        log(f"[collect] shard {shard} ({' '.join(langs)}): {row['status']}, {len(files)} file(s)")

    report["_lane"] = {"shards": shards_out, "spend": spend}
    return report, failures


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────


def _layout(args: argparse.Namespace) -> List[List[str]]:
    return assign((args.langs or "").split(), parse_shards(args.shards))


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--target", default=os.environ.get("TARGET", "accord"))
        p.add_argument("--version", default=os.environ.get("ACCORD_VERSION", ""))
        p.add_argument("--stem", default=os.environ.get("STEM", "") or "accord")

    for name, what in (("matrix", "print the shard matrix as JSON"), ("layout", "print one line per shard")):
        m = sub.add_parser(name, help=what)
        m.add_argument("--shards", default=os.environ.get("SHARDS", str(DEFAULT_SHARDS)))
        m.add_argument("--langs", default=os.environ.get("LANGS", ""))

    p = sub.add_parser("pack", help="(shard) stage this shard's own files for upload")
    common(p)
    p.add_argument("--shard", required=True)
    p.add_argument("--langs", required=True)
    p.add_argument("--rc", default="")
    p.add_argument("--report", type=Path, default=Path(SHARD_REPORT))
    p.add_argument("--log", type=Path, default=Path(SHARD_LOG))
    p.add_argument("--out", type=Path, required=True)

    c = sub.add_parser("collect", help="(collector) refuse foreign files, copy, merge")
    common(c)
    c.add_argument("--shards", default=os.environ.get("SHARDS", str(DEFAULT_SHARDS)))
    c.add_argument("--langs", default=os.environ.get("LANGS", ""))
    c.add_argument("--from", dest="source", type=Path, required=True)
    c.add_argument("--report", type=Path, default=Path(SHARD_REPORT))

    args = ap.parse_args(argv)
    if args.cmd == "matrix":
        print(json.dumps(matrix(_layout(args)), separators=(",", ":")))
        return 0
    if args.cmd == "layout":
        for i, langs in enumerate(_layout(args)):
            print(f"shard {i}: {' '.join(langs)}")
        return 0
    if args.cmd == "pack":
        meta = pack(
            target=args.target,
            version=args.version,
            stem=args.stem,
            shard=args.shard,
            langs=args.langs.split(),
            rc=parse_rc(args.rc),
            out=args.out,
            report=args.report,
            log=args.log,
        )
        print(
            f"[pack] shard {meta['shard']} ({' '.join(meta['langs'])}): rc={meta['rc']}, {len(meta['files'])} file(s)"
        )
        return 0
    report, failures = collect(
        target=args.target, version=args.version, stem=args.stem, layout=_layout(args), source=args.source
    )
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    spend = report["_lane"]["spend"]
    print(f"[collect] spend across shards ~ ${spend['total_usd']:.4f} (estimate; billing is what the API bills)")
    for f in failures:
        print(f"::error::{f}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
