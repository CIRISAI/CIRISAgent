#!/usr/bin/env python3
"""check_csd.py — keep every CIRIS Specification Document and its flow identical.

A CSD (FSD/CSD_STANDARD.md) is Mission Driven Development applied to one feature,
and the property that makes it more than a document is that its §4 flow block is
BYTE-IDENTICAL to the executable file on its ``Flow`` line. That is what lets a
screen reorder fail CI unless the spec, the flow and the screen move together
(CIRISClient#39). This is the gate that makes it a property rather than a hope.

Checks, each a FAIL:
  - a CSD's ``Flow`` line names a file that does not exist        (spec with no test)
  - the embedded ```yaml block differs from that file             (spec and test disagree)
  - a flow file under tools/qa_runner/flows with no CSD, or two   (test with no spec)
  - the flow's ``flow:`` id is not the CSD filename's slug        (spec for one surface driving another)
  - ``Client floor`` absent or not ``>=X.Y.Z`` / ``>X.Y.Z`` / ``unreleased``
  - a §3 source cell that is neither a route/path nor ``unconfirmed``
                                                                   (a guessed endpoint is worse than a named unknown)
  - a CSD not listed in FSD/CSD/README.md                         (the registry is the registry)

``--embed CSD-NNN`` rewrites a CSD's block from its flow file so "keep them
identical" is a command, not a chore. Stdlib only. Exit non-zero on any FAIL.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CSD_DIR = ROOT / "FSD" / "CSD"
FLOW_DIR = ROOT / "tools" / "qa_runner" / "flows"
INDEX = CSD_DIR / "README.md"

_MARKER = re.compile(r"<!-- flow: (?P<path>[^ ]+) -->\n```yaml\n(?P<body>.*?)\n```", re.S)
_HEADER = re.compile(r"^\*\*(?P<key>[A-Za-z ]+)\*\*: (?P<val>.+)$", re.M)
# `>=X.Y.Z`: written against X.Y.Z. `>X.Y.Z`: no released client at or below X.Y.Z
# carries the surface (an unmerged client PR); bumped when the carrying release is cut.
_FLOOR = re.compile(r"^(?:(?:>=|>)\s*\d+(?:\.\d+)+|unreleased)$")
#: A §3 source is a route (`/v1/...`), a backticked path, or the literal word.
_SOURCE_OK = re.compile(r"(`/[^`]+`|/v1/|/lens/|\bunconfirmed\b)")


def _fail(msgs: list[str], msg: str) -> None:
    msgs.append(msg)
    print(f"FAIL {msg}")


def _headers(text: str) -> dict[str, str]:
    return {m.group("key").strip(): m.group("val").strip() for m in _HEADER.finditer(text)}


def _section(text: str, num: int) -> str:
    """Body of `## N.` up to the next `## `."""
    m = re.search(rf"^## {num}\. .*?$(.*?)(?=^## |\Z)", text, re.M | re.S)
    return m.group(1) if m else ""


def check_one(path: Path, msgs: list[str], seen_flows: dict[str, Path]) -> None:
    text = path.read_text(encoding="utf-8")
    slug = re.sub(r"^CSD-\d{3}-", "", path.stem).replace("-", "_")
    hdr = _headers(text)

    flow_line = hdr.get("Flow")
    if not flow_line:
        _fail(msgs, f"{path.name}: no **Flow** header line"); return
    flow_path = ROOT / flow_line
    if not flow_path.exists():
        _fail(msgs, f"{path.name}: Flow names {flow_line}, which does not exist"); return

    floor = hdr.get("Client floor", "")
    if not _FLOOR.match(floor):
        _fail(msgs, f"{path.name}: Client floor {floor!r} is not of the form >=X.Y.Z, >X.Y.Z or unreleased")

    m = _MARKER.search(text)
    if not m:
        _fail(msgs, f"{path.name}: no embedded flow block (`<!-- flow: ... -->` + ```yaml)"); return
    if m.group("path") != flow_line:
        _fail(msgs, f"{path.name}: marker names {m.group('path')} but Flow header names {flow_line}")
    on_disk = flow_path.read_text(encoding="utf-8").rstrip("\n")
    if m.group("body") != on_disk:
        _fail(msgs, f"{path.name}: embedded flow differs from {flow_line} — run: python tools/dev/check_csd.py --embed {path.stem[:7]}")

    fid = re.search(r"^flow:\s*(\S+)", on_disk, re.M)
    if not fid or fid.group(1) != slug:
        _fail(msgs, f"{path.name}: flow id {fid.group(1) if fid else None!r} != filename slug {slug!r}")

    if flow_path in seen_flows:
        _fail(msgs, f"{path.name}: {flow_line} is also embedded by {seen_flows[flow_path].name}")
    seen_flows[flow_path] = path

    # §3 sources: every table row's second cell is a route/path or `unconfirmed`.
    for row in re.findall(r"^\|(?!---)(?!\s*value)([^\n]+)\|$", _section(text, 3), re.M):
        cells = [c.strip() for c in row.split("|")]
        if len(cells) >= 2 and not _SOURCE_OK.search(cells[1]):
            _fail(msgs, f"{path.name} §3: source {cells[1]!r} is neither a route/path nor `unconfirmed`")


def embed(csd_id: str) -> int:
    matches = sorted(CSD_DIR.glob(f"{csd_id}-*.md"))
    if len(matches) != 1:
        print(f"expected one CSD for {csd_id}, found {[p.name for p in matches]}"); return 1
    path = matches[0]
    text = path.read_text(encoding="utf-8")
    flow_line = _headers(text).get("Flow")
    if not flow_line:
        print(f"{path.name}: no Flow header"); return 1
    body = (ROOT / flow_line).read_text(encoding="utf-8").rstrip("\n")
    new, n = _MARKER.subn(lambda m: f"<!-- flow: {flow_line} -->\n```yaml\n{body}\n```", text, count=1)
    if n != 1:
        print(f"{path.name}: no embedded block to rewrite"); return 1
    path.write_text(new, encoding="utf-8")
    print(f"{path.name}: block rewritten from {flow_line}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--embed", metavar="CSD-NNN", help="rewrite this CSD's flow block from its file")
    args = ap.parse_args()
    if args.embed:
        return embed(args.embed)

    msgs: list[str] = []
    csds = sorted(p for p in CSD_DIR.glob("CSD-*.md"))
    if not csds:
        print("no CSDs found; nothing to check"); return 0
    seen: dict[str, Path] = {}
    for p in csds:
        check_one(p, msgs, seen)

    for flow in sorted(FLOW_DIR.glob("*.yaml")) + sorted(FLOW_DIR.glob("*.yml")):
        if flow not in seen:
            _fail(msgs, f"{flow.relative_to(ROOT)}: flow file with no CSD embedding it")

    index_text = INDEX.read_text(encoding="utf-8") if INDEX.exists() else ""
    for p in csds:
        if p.name not in index_text:
            _fail(msgs, f"{p.name}: not listed in {INDEX.relative_to(ROOT)}")

    print(f"check_csd: {len(csds)} CSDs, {len(seen)} flows, {len(msgs)} failures")
    return 1 if msgs else 0


if __name__ == "__main__":
    sys.exit(main())
